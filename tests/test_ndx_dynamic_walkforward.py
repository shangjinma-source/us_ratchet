from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backtest.ndx_dynamic_whole_lot_path import simulate_dynamic_security_id_whole_lot_path
from data.versioning import file_sha256
from scripts.ndx_dynamic_walkforward import (
    NdxDynamicWalkforwardError,
    _canonical_runner_script_input,
    _load_completed_replay_candidates,
    _load_execution_and_valuation_prices,
    _simulate_consumed_path,
    _summary_row,
    _target_metrics_and_trace,
    _user_preference_reference_diagnostics,
    _with_canonical_runner_provenance,
)


class DynamicWalkforwardTests(unittest.TestCase):
    def test_manifest_runner_provenance_uses_canonical_script_and_current_hash(self):
        provenance = _canonical_runner_script_input()
        expected = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "ndx_dynamic_walkforward.py"
        ).resolve()
        self.assertEqual(Path(provenance["path"]), expected)
        self.assertEqual(provenance["sha256"], file_sha256(expected))
        manifest_inputs = _with_canonical_runner_provenance({"config": {"test": True}})
        self.assertEqual(manifest_inputs["runner_script"], provenance)
        self.assertEqual(manifest_inputs["config"], {"test": True})
        with self.assertRaisesRegex(NdxDynamicWalkforwardError, "reserved"):
            _with_canonical_runner_provenance({"runner_script": {}})

    def test_summary_keeps_single_path_out_of_admission(self):
        summary = {
            "maximum_price_date_used": "2024-05-31",
            "valuation_start_date": "2023-04-03",
            "valuation_end_date": "2024-05-31",
            "path_trading_session_count": 252,
            "rebalance_count": 12,
            "minimum_target_k": 3,
            "maximum_target_k": 7,
            "k_path": [3, 5, 7],
            "path_return_net": 0.2,
            "path_annualized_return_net": 0.2,
            "path_max_drawdown": 0.15,
            "total_transaction_cost_usd": 25.0,
        }
        row = _summary_row(
            source_batch="exact", track="strict_technology", role="RETURN",
            execution_track="whole_lot", summary=summary,
            incumbent={"path_annualized_return_net": 0.18, "path_max_drawdown": 0.14},
            target={
                "path_annualized_return_net": 0.25,
                "path_max_drawdown": 0.16,
                "target_asof_no_future_passed": True,
                "target_path_session_count": 252,
                "target_exact_source_date_count": 240,
                "target_lagged_session_count": 12,
                "target_exact_source_date_coverage_ratio": 240 / 252,
                "maximum_target_nav_lag_calendar_days": 2,
                "target_nav_freshness_threshold_registered": False,
                "target_nav_freshness_passed": None,
                "target_publication_time_known": False,
                "benchmark_alignment_role": "ASOF_DIAGNOSTIC_NOT_FRESHNESS_OR_ADMISSION",
            },
        )
        self.assertAlmostEqual(row["annualized_return_vs_original_8"], 0.02)
        self.assertAlmostEqual(row["max_drawdown_cost_vs_012922"], -0.01)
        self.assertFalse(row["single_path_scalar_target_distance_used_for_admission"])
        self.assertFalse(row["promotion_allowed"])

    def test_target_metrics_are_aligned_to_candidate_dates(self):
        path = pd.DataFrame({"date": ["2024-01-02", "2024-01-03", "2024-01-04"]})
        target = pd.DataFrame({
            "Date": ["2024-01-01", "2024-01-04"],
            "Close": [1.0, 1.1],
        })
        with TemporaryDirectory() as temporary:
            target_path = Path(temporary) / "target.csv"
            target.to_csv(target_path, index=False)
            manifest_path = target_path.with_name(target_path.name + ".manifest.json")
            manifest_path.write_text(json.dumps({
                "dataset_key": "012922",
                "dataset_type": "fund_nav",
                "completeness": "verified_against_source_record_count",
                "content_sha256": file_sha256(target_path),
                "row_count": 2,
                "source_record_count": 2,
            }), encoding="utf-8")
            metrics, trace = _target_metrics_and_trace(path, target_path)
        self.assertAlmostEqual(metrics["path_return_net"], 0.1)
        self.assertEqual(metrics["path_max_drawdown"], 0.0)
        self.assertTrue(metrics["target_asof_no_future_passed"])
        self.assertEqual(metrics["target_path_session_count"], 3)
        self.assertEqual(metrics["target_exact_source_date_count"], 1)
        self.assertEqual(metrics["target_lagged_session_count"], 2)
        self.assertAlmostEqual(metrics["target_exact_source_date_coverage_ratio"], 1 / 3)
        self.assertEqual(metrics["maximum_target_nav_lag_calendar_days"], 2)
        self.assertFalse(metrics["target_nav_freshness_threshold_registered"])
        self.assertIsNone(metrics["target_nav_freshness_passed"])
        self.assertEqual(
            metrics["benchmark_alignment_role"],
            "ASOF_DIAGNOSTIC_NOT_FRESHNESS_OR_ADMISSION",
        )
        self.assertEqual(trace["date"].tolist(), path["date"].tolist())
        self.assertEqual(
            trace["target_source_date"].tolist(),
            ["2024-01-01", "2024-01-01", "2024-01-04"],
        )
        self.assertTrue(trace["target_asof_no_future_passed"].all())
        self.assertTrue(trace["diagnostic_only_not_admission"].all())

    def test_max_jobs_smoke_manifest_cannot_claim_complete_source_coverage(self):
        manifest = {
            "manifest_type": "ndx_cardinality_capital_replay_runner",
            "status": "CAPITAL_REPLAY_COMPLETE",
            "completed": 1,
            "planned_job_count": 1,
            "promotion_allowed": False,
            "execution_scope": {
                "only_source_batch": "",
                "only_track": "",
                "only_selection_date": "",
                "max_jobs": 1,
            },
        }
        with self.assertRaisesRegex(
            NdxDynamicWalkforwardError, "max_jobs.*cannot prove complete"
        ):
            _load_completed_replay_candidates(manifest)

    def test_loader_and_consumed_path_use_open_not_same_close(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "ABC.csv"
            raw.write_text(
                "Date,Open,High,Low,Close,Volume\n"
                "2024-01-02,90,110,80,100,1000\n"
                "2024-01-03,105,115,95,110,1000\n",
                encoding="utf-8",
            )
            sidecar = root / "ABC.csv.manifest.json"
            sidecar.write_text("{}\n", encoding="utf-8")
            inventory = root / "inventory.csv"
            pd.DataFrame([{
                "ticker": "ABC",
                "status": "FETCHED",
                "rows": 2,
                "path": raw.as_posix(),
                "sha256": file_sha256(raw),
                "sidecar_path": sidecar.as_posix(),
                "sidecar_sha256": file_sha256(sidecar),
            }]).to_csv(inventory, index=False)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({
                "manifest_type": "ndx_cardinality_whole_lot_execution_price_bundle",
                "status": "READY",
                "artifacts": {
                    "inventory": {
                        "path": inventory.as_posix(),
                        "rows": 1,
                        "sha256": file_sha256(inventory),
                    }
                },
            }), encoding="utf-8")
            execution, valuation = _load_execution_and_valuation_prices(
                manifest_path, {"ABC"}
            )

        self.assertEqual(float(execution.loc[pd.Timestamp("2024-01-02"), "ABC"]), 90.0)
        self.assertEqual(float(valuation.loc[pd.Timestamp("2024-01-02"), "ABC"]), 100.0)
        summary, _, trades, _ = _simulate_consumed_path(
            simulate_dynamic_security_id_whole_lot_path,
            valuation,
            execution,
            [{
                "decision_date": "2024-01-01",
                "execution_date": "2024-01-02",
                "targets": {
                    "security:abc": {
                        "ticker": "ABC",
                        "issuer_id": "issuer:abc",
                        "target_weight": 1.0,
                    }
                },
            }],
            initial_cash_usd=25000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date=pd.Timestamp("2024-01-03"),
        )
        self.assertTrue(summary["separate_execution_price_channel"])
        self.assertTrue(summary["next_session_execution_required"])
        self.assertTrue(summary["issuer_trace_required"])
        self.assertEqual(float(trades.iloc[0]["price_usd"]), 90.0)

    def test_user_preference_failures_remain_visible_but_not_admissible(self):
        candidates = pd.DataFrame([
            {
                "selection_date": "2023-04-03",
                "tickers": "AMAT;AVGO;CDNS;GOOG",
                "weights": "AMAT:0.25;AVGO:0.25;CDNS:0.25;GOOG:0.25",
                "weight_spec": "equal_weight",
                "portfolio_id": "preference-a",
                "declared_constraints_passed": False,
                "constraint_failure_reasons": "WHOLE_LOT_EXECUTABILITY_FAILED",
            },
            {
                "selection_date": "2023-07-03",
                "tickers": "AMAT;AVGO;CDNS;GOOG",
                "weights": "AMAT:0.25;AVGO:0.25;CDNS:0.25;GOOG:0.25",
                "weight_spec": "equal_weight",
                "portfolio_id": "preference-b",
                "declared_constraints_passed": True,
                "constraint_failure_reasons": "",
            },
        ])
        rows = _user_preference_reference_diagnostics(
            candidates, source_batch="exact", track="strict_technology"
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["reason"], "WHOLE_LOT_EXECUTABILITY_FAILED")
        self.assertFalse(rows[0]["reference_path_date_eligible"])
        self.assertFalse(rows[1]["complete_reference_path_available"])
        self.assertTrue(all(row["reference_role"] == "REFERENCE_NOT_FIXED_ANSWER" for row in rows))
        self.assertTrue(all(row["admission_allowed"] is False for row in rows))


if __name__ == "__main__":
    unittest.main()
