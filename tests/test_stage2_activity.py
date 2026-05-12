from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.activity_watcher import process_snapshot
from lifeops.browser_activity import extract_domain_from_text, is_risky_chrome_activity
from lifeops.db import connect, init_db, utc_now
from lifeops.models import ActivitySnapshot
from lifeops.policy_engine import evaluate_activity

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class Stage2ActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-stage2-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def _insert_current_work_block(self) -> None:
        now = datetime.now(DEFAULT_TZ)
        start = (now - timedelta(hours=1)).strftime("%H:%M")
        end = (now + timedelta(hours=1)).strftime("%H:%M")
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level)
                VALUES (?, ?, ?, 'work', '집중 작업', 'normal')
                """,
                (now.date().isoformat(), start, end),
            )
            conn.commit()

    def test_chrome_domain_helpers_are_domain_only(self) -> None:
        self.assertEqual(extract_domain_from_text("https://www.youtube.com/watch"), "youtube.com")
        self.assertTrue(is_risky_chrome_activity("YouTube - Google Chrome", None))
        self.assertTrue(is_risky_chrome_activity("붕괴 스타레일 마이너 갤러리 - Chrome", None))
        self.assertFalse(is_risky_chrome_activity("Python docs - Google Chrome", None))

    def test_policy_ignores_unmonitored_process(self) -> None:
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="game.exe",
            window_title="Example",
            classification="ignored",
        )
        decision = evaluate_activity(snapshot, None)
        self.assertEqual(decision.action, "ignore")

    def test_steam_during_work_creates_pending_intervention(self) -> None:
        self._insert_current_work_block()
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="steam-launched-app",
            window_title="Steam Game",
            classification="steam",
        )
        activity_id, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "intervene")
        self.assertIsNotNone(activity_id)
        with connect() as conn:
            activity_count = conn.execute("SELECT COUNT(*) AS count FROM activity_events").fetchone()["count"]
            pending_count = conn.execute("SELECT COUNT(*) AS count FROM intervention_events WHERE status = 'pending'").fetchone()["count"]
        self.assertEqual(activity_count, 1)
        self.assertEqual(pending_count, 1)

    def test_korean_community_title_during_work_creates_pending_intervention(self) -> None:
        self._insert_current_work_block()
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="chrome.exe",
            window_title="왜 다들 에뵝이 저주해.. - 붕괴 스타레일 마이너 갤러리 - Chrome",
            classification="chrome",
        )
        activity_id, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "intervene")
        self.assertIsNotNone(activity_id)
        with connect() as conn:
            pending_count = conn.execute("SELECT COUNT(*) AS count FROM intervention_events WHERE status = 'pending'").fetchone()["count"]
        self.assertEqual(pending_count, 1)

    def test_risky_chrome_without_current_block_explains_log_only(self) -> None:
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="chrome.exe",
            window_title="왜 다들 에뵝이 저주해.. - 붕괴 스타레일 마이너 갤러리 - Chrome",
            classification="chrome",
        )
        activity_id, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "log_only")
        self.assertIn("현재 계획 블록이 없습니다", decision.reason)
        self.assertIsNotNone(activity_id)
        with connect() as conn:
            pending_count = conn.execute("SELECT COUNT(*) AS count FROM intervention_events WHERE status = 'pending'").fetchone()["count"]
        self.assertEqual(pending_count, 0)

    def test_ignored_process_is_not_recorded(self) -> None:
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="msedge.exe",
            window_title="Ignored",
            classification="ignored",
        )
        activity_id, decision = process_snapshot(snapshot)
        self.assertIsNone(activity_id)
        self.assertEqual(decision.action, "ignore")
        with connect() as conn:
            activity_count = conn.execute("SELECT COUNT(*) AS count FROM activity_events").fetchone()["count"]
        self.assertEqual(activity_count, 0)


if __name__ == "__main__":
    unittest.main()
