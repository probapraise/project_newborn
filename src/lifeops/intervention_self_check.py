from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db, utc_now
from .decision_logging import record_intervention_decision
from .event_dispatcher import dispatch_event
from .models import ActivitySnapshot
from .paths import repo_root

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


def _append_jsonl(name: str, payload: dict[str, object]) -> None:
    path = repo_root() / "data" / "events" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _insert_self_check_block(now: datetime) -> int:
    start = (now - timedelta(minutes=30)).strftime("%H:%M")
    end = (now + timedelta(minutes=30)).strftime("%H:%M")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source)
            VALUES (?, ?, ?, 'work', 'LifeOps self-check focus block', 'normal', 'self_check')
            """,
            (now.date().isoformat(), start, end),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _insert_self_check_activity() -> int:
    snapshot = ActivitySnapshot(
        timestamp=utc_now(),
        process_name="steam-launched-app",
        window_title="LifeOps Self-Check Steam Activity",
        classification="steam",
        source="self_check",
    )
    payload = snapshot.limited_payload()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO activity_events(
                timestamp, process_name, window_title, domain,
                classification, raw_limited_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.timestamp,
                snapshot.process_name,
                snapshot.window_title,
                snapshot.domain,
                snapshot.classification,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
        activity_id = int(cursor.lastrowid)
    _append_jsonl("activity.jsonl", {"id": activity_id, **payload})
    return activity_id


def _insert_self_check_intervention(activity_id: int, block_id: int) -> int:
    timestamp = utc_now()
    reason = "LifeOps self-check: synthetic Steam activity during a focus block."
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO intervention_events(
                timestamp, activity_event_id, schedule_block_id,
                risk_level, reason, status
            ) VALUES (?, ?, ?, 'yellow', ?, 'pending')
            """,
            (timestamp, activity_id, block_id, reason),
        )
        conn.commit()
        event_id = int(cursor.lastrowid)
    _append_jsonl(
        "interventions.jsonl",
        {
            "id": event_id,
            "timestamp": timestamp,
            "activity_event_id": activity_id,
            "schedule_block_id": block_id,
            "risk_level": "yellow",
            "reason": reason,
            "status": "pending",
            "source": "self_check",
        },
    )
    return event_id


def _event_status(event_id: int) -> str:
    with connect() as conn:
        row = conn.execute("SELECT status FROM intervention_events WHERE id = ?", (event_id,)).fetchone()
    if row is None:
        raise LookupError(f"Intervention event #{event_id} not found after self-check.")
    return str(row["status"])


def cleanup_self_check_artifacts() -> dict[str, object]:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE schedule_blocks
            SET status = 'cancelled'
            WHERE source = 'self_check' AND status != 'cancelled'
            """
        )
        cancelled_blocks = int(cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0)
        conn.commit()
    return {
        "status": "cleaned",
        "cancelled_schedule_blocks": cancelled_blocks,
    }


def run_self_check(
    *,
    choice: str = "return_now",
    duration_minutes: int | None = None,
    reason: str = "LifeOps intervention loop self-check",
    cleanup: bool = True,
) -> dict[str, object]:
    init_db()
    now = datetime.now(DEFAULT_TZ)
    block_id = _insert_self_check_block(now)
    activity_id = _insert_self_check_activity()
    event_id = _insert_self_check_intervention(activity_id, block_id)

    dispatch = dispatch_event(event_id, launch=False, mark_dispatched=True)
    decision = record_intervention_decision(
        event_id,
        choice,
        reason=reason,
        duration_minutes=duration_minutes,
    )
    final_status = _event_status(event_id)
    cleanup_result = (
        cleanup_self_check_artifacts()
        if cleanup
        else {
            "status": "skipped",
            "cancelled_schedule_blocks": 0,
        }
    )

    return {
        "status": "pass",
        "event_id": event_id,
        "activity_id": activity_id,
        "schedule_block_id": block_id,
        "prompt_path": str(Path(dispatch.prompt_path)),
        "dispatch_status": dispatch.status,
        "decision": decision["decision"],
        "decision_category": decision["category"],
        "exception_id": decision.get("exception_id"),
        "final_event_status": final_status,
        "cleanup": cleanup_result,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a safe LifeOps intervention loop self-check.")
    parser.add_argument("--choice", default="return_now")
    parser.add_argument("--duration-minutes", type=int)
    parser.add_argument("--reason", default="LifeOps intervention loop self-check")
    parser.add_argument("--keep-artifacts", action="store_true", help="Leave self-check schedule artifacts in place.")
    parser.add_argument("--cleanup-only", action="store_true", help="Only clean old self-check schedule artifacts.")
    args = parser.parse_args(argv)

    if args.cleanup_only:
        result = cleanup_self_check_artifacts()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    result = run_self_check(
        choice=args.choice,
        duration_minutes=args.duration_minutes,
        reason=args.reason,
        cleanup=not args.keep_artifacts,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
