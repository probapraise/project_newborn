from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date as Date
from datetime import datetime, timezone
from pathlib import Path

from lifeops.daily_summary import build_daily_summary, render_daily_summary, write_daily_summary
from lifeops.db import connect, init_db


class Stage3DailySummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-daily-summary-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()
        self.day = Date(2026, 5, 12)
        self.timestamp = datetime(2026, 5, 12, 1, 0, tzinfo=timezone.utc).isoformat(timespec="seconds")
        self._insert_sample_day()

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def _insert_sample_day(self) -> None:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO activity_events(timestamp, process_name, window_title, classification, raw_limited_json)
                VALUES (?, 'steam-launched-app', 'Sample Game', 'steam', '{}')
                """,
                (self.timestamp,),
            )
            conn.execute(
                """
                INSERT INTO intervention_events(timestamp, activity_event_id, risk_level, reason, status)
                VALUES (?, 1, 'yellow', 'sample mismatch', 'decided')
                """,
                (self.timestamp,),
            )
            conn.execute(
                """
                INSERT INTO intervention_decisions(event_id, timestamp, decision, category, duration_minutes, followup_action)
                VALUES (1, ?, 'fatigue', 'fatigue', 30, 'create_fatigue_exception')
                """,
                (self.timestamp,),
            )
            conn.execute(
                """
                INSERT INTO exceptions(start_time, end_time, category, reason, created_from_event_id)
                VALUES (?, ?, 'fatigue', 'sample fatigue', 1)
                """,
                (self.timestamp, datetime(2026, 5, 12, 1, 30, tzinfo=timezone.utc).isoformat(timespec="seconds")),
            )
            conn.execute(
                """
                INSERT INTO recovery_sessions(start_time, end_time, reason, minimized_plan_json)
                VALUES ('2026-05-12T10:00:00+09:00', '2026-05-12T12:00:00+09:00', 'sample recovery', '{}')
                """
            )
            conn.execute(
                """
                INSERT INTO tasks(title, priority, estimated_minutes, due_date, status)
                VALUES ('sample pending task', 'high', 30, '2026-05-12', 'pending')
                """
            )
            conn.execute(
                """
                INSERT INTO tasks(title, priority, estimated_minutes, due_date, status)
                VALUES ('sample deferred task', 'low', 30, '2026-05-12', 'deferred_recovery')
                """
            )
            conn.commit()

    def test_build_daily_summary_counts_operational_signals(self) -> None:
        summary = build_daily_summary(day=self.day)
        self.assertEqual(summary["activity_count"], 1)
        self.assertEqual(summary["intervention_count"], 1)
        self.assertEqual(summary["decision_count"], 1)
        self.assertEqual(summary["exception_count"], 1)
        self.assertEqual(summary["recovery_count"], 1)
        self.assertEqual(summary["pending_tasks_due"], 1)
        self.assertEqual(summary["deferred_tasks"], 1)
        self.assertEqual(summary["decision_categories"], {"fatigue": 1})
        self.assertEqual(summary["exception_categories"], {"fatigue": 1})

    def test_render_daily_summary_is_shame_safe_and_readable(self) -> None:
        text = render_daily_summary(build_daily_summary(day=self.day))
        self.assertIn("## 운영 요약", text)
        self.assertIn("감지 활동 1건", text)
        self.assertIn("회복 모드 1회", text)
        self.assertIn("fatigue=1", text)
        self.assertIn("내일 첫 행동", text)
        for forbidden in ["실패", "위반", "벌점", "의지 부족", "게으름"]:
            self.assertNotIn(forbidden, text)

    def test_write_daily_summary_writes_markdown(self) -> None:
        output = self.tmp / "summary.md"
        path = write_daily_summary(output, day=self.day)
        self.assertEqual(path, output)
        self.assertTrue(path.exists())
        self.assertIn("Daily Summary 2026-05-12", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()