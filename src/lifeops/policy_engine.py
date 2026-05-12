"""Deterministic activity policy for LifeOps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .app_scope import classify_monitored_process, is_monitored_process
from .models import ActivitySnapshot
from .rulebook import ActivityRuleMatch, classify_chrome_activity, classify_steam_activity

PROTECTED_BLOCK_TYPES = frozenset({"work", "appointment", "fixed", "commute", "prep", "sleep", "meal", "medication"})
REST_BLOCK_TYPES = frozenset({"rest", "break", "intentional_rest", "recovery", "leisure"})
RESEARCH_BLOCK_TYPES = frozenset({"research", "study", "reference", "learning"})


@dataclass(frozen=True)
class PolicyDecision:
    action: str
    reason: str
    risk_level: str = "green"
    rule_id: str = ""


def evaluate_stage1() -> PolicyDecision:
    return PolicyDecision(
        action="log_only",
        reason="Stage 1 placeholder: real activity policy starts in Stage 2.",
    )


def evaluate_process_scope(process_name: str | None) -> PolicyDecision:
    """Return the Stage 2 scope decision for a process name."""
    if not is_monitored_process(process_name):
        return PolicyDecision(
            action="ignore",
            reason="현재 감시 범위는 Chrome과 Steam으로 제한되어 있습니다.",
        )
    return PolicyDecision(
        action="log_only",
        reason=f"{classify_monitored_process(process_name)} scope candidate",
    )


def _value(block: Any, key: str, default: str = "") -> str:
    if block is None:
        return default
    if isinstance(block, dict):
        return str(block.get(key, default) or default).lower()
    try:
        return str(block[key] or default).lower()
    except (IndexError, KeyError, TypeError):
        return str(getattr(block, key, default) or default).lower()


def _is_protected_block(block: Any) -> bool:
    block_type = _value(block, "type")
    enforcement = _value(block, "enforcement_level")
    return block_type in PROTECTED_BLOCK_TYPES or enforcement in {"hard", "red"}


def _allows_recreation(block: Any) -> bool:
    block_type = _value(block, "type")
    title = _value(block, "title")
    return block_type in REST_BLOCK_TYPES or "휴식" in title or "rest" in title


def _allows_research(block: Any) -> bool:
    block_type = _value(block, "type")
    title = _value(block, "title")
    return block_type in RESEARCH_BLOCK_TYPES or "자료" in title or "research" in title


def _risk_for_block(block: Any) -> str:
    if _value(block, "type") == "sleep" or _value(block, "enforcement_level") in {"hard", "red"}:
        return "red"
    if _is_protected_block(block):
        return "yellow"
    return "green"


def _rule_reason(prefix: str, match: ActivityRuleMatch) -> str:
    if match.rule_id and match.rule_id != "unknown":
        return f"{prefix} ({match.rule_id}: {match.reason})"
    return prefix


def evaluate_activity(snapshot: ActivitySnapshot, current_block: Any = None) -> PolicyDecision:
    if snapshot.classification not in {"chrome", "steam"}:
        return PolicyDecision(
            action="ignore",
            reason="Chrome/Steam 범위 밖 프로세스입니다.",
        )

    if snapshot.classification == "steam":
        match = classify_steam_activity(snapshot.process_name)
        if _allows_recreation(current_block):
            return PolicyDecision("log_only", "Steam 활동이 휴식/회복 블록 안에 있습니다.", rule_id=match.rule_id)
        if current_block is None:
            return PolicyDecision("log_only", "Steam 활동이 감지되었지만 현재 계획 블록이 없습니다.", rule_id=match.rule_id)
        return PolicyDecision(
            action="intervene",
            reason=_rule_reason("현재 계획 블록 중 Steam 활동이 감지되었습니다.", match),
            risk_level=_risk_for_block(current_block),
            rule_id=match.rule_id,
        )

    if snapshot.classification == "chrome":
        match = classify_chrome_activity(snapshot.window_title, snapshot.domain, current_block)
        if match.category == "aligned":
            return PolicyDecision(
                "log_only",
                _rule_reason("룰북상 현재 계획에 맞는 Chrome 활동으로 기록합니다.", match),
                rule_id=match.rule_id,
            )
        if match.category == "distracting" and _allows_research(current_block):
            return PolicyDecision("log_only", "Chrome 활동이 자료 확인 블록 안에 있습니다.", rule_id=match.rule_id)
        if match.category == "distracting" and _allows_recreation(current_block):
            return PolicyDecision("log_only", "Chrome 활동이 휴식/회복 블록 안에 있습니다.", rule_id=match.rule_id)
        if match.category == "distracting" and current_block is None:
            return PolicyDecision(
                "log_only",
                _rule_reason("주의가 필요한 Chrome 활동이 감지되었지만 현재 계획 블록이 없습니다.", match),
                rule_id=match.rule_id,
            )
        if match.category == "distracting" and current_block is not None and not _allows_recreation(current_block):
            return PolicyDecision(
                action="intervene",
                reason=_rule_reason("현재 계획 블록 중 주의가 필요한 Chrome 활동이 감지되었습니다.", match),
                risk_level=_risk_for_block(current_block),
                rule_id=match.rule_id,
            )
        if current_block is not None and not _allows_recreation(current_block):
            return PolicyDecision(
                action="clarify",
                reason="룰북에 없는 Chrome 활동입니다. 현재 계획과 맞는 사용인지 확인이 필요합니다.",
                risk_level=_risk_for_block(current_block),
                rule_id="unknown_chrome",
            )
        if current_block is None:
            return PolicyDecision("log_only", "룰북에 없는 Chrome 활동이지만 현재 계획 블록이 없습니다.", rule_id="unknown_chrome")
        return PolicyDecision("log_only", "Chrome 활동을 범위 내 이벤트로 기록합니다.")

    return PolicyDecision("ignore", "Chrome/Steam 범위 밖 활동입니다.")
