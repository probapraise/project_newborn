from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.db import connect, init_db
from lifeops.recovery import enter_recovery_mode

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class Stage3RecoveryModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-recovery-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()
        self.now = datetime(2026, 5, 12, 9, 0, tzinfo=DEFAULT_TZ)

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def _clock(self, minutes: int) -> str:
        return (self.now + timedelta(minutes=minutes)).strftime("%H:%M")

    def _insert_block(
        self,
        *,
        title: str,
        block_type: str,
        start_offset: int,
        end_offset: int,
        enforcement: str = "normal",
        source: str = "manual",
    ) -> int:
        today = self.now.date().isoformat()
        with connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (today, self._clock(start_offset), self._clock(end_offset), block_type, title, enforcement, source),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def _insert_task(self, *, title: str, priority: str) -> int:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tasks(title, priority, estimated_minutes, status) VALUES (?, ?, 30, 'pending')",
                (title, priority),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def test_enter_recovery_mode_defers_nonessential_items(self) -> None:
        soft_block = self._insert_block(title="optional study", block_type="study", start_offset=10, end_offset=40)
        meal_block = self._insert_block(title="dinner", block_type="meal", start_offset=45, end_offset=75)
        high_task = self._insert_task(title="submit essential form", priority="high")
        low_task = self._insert_task(title="nice to have cleanup", priority="low")

        result = enter_recovery_mode(reason="fatigue", duration_hours=2, now=self.now)

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.session_id)
        self.assertTrue(result.prompt_path.exists())
        self.assertEqual(result.plan["day_status"], "adjusted_not_failed")
        self.assertEqual(result.plan["deferred_blocks"][0]["id"], soft_block)
        with connect() as conn:
            soft = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (soft_block,)).fetchone()
            meal = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (meal_block,)).fetchone()
            high = conn.execute("SELECT status FROM tasks WHERE id = ?", (high_task,)).fetchone()
            low = conn.execute("SELECT status FROM tasks WHERE id = ?", (low_task,)).fetchone()
            recovery_sessions = conn.execute("SELECT COUNT(*) AS count FROM recovery_sessions").fetchone()
        self.assertEqual(soft["status"], "cancelled")
        self.assertEqual(meal["status"], "planned")
        self.assertEqual(high["status"], "pending")
        self.assertEqual(low["status"], "deferred_recovery")
        self.assertEqual(recovery_sessions["count"], 1)

    def test_recovery_mode_ignores_self_check_blocks(self) -> None:
        self_check_block = self._insert_block(
            title="LifeOps self-check focus block",
            block_type="work",
            start_offset=10,
            end_offset=40,
            source="self_check",
        )
        result = enter_recovery_mode(reason="fatigue", duration_hours=1, apply=False, now=self.now)
        protected_ids = {block["id"] for block in result.plan["protected_blocks"]}
        deferred_ids = {block["id"] for block in result.plan["deferred_blocks"]}
        self.assertNotIn(self_check_block, protected_ids)
        self.assertNotIn(self_check_block, deferred_ids)
        self.assertNotIn("LifeOps self-check", result.plan["next_action"])

    def test_dry_run_does_not_mutate_plan(self) -> None:
        soft_block = self._insert_block(title="optional study", block_type="study", start_offset=10, end_offset=40)
        result = enter_recovery_mode(reason="overload", duration_hours=1, apply=False, now=self.now)
        self.assertFalse(result.applied)
        self.assertIsNone(result.session_id)
        with connect() as conn:
            soft = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (soft_block,)).fetchone()
            recovery_sessions = conn.execute("SELECT COUNT(*) AS count FROM recovery_sessions").fetchone()
        self.assertEqual(soft["status"], "planned")
        self.assertEqual(recovery_sessions["count"], 0)


if __name__ == "__main__":
    unittest.main()
