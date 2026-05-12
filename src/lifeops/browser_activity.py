"""Chrome activity helpers.

Stage 2 can only use foreground process and title text. Stage 4 may add a
Chrome extension for reliable domain-only reporting.
"""

from __future__ import annotations

import re

from .rulebook import classify_chrome_activity

_DOMAIN_RE = re.compile(r"\b(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.IGNORECASE)


def extract_domain_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = _DOMAIN_RE.search(text)
    if not match:
        return None
    return match.group(1).lower().rstrip("./")


def is_risky_chrome_activity(window_title: str | None, domain: str | None) -> bool:
    return classify_chrome_activity(window_title, domain).category == "distracting"


def is_known_aligned_chrome_activity(window_title: str | None, domain: str | None) -> bool:
    return classify_chrome_activity(window_title, domain).category == "aligned"
