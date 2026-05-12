from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from lifeops.db import connect, init_db
from lifeops.intervention_self_check import cleanup_self_check_artifacts, run_self_check


class Stage2InterventionLoopSelfCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-loop-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        prompts = self.tmp / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        (prompts / "intervention_prompt.md").write_text(
            "event `{event_id}`\nblock `{current_block}`\nactivity `{detected_activity}`\nreason `{reason}`\n",
            encoding="utf-8",
        )
        init_db()

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def test_self_check_creates_prompt_and_records_decision(self) -> None:
        result = run_self_check(choice="return_now")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["decision"], "return_now")
        self.assertEqual(result["final_event_status"], "decided")
        self.assertEqual(result["cleanup"]["status"], "cleaned")
        self.assertEqual(result["cleanup"]["cancelled_schedule_blocks"], 1)
        self.assertTrue(Path(str(result["prompt_path"])).exists())
        with connect() as conn:
            decisions = conn.execute("SELECT COUNT(*) AS count FROM intervention_decisions").fetchone()
            exceptions = conn.execute("SELECT COUNT(*) AS count FROM exceptions").fetchone()
            blocks = conn.execute("SELECT status FROM schedule_blocks WHERE source = 'self_check'").fetchall()
        self.assertEqual(decisions["count"], 1)
        self.assertEqual(exceptions["count"], 0)
        self.assertEqual([row["status"] for row in blocks], ["cancelled"])

    def test_cleanup_only_cancels_existing_self_check_blocks(self) -> None:
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source)
                VALUES ('2026-05-12', '09:00', '10:00', 'work', 'LifeOps self-check focus block', 'normal', 'self_check')
                """
            )
            conn.commit()
        result = cleanup_self_check_artifacts()
        self.assertEqual(result["status"], "cleaned")
        self.assertEqual(result["cancelled_schedule_blocks"], 1)
        with connect() as conn:
            block = conn.execute("SELECT status FROM schedule_blocks WHERE source = 'self_check'").fetchone()
        self.assertEqual(block["status"], "cancelled")

    def test_self_check_can_exercise_exception_path(self) -> None:
        result = run_self_check(choice="intentional_rest", duration_minutes=1)
        self.assertEqual(result["decision"], "intentional_rest")
        self.assertIsNotNone(result["exception_id"])
        with connect() as conn:
            exception = conn.execute("SELECT category FROM exceptions WHERE id = ?", (result["exception_id"],)).fetchone()
        self.assertEqual(exception["category"], "intentional_rest")


if __name__ == "__main__":
    unittest.main()
