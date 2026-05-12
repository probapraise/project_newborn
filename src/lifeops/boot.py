from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import connect, init_db
from .paths import default_output_path, repo_root
from .schedule_engine import (
    format_block,
    get_current_block,
    get_fixed_obligations,
    get_next_blocks,
    get_next_tasks,
)

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _format_rows_as_blocks(rows: list[sqlite3.Row]) -> list[str]:
    return [format_block(row) for row in rows]


def _next_actions(conn: sqlite3.Connection, now: datetime) -> list[str]:
    today = now.date().isoformat()
    tasks = get_next_tasks(conn, today, limit=3)
    if tasks:
        return [f"{row['title']} ({row['priority']})" for row in tasks]

    next_blocks = get_next_blocks(conn, now, limit=3)
    if next_blocks:
        return [format_block(row) for row in next_blocks]

    return [
        "data/weekly/current_input.md에 이번 주 근무와 특수 일정을 적기",
        "오늘의 고정 일정이 있으면 schedule_blocks에 추가하기",
        "첫 보호 블록과 완전 휴식일 후보를 정하기",
    ]


def _high_risk_windows(conn: sqlite3.Connection, now: datetime) -> list[str]:
    rows = get_fixed_obligations(conn, now.date().isoformat())
    windows = []
    for row in rows:
        if row["type"] in {"work", "prep", "commute", "sleep"} or row["enforcement_level"] in {"hard", "red"}:
            windows.append(format_block(row))
    if not windows:
        windows.append("기본 수면 보호: 23:30-07:00")
    return windows


def _pending_proposals(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT id, title, confidence FROM rule_proposals
        WHERE status = 'pending'
        ORDER BY created_at, id
        LIMIT 3
        """
    ).fetchall()
    return [f"#{row['id']} {row['title']} ({row['confidence']})" for row in rows]


def _weekly_input_status(text: str) -> list[str]:
    required = [
        "이번 주 근무",
        "특수 일정",
        "우선순위",
        "피로 예상",
        "완전 휴식일 후보",
        "이번 주 차단 강화 시간대",
    ]
    missing = []
    for key in required:
        marker = f"- {key}:"
        line = next((item for item in text.splitlines() if item.strip().startswith(marker)), "")
        if not line or line.strip() == marker:
            missing.append(f"{key}: 확인 필요")
    return missing


def build_boot_context(now: datetime | None = None, db_file: Path | None = None) -> dict[str, object]:
    root = repo_root()
    init_db(db_file)
    current_time = now or datetime.now(DEFAULT_TZ)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=DEFAULT_TZ)

    with connect(db_file) as conn:
        today = current_time.date().isoformat()
        fixed = _format_rows_as_blocks(get_fixed_obligations(conn, today))
        current_block = format_block(get_current_block(conn, current_time))
        next_actions = _next_actions(conn, current_time)
        high_risk = _high_risk_windows(conn, current_time)
        proposals = _pending_proposals(conn)

    weekly_input = _read_text(root / "data" / "weekly" / "current_input.md")
    confirmation_needed = _weekly_input_status(weekly_input)

    return {
        "generated_at": current_time.isoformat(timespec="minutes"),
        "date": current_time.date().isoformat(),
        "fixed_obligations": fixed or ["등록된 고정 일정 없음"],
        "current_block": current_block,
        "next_actions": next_actions[:3],
        "high_risk_windows": high_risk,
        "pending_rule_proposals": proposals or ["승인 대기 중인 시스템 조정 제안 없음"],
        "weekly_input_confirmation_needed": confirmation_needed,
    }


def _render_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_boot_context_markdown(context: dict[str, object]) -> str:
    return "\n".join(
        [
            "# LifeOps Boot Briefing Context",
            "",
            f"generated_at: {context['generated_at']}",
            f"date: {context['date']}",
            "",
            "## 오늘의 고정 일정",
            _render_list(context["fixed_obligations"]),
            "",
            "## 현재 계획 블록",
            str(context["current_block"]),
            "",
            "## 다음 3개 행동",
            _render_list(context["next_actions"]),
            "",
            "## 알려진 고위험 시간대",
            _render_list(context["high_risk_windows"]),
            "",
            "## 승인 대기 중인 시스템 조정 제안",
            _render_list(context["pending_rule_proposals"]),
            "",
            "## 확인 필요",
            _render_list(context["weekly_input_confirmation_needed"] or ["현재 확인 필요 항목 없음"]),
            "",
        ]
    )


def render_boot_prompt(context_markdown: str) -> str:
    return "\n".join(
        [
            "You are LifeOps Operator. Read AGENTS.md and current LifeOps state. Give the user a concise boot briefing.",
            "",
            "규칙:",
            "- 한국어로 답한다.",
            "- 평가, 죄책감, 실패 프레임 없이 말한다.",
            "- 넓은 자기성찰 질문을 하지 않는다.",
            "- 마지막 질문은 하나만 사용한다.",
            "",
            context_markdown,
            "마지막 질문:",
            "오늘 상태를 하나만 고르세요: 정상 / 피곤함 / 과부하 / 아픔 / 일정 변경 있음",
        ]
    )


def write_boot_context(output: Path | None = None) -> Path:
    path = output or default_output_path("boot_briefing_context.md")
    context = build_boot_context()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_boot_context_markdown(context), encoding="utf-8")
    return path


def write_boot_prompt(output: Path | None = None) -> Path:
    context = render_boot_context_markdown(build_boot_context())
    prompt = render_boot_prompt(context)
    path = output or default_output_path("boot_prompt.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")
    return path


