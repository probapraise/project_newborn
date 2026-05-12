from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.activity_patterns import generate_activity_rule_proposals, learned_activity_judgment
from lifeops.activity_watcher import process_snapshot
from lifeops.db import connect, init_db, utc_now
from lifeops.models import ActivitySnapshot

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class ActivityPatternTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-patterns-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()
        now = datetime.now(DEFAULT_TZ)
        start = (now - timedelta(hours=1)).strftime("%H:%M")
        end = (now + timedelta(hours=1)).strftime("%H:%M")
        with connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level)
                VALUES (?, ?, ?, 'work', 'focus work', 'normal')
                """,
                (now.date().isoformat(), start, end),
            )
            self.block_id = int(cursor.lastrowid)
            conn.commit()

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def _insert_historical_decision(self, *, title: str, decision: str, category: str) -> None:
        timestamp = utc_now()
        with connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO activity_events(timestamp, process_name, window_title, domain, classification, raw_limited_json)
                VALUES (?, 'chrome.exe', ?, NULL, 'chrome', '{}')
                """,
                (timestamp, title),
            )
            activity_id = int(cursor.lastrowid)
            event_cursor = conn.execute(
                """
                INSERT INTO intervention_events(timestamp, activity_event_id, schedule_block_id, risk_level, reason, status)
                VALUES (?, ?, ?, 'yellow', 'historical clarification', 'decided')
                """,
                (timestamp, activity_id, self.block_id),
            )
            event_id = int(event_cursor.lastrowid)
            conn.execute(
                """
                INSERT INTO intervention_decisions(event_id, timestamp, decision, category, user_text_summary, followup_action)
                VALUES (?, ?, ?, ?, '', '')
                """,
                (event_id, timestamp, decision, category),
            )
            conn.commit()

    def test_learned_aligned_pattern_suppresses_future_clarification(self) -> None:
        for _ in range(2):
            self._insert_historical_decision(
                title="Unknown Research Site - Chrome",
                decision="plan_aligned",
                category="plan_aligned",
            )
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="chrome.exe",
            window_title="Unknown Research Site - Chrome",
            classification="chrome",
        )
        learned = learned_activity_judgment(snapshot)
        self.assertIsNotNone(learned)
        self.assertEqual(learned.category, "aligned")

        activity_id, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "log_only")
        self.assertIn("반복 결정 패턴상", decision.reason)
        self.assertIsNotNone(activity_id)
        with connect() as conn:
            pending = conn.execute("SELECT COUNT(*) AS count FROM intervention_events WHERE status = 'pending'").fetchone()
        self.assertEqual(pending["count"], 0)

    def test_activity_rule_proposal_is_created_from_consistent_decisions(self) -> None:
        for _ in range(2):
            self._insert_historical_decision(
                title="Unknown Forum - Chrome",
                decision="return_now",
                category="return_to_plan",
            )
        proposals = generate_activity_rule_proposals(days=30)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["category"], "distracting")
        with connect() as conn:
            row = conn.execute("SELECT title, observed_pattern, confidence FROM rule_proposals").fetchone()
        self.assertIn("distracting", row["title"])
        self.assertIn("unknown forum", row["observed_pattern"])


if __name__ == "__main__":
    unittest.main()
