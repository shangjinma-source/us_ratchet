from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backtest import ndx_dynamic_shadow_runtime_v3_migration as migration


ROOT = Path(__file__).resolve().parents[1]


def _inventory():
    return [
        {
            "task_name": migration.OLD_TASK,
            "task_path": "\\",
            "enabled": True,
            "state": "Ready",
            "execute": r"D:\python\python.exe",
            "arguments": "old",
        },
        {
            "task_name": migration.FAILED_V2_TASK,
            "task_path": "\\",
            "enabled": False,
            "state": "Disabled",
            "execute": r"D:\python\python.exe",
            "arguments": "v2",
        },
    ]


class RuntimeV3MigrationReadinessTests(unittest.TestCase):
    def build(self, inventory=None, openclaw_jobs=None, processes=None):
        return migration.build_runtime_v3_migration_readiness(
            repository_root=ROOT,
            inventory=_inventory() if inventory is None else inventory,
            activation_gate={"passed": True, "full_verifier_replayed": True},
            openclaw_jobs=[] if openclaw_jobs is None else openclaw_jobs,
            processes=[] if processes is None else processes,
        )

    def test_exact_three_task_precondition_is_ready(self):
        result = self.build()
        self.assertEqual(
            result["status"],
            "READY_FOR_EXPLICITLY_AUTHORIZED_V3_DISABLED_REGISTRATION_AND_CUTOVER",
        )
        self.assertTrue(result["runtime_process_gate"]["passed"])
        self.assertEqual(result["approved_scheduler_contract"], migration.EXPECTED_SETTINGS)
        self.assertFalse(result["migration_performed"])
        self.assertFalse(result["live_mutation_allowed"])

    def test_failed_v2_enabled_or_new_v3_preexisting_blocks(self):
        inventory = _inventory()
        inventory[1]["enabled"] = True
        inventory[1]["state"] = "Ready"
        self.assertEqual(self.build(inventory=inventory)["status"], "BLOCKED_FAIL_CLOSED")
        inventory = _inventory() + [{
            "task_name": migration.NEW_V3_TASK,
            "task_path": "\\",
            "enabled": False,
            "state": "Disabled",
            "execute": r"D:\python\python.exe",
            "arguments": "v3",
        }]
        result = self.build(inventory=inventory)
        self.assertEqual(result["status"], "BLOCKED_FAIL_CLOSED")
        self.assertFalse(
            result["interrupted_disabled_registration_recovery"]["automatic_resume_allowed"]
        )

    def test_case_insensitive_windows_and_openclaw_duplicates_block(self):
        for command in (
            "NDX_DYNAMIC_SHADOW_DAILY_V3.PY --EXECUTE",
            "NDX_DYNAMIC_SHADOW_FRESH_SEARCH_V3.PY --EXECUTE",
        ):
            duplicate = {
                "task_name": "UNEXPECTED",
                "task_path": "\\Other\\",
                "enabled": True,
                "state": "Ready",
                "execute": r"D:\python\python.exe",
                "arguments": command,
            }
            with self.subTest(kind="windows", command=command):
                self.assertEqual(
                    self.build(inventory=_inventory() + [duplicate])["status"],
                    "BLOCKED_FAIL_CLOSED",
                )
            with self.subTest(kind="openclaw", command=command):
                self.assertEqual(
                    self.build(openclaw_jobs=[{
                        "name": "mixed", "enabled": True, "command": command,
                    }])["status"],
                    "BLOCKED_FAIL_CLOSED",
                )

    def test_daily_or_fresh_search_process_blocks(self):
        for command in (
            "python ndx_dynamic_shadow_daily_v3.py --execute",
            "python NDX_DYNAMIC_SHADOW_FRESH_SEARCH_V3.PY --EXECUTE",
        ):
            with self.subTest(command=command):
                result = self.build(processes=[{"process_id": 7, "command_line": command}])
                self.assertEqual(result["status"], "BLOCKED_FAIL_CLOSED")
                self.assertFalse(result["runtime_process_gate"]["passed"])

    def test_non_root_same_name_is_not_the_canonical_predecessor(self):
        inventory = _inventory()
        inventory[0]["task_path"] = "\\Other\\"
        self.assertEqual(self.build(inventory=inventory)["status"], "BLOCKED_FAIL_CLOSED")

    def test_authority_is_deterministic_and_rejects_noncanonical_path(self):
        authority = migration.build_runtime_v3_migration_authority(repository_root=ROOT)
        self.assertEqual(authority, migration.build_runtime_v3_migration_authority(repository_root=ROOT))
        self.assertFalse(authority["boundaries"]["live_mutation_allowed"])
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "authority.json"
            path.write_text(json.dumps(authority), encoding="utf-8")
            with self.assertRaisesRegex(migration.RuntimeV3MigrationError, "not canonical"):
                migration.verify_runtime_v3_migration_authority(path, repository_root=ROOT)


if __name__ == "__main__":
    unittest.main()
