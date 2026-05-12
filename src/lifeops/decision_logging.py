from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db import connect, utc_now
from .paths import repo_root

DEFAULT_EXCEPTION_MINUTES = 15


@dataclass(frozen=True)
class DecisionOption:
    code: str
    label: str
    category: str
    followup_action: str
    creates_exception: bool = False
    default_duration_minutes: int | None = None
    event_status: str = "decided"


DECISION_OPTIONS: dict[str, DecisionOption] = {
    "plan_aligned": DecisionOption(
        code="plan_aligned",
        label="\ud604\uc7ac \uacc4\ud68d\uc5d0 \ub9de\uc74c",
        category="plan_aligned",
        followup_action="learn_as_plan_aligned",
        event_status="aligned",
    ),
    "return_now": DecisionOption(
        code="return_now",
        label="\uc9c0\uae08 \ubcf5\uadc0",
        category="return_to_plan",
        followup_action="return_to_current_plan",
    ),
    "intentional_rest": DecisionOption(
        code="intentional_rest",
        label="\uc758\ub3c4\uc801 \ud734\uc2dd\uc73c\ub85c \ub4f1\ub85d",
        category="intentional_rest",
        followup_action="create_short_rest_exception",
        creates_exception=True,
        default_duration_minutes=15,
    ),
    "fatigue": DecisionOption(
        code="fatigue",
        label="\ud53c\ub85c \uc608\uc678",
        category="fatigue",
        followup_action="create_fatigue_exception",
        creates_exception=True,
        default_duration_minutes=30,
    ),
    "health": DecisionOption(
        code="health",
        label="\uac74\uac15 \uc608\uc678",
        category="health",
        followup_action="create_health_exception",
        creates_exception=True,
        default_duration_minutes=60,
    ),
    "overload": DecisionOption(
        code="overload",
        label="\uacfc\ubd80\ud558 \uc608\uc678",
        category="sensory_overload",
        followup_action="create_overload_exception",
        creates_exception=True,
        default_duration_minutes=30,
    ),
    "adjust_plan": DecisionOption(
        code="adjust_plan",
        label="\uacc4\ud68d \uc790\uccb4\ub97c \uc218\uc815",
        category="schedule_change",
        followup_action="review_current_plan",
        creates_exception=True,
        default_duration_minutes=15,
    ),
    "false_positive": DecisionOption(
        code="false_positive",
        label="\uc624\ud0d0\uc73c\ub85c \ud45c\uc2dc",
        category="false_positive",
        followup_action="mark_detection_false_positive",
        event_status="false_positive",
    ),
}

ALIASES = {
    "1": "return_now",
    "return": "return_now",
    "return_to_plan": "return_now",
    "\ubcf5\uadc0": "return_now",
    "\uc9c0\uae08 \ubcf5\uadc0": "return_now",
    "aligned": "plan_aligned",
    "plan_match": "plan_aligned",
    "plan_aligned": "plan_aligned",
    "\ub9de\uc74c": "plan_aligned",
    "\uacc4\ud68d\uc5d0 \ub9de\uc74c": "plan_aligned",
    "\ud604\uc7ac \uacc4\ud68d\uc5d0 \ub9de\uc74c": "plan_aligned",
    "2": "intentional_rest",
    "rest": "intentional_rest",
    "intentional_break": "intentional_rest",
    "\ud734\uc2dd": "intentional_rest",
    "\uc758\ub3c4\uc801 \ud734\uc2dd": "intentional_rest",
    "3": "fatigue",
    "fatigue_exception": "fatigue",
    "tired": "fatigue",
    "\ud53c\ub85c": "fatigue",
    "\ud53c\ub85c \uc608\uc678": "fatigue",
    "health_exception": "health",
    "sick": "health",
    "illness": "health",
    "\uac74\uac15": "health",
    "\uac74\uac15 \uc608\uc678": "health",
    "overload_exception": "overload",
    "sensory_overload": "overload",
    "emotional_overload": "overload",
    "\uacfc\ubd80\ud558": "overload",
    "\uacfc\ubd80\ud558 \uc608\uc678": "overload",
    "4": "adjust_plan",
    "schedule_change": "adjust_plan",
    "adjust": "adjust_plan",
    "plan_change": "adjust_plan",
    "\uacc4\ud68d \uc218\uc815": "adjust_plan",
    "\uacc4\ud68d \uc790\uccb4\ub97c \uc218\uc815": "adjust_plan",
    "5": "false_positive",
    "false-positive": "false_positive",
    "false_alarm": "false_positive",
    "\uc624\ud0d0": "false_positive",
    "\uc624\ud0d0\uc73c\ub85c \ud45c\uc2dc": "false_positive",
}


def available_decision_options() -> list[DecisionOption]:
    return [
        DECISION_OPTIONS["plan_aligned"],
        DECISION_OPTIONS["return_now"],
        DECISION_OPTIONS["intentional_rest"],
        DECISION_OPTIONS["fatigue"],
        DECISION_OPTIONS["health"],
        DECISION_OPTIONS["overload"],
        DECISION_OPTIONS["adjust_plan"],
        DECISION_OPTIONS["false_positive"],
    ]


def normalize_decision(value: str) -> DecisionOption:
    normalized = value.strip().lower().replace(" ", "_")
    code = ALIASES.get(value.strip()) or ALIASES.get(normalized) or normalized
    option = DECISION_OPTIONS.get(code)
    if option is None:
        valid = ", ".join(option.code for option in available_decision_options())
        raise ValueError(f"Unknown decision choice '{value}'. Valid choices: {valid}")
    return option


def _append_jsonl(name: str, payload: dict[str, object]) -> None:
    path = repo_root() / "data" / "events" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _duration(option: DecisionOption, explicit_minutes: int | None) -> int | None:
    if explicit_minutes is not None:
        return explicit_minutes
    return option.default_duration_minutes


def _exception_window(minutes: int) -> tuple[str, str]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=minutes)
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def record_intervention_decision(
    event_id: int,
    choice: str,
    *,
    category: str | None = None,
    reason: str = "",
    duration_minutes: int | None = None,
    followup_action: str | None = None,
) -> dict[str, object]:
    option = normalize_decision(choice)
    decided_at = utc_now()
    final_category = category or option.category
    final_followup = followup_action or option.followup_action
    final_duration = _duration(option, duration_minutes)
    if final_duration is not None and final_duration <= 0:
        raise ValueError("duration_minutes must be greater than zero.")

    exception_payload: dict[str, object] | None = None

    with connect() as conn:
        event = conn.execute(
            "SELECT id, status FROM intervention_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if event is None:
            raise LookupError(f"Intervention event #{event_id} not found.")

        existing = conn.execute(
            "SELECT id FROM intervention_decisions WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"Decision already recorded for intervention event #{event_id}.")

        cursor = conn.execute(
            """
            INSERT INTO intervention_decisions(
                event_id, timestamp, decision, category, duration_minutes,
                user_text_summary, followup_action
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                decided_at,
                option.code,
                final_category,
                final_duration,
                reason,
                final_followup,
            ),
        )
        decision_id = int(cursor.lastrowid)

        exception_id: int | None = None
        if option.creates_exception:
            minutes = final_duration or DEFAULT_EXCEPTION_MINUTES
            start_time, end_time = _exception_window(minutes)
            exception_reason = reason or option.label
            exception_cursor = conn.execute(
                """
                INSERT INTO exceptions(start_time, end_time, category, reason, created_from_event_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (start_time, end_time, final_category, exception_reason, event_id),
            )
            exception_id = int(exception_cursor.lastrowid)
            exception_payload = {
                "id": exception_id,
                "start_time": start_time,
                "end_time": end_time,
                "category": final_category,
                "reason": exception_reason,
                "created_from_event_id": event_id,
            }

        conn.execute(
            "UPDATE intervention_events SET status = ? WHERE id = ?",
            (option.event_status, event_id),
        )
        conn.commit()

    payload: dict[str, object] = {
        "decision_id": decision_id,
        "event_id": event_id,
        "timestamp": decided_at,
        "decision": option.code,
        "label": option.label,
        "category": final_category,
        "duration_minutes": final_duration,
        "followup_action": final_followup,
        "event_status": option.event_status,
        "exception_id": exception_id,
    }
    if reason:
        payload["reason"] = reason
    _append_jsonl("intervention_decisions.jsonl", payload)
    if exception_payload is not None:
        _append_jsonl("exceptions.jsonl", exception_payload)
    return payload


def decision_help_text() -> str:
    return "\n".join(
        f"- {option.code}: {option.label} ({option.category})"
        for option in available_decision_options()
    )
