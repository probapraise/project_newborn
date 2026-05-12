from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lifeops.activity_watcher import process_snapshot
from lifeops.bridge_protocol import activity_snapshot_from_payload
from lifeops.db import connect, init_db
from lifeops.server import _intervention_detail, _pending_interventions, record_bridge_decision

DEFAULT_TZ = timezone(timedelta(hours=9), "Asia/Seoul")


class WslCoreApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-core-api-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)
        init_db()
        self.now = datetime.now(DEFAULT_TZ)
        self._insert_current_work_block()

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def _insert_current_work_block(self) -> None:
        start = (self.now - timedelta(minutes=5)).strftime("%H:%M")
        end = (self.now + timedelta(minutes=30)).strftime("%H:%M")
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO schedule_blocks(date, start_time, end_time, type, title, enforcement_level, source)
                VALUES (?, ?, ?, 'work', 'focus work', 'normal', 'test')
                """,
                (self.now.date().isoformat(), start, end),
            )
            conn.commit()

    def _activity_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "process_name": "chrome.exe",
            "window_title": "YouTube - Chrome",
            "domain": "youtube.com",
            "classification": "risky_browser",
        }
        payload.update(overrides)
        return payload

    def test_bridge_payload_normalizes_activity_classification(self) -> None:
        snapshot = activity_snapshot_from_payload(self._activity_payload())
        self.assertEqual(snapshot.classification, "chrome")
        self.assertEqual(snapshot.domain, "youtube.com")

    def test_activity_payload_creates_pending_intervention(self) -> None:
        snapshot = activity_snapshot_from_payload(self._activity_payload())
        activity_id, decision = process_snapshot(snapshot)
        self.assertIsNotNone(activity_id)
        self.assertEqual(decision.action, "intervene")
        pending = _pending_interventions(1)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "pending")
        detail = _intervention_detail(int(pending[0]["id"]))
        self.assertIn("focus work", detail["current_plan"])
        self.assertIn("YouTube", detail["detected_activity"])

    def test_bridge_decision_records_choice(self) -> None:
        snapshot = activity_snapshot_from_payload(
            self._activity_payload(process_name="steam.exe", window_title="Steam", classification="steam", domain=None)
        )
        process_snapshot(snapshot)
        event_id = int(_pending_interventions(1)[0]["id"])
        data = record_bridge_decision(event_id, {"choice": "return_now", "reason": "api test"})
        self.assertEqual(data["decision"]["decision"], "return_now")
        with connect() as conn:
            row = conn.execute("SELECT status FROM intervention_events WHERE id = ?", (event_id,)).fetchone()
        self.assertEqual(row["status"], "decided")


if __name__ == "__main__":
    unittest.main()
