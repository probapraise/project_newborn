from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from .db import connect, init_db, utc_now
from .models import ActivitySnapshot
from .paths import repo_root
from .policy_engine import PolicyDecision, evaluate_activity
from .schedule_engine import get_current_block

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")
INTERVENTION_COOLDOWN_MINUTES = 15
MAX_INTERVENTIONS_PER_HOUR = 3


def write_heartbeat(message: str) -> None:
    root = repo_root()
    log_path = root / "data" / "runtime" / "activity_watcher.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(DEFAULT_TZ).isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _append_jsonl(name: str, payload: dict[str, object]) -> None:
    path = repo_root() / "data" / "events" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _insert_activity(snapshot: ActivitySnapshot) -> int:
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


def _recent_intervention_count(minutes: int) -> int:
    threshold = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM intervention_events
            WHERE timestamp >= ?
            """,
            (threshold,),
        ).fetchone()
    return int(row["count"])


def _should_create_intervention() -> bool:
    if _recent_intervention_count(INTERVENTION_COOLDOWN_MINUTES) > 0:
        return False
    return _recent_intervention_count(60) < MAX_INTERVENTIONS_PER_HOUR


def _insert_intervention(activity_id: int, block_id: int | None, decision: PolicyDecision) -> int | None:
    if not _should_create_intervention():
        write_heartbeat("Intervention suppressed by cooldown policy.")
        return None
    timestamp = utc_now()
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO intervention_events(
                timestamp, activity_event_id, schedule_block_id,
                risk_level, reason, status
            ) VALUES (?, ?, ?, ?, ?, 'pending')
            """,
            (timestamp, activity_id, block_id, decision.risk_level, decision.reason),
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
            "risk_level": decision.risk_level,
            "reason": decision.reason,
            "status": "pending",
        },
    )
    return event_id


def process_snapshot(snapshot: ActivitySnapshot) -> tuple[int | None, PolicyDecision]:
    if snapshot.classification == "ignored":
        return None, PolicyDecision("ignore", "Chrome/Steam 범위 밖 활동입니다.")

    now = datetime.now(DEFAULT_TZ)
    with connect() as conn:
        current_block = get_current_block(conn, now)
        block_id = int(current_block["id"]) if current_block is not None else None

    decision = evaluate_activity(snapshot, current_block)
    if decision.action == "ignore":
        return None, decision

    activity_id = _insert_activity(snapshot)
    if decision.action == "intervene":
        event_id = _insert_intervention(activity_id, block_id, decision)
        if event_id is not None:
            write_heartbeat(f"Pending intervention created: event_id={event_id}, activity_id={activity_id}.")
    return activity_id, decision


def poll_once() -> tuple[ActivitySnapshot | None, PolicyDecision | None]:
    from .windows_activity import get_foreground_activity

    snapshot = get_foreground_activity()
    if snapshot is None:
        write_heartbeat("Foreground activity unavailable; watcher is alive.")
        return None, None
    _, decision = process_snapshot(snapshot)
    return snapshot, decision


def run(interval_seconds: int, once: bool) -> None:
    from .windows_activity import get_foreground_activity

    init_db()
    write_heartbeat("Stage 2 watcher started. Scope: Chrome/Steam only; title and domain-limited metadata only.")
    last_key: tuple[str, str, str | None, str] | None = None
    while True:
        snapshot = get_foreground_activity()
        if snapshot is None:
            if once:
                write_heartbeat("Foreground activity unavailable; watcher is alive.")
                return
        elif snapshot.identity_key() != last_key:
            activity_id, decision = process_snapshot(snapshot)
            if decision.action != "ignore":
                write_heartbeat(f"Activity recorded: activity_id={activity_id}, action={decision.action}, process={snapshot.process_name}.")
            last_key = snapshot.identity_key()
        if once:
            return
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LifeOps Chrome/Steam foreground activity watcher")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    run(args.interval, args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
