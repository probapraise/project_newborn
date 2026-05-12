from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from lifeops.recovery_decision_self_check import run_recovery_decision_self_check


class Stage3RecoveryDecisionSelfCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_root = os.environ.get("LIFEOPS_REPO_ROOT")
        self.tmp = Path(tempfile.mkdtemp(prefix="lifeops-recovery-decision-"))
        os.environ["LIFEOPS_REPO_ROOT"] = str(self.tmp)

    def tearDown(self) -> None:
        if self.old_root is None:
            os.environ.pop("LIFEOPS_REPO_ROOT", None)
        else:
            os.environ["LIFEOPS_REPO_ROOT"] = self.old_root
        shutil.rmtree(self.tmp)

    def test_recovery_decision_self_check_applies_in_sandbox(self) -> None:
        result = run_recovery_decision_self_check()
        self.assertEqual(result["status"], "pass")
        self.assertTrue(str(result["sandbox_root"]).startswith(str(self.tmp)))
        self.assertEqual(result["event_status"], "decided")
        self.assertEqual(result["protected_block_status"], "planned")
        self.assertEqual(result["optional_block_status"], "cancelled")
        self.assertEqual(result["kept_task_status"], "pending")
        self.assertEqual(result["deferred_task_status"], "deferred_recovery")
        self.assertEqual(result["decision_count"], 1)
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(result["recovery_session_count"], 1)

    def test_recovery_decision_self_check_can_preview_recovery(self) -> None:
        result = run_recovery_decision_self_check(recovery_dry_run=True)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["optional_block_status"], "planned")
        self.assertEqual(result["kept_task_status"], "pending")
        self.assertEqual(result["deferred_task_status"], "pending")
        self.assertEqual(result["recovery_session_count"], 0)


if __name__ == "__main__":
    unittest.main()