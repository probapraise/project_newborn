from __future__ import annotations

from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .paths import repo_root

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


def _target_end_date(end_date: str | Date | None = None, now: datetime | None = None) -> Date:
    if isinstance(end_date, Date):
        return end_date
    if isinstance(end_date, str):
        return Date.fromisoformat(end_date)
    current = now or datetime.now(DEFAULT_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TZ)
    return current.astimezone(DEFAULT_TZ).date()


def _date_range(*, end_date: Date, days: int) -> list[Date]:
    if days <= 0:
        raise ValueError("days must be greater than zero.")
    start_date = end_date - timedelta(days=days - 1)
    return [start_date + timedelta(days=offset) for offset in range(days)]


def _utc_window(start_date: Date, end_date: Date) -> tuple[str, str]:
    start_local = datetime.combine(start_date, time.min, tzinfo=DEFAULT_TZ)
    end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=DEFAULT_TZ)
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


def _read_daily_summaries(root: Path, dates: list[Date]) -> list[dict[str, object]]:
    summaries = []
    for day in dates:
        path = root / "data" / "daily" / f"{day.isoformat()}.md"
        exists = path.exists()
        summaries.append(
            {
                "date": day.isoformat(),
                "path": str(path),
                "exists": exists,
                "text": path.read_text(encoding="utf-8") if exists else "",
            }
        )
    return summaries


def _candidate_signals(context: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    if context["intervention_count"] == 0 and context["activity_count"] == 0:
        signals.append("insufficient_data: 이번 기간에는 분석할 활동/개입 기록이 거의 없습니다.")
    if context["open_interventions"] > 0:
        signals.append(f"unclosed_interventions: 닫히지 않은 개입 이벤트 {context['open_interventions']}건이 있습니다.")
    if context["false_positive_count"] > 0:
        signals.append(f"detection_tuning: 오탐 결정 {context['false_positive_count']}건이 있어 감지 규칙 조정 후보입니다.")
    if context["recovery_count"] > 0:
        signals.append(f"recovery_usage: 회복 모드 {context['recovery_count']}회가 사용되어 일정 축소 패턴을 확인할 수 있습니다.")
    if context["exception_categories"]:
        signals.append(f"exception_pressure: 예외 분포는 {_format_counts(context['exception_categories'])}입니다.")
    if context["deferred_tasks"] > 0:
        signals.append(f"deferred_work: 회복 모드로 미뤄진 task {context['deferred_tasks']}건이 남아 있습니다.")
    if not signals:
        signals.append("stable_or_unknown: 뚜렷한 조정 신호가 아직 없습니다. 규칙 변경을 서두르지 않습니다.")
    return signals[:6]


def build_weekly_analysis_context(
    *,
    days: int = 7,
    end_date: str | Date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    init_db()
    end_day = _target_end_date(end_date, now)
    dates = _date_range(end_date=end_day, days=days)
    start_day = dates[0]
    utc_start, utc_end = _utc_window(start_day, end_day)
    root = repo_root()

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
            "SELECT COUNT(*) AS count FROM recovery_sessions WHERE substr(start_time, 1, 10) BETWEEN ? AND ?",
            (start_day.isoformat(), end_day.isoformat()),
        )
        recovery_rows = conn.execute(
            """
            SELECT id, start_time, reason FROM recovery_sessions
            WHERE substr(start_time, 1, 10) BETWEEN ? AND ?
            ORDER BY start_time, id
            LIMIT 10
            """,
            (start_day.isoformat(), end_day.isoformat()),
        ).fetchall()
        open_interventions = _count(
            conn,
            """
            SELECT COUNT(*) AS count FROM intervention_events
            WHERE timestamp >= ? AND timestamp < ? AND status IN ('pending', 'dispatching', 'dispatched')
            """,
            (utc_start, utc_end),
        )
        deferred_tasks = _count(
            conn,
            "SELECT COUNT(*) AS count FROM tasks WHERE status = 'deferred_recovery'",
            (),
        )

    daily_summaries = _read_daily_summaries(root, dates)
    intervention_count = sum(intervention_statuses.values())
    decision_count = sum(decision_categories.values())
    exception_count = sum(exception_categories.values())
    false_positive_count = int(decision_categories.get("false_positive", 0))

    context: dict[str, Any] = {
        "range": {
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "days": days,
            "utc_start": utc_start,
            "utc_end": utc_end,
        },
        "generated_at": (now or datetime.now(DEFAULT_TZ)).astimezone(DEFAULT_TZ).isoformat(timespec="seconds"),
        "activity_count": activity_count,
        "intervention_count": intervention_count,
        "intervention_statuses": intervention_statuses,
        "decision_count": decision_count,
        "decision_categories": decision_categories,
        "false_positive_count": false_positive_count,
        "exception_count": exception_count,
        "exception_categories": exception_categories,
        "recovery_count": recovery_count,
        "recovery_sessions": [dict(row) for row in recovery_rows],
        "open_interventions": open_interventions,
        "deferred_tasks": deferred_tasks,
        "daily_summaries": daily_summaries,
    }
    context["candidate_signals"] = _candidate_signals(context)
    return context


def _recovery_lines(context: dict[str, Any]) -> list[str]:
    sessions = context["recovery_sessions"]
    if not sessions:
        return ["- 회복 모드 기록 없음"]
    return [f"- #{row['id']} {row['start_time']}: {row.get('reason') or 'reason 없음'}" for row in sessions]


def _daily_summary_lines(context: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in context["daily_summaries"]:
        lines.append(f"### {item['date']}")
        if not item["exists"]:
            lines.extend(["", "- daily summary 없음", ""])
            continue
        lines.extend(["", str(item["text"]).strip(), ""])
    return lines


def render_weekly_analysis_context(context: dict[str, Any]) -> str:
    range_info = context["range"]
    lines = [
        "# Weekly Analysis Context",
        "",
        f"range: {range_info['start_date']} -> {range_info['end_date']} ({range_info['days']} days)",
        f"generated_at: {context['generated_at']}",
        "",
        "## Deterministic Counts",
        f"- activity_count: {context['activity_count']}",
        f"- intervention_count: {context['intervention_count']}",
        f"- decision_count: {context['decision_count']}",
        f"- false_positive_count: {context['false_positive_count']}",
        f"- exception_count: {context['exception_count']}",
        f"- recovery_count: {context['recovery_count']}",
        f"- open_interventions: {context['open_interventions']}",
        f"- deferred_tasks: {context['deferred_tasks']}",
        "",
        "## Category Counts",
        f"- intervention_statuses: {_format_counts(context['intervention_statuses'])}",
        f"- decision_categories: {_format_counts(context['decision_categories'])}",
        f"- exception_categories: {_format_counts(context['exception_categories'])}",
        "",
        "## Candidate System Signals",
        *[f"- {signal}" for signal in context["candidate_signals"]],
        "",
        "## Recovery Sessions",
        *_recovery_lines(context),
        "",
        "## Daily Summaries",
        *_daily_summary_lines(context),
        "## Guardrails",
        "- 사용자를 평가하지 않는다.",
        "- 실패, 벌점, streak, 생산성 점수를 만들지 않는다.",
        "- 제안은 최대 3개만 만든다.",
        "- 사용자가 승인하기 전에는 규칙 변경을 적용하지 않는다.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_weekly_analysis_context(
    output: Path | None = None,
    *,
    days: int = 7,
    end_date: str | Date | None = None,
    now: datetime | None = None,
) -> Path:
    context = build_weekly_analysis_context(days=days, end_date=end_date, now=now)
    range_info = context["range"]
    path = output or repo_root() / "data" / "weekly" / f"weekly_context_{range_info['end_date']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_weekly_analysis_context(context), encoding="utf-8")
    return path