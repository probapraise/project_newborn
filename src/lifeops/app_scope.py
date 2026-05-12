"""Application monitoring scope for LifeOps.

The system intentionally watches only Chrome and Steam. All games are assumed to
enter through Steam, so Stage 2 must not maintain a broad game-process catalog.
"""

from __future__ import annotations

CHROME_PROCESSES = frozenset({"chrome.exe"})
STEAM_PROCESSES = frozenset({"steam.exe", "steamwebhelper.exe"})
MONITORED_PROCESSES = CHROME_PROCESSES | STEAM_PROCESSES

IGNORED_PROCESS_HINTS = frozenset(
    {
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "epicgameslauncher.exe",
        "riotclientservices.exe",
        "battle.net.exe",
        "goggalaxy.exe",
    }
)


def is_monitored_process(process_name: str | None) -> bool:
    if not process_name:
        return False
    return process_name.strip().lower() in MONITORED_PROCESSES


def classify_monitored_process(process_name: str | None) -> str:
    normalized = (process_name or "").strip().lower()
    if normalized in CHROME_PROCESSES:
        return "chrome"
    if normalized in STEAM_PROCESSES:
        return "steam"
    return "ignored"
