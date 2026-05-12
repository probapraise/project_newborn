from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.activity_watcher import process_snapshot
from lifeops.db import connect, init_db, utc_now
from lifeops.event_dispatcher import dispatch_next_event, pending_count
from lifeops.models import ActivitySnapshot

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class Stage2DispatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-dispatcher-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        prompts = self.tmp / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        (prompts / "intervention_prompt.md").write_text(
            "event `{event_id}`\n현재 계획: `{current_block}`\n현재 감지된 활동: `{detected_activity}`\n상태: `{risk_level}`, `{time_context}`, `{recent_interventions}`\nreason: `{reason}`\n",
            encoding="utf-8",
        )
        init_db()
        self._insert_current_work_block()

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

    def _create_pending_event(self) -> None:
        snapshot = ActivitySnapshot(
            timestamp=utc_now(),
            process_name="steam-launched-app",
            window_title="Steam Game",
            classification="steam",
        )
        _, decision = process_snapshot(snapshot)
        self.assertEqual(decision.action, "intervene")

    def test_dispatch_next_event_renders_prompt_and_marks_dispatched(self) -> None:
        self._create_pending_event()
        result = dispatch_next_event(launch=False, mark_dispatched=True)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.status, "dispatched")
        self.assertTrue(result.prompt_path.exists())
        text = result.prompt_path.read_text(encoding="utf-8")
        self.assertIn("event `1`", text)
        self.assertIn("Steam Game", text)
        self.assertIn("record-decision --event-id 1", text)
        with connect() as conn:
            row = conn.execute("SELECT status FROM intervention_events WHERE id = 1").fetchone()
        self.assertEqual(row["status"], "dispatched")

    def test_dry_dispatch_restores_pending_status(self) -> None:
        self._create_pending_event()
        result = dispatch_next_event(launch=False, mark_dispatched=False)
        self.assertIsNotNone(result)
        self.assertEqual(pending_count(), 1)
        with connect() as conn:
            row = conn.execute("SELECT status FROM intervention_events WHERE id = 1").fetchone()
        self.assertEqual(row["status"], "pending")

    def test_no_pending_event_returns_none(self) -> None:
        self.assertIsNone(dispatch_next_event(launch=False, mark_dispatched=True))


if __name__ == "__main__":
    unittest.main()