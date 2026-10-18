"""Repository contract wiring, not an activation or Scheduled Task smoke test."""
from pathlib import Path
import hashlib
import unittest

import yaml

from scripts import ndx_dynamic_shadow_daily_v4 as daily
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance
from backtest import ndx_dynamic_shadow_daily_v3 as reviewed


ROOT = Path(__file__).resolve().parents[1]


class RunnerV4ContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = yaml.safe_load(
            (ROOT / "config/ndx_dynamic_shadow_runner_v4.yaml").read_text(encoding="utf-8")
        )

    def test_predecessor_bytes_and_inherited_strategy_are_unchanged(self):
        predecessor = self.contract["predecessor"]
        self.assertEqual(predecessor["path"], "config/ndx_dynamic_shadow_runner_v3.yaml")
        self.assertEqual(predecessor["sha256"], hashlib.sha256(
            (ROOT / predecessor["path"]).read_bytes()).hexdigest())
        self.assertIs(predecessor["inherit_strategy_schedule_execution_and_evidence_contracts"], True)
        self.assertIs(predecessor["strategy_or_dynamic_k_semantics_changed"], False)

    def test_runtime_paths_match_actual_daily_and_acceptance_modules(self):
        runtime = self.contract["runtime_overrides"]
        for key, actual in {
            "candidate_script": daily.GENERATOR_SCRIPT,
            "fresh_search_script": daily.FRESH_SCRIPT,
            "activation_manifest": daily.ACTIVATION,
            "daily_script": ROOT / reviewed.RUNTIME_PATHS["daily_script"],
            "daily_adapter": ROOT / reviewed.RUNTIME_PATHS["daily_engine"],
            "calendar_manifest": ROOT / reviewed.RUNTIME_PATHS["observed_calendar_manifest"],
            "acceptance_receipt_root": ROOT / acceptance.ACCEPTANCE,
        }.items():
            with self.subTest(key=key):
                self.assertEqual((ROOT / runtime[key]).resolve(), actual.resolve())

    def test_receipt_guards_and_non_live_boundaries_are_explicit(self):
        self.assertEqual(self.contract["schema_version"], 4)
        self.assertEqual(self.contract["status"], "ACTIVATION_V5_GATED_RESEARCH_ONLY")
        runtime = self.contract["runtime_overrides"]
        for key in ("acceptance_required_for_every_consumed_final",
                    "acceptance_required_for_every_realized_batch",
                    "preserve_append_only_output_namespaces",
                    "immutable_v1_static_lineage_verification_required"):
            self.assertIs(runtime[key], True)
        for key in ("initialize_calendar_implicitly", "old_and_new_tasks_parallel_allowed",
                    "promotion_allowed", "live_mutation_allowed"):
            self.assertIs(runtime[key], False)


if __name__ == "__main__":
    unittest.main()
