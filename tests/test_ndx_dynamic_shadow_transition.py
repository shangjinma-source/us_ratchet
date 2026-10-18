from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

from backtest.ndx_dynamic_shadow_transition import (
    NdxDynamicShadowTransitionError,
    assess_transition_readiness,
    load_transition_contract,
)
from backtest.ndx_dynamic_shadow_p4_evidence import (
    NdxDynamicShadowP4EvidenceError,
    verify_p4_evaluation_evidence,
)
import backtest.ndx_dynamic_shadow_p4_evidence as p4_evidence


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config/ndx_dynamic_shadow_transition_v1.yaml"


class NdxDynamicShadowTransitionTests(unittest.TestCase):
    def test_current_readiness_rebuilds_p4_and_remains_blocked_without_evidence(self) -> None:
        result = assess_transition_readiness(load_transition_contract(CONTRACT), repository_root=ROOT)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("P4_PORTFOLIO_OPTIMIZATION_GATE_NOT_VERIFIED", result["blockers"])
        self.assertIn("NO_FRESH_COHORTS", result["blockers"])
        self.assertIn("ONE_TIME_USER_APPROVAL_EVIDENCE_NOT_AVAILABLE", result["blockers"])
        self.assertTrue(result["p4_rebuilt_evidence"]["summary_recomputed_from_immutable_evaluations"])
        self.assertFalse(result["caller_supplied_summary_booleans_trusted"])
        self.assertFalse(result["caller_supplied_approval_booleans_accepted"])
        self.assertFalse(result["migration_control_included"])
        self.assertFalse(result["user_preference_override_allowed"])
        self.assertTrue(result["new_money_only"])
        self.assertFalse(result["apply_supported_by_this_module"])
        self.assertFalse(result["orders_created"])

    def test_canonical_p4_verifier_ignores_latest_summary_booleans(self) -> None:
        evidence = verify_p4_evaluation_evidence(
            ROOT / "data/cache/research/ndx_challenger_forward_v5/latest_evaluation/manifest.json",
            repository_root=ROOT,
        )
        self.assertEqual(evidence["status"], "P4_SUMMARY_REBUILT_DIAGNOSTIC_ONLY")
        self.assertEqual(evidence["registered_fresh_cohorts"], 0)
        self.assertEqual(evidence["eligible_portfolio_optimization_candidate_ids"], [])
        self.assertFalse(evidence["latest_summary_booleans_trusted"])
        self.assertTrue(evidence["raw_economic_path_replay_capability_implemented"])
        self.assertFalse(evidence["raw_economic_path_replay_verified"])
        self.assertEqual(
            evidence["admission_blocker"],
            "NO_FRESH_COHORTS",
        )

    def test_caller_cannot_supply_approval_booleans(self) -> None:
        with self.assertRaises(TypeError):
            assess_transition_readiness(
                load_transition_contract(CONTRACT),
                repository_root=ROOT,
                explicit_user_approval_verified=True,
            )

    def test_forged_immutable_summary_boolean_is_rejected_by_rebuild(self) -> None:
        original = p4_evidence._read_csv

        def forged(path, *, expected_rows, label):
            frame = original(path, expected_rows=expected_rows, label=label)
            if label == "P4 immutable summary":
                frame = frame.copy()
                frame.loc[frame.index[0], "policy_gate_ready"] = True
                frame.loc[frame.index[0], "policy_gate_passed"] = True
            return frame

        with patch(
            "backtest.ndx_dynamic_shadow_p4_evidence._read_csv",
            side_effect=forged,
        ):
            with self.assertRaises(NdxDynamicShadowP4EvidenceError):
                verify_p4_evaluation_evidence(
                    ROOT / "data/cache/research/ndx_challenger_forward_v5/latest_evaluation/manifest.json",
                    repository_root=ROOT,
                )

    def test_contract_rejects_fixed_k_migration_or_live_mutation(self) -> None:
        original = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
        mutations = (
            lambda value: value.__setitem__("migration_control_included", True),
            lambda value: value["transition_policy"].__setitem__("fixed_holding_count", 8),
            lambda value: value["transition_policy"].__setitem__("automatic_order_creation_allowed", True),
            lambda value: value["p4_gate"].__setitem__("user_preference_is_reference_not_override", False),
            lambda value: value["approval_gate"].__setitem__("explicit_user_approval_required", False),
            lambda value: value["p4_gate"].__setitem__("minimum_mature_cohorts", 11),
            lambda value: value["transition_policy"].__setitem__("transaction_cost_bps", 9),
            lambda value: value["transition_policy"].__setitem__("minimum_cash_buffer_usd", 99),
        )
        for mutate in mutations:
            changed = copy.deepcopy(original)
            mutate(changed)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "contract.yaml"
                path.write_text(yaml.safe_dump(changed), encoding="utf-8")
                with self.assertRaises(NdxDynamicShadowTransitionError):
                    load_transition_contract(path)


if __name__ == "__main__":
    unittest.main()
