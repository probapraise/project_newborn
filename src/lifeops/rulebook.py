from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
import tomllib

from .paths import repo_root

DEFAULT_ACTIVITY_RULES: dict[str, Any] = {
    "version": 1,
    "unknown_chrome_mode": "clarify_in_protected_block",
    "learned_pattern_min_count": 2,
    "learned_pattern_confidence": 0.80,
    "chrome": {
        "rules": [
            {
                "id": "work_reference_default",
                "category": "aligned",
                "domains": [
                    "github.com",
                    "docs.python.org",
                    "developer.mozilla.org",
                    "stackoverflow.com",
                    "chatgpt.com",
                    "chat.openai.com",
                ],
                "title_contains": [
                    "github",
                    "python docs",
                    "mdn",
                    "stack overflow",
                    "openai",
                    "codex",
                ],
                "allowed_block_types": ["work", "research", "study", "reference", "learning"],
                "reason": "작업/자료 확인 후보입니다.",
            },
            {
                "id": "social_video_community_default",
                "category": "distracting",
                "domains": [
                    "youtube.com",
                    "youtu.be",
                    "twitch.tv",
                    "reddit.com",
                    "instagram.com",
                    "x.com",
                    "dcinside.com",
                ],
                "title_contains": [
                    "youtube",
                    "twitch",
                    "reddit",
                    "instagram",
                    "twitter",
                    "x /",
                    "dcinside",
                    "디시인사이드",
                    "마이너 갤러리",
                ],
                "reason": "영상/SNS/커뮤니티 활동 후보입니다.",
            },
        ]
    },
    "steam": {
        "rules": [
            {
                "id": "steam_default",
                "category": "distracting",
                "processes": ["steam.exe", "steamwebhelper.exe", "steam-launched-app"],
                "reason": "Steam 활동입니다.",
            }
        ]
    },
}


@dataclass(frozen=True)
class ActivityRuleMatch:
    category: str
    rule_id: str = "unknown"
    reason: str = "룰북에 없는 활동입니다."


def _config_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "config" / "activity_rules.toml"


@lru_cache(maxsize=8)
def _load_activity_rules(path_text: str, mtime_ns: int) -> dict[str, Any]:
    path = Path(path_text)
    if not path.exists():
        return DEFAULT_ACTIVITY_RULES
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_activity_rules(root: Path | None = None) -> dict[str, Any]:
    path = _config_path(root).resolve()
    mtime_ns = path.stat().st_mtime_ns if path.exists() else 0
    return _load_activity_rules(str(path), mtime_ns)


def clear_activity_rule_cache() -> None:
    _load_activity_rules.cache_clear()


def learned_pattern_min_count(root: Path | None = None) -> int:
    rules = load_activity_rules(root)
    return int(rules.get("learned_pattern_min_count", 2))


def learned_pattern_confidence(root: Path | None = None) -> float:
    rules = load_activity_rules(root)
    return float(rules.get("learned_pattern_confidence", 0.80))


def _block_type(block: Any) -> str:
    if block is None:
        return ""
    if isinstance(block, dict):
        return str(block.get("type") or "").lower()
    try:
        return str(block["type"] or "").lower()
    except (IndexError, KeyError, TypeError):
        return str(getattr(block, "type", "") or "").lower()


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).lower() for item in value]
    return [str(value).lower()]


def _domain_matches(domain: str | None, candidates: list[str]) -> bool:
    normalized = (domain or "").lower().removeprefix("www.")
    if not normalized:
        return False
    for candidate in candidates:
        item = candidate.lower().removeprefix("www.")
        if normalized == item or normalized.endswith("." + item):
            return True
    return False


def _title_matches(window_title: str | None, candidates: list[str]) -> bool:
    title = (window_title or "").lower()
    return any(candidate in title for candidate in candidates)


def _block_matches(block: Any, allowed_block_types: list[str]) -> bool:
    if not allowed_block_types:
        return True
    return _block_type(block) in {item.lower() for item in allowed_block_types}


def classify_chrome_activity(
    window_title: str | None,
    domain: str | None,
    current_block: Any = None,
    *,
    root: Path | None = None,
) -> ActivityRuleMatch:
    rules = load_activity_rules(root).get("chrome", {}).get("rules", [])
    for rule in rules:
        domains = _list(rule.get("domains"))
        titles = _list(rule.get("title_contains"))
        if not (_domain_matches(domain, domains) or _title_matches(window_title, titles)):
            continue
        allowed_block_types = _list(rule.get("allowed_block_types"))
        if not _block_matches(current_block, allowed_block_types):
            continue
        return ActivityRuleMatch(
            category=str(rule.get("category") or "unknown"),
            rule_id=str(rule.get("id") or "unnamed_rule"),
            reason=str(rule.get("reason") or "룰북 규칙과 일치합니다."),
        )
    return ActivityRuleMatch(category="unknown")


def classify_steam_activity(process_name: str | None, *, root: Path | None = None) -> ActivityRuleMatch:
    process = (process_name or "").lower()
    rules = load_activity_rules(root).get("steam", {}).get("rules", [])
    for rule in rules:
        processes = _list(rule.get("processes"))
        if process in processes:
            return ActivityRuleMatch(
                category=str(rule.get("category") or "distracting"),
                rule_id=str(rule.get("id") or "steam_rule"),
                reason=str(rule.get("reason") or "Steam 활동입니다."),
            )
    return ActivityRuleMatch(category="distracting", rule_id="steam_default", reason="Steam 활동입니다.")
