from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .boot import write_boot_context, write_boot_prompt
from .db import connect, init_db, table_names
from .daily_summary import write_daily_summary
from .decision_logging import decision_help_text, normalize_decision, record_intervention_decision
from .recovery import enter_recovery_mode
from .schedule_engine import format_block, get_current_block, get_fixed_obligations

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


def _print_lines(lines: list[str]) -> None:
    for line in lines:
        print(line)


def cmd_init_db(args: argparse.Namespace) -> int:
    db_file = init_db()
    with connect(db_file) as conn:
        tables = table_names(conn)
    print(f"DB initialized: {db_file}")
    print("Tables: " + ", ".join(tables))
    return 0


def cmd_export_boot_context(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    path = write_boot_context(output)
    if args.print_text:
        print(path.read_text(encoding="utf-8"))
    else:
        print(f"Boot briefing context written: {path}")
    return 0


def cmd_write_boot_prompt(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    path = write_boot_prompt(output)
    if args.print_text:
        print(path.read_text(encoding="utf-8"))
    else:
        print(f"Boot prompt written: {path}")
    return 0


def cmd_get_today_plan(args: argparse.Namespace) -> int:
    init_db()
    now = datetime.now(DEFAULT_TZ)
    with connect() as conn:
        rows = get_fixed_obligations(conn, now.date().isoformat())
    if not rows:
        print("오늘 등록된 고정 일정이 없습니다.")
        return 0
    _print_lines([format_block(row) for row in rows])
    return 0


def cmd_get_current_block(args: argparse.Namespace) -> int:
    init_db()
    now = datetime.now(DEFAULT_TZ)
    with connect() as conn:
        row = get_current_block(conn, now)
    print(format_block(row))
    return 0


def cmd_get_pending_events(args: argparse.Namespace) -> int:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM intervention_events
            WHERE status = 'pending'
            ORDER BY timestamp, id
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
    return 0


def cmd_record_decision(args: argparse.Namespace) -> int:
    init_db()
    choice = args.choice or args.decision
    if not choice:
        print("결정 선택지가 필요합니다. 사용 가능한 선택지:")
        print(decision_help_text())
        return 2
    if args.enter_recovery_mode:
        try:
            recovery_option = normalize_decision(choice)
        except ValueError as exc:
            print(str(exc))
            return 2
        if recovery_option.category not in {"fatigue", "health", "sensory_overload", "schedule_change"}:
            print("--enter-recovery-mode is only for fatigue, health, overload, or adjust_plan decisions.")
            return 2
        if args.recovery_duration_hours <= 0:
            print("recovery_duration_hours must be greater than zero.")
            return 2
    try:
        payload = record_intervention_decision(
            args.event_id,
            choice,
            category=args.category,
            reason=args.reason,
            duration_minutes=args.duration_minutes,
            followup_action=args.followup_action,
        )
    except (LookupError, ValueError) as exc:
        print(str(exc))
        return 2
    print(f"Decision recorded for event #{args.event_id}: {payload['decision']} ({payload['category']})")
    if payload.get("exception_id") is not None:
        print(f"Exception recorded: #{payload['exception_id']}")

    if args.enter_recovery_mode:
        output = Path(args.recovery_output) if args.recovery_output else None
        recovery_reason = args.reason or str(payload["label"])
        recovery_result = enter_recovery_mode(
            reason=f"intervention #{args.event_id}: {payload['category']} - {recovery_reason}",
            duration_hours=args.recovery_duration_hours,
            output=output,
            apply=not args.recovery_dry_run,
        )
        recovery_mode = "entered" if recovery_result.applied else "previewed"
        print(f"Recovery mode {recovery_mode} from event #{args.event_id}.")
        if recovery_result.session_id is not None:
            print(f"Recovery session: #{recovery_result.session_id}")
        print(f"Recovery prompt: {recovery_result.prompt_path}")
        print(f"Recovery next action: {recovery_result.plan['next_action']}")
    return 0


def cmd_enter_recovery_mode(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    try:
        result = enter_recovery_mode(
            reason=args.reason,
            duration_hours=args.duration_hours,
            output=output,
            apply=not args.dry_run,
        )
    except ValueError as exc:
        print(str(exc))
        return 2

    plan = result.plan
    mode = "entered" if result.applied else "previewed"
    print(f"Recovery mode {mode}.")
    if result.session_id is not None:
        print(f"Recovery session: #{result.session_id}")
    print(f"Prompt written: {result.prompt_path}")
    print(f"Protected blocks: {len(plan['protected_blocks'])}")
    print(f"Deferred blocks: {len(plan['deferred_blocks'])}")
    print(f"Deferred tasks: {len(plan['deferred_tasks'])}")
    print(f"Next action: {plan['next_action']}")
    return 0


def cmd_write_daily_summary(args: argparse.Namespace) -> int:
    output = Path(args.output) if args.output else None
    try:
        path = write_daily_summary(output, day=args.date)
    except ValueError as exc:
        print(str(exc))
        return 2
    print(f"Daily summary written: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lifeops", description="LifeOps Codex Operator local CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-db")
    init.set_defaults(func=cmd_init_db)

    boot_context = sub.add_parser("export-boot-briefing-context")
    boot_context.add_argument("--output")
    boot_context.add_argument("--print", dest="print_text", action="store_true")
    boot_context.set_defaults(func=cmd_export_boot_context)

    boot_prompt = sub.add_parser("write-boot-prompt")
    boot_prompt.add_argument("--output")
    boot_prompt.add_argument("--print", dest="print_text", action="store_true")
    boot_prompt.set_defaults(func=cmd_write_boot_prompt)

    today = sub.add_parser("get-today-plan")
    today.set_defaults(func=cmd_get_today_plan)

    current = sub.add_parser("get-current-block")
    current.set_defaults(func=cmd_get_current_block)

    pending = sub.add_parser("get-pending-events")
    pending.add_argument("--limit", type=int, default=20)
    pending.set_defaults(func=cmd_get_pending_events)

    decision = sub.add_parser("record-decision")
    decision.add_argument("--event-id", type=int, required=True)
    decision.add_argument("--choice", help="Canonical choice code such as return_now, intentional_rest, fatigue, health, overload, adjust_plan, false_positive")
    decision.add_argument("--decision", help="Backward-compatible alias for --choice")
    decision.add_argument("--category")
    decision.add_argument("--reason", default="")
    decision.add_argument("--duration-minutes", type=int)
    decision.add_argument("--followup-action")
    decision.add_argument("--enter-recovery-mode", action="store_true", help="After recording the decision, also create a recovery-mode plan.")
    decision.add_argument("--recovery-duration-hours", type=int, default=4)
    decision.add_argument("--recovery-output")
    decision.add_argument("--recovery-dry-run", action="store_true", help="Preview recovery mode without mutating schedule/tasks.")
    decision.set_defaults(func=cmd_record_decision)

    recovery = sub.add_parser("enter-recovery-mode")
    recovery.add_argument("--reason", required=True)
    recovery.add_argument("--duration-hours", type=int, default=4)
    recovery.add_argument("--output")
    recovery.add_argument("--dry-run", action="store_true")
    recovery.set_defaults(func=cmd_enter_recovery_mode)

    daily = sub.add_parser("write-daily-summary")
    daily.add_argument("--output")
    daily.add_argument("--date", help="Local date in YYYY-MM-DD format. Defaults to today in Asia/Seoul.")
    daily.set_defaults(func=cmd_write_daily_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
