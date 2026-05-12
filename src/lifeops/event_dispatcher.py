from __future__ import annotations

import argparse
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .codex_bridge import CodexLaunch, launch_codex_intervention
from .db import connect, init_db, utc_now
from .paths import default_output_path, repo_root
from .schedule_engine import format_block

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


@dataclass(frozen=True)
class DispatchResult:
    event_id: int
    prompt_path: Path
    status: str
    launch: CodexLaunch | None = None


def write_heartbeat(message: str) -> None:
    root = repo_root()
    log_path = root / "data" / "runtime" / "event_dispatcher.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(DEFAULT_TZ).isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def pending_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM intervention_events WHERE status = 'pending'"
        ).fetchone()
        return int(row["count"])


def _load_template() -> str:
    path = repo_root() / "prompts" / "intervention_prompt.md"
    return path.read_text(encoding="utf-8")


def _claim_next_pending_event() -> int | None:
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id FROM intervention_events
            WHERE status = 'pending'
            ORDER BY timestamp, id
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        event_id = int(row["id"])
        conn.execute(
            "UPDATE intervention_events SET status = 'dispatching' WHERE id = ? AND status = 'pending'",
            (event_id,),
        )
        conn.commit()
        return event_id


def _set_event_status(event_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE intervention_events SET status = ? WHERE id = ?", (status, event_id))
        conn.commit()


def _fetch_event_context(event_id: int) -> sqlite3.Row:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
                ie.id AS event_id,
                ie.timestamp AS event_timestamp,
                ie.risk_level,
                ie.reason,
                ie.status,
                ae.id AS activity_id,
                ae.timestamp AS activity_timestamp,
                ae.process_name,
                ae.window_title,
                ae.domain,
                ae.classification,
                sb.id AS schedule_block_id,
                sb.date AS block_date,
                sb.start_time,
                sb.end_time,
                sb.type AS block_type,
                sb.title AS block_title,
                sb.enforcement_level,
                sb.source AS block_source,
                sb.status AS block_status
            FROM intervention_events ie
            LEFT JOIN activity_events ae ON ae.id = ie.activity_event_id
            LEFT JOIN schedule_blocks sb ON sb.id = ie.schedule_block_id
            WHERE ie.id = ?
            """,
            (event_id,),
        ).fetchone()
    if row is None:
        raise LookupError(f"Intervention event #{event_id} not found.")
    return row


def _recent_intervention_summary(event_id: int, hours: int = 1) -> str:
    threshold = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM intervention_events
            WHERE id != ? AND timestamp >= ? AND status IN ('pending', 'dispatching', 'dispatched')
            """,
            (event_id, threshold),
        ).fetchone()
    count = int(row["count"])
    if count == 0:
        return "최근 1시간 내 다른 개입 없음"
    return f"최근 1시간 내 다른 개입 {count}건"


def _format_current_block(row: sqlite3.Row) -> str:
    if row["schedule_block_id"] is None:
        return "등록된 계획 블록 없음"
    return format_block(
        {
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "title": row["block_title"],
            "type": row["block_type"],
            "enforcement_level": row["enforcement_level"],
        }
    )


def _format_detected_activity(row: sqlite3.Row) -> str:
    classification = row["classification"] or "unknown"
    process_name = row["process_name"] or "unknown"
    title = row["window_title"] or "제목 없음"
    domain = row["domain"]
    if domain:
        return f"{classification}: {process_name}, {domain}, {title}"
    return f"{classification}: {process_name}, {title}"


def _format_time_context(row: sqlite3.Row) -> str:
    timestamp = row["event_timestamp"] or row["activity_timestamp"] or utc_now()
    return f"event_id={row['event_id']}, timestamp={timestamp}"


def render_intervention_prompt(row: sqlite3.Row) -> str:
    template = _load_template()
    filled = template.format(
        event_id=row["event_id"],
        current_block=_format_current_block(row),
        detected_activity=_format_detected_activity(row),
        risk_level=row["risk_level"] or "green",
        time_context=_format_time_context(row),
        recent_interventions=_recent_intervention_summary(int(row["event_id"])),
        reason=row["reason"] or "계획과 활동의 불일치가 감지되었습니다.",
    )
    return "\n".join(
        [
            filled.rstrip(),
            "",
            "## 기록 규칙",
            "",
            "선택지 기록 명령:",
            f"- 지금 복귀: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice return_now`",
            f"- 의도적 휴식: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice intentional_rest --duration-minutes 15`",
            f"- 피로 예외: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice fatigue --duration-minutes 30`",
            f"- 건강 예외: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice health --duration-minutes 60`",
            f"- 과부하 예외: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice overload --duration-minutes 30`",
            f"- 계획 수정: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice adjust_plan`",
            f"- 회복 모드까지 연결: 위 피로/건강/과부하/계획 수정 명령 끝에 `--enter-recovery-mode`를 붙인다.",
            f"- 오탐: `python -m lifeops.cli record-decision --event-id {row['event_id']} --choice false_positive`",
            "판단하거나 훈계하지 않는다. 루멘의 persona와 고정 선택지 순서를 유지한다.",
            "",
        ]
    )


def write_intervention_prompt(row: sqlite3.Row) -> Path:
    event_id = int(row["event_id"])
    path = default_output_path(f"intervention_prompt_{event_id}.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_intervention_prompt(row), encoding="utf-8")
    return path


def dispatch_event(event_id: int, *, launch: bool = True, mark_dispatched: bool = True) -> DispatchResult:
    row = _fetch_event_context(event_id)
    prompt_path = write_intervention_prompt(row)
    launch_result: CodexLaunch | None = None
    if launch:
        launch_result = launch_codex_intervention(prompt_path)
    if mark_dispatched:
        _set_event_status(event_id, "dispatched")
        status = "dispatched"
    else:
        _set_event_status(event_id, "pending")
        status = "pending"
    write_heartbeat(f"Intervention event #{event_id} rendered to {prompt_path} with status={status}.")
    return DispatchResult(event_id=event_id, prompt_path=prompt_path, status=status, launch=launch_result)


def dispatch_next_event(*, launch: bool = True, mark_dispatched: bool = True) -> DispatchResult | None:
    event_id = _claim_next_pending_event()
    if event_id is None:
        return None
    try:
        return dispatch_event(event_id, launch=launch, mark_dispatched=mark_dispatched)
    except Exception as exc:
        _set_event_status(event_id, "pending")
        write_heartbeat(f"Intervention event #{event_id} dispatch failed and was restored to pending: {exc}")
        raise


def run(interval_seconds: int, once: bool, *, dry_run: bool = False) -> None:
    init_db()
    write_heartbeat(f"Stage 2 dispatcher started. pending_events={pending_count()}, dry_run={dry_run}.")
    while True:
        result = dispatch_next_event(launch=not dry_run, mark_dispatched=not dry_run)
        if result is None:
            write_heartbeat(f"Stage 2 dispatcher heartbeat. pending_events={pending_count()}.")
        else:
            write_heartbeat(f"Dispatched intervention event #{result.event_id}: {result.prompt_path}.")
        if once:
            return
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LifeOps Codex intervention event dispatcher")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Render the next prompt without launching Codex or changing final event status.")
    args = parser.parse_args(argv)
    run(args.interval, args.once, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
