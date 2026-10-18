import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backtest.ndx_challenger_forward_evaluation import (
    annotate_paired_execution_evidence,
    evaluate_candidate_pair,
    summarize_forward_readiness,
    summarize_research_tracks,
)
from data.versioning import file_sha256
from scripts.ndx_challenger_forward_evaluate import (
    _archive_evaluation_run,
    shadow_horizon_diagnostics,
    summarize_shadow_monitoring,
    validate_cohort_evaluation_identity,
)


def _prices(opens, closes):
    dates = pd.date_range("2026-07-21", periods=len(opens), freq="B")
    return pd.DataFrame({"Open": opens, "Close": closes}, index=dates)


class NdxChallengerForwardEvaluationTests(unittest.TestCase):
    def test_paired_execution_label_rejects_noncompliant_control(self):
        result = annotate_paired_execution_evidence({
            "execution_status": "MATURE_EXECUTABLE",
            "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
            "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_NONCOMPLIANT",
        })
        self.assertFalse(result["paired_execution_evidence_eligible"])
        self.assertEqual(
            result["paired_execution_evidence_status"],
            "ORIGINAL_8_CONTROL_COHORT_NONCOMPLIANT",
        )

    def test_shadow_diagnostics_reports_one_session_remaining_by_track(self):
        evaluations = pd.DataFrame([
            {
                "monitoring_horizon_trading_days": 21,
                "fresh_oos_eligible": True,
                "available_common_sessions": 20,
                "mature": False,
                "target_012922_mature": False,
                "research_track": "portfolio_optimization",
                "status": "WAITING_FOR_MATURITY",
            },
            {
                "monitoring_horizon_trading_days": 21,
                "fresh_oos_eligible": True,
                "available_common_sessions": 20,
                "mature": False,
                "target_012922_mature": False,
                "research_track": "migration_control",
                "status": "WAITING_FOR_MATURITY",
            },
        ])

        diagnostics = shadow_horizon_diagnostics(evaluations, [21, 63])

        self.assertEqual(diagnostics[0]["available_common_sessions_min"], 20)
        self.assertEqual(diagnostics[0]["sessions_remaining_until_all_rows_mature"], 1)
        self.assertEqual(diagnostics[0]["mature_rows_by_research_track"], {
            "migration_control": 0,
            "portfolio_optimization": 0,
        })
        self.assertEqual(diagnostics[1]["sessions_remaining_until_all_rows_mature"], 63)
        self.assertFalse(diagnostics[0]["promotion_allowed"])

    def test_shadow_monitoring_is_early_falsification_only(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D",
        }])
        evaluations = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE",
            "monitoring_horizon_trading_days": 21,
            "fresh_oos_eligible": True,
            "mature": True,
            "execution_status": "MATURE_EXECUTABLE",
            "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
            "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
            "target_012922_mature": True,
            "continuous_return_delta_vs_original_8": -0.01,
            "continuous_drawdown_cost_vs_original_8": 0.02,
            "continuous_return_delta_vs_012922": -0.03,
            "continuous_drawdown_cost_vs_012922": 0.01,
            "execution_return_delta_vs_original_8": -0.02,
            "execution_drawdown_cost_vs_original_8": 0.03,
            "execution_return_delta_vs_012922": -0.04,
            "execution_drawdown_cost_vs_012922": 0.02,
        }])
        result = summarize_shadow_monitoring(active, evaluations, [21, 63]).set_index(
            "monitoring_horizon_trading_days"
        )
        self.assertEqual(
            result.loc[21, "status"],
            "EARLY_FALSIFICATION_EVIDENCE_AVAILABLE_NOT_ADMISSION",
        )
        self.assertEqual(result.loc[21, "mature_fresh_cohorts"], 1)
        self.assertEqual(result.loc[21, "executable_mature_fresh_cohorts"], 1)
        self.assertEqual(result.loc[21, "paired_execution_ineligible_mature_fresh_cohorts"], 0)
        self.assertEqual(result.loc[63, "mature_fresh_cohorts"], 0)
        self.assertFalse(result["promotion_allowed"].any())

    def test_evaluation_run_archive_is_versioned_and_self_hashed(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            latest = root / "latest.csv"
            latest.write_text("x\n1\n", encoding="utf-8")
            archived = _archive_evaluation_run(
                output=root,
                generated=datetime(2026, 7, 22, 1, 2, 3, 456789, tzinfo=timezone.utc),
                artifacts={"evaluations": (latest, 1)},
                base_payload={"schema_version": 1, "generated_at": "2026-07-22T01:02:03+00:00"},
                cohort_index_path=root / "cohort_index.jsonl",
            )
            manifest = Path(archived["path"])
            self.assertTrue(manifest.is_file())
            self.assertEqual(archived["sha256"], file_sha256(manifest))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["manifest_type"], "ndx_challenger_forward_evaluation_run")
            self.assertEqual(payload["artifacts"]["evaluations"]["rows"], 1)

    def test_cohort_evaluation_identity_locks_spec_registry_and_artifacts(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = root / "spec.yaml"
            registry = root / "registry.json"
            candidates = root / "candidates.csv"
            positions = root / "positions.csv"
            spec.write_text("version: 2\n", encoding="utf-8")
            registry.write_text("{}\n", encoding="utf-8")
            candidates.write_text("candidate_id\none\n", encoding="utf-8")
            positions.write_text("ticker\nA\n", encoding="utf-8")
            manifest = {
                "manifest_type": "ndx_challenger_forward_cohort",
                "observation_date": "2026-07-20", "fresh_oos_eligible": True,
                "cohort_origin": "FRESH_SAME_DAY_POST_CLOSE", "active_candidate_count": 1,
                "inputs": {
                    "spec": {"path": spec.as_posix(), "sha256": file_sha256(spec)},
                    "registry_manifest": {"path": registry.as_posix(), "sha256": file_sha256(registry)},
                    "registry_content_sha256": "active-registry-hash",
                },
                "artifacts": {
                    "cohort_candidates": {"path": candidates.as_posix(), "rows": 1, "sha256": file_sha256(candidates)},
                    "cohort_positions": {"path": positions.as_posix(), "rows": 1, "sha256": file_sha256(positions)},
                },
            }
            record = {
                "observation_date": "2026-07-20", "fresh_oos_eligible": True,
                "cohort_origin": "FRESH_SAME_DAY_POST_CLOSE", "active_candidate_count": 1,
                "cohort_candidates_sha256": file_sha256(candidates),
                "cohort_positions_sha256": file_sha256(positions),
            }
            validated = validate_cohort_evaluation_identity(
                manifest, record, spec_path=spec, registry_manifest_path=registry,
                registry_content_sha256="active-registry-hash", active_candidate_count=1,
            )
            self.assertEqual(validated["cohort_candidates"], (candidates, 1))

            changed = dict(manifest)
            changed["inputs"] = {**manifest["inputs"], "registry_content_sha256": "rewritten"}
            with self.assertRaisesRegex(ValueError, "frozen registry content changed"):
                validate_cohort_evaluation_identity(
                    changed, record, spec_path=spec, registry_manifest_path=registry,
                    registry_content_sha256="active-registry-hash", active_candidate_count=1,
                )

    def test_research_track_summary_keeps_dynamic_k_separate_from_migration(self):
        summary = pd.DataFrame([
            {
                "research_track": "portfolio_optimization", "holding_count": 4,
                "registered_fresh_cohorts": 0, "mature_fresh_cohorts": 0,
                "policy_gate_ready": False, "policy_gate_passed": False, "promotion_allowed": False,
            },
            {
                "research_track": "portfolio_optimization", "holding_count": 6,
                "registered_fresh_cohorts": 0, "mature_fresh_cohorts": 0,
                "policy_gate_ready": False, "policy_gate_passed": False, "promotion_allowed": False,
            },
            {
                "research_track": "migration_control", "holding_count": 9,
                "registered_fresh_cohorts": 0, "mature_fresh_cohorts": 0,
                "policy_gate_ready": False, "policy_gate_passed": False, "promotion_allowed": False,
            },
        ])
        result = summarize_research_tracks(summary).set_index("research_track")
        self.assertEqual(result.loc["portfolio_optimization", "observed_holding_counts"], "4;6")
        self.assertEqual(result.loc["portfolio_optimization", "active_candidate_count"], 2)
        self.assertIn("NOT_FIXED_CARDINALITY", result.loc["portfolio_optimization", "target_cardinality_semantics"])
        self.assertIn("NOT_TARGET_CARDINALITY", result.loc["migration_control", "target_cardinality_semantics"])

    def test_readiness_does_not_count_nonexecutable_maturity_as_execution_evidence(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D", "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "selection_rationale": "test_dynamic_k_return",
        }])
        evaluations = pd.DataFrame([
            {
                "registry_entry_id": "FWD_ONE", "fresh_oos_eligible": True,
                "mature": True, "execution_status": status,
                "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "observation_regime": regime, "target_012922_mature": True,
            }
            for status, regime in [
                ("MATURE_EXECUTABLE", "BULL"),
                ("ENTRY_CASH_BUFFER_FAILED", "BEAR"),
            ]
        ])
        summary = summarize_forward_readiness(active, evaluations, {
            "minimum_fresh_mature_cohorts": 2, "minimum_distinct_regimes": 2,
        }).iloc[0]
        self.assertTrue(summary["continuous_evidence_ready"])
        self.assertFalse(summary["execution_evidence_ready"])
        self.assertFalse(summary["incumbent_gate_ready"])
        self.assertEqual(summary["execution_failed_mature_fresh_cohorts"], 1)

    def test_cohort_constraint_failure_is_not_execution_evidence(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D", "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "selection_rationale": "test_dynamic_k_return",
        }])
        evaluations = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "fresh_oos_eligible": True,
            "mature": True, "execution_status": "MATURE_EXECUTABLE",
            "cohort_execution_track_status": "COHORT_WHOLE_LOT_NONCOMPLIANT",
            "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
            "observation_regime": "BULL", "target_012922_mature": True,
        }])
        summary = summarize_forward_readiness(
            active, evaluations,
            {"minimum_fresh_mature_cohorts": 1, "minimum_distinct_regimes": 1},
        ).iloc[0]
        self.assertTrue(summary["continuous_evidence_ready"])
        self.assertFalse(summary["execution_evidence_ready"])
        self.assertEqual(summary["execution_failed_mature_fresh_cohorts"], 1)

    def test_pre_registered_policy_uses_both_tracks_and_target_distance(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D", "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "selection_rationale": "test_dynamic_k_return",
        }])
        rows = []
        for regime in ("BULL", "BEAR"):
            row = {
                "registry_entry_id": "FWD_ONE", "fresh_oos_eligible": True,
                "mature": True, "execution_status": "MATURE_EXECUTABLE",
                "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "observation_regime": regime, "target_012922_mature": True,
                "target_012922_return": 0.20, "target_012922_max_drawdown": 0.10,
            }
            for prefix in ("continuous", "execution"):
                row.update({
                    f"{prefix}_return": 0.21,
                    f"{prefix}_control_return": 0.10,
                    f"{prefix}_return_delta_vs_original_8": 0.11,
                    f"{prefix}_max_drawdown": 0.11,
                    f"{prefix}_control_max_drawdown": 0.20,
                    f"{prefix}_drawdown_cost_vs_original_8": -0.09,
                })
            rows.append(row)
        summary = summarize_forward_readiness(
            active, pd.DataFrame(rows),
            {"minimum_fresh_mature_cohorts": 2, "minimum_distinct_regimes": 2},
            {"policy_gate": {"require_at_least_one_strict_incumbent_improvement": True}},
        ).iloc[0]
        self.assertTrue(summary["policy_gate_ready"])
        self.assertTrue(summary["policy_gate_passed"])
        self.assertEqual(summary["research_track"], "portfolio_optimization")
        self.assertEqual(summary["holding_count_interpretation"], "dynamic_k_portfolio_structure")
        self.assertEqual(summary["holding_count"], 4)
        self.assertGreater(summary["continuous_target_012922_distance_improvement"], 0)
        self.assertFalse(summary["promotion_allowed"])

    def test_target_l1_improvement_cannot_hide_one_worse_dimension(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D",
            "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "selection_rationale": "componentwise_gate_test",
        }])
        rows = []
        for regime in ("BULL", "BEAR"):
            row = {
                "registry_entry_id": "FWD_ONE", "fresh_oos_eligible": True,
                "mature": True, "execution_status": "MATURE_EXECUTABLE",
                "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "observation_regime": regime, "target_012922_mature": True,
                "target_012922_return": 0.20, "target_012922_max_drawdown": 0.10,
            }
            for prefix in ("continuous", "execution"):
                row.update({
                    f"{prefix}_return": 0.20,
                    f"{prefix}_control_return": 0.00,
                    f"{prefix}_return_delta_vs_original_8": 0.20,
                    f"{prefix}_max_drawdown": 0.11,
                    f"{prefix}_control_max_drawdown": 0.10,
                    f"{prefix}_drawdown_cost_vs_original_8": 0.01,
                })
            rows.append(row)
        summary = summarize_forward_readiness(
            active, pd.DataFrame(rows),
            {"minimum_fresh_mature_cohorts": 2, "minimum_distinct_regimes": 2},
            {"policy_gate": {
                "paired_return_p50_minimum": 0.0,
                "paired_return_p10_minimum": 0.0,
                "paired_drawdown_cost_p50_maximum": 0.02,
                "paired_drawdown_cost_p90_maximum": 0.02,
                "target_012922_componentwise_not_worse_than_original_8": True,
                "require_at_least_one_strict_target_dimension_improvement": True,
                "require_at_least_one_strict_incumbent_improvement": True,
            }},
        ).iloc[0]
        self.assertGreater(summary["continuous_target_012922_distance_improvement"], 0)
        self.assertFalse(summary["continuous_target_012922_componentwise_passed"])
        self.assertFalse(summary["continuous_target_012922_componentwise_gate_passed"])
        self.assertFalse(summary["policy_gate_passed"])
        self.assertFalse(summary["policy_target_012922_scalar_l1_used_for_admission"])

    def test_paired_continuous_and_execution_tracks(self):
        candidate = pd.DataFrame([
            {"ticker": "A", "target_weight": 0.5, "cohort_whole_lot_shares": 20},
            {"ticker": "B", "target_weight": 0.5, "cohort_whole_lot_shares": 20},
        ])
        control = pd.DataFrame([
            {"ticker": "A", "target_weight": 1.0, "cohort_whole_lot_shares": 40},
        ])
        prices = {
            "A": _prices([100, 100, 100], [100, 100, 100]),
            "B": _prices([100, 100, 100], [100, 110, 120]),
        }
        target = pd.DataFrame({"Close": [1.0, 1.02, 1.04]}, index=pd.date_range("2026-07-21", periods=3, freq="B"))
        result = evaluate_candidate_pair(
            candidate, control, prices, observation_date="2026-07-20", horizon=3,
            standardized_cash=5000, minimum_cash_buffer=100, transaction_cost_bps=10,
            target_nav=target,
        )
        self.assertTrue(result["mature"])
        self.assertGreater(result["continuous_return_delta_vs_original_8"], 0)
        self.assertEqual(result["execution_status"], "MATURE_EXECUTABLE")
        self.assertGreater(result["execution_return_delta_vs_original_8"], 0)
        self.assertTrue(result["target_012922_mature"])
        self.assertFalse(result["promotion_allowed"])

    def test_policy_gate_uses_preregistered_numeric_thresholds(self):
        active = pd.DataFrame([{
            "registry_entry_id": "FWD_ONE", "candidate_id": "one",
            "selection_role": "RETURN", "action_scope": "VARIABLE_CARDINALITY",
            "research_track": "portfolio_optimization",
            "holding_count_interpretation": "dynamic_k_portfolio_structure",
            "candidate_tickers": "A;B;C;D", "frozen_target_weights": "A:0.25;B:0.25;C:0.25;D:0.25",
            "selection_rationale": "test_dynamic_k_return",
        }])
        rows = []
        for regime in ("BULL", "BEAR"):
            row = {
                "registry_entry_id": "FWD_ONE", "fresh_oos_eligible": True,
                "mature": True, "execution_status": "MATURE_EXECUTABLE",
                "cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "original_8_cohort_execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT",
                "observation_regime": regime, "target_012922_mature": True,
                "target_012922_return": 0.20, "target_012922_max_drawdown": 0.10,
            }
            for prefix in ("continuous", "execution"):
                row.update({
                    f"{prefix}_return": 0.21, f"{prefix}_control_return": 0.20,
                    f"{prefix}_return_delta_vs_original_8": 0.01,
                    f"{prefix}_max_drawdown": 0.10, f"{prefix}_control_max_drawdown": 0.10,
                    f"{prefix}_drawdown_cost_vs_original_8": 0.0,
                })
            rows.append(row)
        result = summarize_forward_readiness(
            active, pd.DataFrame(rows),
            {"minimum_fresh_mature_cohorts": 2, "minimum_distinct_regimes": 2},
            {"policy_gate": {
                "paired_return_p50_minimum": 0.02,
                "paired_return_p10_minimum": 0.0,
                "paired_drawdown_cost_p50_maximum": 0.0,
                "paired_drawdown_cost_p90_maximum": 0.0,
                "target_012922_distance_not_worse_than_original_8": True,
                "require_at_least_one_strict_incumbent_improvement": True,
            }},
        ).iloc[0]
        self.assertTrue(result["policy_gate_ready"])
        self.assertFalse(result["policy_gate_passed"])
        self.assertEqual(result["policy_paired_return_p50_minimum"], 0.02)

    def test_waiting_does_not_emit_outcome_metrics(self):
        positions = pd.DataFrame([{"ticker": "A", "target_weight": 1.0, "cohort_whole_lot_shares": 1}])
        result = evaluate_candidate_pair(
            positions, positions, {"A": _prices([100], [101])}, observation_date="2026-07-20",
            horizon=126, standardized_cash=5000, minimum_cash_buffer=100, transaction_cost_bps=10,
        )
        self.assertEqual(result["status"], "WAITING_FOR_MATURITY")
        self.assertEqual(result["execution_status"], "WAITING_FOR_MATURITY")
        self.assertFalse(result["target_012922_mature"])
        self.assertNotIn("continuous_return", result)

    def test_target_012922_requires_near_aligned_entry_and_exit(self):
        candidate = pd.DataFrame([{"ticker": "A", "target_weight": 1.0, "cohort_whole_lot_shares": 40}])
        prices = {"A": _prices([100] * 8, [100] * 8)}
        late_target = pd.DataFrame(
            {"Close": [1.0, 1.1]},
            index=pd.DatetimeIndex(["2026-07-28", "2026-07-30"]),
        )
        result = evaluate_candidate_pair(
            candidate, candidate, prices, observation_date="2026-07-20", horizon=8,
            standardized_cash=5000, minimum_cash_buffer=100, transaction_cost_bps=10,
            target_nav=late_target,
        )
        self.assertFalse(result["target_012922_mature"])

    def test_entry_gap_cash_failure_is_not_resized(self):
        candidate = pd.DataFrame([{"ticker": "A", "target_weight": 1.0, "cohort_whole_lot_shares": 49}])
        control = pd.DataFrame([{"ticker": "B", "target_weight": 1.0, "cohort_whole_lot_shares": 40}])
        prices = {
            "A": _prices([110, 110], [110, 111]),
            "B": _prices([100, 100], [100, 100]),
        }
        result = evaluate_candidate_pair(
            candidate, control, prices, observation_date="2026-07-20", horizon=2,
            standardized_cash=5000, minimum_cash_buffer=100, transaction_cost_bps=10,
        )
        self.assertEqual(result["execution_status"], "ENTRY_CASH_BUFFER_FAILED")
        self.assertFalse(result["candidate_execution_entry_cash_buffer_passed"])
        self.assertNotIn("execution_return", result)


if __name__ == "__main__":
    unittest.main()
