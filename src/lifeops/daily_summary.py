from __future__ import annotations

from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .paths import repo_root

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")

def _target_day(day: str | Date | None = None, now: datetime | None = None) -> Date:
    if isinstance(day, Date):
        return day
    if isinstance(day, str):
        return Date.fromisoformat(day)
    current = now or datetime.now(DEFAULT_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TZ)
    return current.astimezone(DEFAULT_TZ).date()


def _utc_window(day: Date) -> tuple[str, str]:
    start_local = datetime.combine(day, time.min, tzinfo=DEFAULT_TZ)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
        end_local.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def _count(conn: Any, query: str, params: tuple[object, ...]) -> int:
    row = conn.execute(query, params).fetchone()
    return int(row["count"] if row is not None else 0)


def _count_by(conn: Any, query: str, params: tuple[object, ...], key: str = "key") -> dict[str, int]:
    rows = conn.execute(query, params).fetchall()
    return {str(row[key] or "unknown"): int(row["count"]) for row in rows}


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "없음"
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def build_daily_summary(*, day: str | Date | None = None, now: datetime | None = None) -> dict[str, Any]:
    init_db()
    target_day = _target_day(day, now)
    utc_start, utc_end = _utc_window(target_day)
    local_prefix = target_day.isoformat()

    with connect() as conn:
        activity_count = _count(
            conn,
            "SELECT COUNT(*) AS count FROM activity_events WHERE timestamp >= ? AND timestamp < ?",
            (utc_start, utc_end),
        )
        intervention_statuses = _count_by(
            conn,
            """
            SELECT status AS key, COUNT(*) AS count FROM intervention_events
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY status
            ORDER BY count DESC, status
            """,
            (utc_start, utc_end),
        )
        decision_categories = _count_by(
            conn,
            """
            SELECT category AS key, COUNT(*) AS count FROM intervention_decisions
            WHERE timestamp >= ? AND timestamp < ?
            GROUP BY category
            ORDER BY count DESC, category
            """,
            (utc_start, utc_end),
        )
        exception_categories = _count_by(
            conn,
            """
            SELECT category AS key, COUNT(*) AS count FROM exceptions
            WHERE start_time >= ? AND start_time < ?
            GROUP BY category
            ORDER BY count DESC, category
            """,
            (utc_start, utc_end),
        )
        recovery_count = _count(
            conn,
            "SELECT COUNT(*) AS count FROM recovery_sessions WHERE start_time LIKE ?",
            (f"{local_prefix}%",),
        )
        recovery_rows = conn.execute(
            """
            SELECT id, start_time, reason FROM recovery_sessions
            WHERE start_time LIKE ?
            ORDER BY start_time, id
            LIMIT 3
            """,
            (f"{local_prefix}%",),
        ).fetchall()
        open_interventions = _count(
            conn,
            """
            SELECT COUNT(*) AS count FROM intervention_events
            WHERE timestamp >= ? AND timestamp < ? AND status IN ('pending', 'dispatching', 'dispatched')
            """,
            (utc_start, utc_end),
        )
        pending_tasks_due = _count(
            conn,
            """
            SELECT COUNT(*) AS count FROM tasks
            WHERE status = 'pending' AND (due_date IS NULL OR due_date <= ?)
            """,
            (local_prefix,),
        )
        deferred_tasks = _count(
            conn,
            "SELECT COUNT(*) AS count FROM tasks WHERE status = 'deferred_recovery'",
            (),
        )
        false_positive_count = int(decision_categories.get("false_positive", 0))

    intervention_total = sum(intervention_statuses.values())
    decision_total = sum(decision_categories.values())
    exception_total = sum(exception_categories.values())

    return {
        "date": local_prefix,
        "generated_at": (now or datetime.now(DEFAULT_TZ)).astimezone(DEFAULT_TZ).isoformat(timespec="seconds"),
        "utc_window": {"start": utc_start, "end": utc_end},
        "activity_count": activity_count,
        "intervention_count": intervention_total,
        "intervention_statuses": intervention_statuses,
        "decision_count": decision_total,
        "decision_categories": decision_categories,
        "false_positive_count": false_positive_count,
        "exception_count": exception_total,
        "exception_categories": exception_categories,
        "recovery_count": recovery_count,
        "recovery_sessions": [dict(row) for row in recovery_rows],
        "open_interventions": open_interventions,
        "pending_tasks_due": pending_tasks_due,
        "deferred_tasks": deferred_tasks,
    }


def _recovery_lines(summary: dict[str, Any]) -> list[str]:
    sessions = summary["recovery_sessions"]
    if not sessions:
        return ["- 회복 모드 기록은 없습니다."]
    lines = []
    for session in sessions:
        reason = str(session.get("reason") or "reason 없음")
        lines.append(f"- #{session['id']} {session['start_time']}: {reason}")
    return lines


def render_daily_summary(summary: dict[str, Any]) -> str:
    intervention_statuses = _format_counts(summary["intervention_statuses"])
    decision_categories = _format_counts(summary["decision_categories"])
    exception_categories = _format_counts(summary["exception_categories"])

    lines = [
        f"# Daily Summary {summary['date']}",
        "",
        "## 운영 요약",
        f"- 감지 활동 {summary['activity_count']}건, 개입 이벤트 {summary['intervention_count']}건이 기록되었습니다.",
        f"- 결정 기록 {summary['decision_count']}건, 오탐 {summary['false_positive_count']}건입니다.",
        f"- 예외 {summary['exception_count']}건: {exception_categories}.",
        f"- 회복 모드 {summary['recovery_count']}회 사용되었습니다.",
        "",
        "## 상태 분포",
        f"- intervention_statuses: {intervention_statuses}",
        f"- decision_categories: {decision_categories}",
        "",
        "## 회복 기록",
        *_recovery_lines(summary),
        "",
        "## 남은 확인",
        f"- 아직 닫히지 않은 개입 이벤트: {summary['open_interventions']}건",
        f"- 오늘 기준 pending task: {summary['pending_tasks_due']}건",
        f"- 회복 모드로 미룬 task: {summary['deferred_tasks']}건",
        "",
        "## 내일 첫 행동",
        "- 부팅 브리핑을 열고 현재 블록과 다음 3분 행동 하나만 확인합니다.",
        "",
        "점수 없음. 처벌 없음. 시스템 조정 참고용 요약입니다.",
    ]
    return "\n".join(lines) + "\n"


def write_daily_summary(
    output: Path | None = None,
    *,
    day: str | Date | None = None,
    now: datetime | None = None,
) -> Path:
    summary = build_daily_summary(day=day, now=now)
    path = output or repo_root() / "data" / "daily" / f"{summary['date']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_daily_summary(summary), encoding="utf-8")
    return path