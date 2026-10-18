import unittest
from pathlib import Path

import pandas as pd
import yaml

from backtest.ndx_challenger_forward_registry import (
    NdxChallengerForwardRegistryError,
    build_forward_registry,
    validate_forward_spec,
    validate_registry_spec_binding,
)
from data.versioning import file_sha256
from scripts.ndx_challenger_forward_registry import _validated_registry_lineage


def _spec():
    return {
        "schema_version": 1, "status": "PRE_REGISTERED_FORWARD_ONLY_NOT_ADMISSION",
        "registration_date": "2026-07-20", "safe_leg_included": False,
        "external_index_included": False, "personal_off_strategy_positions_included": False,
        "candidate_contract": {
            "active_execution_status": "WHOLE_LOT_REPLAY_COMPLIANT",
            "frozen_entries": [{"candidate_id": "one", "selection_role": "RETURN", "rationale": "test_return"}],
            "failed_controls_preserved": True, "source_roles_are_independent": True,
            "composite_score_used": False, "target_weights_frozen_at_registration": True,
            "historical_whole_lot_shares_are_audit_only": True,
            "future_whole_lot_shares_must_be_resized_from_cohort_cash_and_prior_close": True,
        },
        "forward_contract": {
            "cohort_frequency": "monthly_first_completed_us_trading_session",
            "observation_price": "completed_session_close",
            "entry": "first_common_session_open_strictly_after_observation_date",
            "standardized_execution_cash_usd": 5000,
            "minimum_cash_buffer_usd": 100,
            "primary_horizon_trading_days": 126, "minimum_fresh_mature_cohorts": 12,
            "minimum_distinct_regimes": 2,
            "liquidity_lookback_trading_days": 126, "minimum_liquidity_observations": 60,
            "minimum_median_dollar_volume_usd": 50_000_000.0,
            "selection_date_or_later_data_for_registration_allowed": False,
        },
        "promotion_contract": {
            "fresh_oos_required": True, "incumbent_p50_p10_and_drawdown_p50_p90_required": True,
            "target_012922_envelope_required": True,
            "execution_cost_liquidity_and_risk_chain_required": True,
            "today_diff_and_rollback_required": True, "user_confirmation_required": True,
            "promotion_allowed_at_registration": False, "live_mutation_allowed": False,
            "policy_gate": {
                "paired_return_p50_minimum": 0.0, "paired_return_p10_minimum": 0.0,
                "paired_drawdown_cost_p50_maximum": 0.0, "paired_drawdown_cost_p90_maximum": 0.0,
                "target_012922_distance_not_worse_than_original_8": True,
                "require_continuous_and_execution_tracks": True,
                "require_at_least_one_strict_incumbent_improvement": True,
            },
        },
    }


def _master():
    common = {
        "action_scope": "ADD_ONLY", "candidate_tickers": "A;B",
        "candidate_weights": "A:0.4;B:0.6", "whole_lot_shares": "A:1;B:2",
        "evidence_status": "TRAINING", "portfolio_scope": "HSBC_US_EQUITY_SLEEVE_ONLY",
        "safe_leg_included": False, "external_index_included": False,
        "promotion_allowed": False,
    }
    return pd.DataFrame([
        {**common, "candidate_id": "one", "selection_role": "RETURN", "execution_status": "WHOLE_LOT_REPLAY_COMPLIANT"},
        {**common, "candidate_id": "two", "selection_role": "DRAWDOWN", "execution_status": "WHOLE_LOT_REPLAY_NONCOMPLIANT"},
    ])


class NdxChallengerForwardRegistryTests(unittest.TestCase):
    def test_v5_is_componentwise_and_bound_to_immutable_v4_lineage(self):
        spec_path = Path("config/ndx_challenger_forward_v5.yaml").resolve()
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        validate_forward_spec(spec)
        lineage = _validated_registry_lineage(spec)
        self.assertEqual(
            lineage["predecessor_registry_id"],
            "ndx_pure_equity_challenger_forward_v4",
        )
        self.assertEqual(
            str(spec["forward_contract"]["first_fresh_observation_on_or_after"]),
            "2026-10-01",
        )
        self.assertEqual(spec["forward_contract"]["standardized_execution_cash_usd"], 25000)
        policy = spec["promotion_contract"]["policy_gate"]
        self.assertTrue(policy["target_012922_componentwise_not_worse_than_original_8"])
        self.assertFalse(policy["target_012922_scalar_l1_used_for_admission"])
        self.assertTrue(policy["require_at_least_one_strict_target_dimension_improvement"])

        manifest = {
            "manifest_type": "ndx_pure_equity_challenger_forward_registry",
            "registry_id": spec["registry_id"],
            "promotion_allowed": False,
            "inputs": {"spec": {"sha256": file_sha256(spec_path)}},
        }
        validate_registry_spec_binding(
            manifest, spec, spec_sha256=file_sha256(spec_path),
        )
        with self.assertRaisesRegex(NdxChallengerForwardRegistryError, "hash mismatch"):
            validate_registry_spec_binding(
                manifest, spec, spec_sha256="changed-spec",
            )

    def test_v5_rejects_scalar_target_gate_or_early_cohort(self):
        spec_path = Path("config/ndx_challenger_forward_v5.yaml").resolve()
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        spec["promotion_contract"]["policy_gate"][
            "target_012922_scalar_l1_used_for_admission"
        ] = True
        with self.assertRaisesRegex(NdxChallengerForwardRegistryError, "componentwise"):
            validate_forward_spec(spec)
        spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
        spec["forward_contract"]["first_fresh_observation_on_or_after"] = "2026-09-01"
        with self.assertRaisesRegex(NdxChallengerForwardRegistryError, "precede registry"):
            validate_forward_spec(spec)

    def test_v4_requires_full_sleeve_non_return_capital_contract(self):
        spec = _spec()
        spec["registry_id"] = "ndx_pure_equity_challenger_forward_v4"
        spec["forward_contract"].update({
            "standardized_execution_cash_role": "full_sleeve_comparison_capital_not_incremental_funding",
            "capital_feasibility_uses_return_data": False,
            "capital_feasibility_observation_dates": ["2026-08-03", "2026-09-01"],
            "cohort_version_reset_required": True,
        })
        validate_forward_spec(spec)
        spec["forward_contract"]["capital_feasibility_uses_return_data"] = True
        with self.assertRaisesRegex(NdxChallengerForwardRegistryError, "cannot use returns"):
            validate_forward_spec(spec)

    def test_freezes_active_and_preserves_failed_control(self):
        active, failed = build_forward_registry(_master(), _spec())
        self.assertEqual(len(active), 1)
        self.assertEqual(len(failed), 1)
        self.assertEqual(active.loc[0, "future_cohort_shares"], "")
        self.assertEqual(active.loc[0, "research_track"], "migration_control")
        self.assertEqual(
            active.loc[0, "holding_count_interpretation"],
            "frozen_incumbent_migration_action_not_target_cardinality",
        )
        self.assertFalse(active["promotion_allowed"].any())

    def test_variable_cardinality_is_the_portfolio_optimization_track(self):
        master = _master().iloc[[0]].copy()
        master["action_scope"] = "VARIABLE_CARDINALITY"
        active, _ = build_forward_registry(master, _spec())
        self.assertEqual(active.loc[0, "research_track"], "portfolio_optimization")
        self.assertEqual(active.loc[0, "holding_count_interpretation"], "dynamic_k_portfolio_structure")

    def test_unselected_compliant_candidate_is_preserved_as_control(self):
        master = _master()
        extra = master.iloc[[0]].copy()
        extra["candidate_id"] = "three"
        extra["selection_role"] = "BAD_TAIL"
        combined = pd.concat([master, extra], ignore_index=True)
        active, controls = build_forward_registry(combined, _spec())
        self.assertEqual(len(active), 1)
        self.assertIn("FROZEN_NOT_SELECTED_CONTROL", set(controls["registry_status"]))

    def test_forward_data_or_duplicate_identity_fails_closed(self):
        spec = _spec()
        spec["forward_contract"]["selection_date_or_later_data_for_registration_allowed"] = True
        with self.assertRaises(NdxChallengerForwardRegistryError):
            validate_forward_spec(spec)
        duplicate = pd.concat([_master(), _master().iloc[[0]]], ignore_index=True)
        with self.assertRaises(NdxChallengerForwardRegistryError):
            build_forward_registry(duplicate, _spec())


if __name__ == "__main__":
    unittest.main()
