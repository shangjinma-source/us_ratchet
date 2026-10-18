from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.ndx_dynamic_shadow_search_budget_task_migration import (
    NEW_TASK,
    OLD_TASK,
    _p0_activation_evidence,
    build_readiness,
)


OLD = {
    "task_name": OLD_TASK,
    "enabled": True,
    "state": "Ready",
    "execute": r"D:\python\python.exe",
    "arguments": r'-B "E:\Git\us_ratchet\scripts\ndx_dynamic_shadow_daily.py" --execute',
}


class SearchBudgetTaskMigrationTest(unittest.TestCase):
    def _build(self, inventory):
        with (
            patch(
                "scripts.ndx_dynamic_shadow_search_budget_task_migration._old_lineage_gate",
                return_value={"passed": True},
            ),
            patch(
                "scripts.ndx_dynamic_shadow_search_budget_task_migration._activation_and_action_gate",
                return_value={"passed": True},
            ),
            patch(
                "scripts.ndx_dynamic_shadow_search_budget_task_migration._openclaw_duplicates",
                return_value=[],
            ),
        ):
            return build_readiness(inventory=inventory)

    def test_ready_plan_never_mutates_or_authorizes_migration(self):
        result = self._build([OLD])
        self.assertEqual(result["status"], "READY_FOR_EXPLICITLY_AUTHORIZED_ATOMIC_MIGRATION")
        self.assertEqual(result["mode"], "PLAN_ONLY")
        self.assertFalse(result["migration_allowed_by_this_run"])
        self.assertFalse(result["scheduled_task_mutation_performed"])
        self.assertFalse(result["rollback_contract"]["delete_either_task_allowed"])

    def test_missing_or_disabled_predecessor_fails_closed(self):
        self.assertEqual(self._build([])["status"], "BLOCKED_FAIL_CLOSED")
        self.assertEqual(self._build([{**OLD, "enabled": False}])["status"], "BLOCKED_FAIL_CLOSED")

    def test_new_task_must_be_absent_before_separate_registration_approval(self):
        new = {**OLD, "task_name": NEW_TASK}
        self.assertEqual(self._build([OLD, new])["status"], "BLOCKED_FAIL_CLOSED")

    def test_third_dynamic_scheduler_fails_closed(self):
        third = {**OLD, "task_name": "unexpected_dynamic_shadow_selection"}
        self.assertEqual(self._build([OLD, third])["status"], "BLOCKED_FAIL_CLOSED")

    def test_new_task_battery_and_atomic_rollback_contract_are_explicit(self):
        result = self._build([OLD])
        settings = result["desired_new_task_settings"]
        self.assertFalse(settings["disallow_start_if_on_batteries"])
        self.assertFalse(settings["stop_if_going_on_batteries"])
        self.assertFalse(result["duplicate_scheduler_gate"]["old_and_new_parallel_enable_allowed"])
        self.assertEqual(result["rollback_contract"]["action"], "DISABLE_NEW_THEN_REENABLE_OLD")

    def test_old_activation_without_new_p0_evidence_is_blocked(self):
        result = _p0_activation_evidence({"inputs": {}, "synthetic_e2e": {}})
        self.assertFalse(result["passed"])
        self.assertFalse(result["activation_self_module_and_cli_hash_bound"])
        self.assertFalse(result["controller_verifier_and_hash_bound"])
        self.assertFalse(result["dual_track_full_k_real_checkpoint_proof"])

    def test_canonical_v3_p0_evidence_passes_but_extra_controller_key_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(_p0_activation_evidence(manifest)["passed"])
        malicious = copy.deepcopy(manifest)
        malicious["controller_verifier"]["unreviewed"] = True
        self.assertFalse(_p0_activation_evidence(malicious)["passed"])

    def test_synthetic_extra_field_or_missing_bogus_rejection_is_rejected(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "data/cache/research/ndx_dynamic_shadow_activation_v3/manifest.json").read_text(encoding="utf-8"))
        source = json.loads(Path(manifest["synthetic_e2e"]["path"]).read_text(encoding="utf-8"))
        variants = []
        extra = copy.deepcopy(source)
        extra["scenarios"]["checkpoint_proof"]["unreviewed"] = True
        variants.append(extra)
        missing_rejection = copy.deepcopy(source)
        missing_rejection["scenarios"]["checkpoint_proof"]["bogus_self_consistent_checkpoint_rejected"] = False
        variants.append(missing_rejection)
        with tempfile.TemporaryDirectory() as directory:
            for index, payload in enumerate(variants):
                path = Path(directory) / f"synthetic-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                malicious = copy.deepcopy(manifest)
                malicious["synthetic_e2e"]["path"] = str(path)
                malicious["synthetic_e2e"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertFalse(_p0_activation_evidence(malicious)["passed"])


if __name__ == "__main__":
    unittest.main()
