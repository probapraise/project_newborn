from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .db import connect, init_db
from .paths import default_output_path, repo_root
from .schedule_engine import get_today_blocks

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")
DEFAULT_DURATION_HOURS = 4
PROTECTED_BLOCK_TYPES = frozenset(
    {
        "work",
        "appointment",
        "fixed",
        "commute",
        "prep",
        "sleep",
        "meal",
        "medication",
        "hygiene",
    }
)
PROTECTED_TITLE_KEYWORDS = (
    "sleep",
    "meal",
    "medication",
    "hygiene",
    "commute",
    "work",
    "appointment",
    "\uc218\uba74",
    "\uc2dd\uc0ac",
    "\ubcf5\uc57d",
    "\uc704\uc0dd",
    "\ucd9c\uadfc",
    "\ud1f4\uadfc",
    "\uadfc\ubb34",
    "\ubcd1\uc6d0",
    "\uc57d\uc18d",
)

@dataclass(frozen=True)
class RecoveryResult:
    session_id: int | None
    prompt_path: Path
    plan: dict[str, Any]
    applied: bool


def _append_jsonl(name: str, payload: dict[str, object]) -> None:
    path = repo_root() / "data" / "events" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")



def _block_summary(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "type": row["type"],
        "title": row["title"],
        "enforcement_level": row["enforcement_level"],
        "status": row["status"],
    }


def _task_summary(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "priority": row["priority"],
        "estimated_minutes": row["estimated_minutes"],
        "due_date": row["due_date"],
        "status": row["status"],
    }


def _time_after_or_current(row: Any, current_clock: str) -> bool:
    return str(row["end_time"]) > current_clock or str(row["start_time"]) >= current_clock


def _is_self_check_block(row: Any) -> bool:
    try:
        source = row["source"]
    except (IndexError, KeyError, TypeError):
        return False
    return str(source or "").lower() == "self_check"


def _is_protected_block(row: Any) -> bool:
    block_type = str(row["type"] or "").lower()
    enforcement = str(row["enforcement_level"] or "").lower()
    title = str(row["title"] or "").lower()
    if block_type in PROTECTED_BLOCK_TYPES or enforcement in {"hard", "red"}:
        return True
    return any(keyword in title for keyword in PROTECTED_TITLE_KEYWORDS)


def _fetch_pending_tasks(today: str) -> list[Any]:
    with connect() as conn:
        return conn.execute(
            """
            SELECT * FROM tasks
            WHERE status = 'pending' AND (due_date IS NULL OR due_date <= ?)
            ORDER BY
                CASE priority
                    WHEN 'high' THEN 0
                    WHEN 'medium' THEN 1
                    WHEN 'low' THEN 2
                    ELSE 3
                END,
                COALESCE(estimated_minutes, 9999),
                COALESCE(due_date, '9999-12-31'),
                id
            """,
            (today,),
        ).fetchall()


def _split_tasks(rows: list[Any]) -> tuple[list[Any], list[Any]]:
    if not rows:
        return [], []
    high_priority = [row for row in rows if str(row["priority"] or "").lower() == "high"]
    if high_priority:
        kept = high_priority[:1]
    else:
        kept = rows[:1]
    kept_ids = {int(row["id"]) for row in kept}
    deferred = [row for row in rows if int(row["id"]) not in kept_ids]
    return kept, deferred


def _next_action(kept_tasks: list[Any], protected_blocks: list[Any]) -> str:
    if kept_tasks:
        title = str(kept_tasks[0]["title"])
        return f"Open task '{title}' and work for 3 minutes only."
    if protected_blocks:
        title = str(protected_blocks[0]["title"])
        return f"Prepare the next protected block: '{title}' for 3 minutes."
    return "Drink water, reduce the screen, and choose one necessary action for 3 minutes."


def build_recovery_plan(
    *,
    reason: str,
    now: datetime | None = None,
    duration_hours: int = DEFAULT_DURATION_HOURS,
) -> dict[str, Any]:
    current = now or datetime.now(DEFAULT_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TZ)
    today = current.date().isoformat()
    current_clock = current.strftime("%H:%M")
    end_time = current + timedelta(hours=duration_hours)

    with connect() as conn:
        today_blocks = get_today_blocks(conn, today)
    remaining_blocks = [
        row
        for row in today_blocks
        if _time_after_or_current(row, current_clock) and not _is_self_check_block(row)
    ]
    protected_blocks = [row for row in remaining_blocks if _is_protected_block(row)]
    deferred_blocks = [row for row in remaining_blocks if not _is_protected_block(row)]

    tasks = _fetch_pending_tasks(today)
    kept_tasks, deferred_tasks = _split_tasks(tasks)

    plan = {
        "label": "\ub0a8\uc740 \ud558\ub8e8 \ucd5c\uc18c\uc548",
        "reason": reason,
        "generated_at": current.isoformat(timespec="seconds"),
        "start_time": current.isoformat(timespec="seconds"),
        "end_time": end_time.isoformat(timespec="seconds"),
        "duration_hours": duration_hours,
        "mode": "recovery",
        "day_status": "adjusted_not_failed",
        "preserve": [
            "sleep",
            "meals",
            "medication",
            "hygiene",
            "fixed obligations",
            "work shifts",
        ],
        "protected_blocks": [_block_summary(row) for row in protected_blocks],
        "deferred_blocks": [_block_summary(row) for row in deferred_blocks],
        "kept_tasks": [_task_summary(row) for row in kept_tasks],
        "deferred_tasks": [_task_summary(row) for row in deferred_tasks],
        "next_action": _next_action(kept_tasks, protected_blocks),
        "notes": [
            "No score.",
            "No debt-based punishment.",
            "The day is adjusted, not failed.",
            "Only one next action is selected.",
        ],
    }
    return plan


def render_recovery_prompt(plan: dict[str, Any]) -> str:
    def _lines(items: list[dict[str, Any]], empty: str) -> list[str]:
        if not items:
            return [f"- {empty}"]
        return [f"- #{item['id']} {item.get('start_time', '')}-{item.get('end_time', '')} {item['title']}" for item in items]

    def _task_lines(items: list[dict[str, Any]], empty: str) -> list[str]:
        if not items:
            return [f"- {empty}"]
        return [f"- #{item['id']} {item['title']} ({item['priority']})" for item in items]

    parts = [
        "# LifeOps Recovery Mode",
        "",
        "You are Lumen, the LifeOps operator. Speak in Korean.",
        "Do not use guilt, debt, punishment, or failure framing.",
        "Treat the day as adjusted, not failed.",
        "Ask at most one question.",
        "",
        f"reason: {plan['reason']}",
        f"window: {plan['start_time']} -> {plan['end_time']}",
        "",
        "## Protected",
        *_lines(plan["protected_blocks"], "No protected blocks in the remaining window"),
        "",
        "## Deferred",
        *_lines(plan["deferred_blocks"], "No flexible blocks deferred"),
        "",
        "## Kept Tasks",
        *_task_lines(plan["kept_tasks"], "No task kept"),
        "",
        "## Deferred Tasks",
        *_task_lines(plan["deferred_tasks"], "No task deferred"),
        "",
        "## Next Action",
        f"- {plan['next_action']}",
        "",
        "Final line must be one small action under 5 minutes.",
    ]
    return "\n".join(parts) + "\n"


def _apply_plan(plan: dict[str, Any]) -> int:
    started_at = str(plan["start_time"])
    ended_at = str(plan["end_time"])
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO recovery_sessions(start_time, end_time, reason, minimized_plan_json)
            VALUES (?, ?, ?, ?)
            """,
            (started_at, ended_at, plan["reason"], payload),
        )
        session_id = int(cursor.lastrowid)
        for block in plan["deferred_blocks"]:
            conn.execute(
                "UPDATE schedule_blocks SET status = 'cancelled' WHERE id = ?",
                (block["id"],),
            )
        for task in plan["deferred_tasks"]:
            conn.execute(
                "UPDATE tasks SET status = 'deferred_recovery' WHERE id = ?",
                (task["id"],),
            )
        conn.execute(
            """
            INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source, status)
            VALUES (?, ?, ?, 'recovery', 'Recovery mode active', 'normal', 'recovery', 'planned')
            """,
            (
                str(plan["start_time"])[:10],
                str(plan["start_time"])[11:16],
                str(plan["end_time"])[11:16],
            ),
        )
        conn.commit()
    event = {
        "id": session_id,
        "start_time": started_at,
        "end_time": ended_at,
        "reason": plan["reason"],
        "deferred_blocks": [block["id"] for block in plan["deferred_blocks"]],
        "deferred_tasks": [task["id"] for task in plan["deferred_tasks"]],
        "next_action": plan["next_action"],
    }
    _append_jsonl("recovery_sessions.jsonl", event)
    return session_id


def enter_recovery_mode(
    *,
    reason: str,
    duration_hours: int = DEFAULT_DURATION_HOURS,
    output: Path | None = None,
    apply: bool = True,
    now: datetime | None = None,
) -> RecoveryResult:
    init_db()
    if duration_hours <= 0:
        raise ValueError("duration_hours must be greater than zero.")
    plan = build_recovery_plan(reason=reason, duration_hours=duration_hours, now=now)
    session_id = _apply_plan(plan) if apply else None
    if session_id is not None:
        plan["session_id"] = session_id
    prompt_path = output or default_output_path(
        f"recovery_prompt_{session_id if session_id is not None else 'preview'}.md"
    )
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(render_recovery_prompt(plan), encoding="utf-8")
    return RecoveryResult(session_id=session_id, prompt_path=prompt_path, plan=plan, applied=apply)
