from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .paths import db_path as default_db_path
from .paths import ensure_dirs, repo_root

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    enforcement_level TEXT NOT NULL DEFAULT 'normal',
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'planned'
);

CREATE INDEX IF NOT EXISTS idx_schedule_blocks_date
ON schedule_blocks(date, start_time, end_time);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'medium',
    estimated_minutes INTEGER,
    energy_level TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_due
ON tasks(status, due_date, priority);

CREATE TABLE IF NOT EXISTS activity_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    process_name TEXT,
    window_title TEXT,
    domain TEXT,
    classification TEXT,
    raw_limited_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_activity_events_timestamp
ON activity_events(timestamp);

CREATE TABLE IF NOT EXISTS intervention_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    activity_event_id INTEGER,
    schedule_block_id INTEGER,
    risk_level TEXT NOT NULL DEFAULT 'green',
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY(activity_event_id) REFERENCES activity_events(id),
    FOREIGN KEY(schedule_block_id) REFERENCES schedule_blocks(id)
);

CREATE INDEX IF NOT EXISTS idx_intervention_events_status
ON intervention_events(status, timestamp);

CREATE TABLE IF NOT EXISTS intervention_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    decision TEXT NOT NULL,
    category TEXT,
    duration_minutes INTEGER,
    user_text_summary TEXT,
    followup_action TEXT,
    FOREIGN KEY(event_id) REFERENCES intervention_events(id)
);

CREATE TABLE IF NOT EXISTS exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    category TEXT NOT NULL,
    reason TEXT,
    created_from_event_id INTEGER,
    FOREIGN KEY(created_from_event_id) REFERENCES intervention_events(id)
);

CREATE TABLE IF NOT EXISTS recovery_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT,
    reason TEXT,
    minimized_plan_json TEXT
);

CREATE TABLE IF NOT EXISTS pattern_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    evidence_summary TEXT NOT NULL,
    confidence TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rule_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    title TEXT NOT NULL,
    observed_pattern TEXT NOT NULL,
    proposed_change TEXT NOT NULL,
    risk TEXT,
    confidence TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);
"""

EVENT_LOGS = [
    "activity.jsonl",
    "interventions.jsonl",
    "exceptions.jsonl",
    "intervention_decisions.jsonl",
    "recovery_sessions.jsonl",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    root = repo_root()
    ensure_dirs(root)
    db_file = path or default_db_path(root)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_event_logs(root: Path | None = None) -> None:
    base = root or repo_root()
    events_dir = base / "data" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    for name in EVENT_LOGS:
        path = events_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")


def init_db(path: Path | None = None) -> Path:
    root = repo_root()
    ensure_dirs(root)
    ensure_event_logs(root)
    db_file = path or default_db_path(root)
    with connect(db_file) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.execute(
            """
            INSERT INTO meta(key, value, updated_at)
            VALUES('schema_version', '1', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (utc_now(),),
        )
        conn.commit()
    return db_file


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [row["name"] for row in rows]
