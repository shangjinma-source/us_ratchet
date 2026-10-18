from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest import ndx_equal_weight_schedule_extension_runner as runner
from backtest.ndx_whole_lot_rebalance import (
    simulate_continuous_whole_lot_rebalance,
)


ROOT = Path(__file__).resolve().parents[1]


def _synthetic_case(*, drifting: bool = False):
    dates = pd.bdate_range("2024-01-02", periods=70)
    prices = pd.DataFrame(index=dates)
    for index in range(4):
        if drifting and index == 0:
            prices[f"T{index}"] = [100.0 * (1.025**day) for day in range(70)]
        else:
            prices[f"T{index}"] = [100.0 + index + day * 0.10 for day in range(70)]
    tickers = list(prices.columns)
    weights = {ticker: 0.25 for ticker in tickers}
    schedule = [(dates[0], weights.copy()), (dates[21], weights.copy())]
    contract = {
        "risk_chain_by_ticker": {
            ticker: f"CHAIN_{index}" for index, ticker in enumerate(tickers)
        },
        "portfolio_cash_usd": 25_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        **runner.LOCKED_RISK_THRESHOLDS,
    }
    summary, _ = simulate_continuous_whole_lot_rebalance(
        prices, schedule, **contract
    )
    expected = {
        field: summary[field] for field in runner.ORIGINAL_SUMMARY_FIELDS
    }
    candidate = {
        "candidate_key": "a" * 24,
        "candidate_identity_sha256": "b" * 64,
        "source_batch": runner.SOURCE_BATCH,
        "job_search_class": runner.JOB_SEARCH_CLASS,
        "evaluation_semantics_sha256": runner.EVALUATOR_SHA256,
        "universe_track": "strict_technology",
        "selection_date": runner.SELECTION_DATE,
        "portfolio_id": "synthetic-dynamic-k4",
        "holding_count": 4,
        "tickers": tickers,
        "weights": weights,
        "security_ids": [f"SEC_{index}" for index in range(4)],
        "issuer_ids": [f"ISSUER_{index}" for index in range(4)],
        "risk_chains": [f"CHAIN_{index}" for index in range(4)],
        "source_failure_class": "SOURCE_REPORTED_ELIGIBLE",
        "source_failure_reasons": [],
        "expected_original_summary": expected,
    }
    return prices, schedule, contract, candidate


class EqualWeightScheduleExtensionRunnerTest(unittest.TestCase):
    def test_canonical_plan_locks_all_323_latest_exact_candidates(self):
        plan = runner.build_locked_replay_plan(repository_root=ROOT)
        self.assertEqual(plan["counts"], runner.EXPECTED_TOTALS)
        self.assertEqual(
            {group["universe_track"] for group in plan["groups"]},
            {"strict_technology", "technology_plus_adjacent"},
        )
        self.assertEqual(sum(len(group["candidates"]) for group in plan["groups"]), 323)
        self.assertEqual(plan["locked_risk_thresholds"], runner.LOCKED_RISK_THRESHOLDS)
        self.assertEqual(plan["checkpoint_write_boundary"], "AFTER_COMPLETE_TRACK_CAPTURE")
        self.assertFalse(plan["candidate_set_or_weight_search_run"])
        self.assertFalse(plan["migration_control_included"])

    def test_reproduces_b_before_only_21_session_extension_a(self):
        prices, schedule, contract, candidate = _synthetic_case()
        result = runner.diagnose_locked_equal_weight_candidate(
            prices, schedule, candidate=candidate, execution_contract=contract
        )
        self.assertTrue(
            result["stored_identity_weights_trace_and_13_summary_reproduced_before_a"]
        )
        self.assertEqual(result["original_schedule_b"]["schedule_dates"], [
            prices.index[0].date().isoformat(), prices.index[21].date().isoformat()
        ])
        self.assertEqual(result["continued_schedule_a"]["added_rebalance_dates"], [
            prices.index[42].date().isoformat(), prices.index[63].date().isoformat()
        ])
        self.assertFalse(result["ab_comparison"]["ranking_score_computed"])
        self.assertIn(
            "a_nonworse_return_and_corrected_drawdown", result["ab_comparison"]
        )
        self.assertIn(
            "a_nonworse_return_and_legacy_drawdown", result["ab_comparison"]
        )

    def test_old_trace_mismatch_stops_before_extension_simulation(self):
        prices, schedule, contract, candidate = _synthetic_case()
        candidate["expected_original_summary"] = dict(
            candidate["expected_original_summary"]
        )
        candidate["expected_original_summary"][
            "whole_lot_rebalance_trace_sha256"
        ] = "0" * 64
        original = runner.simulate_continuous_whole_lot_rebalance
        with patch.object(
            runner,
            "simulate_continuous_whole_lot_rebalance",
            wraps=original,
        ) as simulation:
            with self.assertRaisesRegex(
                runner.NdxEqualWeightScheduleExtensionRunnerError,
                "stored whole-lot summary was not reproduced",
            ):
                runner.diagnose_locked_equal_weight_candidate(
                    prices,
                    schedule,
                    candidate=candidate,
                    execution_contract=contract,
                )
        self.assertEqual(simulation.call_count, 1)

    def test_risk_threshold_change_is_rejected_even_if_old_trace_matches(self):
        prices, schedule, contract, candidate = _synthetic_case()
        capture = runner.serialize_replay_capture(prices, schedule, contract)
        capture["execution_contract"]["top_weight_cap"] = 0.79
        with self.assertRaisesRegex(
            runner.NdxEqualWeightScheduleExtensionRunnerError,
            "risk-threshold contract changed",
        ):
            runner.rebuild_result_from_capture(capture, candidate)

    def test_daily_risk_failures_include_dates_and_reasons(self):
        prices, schedule, contract, candidate = _synthetic_case(drifting=True)
        result = runner.diagnose_locked_equal_weight_candidate(
            prices, schedule, candidate=candidate, execution_contract=contract
        )
        audit = result["original_schedule_b"]["daily_risk_audit"]
        self.assertGreater(audit["failure_session_count"], 0)
        self.assertTrue(all(row["session_date"] for row in audit["failure_sessions"]))
        self.assertIn("MAX_SINGLE_WEIGHT", audit["failure_reason_counts"])

    def test_intraday_timezone_and_same_day_coordinates_fail_closed(self):
        prices, schedule, contract, _ = _synthetic_case()
        intraday = prices.copy()
        intraday.index = intraday.index + pd.Timedelta(hours=16)
        with self.assertRaisesRegex(
            runner.NdxEqualWeightScheduleExtensionRunnerError, "coordinate changed"
        ):
            runner.serialize_replay_capture(intraday, schedule, contract)
        timezone_prices = prices.copy()
        timezone_prices.index = timezone_prices.index.tz_localize("UTC")
        with self.assertRaisesRegex(
            runner.NdxEqualWeightScheduleExtensionRunnerError, "coordinate changed"
        ):
            runner.serialize_replay_capture(timezone_prices, schedule, contract)
        duplicate = prices.iloc[:3].copy()
        duplicate.index = pd.DatetimeIndex(
            ["2024-01-02 09:00", "2024-01-02 16:00", "2024-01-03"]
        )
        with self.assertRaisesRegex(
            runner.NdxEqualWeightScheduleExtensionRunnerError, "coordinate changed"
        ):
            runner.serialize_replay_capture(duplicate, schedule, contract)

    def test_capture_dates_require_exact_iso_and_checkpoint_needs_recapture(self):
        prices, schedule, contract, candidate = _synthetic_case()
        capture = runner.serialize_replay_capture(prices, schedule, contract)
        captured = {
            "capture": capture,
            "result": runner.rebuild_result_from_capture(capture, candidate),
        }
        with tempfile.TemporaryDirectory() as temporary_name:
            checkpoint_path = Path(temporary_name) / "candidate.json"
            runner.write_candidate_checkpoint(
                checkpoint_path,
                plan_fingerprint="c" * 64,
                candidate=candidate,
                captured=captured,
            )
            runner._verify_checkpoint_against_recapture(
                checkpoint_path,
                plan_fingerprint="c" * 64,
                candidate=candidate,
                recaptured=captured,
            )
            malicious_capture = json.loads(json.dumps(capture))
            malicious_capture["price_rows"][1]["closes"]["T0"] += 0.01
            malicious = {
                "capture": malicious_capture,
                "result": runner.rebuild_result_from_capture(
                    malicious_capture, candidate
                ),
            }
            runner.write_candidate_checkpoint(
                Path(temporary_name) / "self_signed.json",
                plan_fingerprint="c" * 64,
                candidate=candidate,
                captured=malicious,
            )
            with self.assertRaisesRegex(
                runner.NdxEqualWeightScheduleExtensionRunnerError,
                "fresh canonical source replay",
            ):
                runner._verify_checkpoint_against_recapture(
                    Path(temporary_name) / "self_signed.json",
                    plan_fingerprint="c" * 64,
                    candidate=candidate,
                    recaptured=captured,
                )
            bad_date = json.loads(json.dumps(capture))
            bad_date["price_rows"][0]["session_date"] = "2024-01-02T16:00:00"
            with self.assertRaisesRegex(
                runner.NdxEqualWeightScheduleExtensionRunnerError,
                "canonical YYYY-MM-DD",
            ):
                runner.rebuild_result_from_capture(bad_date, candidate)

    def test_fingerprint_lock_is_nonblocking_and_os_released(self):
        with tempfile.TemporaryDirectory() as temporary_name:
            lock_path = Path(temporary_name) / "run.lock"
            with runner._single_instance_lock(lock_path):
                with self.assertRaisesRegex(
                    runner.NdxEqualWeightScheduleExtensionRunnerError,
                    "another replay",
                ):
                    with runner._single_instance_lock(lock_path):
                        self.fail("nested writer lock unexpectedly succeeded")
            with runner._single_instance_lock(lock_path):
                pass

    def test_cli_help_runs_from_repository_checkout(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/ndx_equal_weight_schedule_extension_runner.py"),
                "--help",
            ],
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--verify", completed.stdout)


if __name__ == "__main__":
    unittest.main()
