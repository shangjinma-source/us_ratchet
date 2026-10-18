from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.ndx_dynamic_shadow_task_migration_notary import (
    EVIDENCE_ALGORITHMS,
    EVIDENCE_ROOT,
    PS51,
    PS76,
    TaskMigrationNotaryError,
    _verify_notary_ledger,
    build_observation,
    verify_declared_record,
)


class TaskMigrationNotaryTest(unittest.TestCase):
    def test_each_original_record_uses_its_single_declared_host_algorithm(self):
        results = {
            name: verify_declared_record(EVIDENCE_ROOT / name, algorithm)
            for name, algorithm in EVIDENCE_ALGORITHMS.items()
        }
        self.assertEqual(results["pre_cutover.json"]["serializer"], PS51)
        self.assertEqual(results["new_disabled.json"]["serializer"], PS51)
        self.assertEqual(results["post_cutover.json"]["serializer"], PS51)
        self.assertEqual(results["rollback.json"]["serializer"], PS76)

    def test_wrong_declared_algorithm_is_rejected_without_fallback(self):
        with self.assertRaises(TaskMigrationNotaryError):
            verify_declared_record(EVIDENCE_ROOT / "rollback.json", PS51)
        with self.assertRaises(TaskMigrationNotaryError):
            verify_declared_record(EVIDENCE_ROOT / "pre_cutover.json", PS76)

    def test_scheduler_rollback_is_verified_but_runtime_recovery_is_not_claimed(self):
        result = build_observation()
        self.assertTrue(result["scheduler_rollback_verified"])
        self.assertFalse(result["runtime_recovery_claimed"])
        self.assertTrue(result["runtime_calendar_revision_unresolved"])
        self.assertTrue(result["task_state"]["us_ratchet_ndx_dynamic_shadow_selection_daily"]["enabled"])
        self.assertFalse(result["task_state"]["us_ratchet_ndx_dynamic_shadow_selection_daily_v2_budgeted"]["enabled"])

    def test_notary_chain_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.jsonl"
            path.write_text(json.dumps({
                "sequence": 1, "previous_record_sha256": None,
                "record_sha256": "0" * 64, "value": "tampered",
            }) + "\n", encoding="utf-8")
            with self.assertRaises(TaskMigrationNotaryError):
                _verify_notary_ledger(path)


if __name__ == "__main__":
    unittest.main()
