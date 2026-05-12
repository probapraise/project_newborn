from __future__ import annotations

import sqlite3
from datetime import datetime, time

FIXED_TYPES = {"work", "appointment", "fixed", "commute", "prep", "sleep", "meal", "medication"}


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", 1)
    return time(int(hour), int(minute))


def _contains_clock(start: str, end: str, current: time) -> bool:
    start_t = _parse_time(start)
    end_t = _parse_time(end)
    if start_t <= end_t:
        return start_t <= current < end_t
    return current >= start_t or current < end_t


def get_today_blocks(conn: sqlite3.Connection, date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM schedule_blocks
        WHERE date = ? AND status != 'cancelled'
        ORDER BY start_time, end_time, id
        """,
        (date,),
    ).fetchall()


def get_fixed_obligations(conn: sqlite3.Connection, date: str) -> list[sqlite3.Row]:
    rows = get_today_blocks(conn, date)
    return [row for row in rows if row["type"] in FIXED_TYPES or row["enforcement_level"] == "hard"]


def get_current_block(conn: sqlite3.Connection, now: datetime) -> sqlite3.Row | None:
    rows = get_today_blocks(conn, now.date().isoformat())
    current = now.time().replace(second=0, microsecond=0)
    for row in rows:
        if _contains_clock(row["start_time"], row["end_time"], current):
            return row
    return None


def get_next_blocks(conn: sqlite3.Connection, now: datetime, limit: int = 3) -> list[sqlite3.Row]:
    today = now.date().isoformat()
    current = now.time().strftime("%H:%M")
    return conn.execute(
        """
        SELECT * FROM schedule_blocks
        WHERE date = ? AND status != 'cancelled' AND start_time >= ?
        ORDER BY start_time, end_time, id
        LIMIT ?
        """,
        (today, current, limit),
    ).fetchall()


def get_next_tasks(conn: sqlite3.Connection, today: str, limit: int = 3) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM tasks
        WHERE status = 'pending' AND (due_date IS NULL OR due_date >= ?)
        ORDER BY
            CASE priority
                WHEN 'high' THEN 0
                WHEN 'medium' THEN 1
                WHEN 'low' THEN 2
                ELSE 3
            END,
            COALESCE(due_date, '9999-12-31'),
            id
        LIMIT ?
        """,
        (today, limit),
    ).fetchall()


def format_block(row: sqlite3.Row | None) -> str:
    if row is None:
        return "등록된 계획 블록 없음"
    return f"{row['start_time']}-{row['end_time']} {row['title']} ({row['type']}, {row['enforcement_level']})"
