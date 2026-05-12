from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .app_scope import classify_monitored_process
from .models import ActivitySnapshot

DECISION_CHOICES = frozenset(
    {
        "return_now",
        "intentional_rest",
        "fatigue",
        "health",
        "overload",
        "adjust_plan",
        "false_positive",
    }
)


@dataclass(frozen=True)
class DecisionPayload:
    choice: str
    duration_minutes: int | None = None
    reason: str = ""
    followup_action: str | None = None
    enter_recovery_mode: bool = False
    recovery_duration_hours: int = 4


def _optional_str(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return str(value)


def _classification(process_name: str, payload_value: str | None) -> str:
    normalized = (payload_value or "").strip().lower()
    if normalized in {"chrome", "steam", "ignored"}:
        return normalized
    if process_name == "steam-launched-app":
        return "steam"
    return classify_monitored_process(process_name)


def activity_snapshot_from_payload(payload: dict[str, Any]) -> ActivitySnapshot:
    timestamp = _optional_str(payload, "timestamp")
    process_name = (_optional_str(payload, "process_name") or "").strip().lower()
    if not timestamp:
        raise ValueError("timestamp is required.")
    if not process_name:
        raise ValueError("process_name is required.")

    classification = _classification(process_name, _optional_str(payload, "classification"))
    if classification == "ignored":
        return ActivitySnapshot(
            timestamp=timestamp,
            process_name=process_name,
            classification="ignored",
            source="wsl_bridge",
        )

    return ActivitySnapshot(
        timestamp=timestamp,
        process_name=process_name,
        window_title=_optional_str(payload, "window_title") or "",
        domain=_optional_str(payload, "domain"),
        classification=classification,
        source="wsl_bridge",
    )


def decision_payload_from_json(payload: dict[str, Any]) -> DecisionPayload:
    choice = (_optional_str(payload, "choice") or "").strip()
    if choice not in DECISION_CHOICES:
        valid = ", ".join(sorted(DECISION_CHOICES))
        raise ValueError(f"choice must be one of: {valid}")

    duration = payload.get("duration_minutes")
    duration_minutes = int(duration) if duration is not None else None
    if duration_minutes is not None and duration_minutes <= 0:
        raise ValueError("duration_minutes must be greater than zero.")

    recovery_duration = payload.get("recovery_duration_hours", 4)
    recovery_duration_hours = int(recovery_duration)
    if recovery_duration_hours <= 0:
        raise ValueError("recovery_duration_hours must be greater than zero.")

    return DecisionPayload(
        choice=choice,
        duration_minutes=duration_minutes,
        reason=_optional_str(payload, "reason") or "",
        followup_action=_optional_str(payload, "followup_action"),
        enter_recovery_mode=bool(payload.get("enter_recovery_mode", False)),
        recovery_duration_hours=recovery_duration_hours,
    )
