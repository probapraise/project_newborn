from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.activity_watcher import process_snapshot
from lifeops.db import connect, init_db, utc_now
from lifeops.cli import cmd_record_decision
from lifeops.decision_logging import normalize_decision, record_intervention_decision
from lifeops.models import ActivitySnapshot

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class Stage2DecisionLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-decisions-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()
        self._insert_current_work_block()
        self._create_pending_event()

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
                VALUES (?, ?, ?, 'work', 'focus work', 'normal')
                """,
                (now.date().isoformat(), start, end),
            )
            conn.commit()

    def _create_pending_event(self) -> None:
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="steam-launched-app",
            window_title="Steam Game",
            classification="steam",
        )
        _, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "intervene")

    def _insert_current_optional_block(self) -> int:
        now = datetime.now(DEFAULT_TZ)
        start = (now - timedelta(minutes=5)).strftime("%H:%M")
        end = (now + timedelta(minutes=30)).strftime("%H:%M")
        with connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level)
                VALUES (?, ?, ?, 'study', 'optional review', 'normal')
                """,
                (now.date().isoformat(), start, end),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def test_aliases_normalize_to_canonical_choices(self) -> None:
        self.assertEqual(normalize_decision("1").code, "return_now")
        self.assertEqual(normalize_decision("aligned").code, "plan_aligned")
        self.assertEqual(normalize_decision("false-positive").code, "false_positive")
        self.assertEqual(normalize_decision("sensory overload").code, "overload")

    def test_return_now_records_decision_without_exception(self) -> None:
        payload = record_intervention_decision(1, "return_now", reason="back to work")
        self.assertEqual(payload["decision"], "return_now")
        self.assertEqual(payload["category"], "return_to_plan")
        self.assertIsNone(payload["exception_id"])
        with connect() as conn:
            event = conn.execute("SELECT status FROM intervention_events WHERE id = 1").fetchone()
            decisions = conn.execute("SELECT COUNT(*) AS count FROM intervention_decisions").fetchone()
            exceptions = conn.execute("SELECT COUNT(*) AS count FROM exceptions").fetchone()
        self.assertEqual(event["status"], "decided")
        self.assertEqual(decisions["count"], 1)
        self.assertEqual(exceptions["count"], 0)
        log_text = (self.tmp / "data" / "events" / "intervention_decisions.jsonl").read_text(encoding="utf-8")
        self.assertIn("return_now", log_text)

    def test_plan_aligned_records_learnable_decision(self) -> None:
        payload = record_intervention_decision(1, "plan_aligned", reason="research for current task")
        self.assertEqual(payload["decision"], "plan_aligned")
        self.assertEqual(payload["category"], "plan_aligned")
        self.assertEqual(payload["event_status"], "aligned")
        with connect() as conn:
            event = conn.execute("SELECT status FROM intervention_events WHERE id = 1").fetchone()
        self.assertEqual(event["status"], "aligned")

    def test_intentional_rest_creates_exception(self) -> None:
        payload = record_intervention_decision(1, "intentional_rest", duration_minutes=20)
        self.assertEqual(payload["category"], "intentional_rest")
        self.assertEqual(payload["duration_minutes"], 20)
        self.assertIsNotNone(payload["exception_id"])
        with connect() as conn:
            exception = conn.execute("SELECT * FROM exceptions WHERE id = ?", (payload["exception_id"],)).fetchone()
        self.assertEqual(exception["category"], "intentional_rest")
        log_text = (self.tmp / "data" / "events" / "exceptions.jsonl").read_text(encoding="utf-8")
        self.assertIn("intentional_rest", log_text)

    def test_false_positive_marks_event_without_exception(self) -> None:
        payload = record_intervention_decision(1, "false_positive")
        self.assertEqual(payload["event_status"], "false_positive")
        with connect() as conn:
            event = conn.execute("SELECT status FROM intervention_events WHERE id = 1").fetchone()
            exceptions = conn.execute("SELECT COUNT(*) AS count FROM exceptions").fetchone()
        self.assertEqual(event["status"], "false_positive")
        self.assertEqual(exceptions["count"], 0)

    def test_duplicate_decision_is_rejected(self) -> None:
        record_intervention_decision(1, "return_now")
        with self.assertRaises(ValueError):
            record_intervention_decision(1, "false_positive")

    def test_cli_rejects_recovery_mode_for_return_now(self) -> None:
        args = SimpleNamespace(
            event_id=1,
            choice="return_now",
            decision=None,
            category=None,
            reason="back to work",
            duration_minutes=None,
            followup_action=None,
            enter_recovery_mode=True,
            recovery_duration_hours=2,
            recovery_output=None,
            recovery_dry_run=False,
        )
        self.assertEqual(cmd_record_decision(args), 2)
        with connect() as conn:
            decisions = conn.execute("SELECT COUNT(*) AS count FROM intervention_decisions").fetchone()
            recovery_sessions = conn.execute("SELECT COUNT(*) AS count FROM recovery_sessions").fetchone()
        self.assertEqual(decisions["count"], 0)
        self.assertEqual(recovery_sessions["count"], 0)

    def test_cli_decision_can_enter_recovery_mode(self) -> None:
        optional_block = self._insert_current_optional_block()
        args = SimpleNamespace(
            event_id=1,
            choice="fatigue",
            decision=None,
            category=None,
            reason="too tired to continue normally",
            duration_minutes=30,
            followup_action=None,
            enter_recovery_mode=True,
            recovery_duration_hours=2,
            recovery_output=None,
            recovery_dry_run=False,
        )
        self.assertEqual(cmd_record_decision(args), 0)
        with connect() as conn:
            block = conn.execute("SELECT status FROM schedule_blocks WHERE id = ?", (optional_block,)).fetchone()
            recovery_sessions = conn.execute("SELECT COUNT(*) AS count FROM recovery_sessions").fetchone()
            decisions = conn.execute("SELECT COUNT(*) AS count FROM intervention_decisions").fetchone()
            exceptions = conn.execute("SELECT COUNT(*) AS count FROM exceptions").fetchone()
        self.assertEqual(block["status"], "cancelled")
        self.assertEqual(recovery_sessions["count"], 1)
        self.assertEqual(decisions["count"], 1)
        self.assertEqual(exceptions["count"], 1)


if __name__ == "__main__":
    unittest.main()
