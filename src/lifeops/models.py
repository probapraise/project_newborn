from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScheduleBlock:
    id: int
    date: str
    start_time: str
    end_time: str
    type: str
    title: str
    enforcement_level: str
    source: str
    status: str


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    priority: str
    estimated_minutes: int | None
    energy_level: str | None
    due_date: str | None
    status: str


@dataclass(frozen=True)
class ActivitySnapshot:
    timestamp: str
    process_name: str
    window_title: str = ""
    domain: str | None = None
    classification: str = "ignored"
    source: str = "foreground_window"

    def limited_payload(self) -> dict[str, object]:
        payload = asdict(self)
        if len(self.window_title) > 240:
            payload["window_title"] = self.window_title[:237] + "..."
        return payload

    def identity_key(self) -> tuple[str, str, str | None, str]:
        return (
            self.process_name.lower(),
            self.window_title,
            self.domain,
            self.classification,
        )
