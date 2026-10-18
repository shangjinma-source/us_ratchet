from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from backtest.ndx_experiment_analysis import (
    NdxExperimentAnalysisError,
    SHAPE_KEYS,
    _apply_concentration_guard,
    _concentration_baselines,
    _paired_effects,
    _phase_decision,
    _read_verified_bundle,
    _research_seeds,
    _selection_concentration,
    _split_phase_evidence,
)
from data.ndx_history import NdxHistoryMeta


def _shape(**overrides) -> dict:
    values = {
        "lookback_years": 2.0,
        "top_n": 4,
        "weight_mode": "equal",
        "rebalance_months": 6,
        "safe_weight": 0.0,
        "max_weight": 0.25,
        "trade_cost_bps": 10.0,
    }
    values.update(overrides)
    return values


class NdxExperimentAnalysisTests(unittest.TestCase):
    def test_concentration_guard_uses_the_selection_audit_tolerance(self):
        candidate = pd.DataFrame([{"profile_id": "envelope"}])
        incumbent = {"effective_n": 8.0, "top1": 0.16, "top3": 0.44}
        within_roundoff = pd.DataFrame([{
            "profile_id": "envelope",
            "effective_n_p10": 8.0 - 5e-9,
            "top1_p90": 0.16 + 5e-9,
            "top3_p90": 0.44 + 5e-9,
        }])

        passed = _apply_concentration_guard(
            candidate,
            within_roundoff,
            shape_keys=["profile_id"],
            incumbent=incumbent,
        )

        self.assertTrue(bool(passed.loc[0, "concentration_guard_passed"]))
        outside_tolerance = within_roundoff.copy()
        outside_tolerance.loc[0, "top3_p90"] = 0.44 + 2e-8
        failed = _apply_concentration_guard(
            candidate,
            outside_tolerance,
            shape_keys=["profile_id"],
            incumbent=incumbent,
        )
        self.assertFalse(bool(failed.loc[0, "concentration_guard_passed"]))

    def test_verified_bundle_rejects_incomplete_jobs_before_reading_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(
                json.dumps({"completed_jobs": 8, "planned_jobs": 9}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(NdxExperimentAnalysisError, "incomplete"):
                _read_verified_bundle(root)

    def test_verified_bundle_rejects_tampered_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            filenames = {
                "candidates": "candidates.csv",
                "windows": "windows.csv",
                "selections": "selections.csv",
                "gate_failures": "gate_failures.csv",
                "versions": "versions.csv",
            }
            evidence = {}
            for key, filename in filenames.items():
                path = root / filename
                row = {"value": key}
                if key == "candidates":
                    row["target_benchmark"] = "012922"
                pd.DataFrame([row]).to_csv(path, index=False)
                evidence[key] = {
                    "filename": filename,
                    "rows": 1,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            manifest = {
                "completed_jobs": 1,
                "planned_jobs": 1,
                "failed_jobs": 0,
                "candidate_rows": 1,
                "window_rows": 1,
                "selection_rows": 1,
                "selection_constraint_audit": {"passed": True},
                "phase_version_consistency": {
                    "training": {"comparison_ready": True}
                },
                "evidence_files": evidence,
            }
            (root / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            _, frames = _read_verified_bundle(root)
            self.assertEqual(frames["candidates"].loc[0, "target_benchmark"], "012922")
            pd.DataFrame([{"value": "changed"}]).to_csv(
                root / "candidates.csv", index=False
            )

            with self.assertRaisesRegex(NdxExperimentAnalysisError, "fingerprint mismatch"):
                _read_verified_bundle(root)

    def test_selection_concentration_is_computed_from_each_rebalance(self):
        rows = [
            {
                **_shape(),
                "selection_date": "2020-01-02",
                "report_date": "2019-09-30",
                "available_date": "2019-11-30",
                "accession_number": "report-a",
                "weights": "AAPL:0.25;AMZN:0.25;GOOG:0.25;MSFT:0.25",
                "tickers": "AAPL;AMZN;GOOG;MSFT",
                "churn": 0.5,
            },
            {
                **_shape(),
                "selection_date": "2020-02-03",
                "report_date": "2019-09-30",
                "available_date": "2019-11-30",
                "accession_number": "report-a",
                "weights": "AAPL:0.4;AMZN:0.3;GOOG:0.2;MSFT:0.1",
                "tickers": "AAPL;AMZN;GOOG;MSFT",
                "churn": 0.7,
            },
            {
                **_shape(),
                "selection_date": "2020-02-03",
                "report_date": "2019-09-30",
                "available_date": "2019-11-30",
                "accession_number": "report-a",
                "weights": "AAPL:0.4;AMZN:0.3;GOOG:0.2;MSFT:0.1",
                "tickers": "AAPL;AMZN;GOOG;MSFT",
                "churn": 0.9,
            },
            {
                **_shape(trade_cost_bps=25.0),
                "selection_date": "2020-01-02",
                "report_date": "2019-09-30",
                "available_date": "2019-11-30",
                "accession_number": "report-a",
                "weights": "AAPL:1.0",
                "tickers": "AAPL",
                "churn": 1.0,
            },
        ]

        result = _selection_concentration(
            pd.DataFrame(rows), canonical_cost_bps=10.0
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "selection_rows"], 2)
        self.assertEqual(result.loc[0, "window_conditioned_rows"], 3)
        self.assertEqual(result.loc[0, "duplicate_window_rows"], 1)
        self.assertAlmostEqual(result.loc[0, "effective_n_p50"], 3.6666666667)
        self.assertAlmostEqual(result.loc[0, "top1_p50"], 0.325)
        self.assertAlmostEqual(result.loc[0, "top3_p50"], 0.825)
        self.assertAlmostEqual(result.loc[0, "window_conditioned_churn_p50"], 0.7)

    def test_selection_concentration_blends_incumbent_anchor_risk_targets(self):
        row = {
            **_shape(),
            "challenger_sleeve_weight": 0.20,
            "selection_date": "2020-01-02",
            "report_date": "2019-09-30",
            "available_date": "2019-11-30",
            "accession_number": "report-a",
            "weights": "A:1.0",
            "tickers": "A",
            "churn": 0.0,
        }

        result = _selection_concentration(
            pd.DataFrame([row]),
            canonical_cost_bps=10.0,
            incumbent_weights={"B": 0.50, "C": 0.50},
            incumbent_safe_weight=0.25,
        )

        self.assertAlmostEqual(result.loc[0, "effective_n_p50"], 1.0 / 0.34375)
        self.assertAlmostEqual(result.loc[0, "top1_p50"], 0.375)
        self.assertAlmostEqual(result.loc[0, "top3_p50"], 1.0)

    def test_research_seeds_are_never_validation_candidates(self):
        rows = []
        for index, values in enumerate(
            [
                (0.01, 3.0, False),
                (-0.01, 1.5, False),
                (-0.02, 3.0, True),
                (-0.03, 1.0, True),
            ]
        ):
            excess, turnover, concentration_passed = values
            rows.append({
                **_shape(top_n=4 + index),
                "target_excess_p50": excess,
                "target_excess_p10": excess - 0.05,
                "target_dd_relief_p50": -0.01,
                "turnover_x_p50": turnover,
                "concentration_guard_passed": concentration_passed,
            })

        seeds = _research_seeds(pd.DataFrame(rows))

        self.assertEqual(len(seeds), 4)
        self.assertEqual(
            set(seeds["seed_status"]), {"STRUCTURE_ONLY_NOT_VALIDATION"}
        )
        self.assertFalse(seeds["locked_validation_eligible"].any())
        self.assertFalse(seeds["promotion_allowed"].any())

    def test_locked_validation_failure_overrides_training_qualification(self):
        decision, direction, next_research = _phase_decision(
            objective_compatible=True,
            profile_experiment=True,
            component_family="incumbent_anchor",
            training_qualified=True,
            locked_validation_executed=True,
            locked_validation_passed=False,
        )

        self.assertEqual(decision, "LOCKED_VALIDATION_FAILED_NO_PROMOTION")
        self.assertEqual(direction, "ACTIVE_ITERATION_VALIDATION_FAILED")
        self.assertTrue(any("held-out period" in item for item in next_research))
        self.assertTrue(any("incumbent" in item for item in next_research))

    def test_locked_validation_pass_requires_final_review(self):
        decision, direction, next_research = _phase_decision(
            objective_compatible=True,
            profile_experiment=True,
            component_family="incumbent_anchor",
            training_qualified=True,
            locked_validation_executed=True,
            locked_validation_passed=True,
        )

        self.assertEqual(
            decision,
            "LOCKED_VALIDATION_PASSED_REQUIRES_FINAL_REVIEW",
        )
        self.assertEqual(direction, "VALIDATION_PASSED_REVIEW_REQUIRED")
        self.assertTrue(any("explicit user confirmation" in item for item in next_research))

    def test_locked_validation_rows_never_enter_training_tables(self):
        candidates = pd.DataFrame([
            {"phase_id": "training", "phase_role": "exploratory_training"},
            {"phase_id": "validation", "phase_role": "locked_validation"},
        ])
        windows = pd.DataFrame([
            {"phase_id": "training", "row": "train-window"},
            {"phase_id": "validation", "row": "locked-window"},
        ])
        selections = pd.DataFrame([
            {"phase_id": "training", "row": "train-selection"},
            {"phase_id": "validation", "row": "locked-selection"},
        ])

        split = _split_phase_evidence(candidates, windows, selections)

        self.assertEqual(split[0]["phase_id"].tolist(), ["training"])
        self.assertEqual(split[1]["phase_id"].tolist(), ["validation"])
        self.assertEqual(split[2]["row"].tolist(), ["train-window"])
        self.assertEqual(split[3]["row"].tolist(), ["locked-window"])
        self.assertEqual(split[4]["row"].tolist(), ["train-selection"])
        self.assertEqual(split[5]["row"].tolist(), ["locked-selection"])

    def test_concentration_baseline_uses_manifest_version_from_history_meta(self):
        history = pd.DataFrame([
            {
                "report_date": "2025-12-31",
                "available_date": "2026-02-01",
                "ticker": "GOOG",
                "weight": 0.3,
            },
            {
                "report_date": "2025-12-31",
                "available_date": "2026-02-01",
                "ticker": "GOOGL",
                "weight": 0.2,
            },
            {
                "report_date": "2025-12-31",
                "available_date": "2026-02-01",
                "ticker": "MSFT",
                "weight": 0.5,
            },
        ])
        meta = NdxHistoryMeta(
            source="test",
            rows=3,
            report_count=1,
            cached=True,
            manifest={"version_id": "ndx_history:test"},
        )
        cfg = SimpleNamespace(
            symbols=[
                SimpleNamespace(ticker="AAPL", cap_total=0.6),
                SimpleNamespace(ticker="MSFT", cap_total=0.4),
            ]
        )

        with patch(
            "backtest.ndx_experiment_analysis.get_ndx_point_in_time_history",
            return_value=(history, meta),
        ):
            baseline, incumbent = _concentration_baselines(cfg)

        self.assertEqual(incumbent["history_version_id"], "ndx_history:test")
        self.assertAlmostEqual(incumbent["effective_n"], 1.0 / 0.52)
        self.assertAlmostEqual(baseline.iloc[0]["effective_n"], 2.0)
        self.assertEqual(set(SHAPE_KEYS), set(_shape()))

    def test_declared_profile_baseline_produces_cost_and_window_paired_effects(self):
        candidate_rows = []
        window_rows = []
        for cost in (5.0, 10.0):
            job_id = f"job-{cost:g}"
            for profile_id, excess in (("seed", 0.20), ("quality", 0.25)):
                candidate_rows.append({
                    "phase_id": "training",
                    "job_id": job_id,
                    "profile_id": profile_id,
                    "lookback_years": 1.0,
                    "trade_cost_bps": cost,
                    "target_excess_p50": excess,
                    "target_excess_p10": excess - 0.05,
                    "target_dd_relief_p50": 0.01,
                    "target_dd_relief_p10": -0.02,
                    "turnover_x_p50": 4.0,
                })
                window_rows.append({
                    "phase_id": "training",
                    "job_id": job_id,
                    "start": "2022-01-11",
                    "end": "2024-06-28",
                    "profile_id": profile_id,
                    "strategy_xirr": excess,
                    "target_excess_xirr": excess - 0.10,
                    "turnover_x": 4.0,
                })

        effects = _paired_effects(
            pd.DataFrame(candidate_rows),
            pd.DataFrame(window_rows),
            baseline_id="seed",
        )

        cost_effect = effects[
            effects["evidence_level"].eq("cost_rollup")
            & effects["metric"].eq("target_excess_p50")
        ].iloc[0]
        window_effect = effects[
            effects["evidence_level"].eq("paired_window")
            & effects["metric"].eq("target_excess_xirr")
        ].iloc[0]
        self.assertEqual(cost_effect["pairs"], 2)
        self.assertAlmostEqual(cost_effect["delta_p50"], 0.05)
        self.assertEqual(window_effect["pairs"], 2)
        self.assertAlmostEqual(window_effect["improvement_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
