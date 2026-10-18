from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest import ndx_dynamic_shadow_runtime_v3_recovery as recovery
from backtest.ndx_dynamic_shadow_runtime_v3_migration import (
    FAILED_V2_TASK, NEW_V3_TASK, OLD_TASK,
)


ROOT = Path(__file__).resolve().parents[1]


def inventory():
    return [
        {"task_name": OLD_TASK, "task_path": "\\", "enabled": True, "state": "Ready"},
        {"task_name": FAILED_V2_TASK, "task_path": "\\", "enabled": False, "state": "Disabled"},
        {"task_name": NEW_V3_TASK, "task_path": "\\", "enabled": False, "state": "Disabled"},
    ]


class RuntimeV3RecoveryTests(unittest.TestCase):
    def test_failed_attempt_and_authority_are_rebuilt(self):
        attempt = recovery.verify_failed_attempt(ROOT)
        self.assertEqual(attempt["rollback"]["sha256"], "640dec13c6ec1f2957fcde66ea16328088ba9c850cf4e62bbfe7281bff1f3065")
        authority = recovery.build_recovery_authority(repository_root=ROOT)
        self.assertTrue(authority["boundaries"]["reuse_existing_disabled_v3_task_only"])
        self.assertFalse(authority["boundaries"]["task_registration_allowed"])

    def test_ready_requires_exact_three_task_state_and_no_process(self):
        result = recovery.build_recovery_readiness(
            repository_root=ROOT, inventory=inventory(), processes=[], openclaw_jobs=[],
            activation_gate={"passed": True},
        )
        self.assertEqual(result["status"], "READY_FOR_REVIEWED_EXISTING_TASK_RECOVERY")
        self.assertFalse(result["registration_allowed"])
        bad = inventory()
        bad[2]["enabled"] = True
        self.assertEqual(recovery.build_recovery_readiness(
            repository_root=ROOT, inventory=bad, processes=[], openclaw_jobs=[],
            activation_gate={"passed": True},
        )["status"], "BLOCKED_FAIL_CLOSED")

    def test_unexpected_scheduler_is_summarised_without_action_arguments(self):
        rows = inventory() + [{
            "task_name": "EVIL_FRESH_SEARCH",
            "task_path": "\\Other\\",
            "enabled": True,
            "state": "Ready",
            "execute": "D:/python/python.exe",
            "arguments": "ndx_dynamic_shadow_fresh_search.py --execute --token SECRET",
        }]
        result = recovery.build_recovery_readiness(
            repository_root=ROOT, inventory=rows, processes=[], openclaw_jobs=[],
            activation_gate={"passed": True},
        )
        self.assertEqual(result["status"], "BLOCKED_FAIL_CLOSED")
        self.assertEqual(len(result["task_gate"]["observed"]), 3)
        self.assertEqual(result["task_gate"]["unexpected_enabled_duplicates"], [{
            "task_name": "EVIL_FRESH_SEARCH",
            "task_path": "\\Other\\",
            "state": "Ready",
            "enabled": True,
        }])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_record_outer_tamper_is_rejected(self):
        source = ROOT / recovery.FAILED_ATTEMPT_RELATIVE / "rollback.json"
        value = json.loads(source.read_text(encoding="utf-8"))
        value["reason"] = "forged"
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "rollback.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(recovery.RuntimeV3RecoveryError, "envelope"):
                recovery._record(path)


if __name__ == "__main__":
    unittest.main()
