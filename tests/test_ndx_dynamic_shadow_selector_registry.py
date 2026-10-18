from __future__ import annotations

import copy
import unittest
from pathlib import Path

from backtest.ndx_dynamic_shadow_selector_registry import (
    NdxDynamicShadowSelectorRegistryError,
    build_dynamic_shadow_selector_registry_audit,
    load_dynamic_shadow_selector_registry,
    validate_dynamic_shadow_selector_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "config" / "ndx_dynamic_shadow_selector_registry_v1.yaml"


class NdxDynamicShadowSelectorRegistryTests(unittest.TestCase):
    def test_registry_is_complete_inactive_two_by_five_matrix(self) -> None:
        registry = load_dynamic_shadow_selector_registry(REGISTRY_PATH)
        matrix = registry["selector_matrix"]
        coordinates = {
            (selector["universe_track"], selector["policy_role"])
            for selector in matrix["selectors"]
        }

        self.assertEqual(matrix["expected_selector_count"], 10)
        self.assertEqual(len(coordinates), 10)
        self.assertEqual(
            coordinates,
            {
                (track, role)
                for track in ("strict_technology", "technology_plus_adjacent")
                for role in ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
            },
        )
        self.assertFalse(registry["activation"]["active"])
        self.assertFalse(registry["activation"]["runner_registered"])
        self.assertFalse(registry["activation"]["automation_enabled"])
        self.assertFalse(registry["activation"]["decision_generation_allowed"])

    def test_target_scalar_is_training_only_and_never_admission(self) -> None:
        registry = load_dynamic_shadow_selector_registry(REGISTRY_PATH)
        target_selectors = [
            selector
            for selector in registry["selector_matrix"]["selectors"]
            if selector["policy_role"] == "TARGET_ENVELOPE"
        ]

        self.assertEqual(len(target_selectors), 2)
        self.assertTrue(
            all(
                selector["target_scalar_training_usage"] == "primary_training_rank_only"
                for selector in target_selectors
            )
        )
        self.assertFalse(registry["per_selector_contract"]["target_scalar_admission_allowed"])
        self.assertTrue(
            registry["per_selector_contract"][
                "componentwise_012922_forward_gate_required_for_formal_admission"
            ]
        )
        self.assertFalse(registry["evidence_and_promotion"]["target_scalar_can_admit"])

    def test_parallel_paths_cannot_be_spliced_or_selected_ex_post(self) -> None:
        registry = load_dynamic_shadow_selector_registry(REGISTRY_PATH)
        boundary = registry["parallel_path_boundary"]

        self.assertTrue(boundary["selectors_run_in_parallel"])
        self.assertFalse(boundary["shared_realized_path_allowed"])
        self.assertFalse(boundary["cross_selector_path_splicing_allowed"])
        self.assertFalse(boundary["winner_take_all_ex_post_selection_allowed"])

        changed = copy.deepcopy(registry)
        changed["parallel_path_boundary"]["cross_selector_path_splicing_allowed"] = True
        with self.assertRaisesRegex(NdxDynamicShadowSelectorRegistryError, "splicing"):
            validate_dynamic_shadow_selector_registry(changed)

    def test_registry_rejects_missing_lane_and_premature_activation(self) -> None:
        registry = load_dynamic_shadow_selector_registry(REGISTRY_PATH)
        missing = copy.deepcopy(registry)
        missing["selector_matrix"]["selectors"].pop()
        with self.assertRaisesRegex(NdxDynamicShadowSelectorRegistryError, "10 independent"):
            validate_dynamic_shadow_selector_registry(missing)

        active = copy.deepcopy(registry)
        active["activation"]["active"] = True
        with self.assertRaisesRegex(NdxDynamicShadowSelectorRegistryError, "activation.active"):
            validate_dynamic_shadow_selector_registry(active)

    def test_selector_rows_reject_all_unknown_override_keys(self) -> None:
        registry = load_dynamic_shadow_selector_registry(REGISTRY_PATH)
        malicious_fields = {
            "active": True,
            "target_scalar_admission_allowed": True,
            "splice_from_selector_id": "strict_technology__return__v1",
            "shared_realized_path_id": "ex_post_winner",
        }
        for field, value in malicious_fields.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(registry)
                changed["selector_matrix"]["selectors"][3][field] = value
                with self.assertRaisesRegex(NdxDynamicShadowSelectorRegistryError, "keys mismatch"):
                    validate_dynamic_shadow_selector_registry(changed)

    def test_audit_binds_current_sources_descriptively_but_not_for_activation(self) -> None:
        audit = build_dynamic_shadow_selector_registry_audit(
            registry_path=REGISTRY_PATH,
            objective_path=ROOT / "config" / "ndx_portfolio_objective_v1.yaml",
            dynamic_walkforward_path=ROOT / "config" / "ndx_dynamic_walkforward_v1.yaml",
            selector_policy_module_path=ROOT / "backtest" / "ndx_dynamic_candidate_policy.py",
        )

        self.assertEqual(audit["registry"]["selector_count"], 10)
        self.assertEqual(len(audit["registry"]["canonical_sha256"]), 64)
        self.assertTrue(
            all(len(value) == 64 for value in audit["current_unbound_source_hashes"].values())
        )
        self.assertEqual(audit["activation"]["hash_binding_state"], "PENDING_ACTIVATION")
        self.assertFalse(audit["activation"]["activation_ready"])
        self.assertFalse(audit["admission_boundary"]["target_scalar_can_admit"])
        self.assertFalse(audit["admission_boundary"]["shadow_can_replace_v4_formal_gate"])
        self.assertFalse(audit["mutation_assertions"]["live_configuration_mutated"])

    def test_audit_rejects_policy_module_path_not_declared_by_registry(self) -> None:
        with self.assertRaisesRegex(NdxDynamicShadowSelectorRegistryError, "does not match registry"):
            build_dynamic_shadow_selector_registry_audit(
                registry_path=REGISTRY_PATH,
                objective_path=ROOT / "config" / "ndx_portfolio_objective_v1.yaml",
                dynamic_walkforward_path=ROOT / "config" / "ndx_dynamic_walkforward_v1.yaml",
                selector_policy_module_path=ROOT / "README.md",
            )


if __name__ == "__main__":
    unittest.main()
