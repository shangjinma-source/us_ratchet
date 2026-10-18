from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from backtest.ndx_portfolio_objective import (
    NdxPortfolioObjectiveError,
    build_objective_audit,
    calculate_fund_nav_snapshot,
    evaluate_componentwise_target_gate,
    evaluate_dynamic_shadow_path_evidence,
    load_objective_contract,
    validate_objective_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "ndx_portfolio_objective_v1.yaml"


class NdxPortfolioObjectiveContractTests(unittest.TestCase):
    def test_contract_preserves_relative_dynamic_objective(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)

        self.assertEqual(contract["user_objective"]["objective_mode"], "relative_dynamic_benchmark")
        self.assertEqual(str(contract["user_objective"]["primary_target_id"]), "012922")
        self.assertIsNone(contract["user_objective"]["absolute_targets"]["annualized_return_floor"])
        self.assertIsNone(contract["user_objective"]["absolute_targets"]["max_drawdown_ceiling"])
        self.assertFalse(contract["user_objective"]["absolute_targets"]["explicitly_stated_by_user"])

        cardinality = contract["portfolio_cardinality"]
        self.assertEqual(cardinality["mode"], "dynamic")
        self.assertEqual(cardinality["minimum_k"], 1)
        self.assertEqual(cardinality["maximum_k"], "eligible_pool_distinct_issuer_count")
        self.assertIsNone(cardinality["fixed_k"])
        self.assertFalse(cardinality["eight_is_target_holding_count"])

    def test_contract_separates_optimization_migration_and_broker_overlay(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)

        tracks = contract["optimization_tracks"]
        self.assertEqual(
            tracks["portfolio_optimization"]["candidate_k"],
            "1..eligible_pool_distinct_issuer_count",
        )
        self.assertFalse(tracks["migration_control"]["may_determine_portfolio_optimization_k"])
        registry = contract["benchmark_registry"]
        self.assertEqual(len(registry["original_8_incumbent"]["tickers"]), 8)
        self.assertEqual(len(registry["broker_account_overlay"]["registered_snapshot_tickers"]), 6)
        self.assertFalse(registry["broker_account_overlay"]["may_be_used_as_original_8_control"])

    def test_contract_requires_dual_25k_execution_tracks_and_no_live_mutation(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)

        execution = contract["execution_contract"]
        self.assertEqual(execution["standardized_comparison_capital_usd"], 25000)
        self.assertEqual(set(execution["tracks"]), {"continuous", "whole_lot"})
        self.assertFalse(execution["tracks"]["whole_lot"]["fractional_shares_allowed"])
        self.assertEqual(
            execution["tracks"]["whole_lot"]["role"],
            "dynamic_security_id_continuous_whole_lot_rebalance",
        )
        boundary = contract["mutation_boundary"]
        self.assertTrue(boundary["research_output_only"])
        self.assertFalse(boundary["live_configuration_mutation_allowed"])
        self.assertFalse(boundary["state_mutation_allowed"])
        self.assertFalse(boundary["order_creation_allowed"])

    def test_validation_rejects_fixed_absolute_goal(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        changed = copy.deepcopy(contract)
        changed["user_objective"]["absolute_targets"]["annualized_return_floor"] = 0.30

        with self.assertRaisesRegex(NdxPortfolioObjectiveError, "annualized_return_floor"):
            validate_objective_contract(changed)

    def test_validation_rejects_scalarized_target_admission(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        changed = copy.deepcopy(contract)
        changed["metric_contract"]["target_012922_componentwise_gate"]["scalar_l1_distance"][
            "admission_decision_allowed"
        ] = True

        with self.assertRaisesRegex(NdxPortfolioObjectiveError, "admission_decision_allowed"):
            validate_objective_contract(changed)

    def test_dynamic_shadow_path_keeps_formal_v4_gate_and_next_session_execution(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        shadow = contract["dynamic_shadow_path"]

        self.assertEqual(shadow["portfolio_track"], "portfolio_optimization")
        self.assertFalse(shadow["migration_control_included"])
        self.assertEqual(str(shadow["availability"]["planned_first_decision_on_or_after"]), "2026-10-01")
        self.assertEqual(shadow["availability"]["one_year_review_target_quarter"], "2027Q4")
        self.assertEqual(shadow["availability"]["minimum_completed_trading_days"], 252)
        self.assertEqual(shadow["availability"]["minimum_executed_monthly_rebalances"], 12)
        self.assertEqual(
            shadow["execution"]["execution_session"],
            "first_common_us_trading_session_strictly_after_decision",
        )
        self.assertEqual(shadow["execution"]["execution_price"], "nominal_unadjusted_session_open")
        self.assertEqual(shadow["execution"]["security_identity_key"], "security_id")
        self.assertTrue(shadow["implementation_readiness"]["contract_defined"])
        self.assertFalse(shadow["implementation_readiness"]["runner_registered"])
        self.assertFalse(shadow["implementation_readiness"]["automation_enabled"])
        self.assertFalse(shadow["evidence_boundary"]["formal_v4_gate_substitution_allowed"])
        self.assertFalse(shadow["evidence_boundary"]["direct_live_promotion_allowed"])
        self.assertEqual(shadow["formal_gate_relationship"]["formal_gate_minimum_fresh_mature_cohorts"], 12)
        self.assertEqual(shadow["formal_gate_relationship"]["formal_gate_primary_horizon_trading_days"], 126)

    def test_validation_rejects_shadow_substitution_for_formal_gate(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        changed = copy.deepcopy(contract)
        changed["dynamic_shadow_path"]["evidence_boundary"]["formal_v4_gate_substitution_allowed"] = True

        with self.assertRaisesRegex(NdxPortfolioObjectiveError, "formal_v4_gate_substitution_allowed"):
            validate_objective_contract(changed)


class NdxPortfolioObjectiveGateTests(unittest.TestCase):
    def test_componentwise_gate_rejects_cross_dimension_l1_compensation(self) -> None:
        names = ("return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90")
        target = {name: 0.0 for name in names}
        control = {name: 4.0 for name in names}
        candidate = {
            "return_p50": 5.0,
            "return_p10": 0.0,
            "max_drawdown_p50": 0.0,
            "max_drawdown_p90": 0.0,
        }

        result = evaluate_componentwise_target_gate(candidate, control, target)

        self.assertTrue(result["scalar_l1_reporting_only"]["candidate_not_worse"])
        self.assertFalse(result["checks"]["return_p50"]["passed"])
        self.assertFalse(result["passed"])
        self.assertFalse(result["scalar_l1_reporting_only"]["used_for_admission"])

    def test_componentwise_gate_passes_only_with_every_dimension_and_one_strict(self) -> None:
        target = {name: 0.0 for name in ("return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90")}
        control = {name: 2.0 for name in target}
        candidate = dict(control)
        candidate["return_p10"] = 1.0

        result = evaluate_componentwise_target_gate(candidate, control, target)

        self.assertTrue(result["passed"])
        self.assertEqual(result["strict_improvement_count"], 1)

    def test_componentwise_gate_rejects_equal_distances_without_strict_improvement(self) -> None:
        target = {name: 0.0 for name in ("return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90")}
        control = {name: 2.0 for name in target}

        result = evaluate_componentwise_target_gate(control, control, target)

        self.assertTrue(result["componentwise_passed"])
        self.assertFalse(result["strict_requirement_passed"])
        self.assertFalse(result["passed"])


class NdxDynamicShadowEvidenceBoundaryTests(unittest.TestCase):
    def test_self_reported_one_year_counts_cannot_open_research_review(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        result = evaluate_dynamic_shadow_path_evidence(
            {
                "completed_trading_days": 252,
                "executed_monthly_rebalances": 12,
                "integrity_guards": {"every_unverified_guard": True},
            },
            contract,
        )

        self.assertEqual(result["status"], "UNVERIFIED_EVIDENCE_RUNNER_NOT_REGISTERED")
        self.assertEqual(result["evidence_role"], "NO_ADMISSIBLE_EVIDENCE_UNTIL_ARTIFACT_VERIFIER")
        self.assertFalse(result["self_reported_counts_accepted"])
        self.assertFalse(result["self_reported_guard_booleans_accepted"])
        self.assertFalse(result["one_year_requirements_passed"])
        self.assertFalse(result["internal_shadow_review_allowed"])
        self.assertFalse(result["configuration_candidate_promotion_allowed"])
        self.assertFalse(result["counts_as_v4_fresh_mature_cohort"])
        self.assertFalse(result["single_adaptive_path_is_independent_cohort_sample"])
        self.assertFalse(result["path_level_metrics_can_satisfy_componentwise_formal_gate"])
        self.assertFalse(result["formal_v4_gate_substitution_allowed"])
        self.assertFalse(result["live_promotion_allowed"])

    def test_contract_requires_hash_bound_artifact_verifier_before_classification(self) -> None:
        contract = load_objective_contract(CONTRACT_PATH)
        verification = contract["dynamic_shadow_path"]["evidence_verification"]

        self.assertEqual(
            verification["status"],
            "DISABLED_UNTIL_IMMUTABLE_RUNNER_ARTIFACT_VERIFIER",
        )
        self.assertFalse(verification["self_reported_counts_allowed"])
        self.assertFalse(verification["self_reported_guard_booleans_allowed"])
        self.assertEqual(len(verification["required_artifact_hashes"]), 10)


class NdxPortfolioObjectiveAuditTests(unittest.TestCase):
    def _write_evidence(self, root: Path) -> tuple[Path, Path, Path]:
        csv_path = root / "012922.csv"
        csv_bytes = (
            "Date,UnitNav,AccumNav,DailyPct,Close\n"
            "2024-01-01,1.0,1.0,,100\n"
            "2024-07-01,1.1,1.1,,110\n"
            "2025-01-01,0.99,0.99,,99\n"
        ).encode("utf-8")
        csv_path.write_bytes(csv_bytes)
        manifest_path = root / "012922.csv.manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "dataset_key": "012922",
                    "dataset_type": "fund_nav",
                    "version_id": "fund_nav:012922:test",
                    "source": "test_fixture",
                    "completeness": "verified_against_source_record_count",
                    "row_count": 3,
                    "data_start": "2024-01-01",
                    "data_end": "2025-01-01",
                    "generated_at": "2025-01-02T00:00:00+00:00",
                    "content_sha256": hashlib.sha256(csv_bytes).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        broker_path = root / "broker_positions.json"
        broker_path.write_text(
            json.dumps(
                {
                    "positions": [
                        {"ticker": ticker, "shares": 1, "average_cost": 1.0}
                        for ticker in ("ASML", "AVGO", "DRAM", "GOOG", "MU", "TSM")
                    ]
                }
            ),
            encoding="utf-8",
        )
        return csv_path, manifest_path, broker_path

    def test_nav_snapshot_is_descriptive_and_has_drawdown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path, _, _ = self._write_evidence(Path(temporary_directory))

            snapshot = calculate_fund_nav_snapshot(csv_path)

        self.assertEqual(snapshot["metric_role"], "descriptive_latest_available_not_absolute_user_target")
        self.assertAlmostEqual(snapshot["cumulative_return"], -0.01)
        self.assertAlmostEqual(snapshot["max_drawdown"], 0.10)
        self.assertEqual(snapshot["max_drawdown_peak_date"], "2024-07-01")
        self.assertEqual(snapshot["max_drawdown_trough_date"], "2025-01-01")

    def test_audit_validates_manifest_hash_and_benchmark_separation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path, manifest_path, broker_path = self._write_evidence(Path(temporary_directory))

            audit = build_objective_audit(
                contract_path=CONTRACT_PATH,
                fund_manifest_path=manifest_path,
                fund_csv_path=csv_path,
                broker_snapshot_path=broker_path,
            )

        self.assertEqual(audit["target_012922"]["manifest"]["row_count"], 3)
        self.assertEqual(len(audit["contract"]["canonical_sha256"]), 64)
        self.assertEqual(audit["optimization_scope"]["cardinality_mode"], "dynamic")
        self.assertNotEqual(
            set(audit["benchmark_separation"]["original_8"]),
            set(audit["benchmark_separation"]["broker_overlay_tickers"]),
        )
        self.assertFalse(audit["admission_semantics"]["scalar_l1_admission_allowed"])

    def test_audit_rejects_tampered_fund_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path, manifest_path, broker_path = self._write_evidence(Path(temporary_directory))
            with csv_path.open("a", encoding="utf-8") as handle:
                handle.write("2025-02-01,1.0,1.0,,100\n")

            with self.assertRaisesRegex(NdxPortfolioObjectiveError, "hash"):
                build_objective_audit(
                    contract_path=CONTRACT_PATH,
                    fund_manifest_path=manifest_path,
                    fund_csv_path=csv_path,
                    broker_snapshot_path=broker_path,
                )


if __name__ == "__main__":
    unittest.main()
