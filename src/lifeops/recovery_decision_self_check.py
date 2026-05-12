from __future__ import annotations

import argparse
import io
import json
import os
import shutil
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from .cli import cmd_record_decision
from .db import connect, init_db, utc_now
from .models import ActivitySnapshot
from .paths import repo_root

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")
SANDBOX_RELATIVE_PATH = Path("data") / "runtime" / "recovery_decision_self_check"


def _append_jsonl(name: str, payload: dict[str, object]) -> None:
    path = repo_root() / "data" / "events" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _prepare_sandbox(real_root: Path) -> Path:
    sandbox = (real_root / SANDBOX_RELATIVE_PATH).resolve()
    expected_parent = (real_root / "data" / "runtime").resolve()
    if expected_parent not in sandbox.parents:
        raise RuntimeError(f"Refusing to reset unexpected self-check sandbox path: {sandbox}")
    if sandbox.exists():
        shutil.rmtree(sandbox)
    (sandbox / "prompts").mkdir(parents=True, exist_ok=True)
    source_prompt = real_root / "prompts" / "intervention_prompt.md"
    target_prompt = sandbox / "prompts" / "intervention_prompt.md"
    if source_prompt.exists():
        shutil.copyfile(source_prompt, target_prompt)
    else:
        target_prompt.write_text(
            "event `{event_id}`\nblock `{current_block}`\nactivity `{detected_activity}`\nreason `{reason}`\n",
            encoding="utf-8",
        )
    return sandbox


def _clock_at(now: datetime, minutes: int) -> str:
    return (now + timedelta(minutes=minutes)).strftime("%H:%M")


def _insert_block(*, now: datetime, title: str, block_type: str, start_offset: int, end_offset: int) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source)
            VALUES (?, ?, ?, ?, ?, 'normal', 'recovery_decision_self_check')
            """,
            (now.date().isoformat(), _clock_at(now, start_offset), _clock_at(now, end_offset), block_type, title),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _insert_task(*, today: str, title: str, priority: str) -> int:
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks(title, priority, estimated_minutes, due_date, status)
            VALUES (?, ?, 30, ?, 'pending')
            """,
            (title, priority, today),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _insert_activity() -> int:
    snapshot = ActivitySnapshot(
        timestamp=utc_now(),
        process_name="steam-launched-app",
        window_title="LifeOps Recovery Self-Check Steam Activity",
        classification="steam",
        source="recovery_decision_self_check",
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


def _insert_intervention(activity_id: int, schedule_block_id: int) -> int:
    timestamp = utc_now()
    reason = "LifeOps recovery decision self-check: synthetic Steam activity during a focus block."
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO intervention_events(
                timestamp, activity_event_id, schedule_block_id,
                risk_level, reason, status
            ) VALUES (?, ?, ?, 'yellow', ?, 'pending')
            """,
            (timestamp, activity_id, schedule_block_id, reason),
        )
        conn.commit()
        event_id = int(cursor.lastrowid)
    _append_jsonl(
        "interventions.jsonl",
        {
            "id": event_id,
            "timestamp": timestamp,
            "activity_event_id": activity_id,
            "schedule_block_id": schedule_block_id,
            "risk_level": "yellow",
            "reason": reason,
            "status": "pending",
            "source": "recovery_decision_self_check",
        },
    )
    return event_id


def _fetch_statuses(
    *,
    event_id: int,
    protected_block_id: int,
    optional_block_id: int,
    kept_task_id: int,
    deferred_task_id: int,
) -> dict[str, object]:
    with connect() as conn:
        event = conn.execute("SELECT status FROM intervention_events WHERE id = ?", (event_id,)).fetchone()
        protected_block = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (protected_block_id,)).fetchone()
        optional_block = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (optional_block_id,)).fetchone()
        kept_task = conn.execute("SELECT status FROM tasks WHERE id = ?", (kept_task_id,)).fetchone()
        deferred_task = conn.execute("SELECT status FROM tasks WHERE id = ?", (deferred_task_id,)).fetchone()
        decisions = conn.execute("SELECT COUNT(*) AS count FROM intervention_decisions").fetchone()
        exceptions = conn.execute("SELECT COUNT(*) AS count FROM exceptions").fetchone()
        recovery_sessions = conn.execute("SELECT COUNT(*) AS count FROM recovery_sessions").fetchone()
    return {
        "event_status": event["status"],
        "protected_block_status": protected_block["status"],
        "optional_block_status": optional_block["status"],
        "kept_task_status": kept_task["status"],
        "deferred_task_status": deferred_task["status"],
        "decision_count": int(decisions["count"]),
        "exception_count": int(exceptions["count"]),
        "recovery_session_count": int(recovery_sessions["count"]),
    }


def run_recovery_decision_self_check(
    *,
    choice: str = "fatigue",
    duration_minutes: int = 30,
    recovery_duration_hours: int = 2,
    recovery_dry_run: bool = False,
) -> dict[str, object]:
    real_root = repo_root()
    old_root = os.environ.get("LIFEOPS_REPO_ROOT")
    sandbox = _prepare_sandbox(real_root)
    os.environ["LIFEOPS_REPO_ROOT"] = str(sandbox)
    try:
        init_db()
        now = datetime.now(DEFAULT_TZ)
        protected_block_id = _insert_block(
            now=now,
            title="LifeOps recovery self-check protected focus block",
            block_type="work",
            start_offset=-10,
            end_offset=30,
        )
        optional_block_id = _insert_block(
            now=now,
            title="LifeOps recovery self-check optional block",
            block_type="study",
            start_offset=35,
            end_offset=65,
        )
        kept_task_id = _insert_task(
            today=now.date().isoformat(),
            title="LifeOps recovery self-check required task",
            priority="high",
        )
        deferred_task_id = _insert_task(
            today=now.date().isoformat(),
            title="LifeOps recovery self-check optional task",
            priority="low",
        )
        activity_id = _insert_activity()
        event_id = _insert_intervention(activity_id, protected_block_id)
        args = SimpleNamespace(
            event_id=event_id,
            choice=choice,
            decision=None,
            category=None,
            reason="LifeOps recovery decision self-check",
            duration_minutes=duration_minutes,
            followup_action=None,
            enter_recovery_mode=True,
            recovery_duration_hours=recovery_duration_hours,
            recovery_output=None,
            recovery_dry_run=recovery_dry_run,
        )
        cli_output = io.StringIO()
        with redirect_stdout(cli_output):
            cli_exit_code = cmd_record_decision(args)
        statuses = _fetch_statuses(
            event_id=event_id,
            protected_block_id=protected_block_id,
            optional_block_id=optional_block_id,
            kept_task_id=kept_task_id,
            deferred_task_id=deferred_task_id,
        )
        expected_optional = "planned" if recovery_dry_run else "cancelled"
        expected_deferred_task = "pending" if recovery_dry_run else "deferred_recovery"
        expected_recovery_sessions = 0 if recovery_dry_run else 1
        checks = {
            "cli_exit_code": cli_exit_code == 0,
            "event_decided": statuses["event_status"] == "decided",
            "protected_block_preserved": statuses["protected_block_status"] == "planned",
            "optional_block_handled": statuses["optional_block_status"] == expected_optional,
            "kept_task_preserved": statuses["kept_task_status"] == "pending",
            "deferred_task_handled": statuses["deferred_task_status"] == expected_deferred_task,
            "decision_recorded": statuses["decision_count"] == 1,
            "exception_recorded": statuses["exception_count"] == 1,
            "recovery_session_count": statuses["recovery_session_count"] == expected_recovery_sessions,
        }
        status = "pass" if all(checks.values()) else "fail"
        return {
            "status": status,
            "sandbox_root": str(sandbox),
            "event_id": event_id,
            "activity_id": activity_id,
            "protected_block_id": protected_block_id,
            "optional_block_id": optional_block_id,
            "kept_task_id": kept_task_id,
            "deferred_task_id": deferred_task_id,
            "choice": choice,
            "recovery_dry_run": recovery_dry_run,
            "cli_output": [line for line in cli_output.getvalue().splitlines() if line],
            "checks": checks,
            **statuses,
        }
    finally:
        if old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = old_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an isolated LifeOps recovery decision self-check.")
    parser.add_argument("--choice", default="fatigue")
    parser.add_argument("--duration-minutes", type=int, default=30)
    parser.add_argument("--recovery-duration-hours", type=int, default=2)
    parser.add_argument("--recovery-dry-run", action="store_true")
    args = parser.parse_args(argv)

    result = run_recovery_decision_self_check(
        choice=args.choice,
        duration_minutes=args.duration_minutes,
        recovery_duration_hours=args.recovery_duration_hours,
        recovery_dry_run=args.recovery_dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())