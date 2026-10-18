from __future__ import annotations

import json
import copy
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from backtest.ndx_experiment_lab import (
    NdxExperimentLabError,
    _construction_contract_error,
    candidate_diagnosis,
    checkpoint_payload,
    expand_experiment_jobs,
    load_experiment_spec,
    selection_constraint_audit,
    validate_checkpoint,
    write_export_bundle,
)


TEST_TMP_ROOT = Path(__file__).resolve().parents[1] / "data" / "cache" / "test_tmp"
TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def _workspace_test_dir():
    path = TEST_TMP_ROOT / f"case_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _spec_text(*, locked: bool = False) -> str:
    role = "locked_validation" if locked else "exploratory_training"
    extra = "locked_candidates: []" if locked else "sweep:\n      lookback_years: [1, 2]\n      trade_cost_bps: [5, 10]"
    return f"""schema_version: 1
experiment_id: ndx_lab_test
research_question: deterministic test
research_only: true
candidate_assets: nasdaq_100_individual_securities
qqq_role: benchmark_only_not_candidate
direction_status: active_iteration
defaults:
  local_only: true
  include_samples: true
phases:
  - phase_id: phase_a
    enabled: true
    role: {role}
    start: 2019-11-30
    end: 2022-01-10
    target: QQQ
    min_years: 1
    shared_grid:
      top_ns: [4, 6]
      weight_modes: [equal]
      safe_weights: [0.0]
      rebalance_months: [6]
      max_weights: [0.25]
    {extra}
"""


def _load_spec(tmp: str, *, locked: bool = False) -> dict:
    path = Path(tmp) / "experiment.yaml"
    path.write_text(_spec_text(locked=locked), encoding="utf-8")
    return load_experiment_spec(path)


def _result() -> dict:
    strategy = {"xirr": 0.20, "maxdd": 0.25, "final": 200.0}
    target = {"xirr": 0.30, "maxdd": 0.20, "final": 250.0}
    qqq = {"xirr": 0.199, "maxdd": 0.21, "final": 199.0}
    incumbent = {"xirr": 0.28, "maxdd": 0.19, "final": 240.0}
    return {
        "summary": {
            "candidate_assets": "Nasdaq-100 individual securities",
            "qqq_role": "benchmark_only_not_candidate",
            "target_benchmark": "QQQ",
        },
        "data_manifest": {
            "ndx_history": {"version_id": "ndx_history:test"},
            "price_universe": {"version_id": "ndx_prices:test"},
            "target_nav": {"version_id": "target:test"},
            "future_data_guard": "available_date <= selection_date",
        },
        "rows": [{
            "basket": "top4_equal",
            "lookback_years": 1.0,
            "top_n": 4,
            "weight_mode": "equal",
            "rebalance_months": 6,
            "safe_weight": 0.0,
            "max_weight": 0.25,
            "trade_cost_bps": 5.0,
            "windows": 1,
            "range": ["2020-01-02", "2020-01-02"],
            "win_rate": 0.0,
            "dd_win_rate": 0.0,
            "excess_p50": -0.10,
            "excess_p10": -0.10,
            "dd_relief_p50": -0.05,
            "dd_relief_p10": -0.05,
            "qqq_win_rate": 1.0,
            "qqq_excess_p50": 0.001,
            "qqq_excess_p10": 0.001,
            "qqq_dd_relief_p50": -0.04,
            "qqq_dd_relief_p10": -0.04,
            "target_envelope": {
                "passed": False,
                "return_passed": False,
                "risk_passed": False,
                "classification": "RETURN_NOT_ATTRACTIVE",
                "checks": [{"name": "target_win_rate", "passed": False}],
            },
            "incumbent_guard": {
                "passed": False,
                "checks": [{"name": "xirr_margin_p50_vs_incumbent", "passed": False}],
                "margins": {"xirr_p50_vs_incumbent": -0.08},
            },
            "admission_passed": False,
            "distribution": {
                "strategy_xirr": {"p10": 0.20, "p50": 0.20, "p90": 0.20},
                "strategy_maxdd": {"p50": 0.25, "p90": 0.25},
            },
            "tickers_observed": ["AAPL", "AMZN", "GOOG", "MSFT"],
        }],
        "samples": [{
            "start": "2020-01-02",
            "end": "2022-01-10",
            "basket": "top4_equal",
            "lookback_years": 1.0,
            "top_n": 4,
            "weight_mode": "equal",
            "rebalance_months": 6,
            "safe_weight": 0.0,
            "max_weight": 0.25,
            "trade_cost_bps": 5.0,
            "strategy": strategy,
            "benchmark": target,
            "qqq": qqq,
            "incumbent": incumbent,
            "excess_xirr": -0.10,
            "dd_relief": -0.05,
            "qqq_excess_xirr": 0.001,
            "qqq_dd_relief": -0.04,
            "min_weight": 0.02,
            "tickers_observed": ["AAPL", "AMZN", "GOOG", "MSFT"],
            "selections": [{
                "date": "2020-01-02",
                "trigger": "scheduled",
                "report_date": "2019-09-30",
                "available_date": "2019-11-30",
                "accession_number": "test",
                "expected_count": 100,
                "expected_issuer_count": 99,
                "price_count": 100,
                "scored_count": 99,
                "price_coverage": 1.0,
                "score_coverage": 0.99,
                "tickers": ["AAPL", "AMZN", "GOOG", "MSFT"],
                "weights": {
                    "AAPL": 0.25,
                    "AMZN": 0.25,
                    "GOOG": 0.25,
                    "MSFT": 0.25,
                },
                "churn": 1.0,
                "turnover": 100.0,
                "cost": 0.05,
            }],
        }],
        "current_selection": {"available": False},
        "current_selection_best_qqq": {"available": False},
        "skipped": [],
    }


def _attach_quality_sic_evidence(result: dict) -> dict:
    profile_fields = {
        "profile_id": "quality_sic",
        "selection_mode": "rank",
        "fundamental_score_weight": 0.25,
        "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
        "max_names_per_sic4": 2,
        "max_names_per_sic2": 2,
        "sic4_max_weight": 0.50,
        "sic2_max_weight": 0.60,
    }
    result["rows"][0].update(profile_fields)
    result["samples"][0].update(profile_fields)
    result["data_manifest"]["quality_scores"] = {
        "version_id": "ndx_quality:test",
        "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
    }
    selection = result["samples"][0]["selections"][0]
    selection.update({
        "selection_mode": "rank",
        "fundamental_score_weight": 0.25,
        "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
        "quality_score_coverage": 0.99,
        "quality_score_date": selection["date"],
        "quality_future_data_guard_passed": True,
        "max_names_per_sic4": 2,
        "max_names_per_sic2": 2,
        "sic4_max_weight": 0.50,
        "sic2_max_weight": 0.60,
        "sic4_by_ticker": {
            "AAPL": 7372,
            "AMZN": 7372,
            "GOOG": 3674,
            "MSFT": 2834,
        },
        "sic2_by_ticker": {
            "AAPL": "73",
            "AMZN": "73",
            "GOOG": "36",
            "MSFT": "28",
        },
        "sic4_weights": {"7372": 0.50, "3674": 0.25, "2834": 0.25},
        "sic2_weights": {"73": 0.50, "36": 0.25, "28": 0.25},
        "rejected_sic_tickers": [],
        "rejected_sic_reasons": {},
    })
    return result


def _attach_valuation_evidence(result: dict) -> dict:
    fields = {
        "valuation_score_weight": 0.10,
        "valuation_policy_id": "ndx_fcf_yield_neutral_missing_v1",
    }
    result["rows"][0].update(fields)
    result["samples"][0].update(fields)
    result["data_manifest"]["valuation_scores"] = {
        "version_id": "ndx_valuation:test",
        "valuation_policy_id": "ndx_fcf_yield_neutral_missing_v1",
    }
    selection = result["samples"][0]["selections"][0]
    selection.update({
        **fields,
        "valuation_score_coverage": 1.0,
        "valuation_observed_coverage": 0.84,
        "valuation_score_date": selection["date"],
        "valuation_future_data_guard_passed": True,
        "valuation_missing_neutral_count": 16,
    })
    return result


class NdxExperimentLabTests(unittest.TestCase):
    def test_candidate_ticker_contract_treats_list_and_delimited_export_as_equal(self):
        job = {
            "params": {
                "construction_profiles": [{
                    "id": "pool_test",
                    "candidate_tickers": ["MSFT", "AAPL", "NVDA"],
                }]
            }
        }
        result = {
            "rows": [{
                "profile_id": "pool_test",
                "candidate_tickers": "AAPL;MSFT;NVDA",
            }],
            "samples": [{"profile_id": "pool_test"}],
        }

        self.assertIsNone(_construction_contract_error(job, result))
        result["rows"][0]["candidate_tickers"] = "AAPL;MSFT;AVGO"
        self.assertEqual(
            _construction_contract_error(job, result),
            "construction profile pool_test.candidate_tickers changed",
        )

    def test_construction_contract_detects_envelope_field_drift(self):
        job = {
            "params": {
                "construction_profiles": [{
                    "id": "envelope",
                    "top_weight_count": 3,
                    "top_weight_cap": 0.44265033407572385,
                    "min_effective_n": 7.766701539921048,
                }]
            }
        }
        result = {
            "rows": [{
                "profile_id": "envelope",
                "top_weight_count": 3,
                "top_weight_cap": 0.44265033407572385,
                "min_effective_n": 7.766701539921048,
            }],
            "samples": [{"profile_id": "envelope"}],
        }

        self.assertIsNone(_construction_contract_error(job, result))
        result["rows"][0]["top_weight_cap"] = 0.45
        self.assertEqual(
            _construction_contract_error(job, result),
            "construction profile envelope.top_weight_cap changed",
        )

    def test_experiment_grid_is_deterministic_and_explicit(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            first = expand_experiment_jobs(spec)
            second = expand_experiment_jobs(spec)

        self.assertEqual(len(first), 4)
        self.assertEqual(
            [job["job_sha256"] for job in first],
            [job["job_sha256"] for job in second],
        )
        self.assertTrue(all(job["expected_candidate_rows"] == 2 for job in first))
        self.assertTrue(all(job["params"]["local_only"] for job in first))

    def test_locked_validation_requires_explicit_single_shape_candidates(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp, locked=True)
            with self.assertRaisesRegex(NdxExperimentLabError, "locked_candidates"):
                expand_experiment_jobs(spec)

    def test_objective_contract_rejects_qqq_target_drift_before_running(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            spec["objective_contract"] = {
                "candidate_universe_source": "qqq_sec_nport_nasdaq100_proxy",
                "primary_target": "012922",
                "qqq_performance_role": "auxiliary_reference_only",
                "incumbent_role": "current_config_replacement_guard",
            }

            with self.assertRaisesRegex(NdxExperimentLabError, "violates primary target"):
                expand_experiment_jobs(spec)

    def test_v3_plan_keeps_012922_as_the_only_optimization_target(self):
        path = Path(__file__).resolve().parents[1] / "config" / "ndx_experiment_lab_012922_v3.yaml"
        spec = load_experiment_spec(path)
        jobs = expand_experiment_jobs(spec)

        self.assertEqual(len(jobs), 9)
        self.assertEqual({job["params"]["target"] for job in jobs}, {"012922"})
        self.assertEqual(
            {job["objective_contract"]["qqq_performance_role"] for job in jobs},
            {"auxiliary_reference_only"},
        )

    def test_v5_plan_is_narrow_quality_sic_training_with_validation_closed(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "ndx_experiment_lab_012922_v5.yaml"
        )
        spec = load_experiment_spec(path)
        jobs = expand_experiment_jobs(spec)

        self.assertEqual(len(jobs), 3)
        self.assertTrue(all(job["expected_candidate_rows"] == 5 for job in jobs))
        self.assertEqual({job["params"]["target"] for job in jobs}, {"012922"})
        self.assertEqual(
            {job["params"]["lookback_years"] for job in jobs},
            {1.0},
        )
        self.assertEqual(
            {
                profile["id"]
                for profile in jobs[0]["params"]["construction_profiles"]
            },
            {
                "seed_price_w0",
                "price_sic_guard",
                "quality25_raw",
                "quality25_sic_guard",
                "quality50_sic_guard",
            },
        )
        self.assertFalse(spec["phases"][1]["enabled"])

    def test_explicit_construction_profiles_replace_cartesian_row_count(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            spec["phases"][0]["construction_profiles"] = [
                {
                    "id": "seed_rank",
                    "top_n": 6,
                    "weight_mode": "source_weight",
                    "rebalance_months": 6,
                    "safe_weight": 0.0,
                    "max_weight": 0.35,
                },
                {
                    "id": "seed_corr_vt",
                    "top_n": 6,
                    "weight_mode": "source_weight",
                    "rebalance_months": 6,
                    "safe_weight": 0.10,
                    "max_weight": 0.35,
                    "selection_mode": "correlation_replacement",
                    "correlation_threshold": 0.75,
                    "defense_mode": "vol_target",
                },
            ]
            jobs = expand_experiment_jobs(spec)

        self.assertEqual(len(jobs), 4)
        self.assertTrue(all(job["expected_candidate_rows"] == 2 for job in jobs))
        self.assertEqual(
            [item["id"] for item in jobs[0]["params"]["construction_profiles"]],
            ["seed_rank", "seed_corr_vt"],
        )

    def test_checkpoint_rejects_explicit_profile_drift(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            profile = {
                "id": "seed_rank",
                "top_n": 4,
                "weight_mode": "equal",
                "rebalance_months": 6,
                "safe_weight": 0.0,
                "max_weight": 0.25,
            }
            spec["phases"][0]["construction_profiles"] = [profile]
            job = expand_experiment_jobs(spec)[0]
            result = _result()
            result["rows"][0]["profile_id"] = "seed_rank"
            result["samples"][0]["profile_id"] = "seed_rank"
            result["rows"][0]["max_weight"] = 0.35

            with self.assertRaisesRegex(NdxExperimentLabError, "max_weight changed"):
                checkpoint_payload(
                    job,
                    result,
                    started_at="2026-07-12T00:00:00+00:00",
                    duration_seconds=1.0,
                )

    def test_checkpoint_rejects_output_with_a_changed_primary_target(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            spec["objective_contract"] = {
                "candidate_universe_source": "qqq_sec_nport_nasdaq100_proxy",
                "primary_target": "012922",
                "qqq_performance_role": "auxiliary_reference_only",
                "incumbent_role": "current_config_replacement_guard",
            }
            spec["phases"][0]["target"] = "012922"
            job = expand_experiment_jobs(spec)[0]

            with self.assertRaisesRegex(NdxExperimentLabError, "target does not match"):
                checkpoint_payload(
                    job,
                    _result(),
                    started_at="2026-07-11T00:00:00+00:00",
                    duration_seconds=1.0,
                )

    def test_failed_shape_keeps_research_direction_active(self):
        diagnosis = candidate_diagnosis(_result()["rows"][0])

        self.assertEqual(diagnosis["shape_diagnosis"], "NEAR_QQQ_BUT_GATE_FAILED")
        self.assertEqual(diagnosis["direction_status"], "ACTIVE_ITERATION")
        self.assertFalse(diagnosis["terminal_direction_decision"])
        self.assertIn("target:target_win_rate", diagnosis["failed_checks"])

    def test_checkpoint_and_csv_excel_exports_preserve_white_box_evidence(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            job = expand_experiment_jobs(spec)[0]
            checkpoint = checkpoint_payload(
                job,
                _result(),
                started_at="2026-07-11T00:00:00+00:00",
                duration_seconds=1.25,
            )
            valid, reason = validate_checkpoint(checkpoint, job)
            self.assertTrue(valid, reason)

            output = Path(tmp) / "output"
            manifest = write_export_bundle(
                spec, [job], [checkpoint], output, write_xlsx=True
            )
            candidates = pd.read_csv(output / "candidates.csv")
            windows = pd.read_csv(output / "windows.csv")
            selections = pd.read_csv(output / "selections.csv")
            gate_failures = pd.read_csv(output / "gate_failures.csv")

            self.assertEqual(candidates.loc[0, "direction_status"], "ACTIVE_ITERATION")
            self.assertFalse(bool(candidates.loc[0, "terminal_direction_decision"]))
            self.assertEqual(candidates.loc[0, "price_version_id"], "ndx_prices:test")
            self.assertEqual(windows.loc[0, "safe_weight"], 0.0)
            self.assertTrue(bool(selections.loc[0, "future_data_guard_passed"]))
            self.assertIn("target:target_win_rate", set(gate_failures["failed_check"]))
            self.assertTrue((output / "ndx_experiment_report.xlsx").exists())
            with pd.ExcelFile(output / "ndx_experiment_report.xlsx") as workbook:
                self.assertIn("使用说明", workbook.sheet_names)
                self.assertIn("组合候选", workbook.sheet_names)
                self.assertIn("调仓明细", workbook.sheet_names)
                self.assertIn("字段字典", workbook.sheet_names)
            self.assertEqual(manifest["completed_jobs"], 1)
            self.assertEqual(manifest["evidence_files"]["candidates"]["rows"], 1)
            self.assertEqual(len(manifest["evidence_files"]["candidates"]["sha256"]), 64)
            self.assertTrue(
                manifest["phase_version_consistency"]["phase_a"]["comparison_ready"]
            )

            manifest_disk = json.loads((output / "manifest.json").read_text("utf-8"))
            self.assertFalse(manifest_disk["terminal_direction_decision"])

    def test_checkpoint_rejects_a_selection_above_its_effective_cap(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            job = expand_experiment_jobs(spec)[0]
            result = copy.deepcopy(_result())
            result["samples"][0]["selections"][0]["weights"] = {
                "AAPL": 0.40,
                "AMZN": 0.20,
                "GOOG": 0.20,
                "MSFT": 0.20,
            }
            checkpoint = checkpoint_payload(
                job,
                result,
                started_at="2026-07-11T00:00:00+00:00",
                duration_seconds=1.0,
            )

            valid, reason = validate_checkpoint(checkpoint, job)

        self.assertFalse(valid)
        self.assertIn("constraint audit", reason)

    def test_envelope_audit_recomputes_top_weight_and_effective_names(self):
        result = copy.deepcopy(_result())
        sample = result["samples"][0]
        sample.update({
            "max_weight": 0.40,
            "top_weight_count": 3,
            "top_weight_cap": 0.75,
            "min_effective_n": 4.0,
        })

        valid = selection_constraint_audit(result)

        self.assertTrue(valid["passed"])
        top_broken = copy.deepcopy(result)
        top_broken["samples"][0]["min_effective_n"] = None
        top_broken["samples"][0]["selections"][0]["weights"] = {
            "AAPL": 0.30,
            "AMZN": 0.25,
            "GOOG": 0.25,
            "MSFT": 0.20,
        }
        top_failed = selection_constraint_audit(top_broken)
        self.assertEqual(top_failed["top_weight_cap_failures"], 1)

        effective_broken = copy.deepcopy(result)
        effective_broken["samples"][0]["top_weight_cap"] = 0.90
        effective_broken["samples"][0]["selections"][0]["weights"] = {
            "AAPL": 0.40,
            "AMZN": 0.20,
            "GOOG": 0.20,
            "MSFT": 0.20,
        }
        effective_failed = selection_constraint_audit(effective_broken)
        self.assertEqual(effective_failed["effective_n_floor_failures"], 1)

    def test_candidate_pool_audit_rejects_any_holding_outside_frozen_pool(self):
        result = copy.deepcopy(_result())
        result["samples"][0]["candidate_tickers"] = "AAPL;AMZN;GOOG;NVDA"

        failed = selection_constraint_audit(result)

        self.assertFalse(failed["passed"])
        self.assertEqual(failed["candidate_pool_failures"], 1)

    def test_quality_sic_audit_recomputes_name_and_weight_caps(self):
        result = _attach_quality_sic_evidence(copy.deepcopy(_result()))

        valid = selection_constraint_audit(result)

        self.assertTrue(valid["passed"])
        broken = copy.deepcopy(result)
        selection = broken["samples"][0]["selections"][0]
        selection["sic2_by_ticker"]["GOOG"] = "73"
        failed = selection_constraint_audit(broken)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["sic2_name_cap_failures"], 1)
        self.assertEqual(failed["sic2_weight_cap_failures"], 1)

    def test_valuation_audit_requires_exact_policy_date_and_neutral_coverage(self):
        result = _attach_valuation_evidence(copy.deepcopy(_result()))

        valid = selection_constraint_audit(result)

        self.assertTrue(valid["passed"])
        self.assertEqual(valid["valuation_evidence_failures"], 0)
        self.assertEqual(valid["valuation_score_coverage_failures"], 0)
        broken = copy.deepcopy(result)
        broken["samples"][0]["selections"][0][
            "valuation_score_date"
        ] = "2019-12-31"
        failed = selection_constraint_audit(broken)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["valuation_future_data_guard_failures"], 1)

    def test_bounded_quality_replacement_audit_checks_price_pool_and_budget(self):
        result = _attach_quality_sic_evidence(copy.deepcopy(_result()))
        sample = result["samples"][0]
        selection = sample["selections"][0]
        for target in (result["rows"][0], sample, selection):
            target.update({
                "fundamental_score_weight": 0.0,
                "quality_selection_mode": "bounded_challenge",
                "quality_challenge_pool_size": 8,
                "max_quality_replacements": 1,
            })
        pool = [
            "AAPL", "AMZN", "GOOG", "MSFT",
            "NVDA", "COST", "INTC", "CSCO",
        ]
        selection.update({
            "tickers": ["AMZN", "GOOG", "MSFT", "NVDA"],
            "weights": {
                "AMZN": 0.25,
                "GOOG": 0.25,
                "MSFT": 0.25,
                "NVDA": 0.25,
            },
            "quality_challenge_pool_tickers": pool,
            "quality_replacement_pairs": [{
                "outgoing_ticker": "AAPL",
                "incoming_ticker": "NVDA",
                "outgoing_price_rank": 1,
                "incoming_price_rank": 5,
                "outgoing_quality_score": 20.0,
                "incoming_quality_score": 80.0,
                "quality_score_delta": 60.0,
            }],
            "sic4_by_ticker": {
                "AMZN": 7372,
                "GOOG": 3674,
                "MSFT": 2834,
                "NVDA": 3674,
            },
            "sic2_by_ticker": {
                "AMZN": "73",
                "GOOG": "36",
                "MSFT": "28",
                "NVDA": "36",
            },
            "sic4_weights": {"7372": 0.25, "3674": 0.50, "2834": 0.25},
            "sic2_weights": {"73": 0.25, "36": 0.50, "28": 0.25},
        })

        valid = selection_constraint_audit(result)

        self.assertTrue(valid["passed"])
        broken = copy.deepcopy(result)
        broken_pair = broken["samples"][0]["selections"][0][
            "quality_replacement_pairs"
        ][0]
        broken_pair["incoming_price_rank"] = 6
        failed = selection_constraint_audit(broken)
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["quality_replacement_guard_failures"], 1)

    def test_quality_profile_checkpoint_requires_versioned_score_evidence(self):
        with _workspace_test_dir() as tmp:
            spec = _load_spec(tmp)
            spec["phases"][0]["construction_profiles"] = [{
                "id": "quality_sic",
                "top_n": 4,
                "weight_mode": "equal",
                "rebalance_months": 6,
                "safe_weight": 0.0,
                "max_weight": 0.25,
                "fundamental_score_weight": 0.25,
                "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
                "max_names_per_sic4": 2,
                "max_names_per_sic2": 2,
                "sic4_max_weight": 0.50,
                "sic2_max_weight": 0.60,
            }]
            job = expand_experiment_jobs(spec)[0]
            result = _attach_quality_sic_evidence(copy.deepcopy(_result()))
            checkpoint = checkpoint_payload(
                job,
                result,
                started_at="2026-07-12T00:00:00+00:00",
                duration_seconds=1.0,
            )
            del checkpoint["result"]["data_manifest"]["quality_scores"]

            valid, reason = validate_checkpoint(checkpoint, job)

        self.assertFalse(valid)
        self.assertIn("quality score version", reason)


if __name__ == "__main__":
    unittest.main()
