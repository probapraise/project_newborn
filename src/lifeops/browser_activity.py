"""Chrome activity helpers.

Stage 2 can only use foreground process and title text. Stage 4 may add a
Chrome extension for reliable domain-only reporting.
"""

from __future__ import annotations

import re

RISKY_DOMAIN_HINTS = frozenset(
    {
        "dcinside.com",
        "youtube.com",
        "youtu.be",
        "twitch.tv",
        "reddit.com",
        "instagram.com",
        "x.com",
    }
)

RISKY_TITLE_HINTS = frozenset(
    {
        "dcinside",
        "디시인사이드",
        "마이너 갤러리",
        "youtube",
        "twitch",
        "reddit",
        "instagram",
        "x /",
        "twitter",
    }
)

_DOMAIN_RE = re.compile(r"\b(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.IGNORECASE)


def extract_domain_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = _DOMAIN_RE.search(text)
    if not match:
        return None
    return match.group(1).lower().rstrip("./")


def is_risky_chrome_activity(window_title: str | None, domain: str | None) -> bool:
    normalized_domain = (domain or "").lower()
    if normalized_domain in RISKY_DOMAIN_HINTS:
        return True
    title = (window_title or "").lower()
    return any(hint in title for hint in RISKY_TITLE_HINTS)
