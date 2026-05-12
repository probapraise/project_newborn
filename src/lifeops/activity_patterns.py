from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from .db import connect, utc_now
from .models import ActivitySnapshot
from .rulebook import learned_pattern_confidence, learned_pattern_min_count

ALIGNED_CATEGORIES = frozenset({"plan_aligned", "false_positive"})
DISTRACTING_CATEGORIES = frozenset({"return_to_plan", "intentional_rest"})


@dataclass(frozen=True)
class LearnedActivityJudgment:
    category: str
    pattern_key: str
    support_count: int
    confidence: float
    reason: str


def _normalize_title(title: str | None) -> str:
    value = (title or "").lower()
    value = re.sub(r"\s+-\s+(google )?chrome$", "", value).strip()
    parts = [part.strip() for part in value.split(" - ") if part.strip()]
    if len(parts) >= 2:
        value = parts[-1]
    value = re.sub(r"\s+", " ", value).strip()
    return value[:80]


def activity_pattern_key(snapshot: ActivitySnapshot) -> str:
    domain = (snapshot.domain or "").lower().removeprefix("www.")
    if domain:
        return f"domain:{domain}"
    title = _normalize_title(snapshot.window_title)
    if title:
        return f"title:{title}"
    return f"process:{snapshot.process_name.lower()}"


def _row_pattern_key(row: Any) -> str:
    snapshot = ActivitySnapshot(
        timestamp=str(row["timestamp"]),
        process_name=str(row["process_name"] or ""),
        window_title=str(row["window_title"] or ""),
        domain=row["domain"],
        classification=str(row["classification"] or "chrome"),
    )
    return activity_pattern_key(snapshot)


def _category_bucket(category: str | None) -> str | None:
    normalized = str(category or "")
    if normalized in ALIGNED_CATEGORIES:
        return "aligned"
    if normalized in DISTRACTING_CATEGORIES:
        return "distracting"
    return None


def learned_activity_judgment(snapshot: ActivitySnapshot, *, days: int = 30) -> LearnedActivityJudgment | None:
    key = activity_pattern_key(snapshot)
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    counts = {"aligned": 0, "distracting": 0}
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ae.timestamp, ae.process_name, ae.window_title, ae.domain, ae.classification, id.category
            FROM intervention_decisions id
            JOIN intervention_events ie ON ie.id = id.event_id
            JOIN activity_events ae ON ae.id = ie.activity_event_id
            WHERE ae.classification = 'chrome' AND id.timestamp >= ?
            ORDER BY id.timestamp DESC
            LIMIT 200
            """,
            (threshold,),
        ).fetchall()

    for row in rows:
        if _row_pattern_key(row) != key:
            continue
        bucket = _category_bucket(row["category"])
        if bucket:
            counts[bucket] += 1

    total = counts["aligned"] + counts["distracting"]
    min_count = learned_pattern_min_count()
    required_confidence = learned_pattern_confidence()
    if total < min_count:
        return None

    category = "aligned" if counts["aligned"] >= counts["distracting"] else "distracting"
    confidence = counts[category] / total
    if confidence < required_confidence:
        return None

    reason = (
        f"최근 {total}회 같은 패턴 결정 중 {counts[category]}회가 "
        f"{'계획에 맞음' if category == 'aligned' else '계획과 어긋남'}으로 기록되었습니다."
    )
    return LearnedActivityJudgment(
        category=category,
        pattern_key=key,
        support_count=total,
        confidence=confidence,
        reason=reason,
    )


def generate_activity_rule_proposals(*, days: int = 30, min_count: int | None = None) -> list[dict[str, object]]:
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    required_count = min_count or learned_pattern_min_count()
    required_confidence = learned_pattern_confidence()
    grouped: dict[str, dict[str, object]] = {}

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT ae.timestamp, ae.process_name, ae.window_title, ae.domain, ae.classification,
                   id.category, id.decision
            FROM intervention_decisions id
            JOIN intervention_events ie ON ie.id = id.event_id
            JOIN activity_events ae ON ae.id = ie.activity_event_id
            WHERE ae.classification = 'chrome' AND id.timestamp >= ?
            ORDER BY id.timestamp DESC
            LIMIT 500
            """,
            (threshold,),
        ).fetchall()

        for row in rows:
            key = _row_pattern_key(row)
            bucket = _category_bucket(row["category"])
            if bucket is None:
                continue
            item = grouped.setdefault(
                key,
                {
                    "pattern_key": key,
                    "window_title": row["window_title"] or "",
                    "domain": row["domain"] or "",
                    "aligned": 0,
                    "distracting": 0,
                },
            )
            item[bucket] = int(item[bucket]) + 1

        created: list[dict[str, object]] = []
        for item in grouped.values():
            aligned = int(item["aligned"])
            distracting = int(item["distracting"])
            total = aligned + distracting
            if total < required_count:
                continue
            category = "aligned" if aligned >= distracting else "distracting"
            confidence = (aligned if category == "aligned" else distracting) / total
            if confidence < required_confidence:
                continue

            observed = str(item["pattern_key"])
            existing = conn.execute(
                """
                SELECT id FROM rule_proposals
                WHERE observed_pattern = ? AND status = 'pending'
                LIMIT 1
                """,
                (observed,),
            ).fetchone()
            if existing is not None:
                continue

            title = f"Chrome {category} rule candidate: {observed}"
            proposed_change = (
                "config/activity_rules.toml의 [[chrome.rules]]에 "
                f"category='{category}' 규칙을 추가하는 후보입니다."
            )
            cursor = conn.execute(
                """
                INSERT INTO rule_proposals(
                    created_at, title, observed_pattern, proposed_change, risk, confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    utc_now(),
                    title,
                    observed,
                    proposed_change,
                    f"support={total}, aligned={aligned}, distracting={distracting}",
                    "high" if confidence >= 0.9 else "medium",
                ),
            )
            payload = {
                "id": int(cursor.lastrowid),
                "title": title,
                "observed_pattern": observed,
                "proposed_change": proposed_change,
                "confidence": confidence,
                "support_count": total,
                "category": category,
            }
            created.append(payload)
        conn.commit()
    return created
