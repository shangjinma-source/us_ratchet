from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_user_preference_whole_lot_diagnostic import (
    NdxUserPreferenceWholeLotDiagnosticError,
    _rebuild_ab_from_capture,
    _serialize_replay_capture,
    diagnose_equal_weight_schedule_ab,
    extend_equal_weight_schedule,
    verify_diagnostic_bundle,
    write_diagnostic_bundle,
)


TICKERS = ("AMAT", "AVGO", "CDNS", "GOOG")


def _contract() -> dict[str, object]:
    return {
        "risk_chain_by_ticker": {ticker: ticker for ticker in TICKERS},
        "portfolio_cash_usd": 10_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        "max_single_weight": 0.45,
        "min_single_weight": 0.05,
        "top_weight_cap": 0.80,
        "minimum_effective_n_ratio": 0.70,
        "risk_chain_top1_cap": 0.55,
    }


def _canonical_contract() -> dict[str, object]:
    return {
        "risk_chain_by_ticker": {
            "AMAT": "semiconductor_equipment",
            "AVGO": "diversified_technology",
            "CDNS": "eda_ip",
            "GOOG": "platform_advertising",
        },
        "portfolio_cash_usd": 25_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        "max_single_weight": 0.45,
        "min_single_weight": 0.05,
        "top_weight_cap": 0.80,
        "minimum_effective_n_ratio": 0.70,
        "risk_chain_top1_cap": 0.55,
    }


def _case() -> tuple[pd.DataFrame, list[tuple[pd.Timestamp, dict[str, float]]]]:
    sessions = pd.bdate_range("2024-01-02", periods=8)
    prices = pd.DataFrame({
        "AMAT": [100.0] * 8,
        "AVGO": [100.0] * 8,
        "CDNS": [100.0, 100.0, 100.0, 90.0, 80.0, 75.0, 70.0, 70.0],
        "GOOG": [100.0] * 8,
    }, index=sessions)
    equal = {ticker: 0.25 for ticker in TICKERS}
    return prices, [(sessions[0], equal.copy()), (sessions[2], equal.copy())]


def _canonical_bundle_case() -> tuple[
    pd.DataFrame, list[tuple[pd.Timestamp, dict[str, float]]]
]:
    sessions = pd.bdate_range("2024-01-02", periods=22)
    prices = pd.DataFrame(
        {ticker: [100.0] * len(sessions) for ticker in TICKERS}, index=sessions
    )
    return prices, [(sessions[0], {ticker: 0.25 for ticker in TICKERS})]


class NdxUserPreferenceWholeLotDiagnosticTests(unittest.TestCase):
    def test_continued_cadence_removes_only_observed_synthetic_breaches(self) -> None:
        prices, schedule = _case()
        result = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=2, **_contract()
        )
        original = result["original_schedule_b"]
        continued = result["continued_cadence_a"]
        self.assertEqual(original["daily_risk_attribution"]["risk_failure_session_count"], 2)
        self.assertEqual(continued["daily_risk_attribution"]["risk_failure_session_count"], 0)
        self.assertEqual(continued["added_rebalance_dates"], ["2024-01-08", "2024-01-10"])
        self.assertTrue(
            result["comparison"]["continued_cadence_removed_all_observed_risk_breaches"]
        )
        self.assertFalse(result["comparison"]["risk_threshold_changed"])
        self.assertFalse(result["comparison"]["risk_triggered_trading_added"])

    def test_original_summary_and_trace_must_reproduce_exactly(self) -> None:
        prices, schedule = _case()
        first = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=2, **_contract()
        )
        expected = dict(first["original_schedule_b"]["summary"])
        verified = diagnose_equal_weight_schedule_ab(
            prices, schedule, expected_original_summary=expected,
            cadence_sessions=2, **_contract()
        )
        self.assertTrue(
            verified["original_schedule_b"]["stored_summary_and_trace_fully_reproduced"]
        )
        expected["whole_lot_rebalance_trace_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            NdxUserPreferenceWholeLotDiagnosticError, "does not reproduce"
        ):
            diagnose_equal_weight_schedule_ab(
                prices, schedule, expected_original_summary=expected,
                cadence_sessions=2, **_contract()
            )

    def test_non_equal_weight_or_wrong_names_cannot_enter_a_path(self) -> None:
        prices, schedule = _case()
        schedule[0][1]["AMAT"] = 0.30
        with self.assertRaisesRegex(
            NdxUserPreferenceWholeLotDiagnosticError, "equal weight"
        ):
            diagnose_equal_weight_schedule_ab(
                prices, schedule, cadence_sessions=2, **_contract()
            )

    def test_initial_capital_drawdown_is_separate_from_legacy_metric(self) -> None:
        sessions = pd.bdate_range("2024-01-02", periods=2)
        prices = pd.DataFrame(
            {ticker: [100.0, 100.0] for ticker in TICKERS}, index=sessions
        )
        schedule = [(sessions[0], {ticker: 0.25 for ticker in TICKERS})]
        result = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=21, **_contract()
        )
        audit = result["original_schedule_b"]["daily_risk_attribution"]
        self.assertEqual(audit["old_engine_drawdown_without_initial_capital_peak"], 0.0)
        self.assertGreater(
            audit["corrected_drawdown_with_initial_capital_peak"], 0.0
        )
        self.assertEqual(audit["initial_capital_usd"], 10_000.0)
        self.assertTrue(audit["drawdown_metrics_are_reported_separately"])

    def test_schedule_extension_uses_sessions_not_future_price_values(self) -> None:
        prices, schedule = _case()
        changed = prices.copy()
        changed.loc[changed.index[3]:, "CDNS"] *= 7.0
        left = extend_equal_weight_schedule(prices, schedule, cadence_sessions=2)
        right = extend_equal_weight_schedule(changed, schedule, cadence_sessions=2)
        self.assertEqual([day for day, _ in left], [day for day, _ in right])
        self.assertEqual([weights for _, weights in left], [weights for _, weights in right])

    def test_residual_daily_risk_breach_remains_failed(self) -> None:
        prices, schedule = _case()
        prices["CDNS"] = [100.0, 10.0, 100.0, 10.0, 100.0, 10.0, 100.0, 10.0]
        result = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=2, **_contract()
        )
        continued = result["continued_cadence_a"]
        self.assertEqual(continued["research_constraint_status"], "FAIL")
        self.assertIn("DAILY_RISK_DRIFT", continued["constraint_failure_classes"])
        self.assertFalse(
            result["comparison"]["continued_cadence_removed_all_observed_risk_breaches"]
        )

    def test_bundle_is_immutable_and_tamper_evident(self) -> None:
        prices, schedule = _canonical_bundle_case()
        initial = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=21, **_canonical_contract()
        )
        expected = initial["original_schedule_b"]["summary"]
        ab = diagnose_equal_weight_schedule_ab(
            prices,
            schedule,
            cadence_sessions=21,
            expected_original_summary=expected,
            **_canonical_contract(),
        )
        capture = _serialize_replay_capture(
            prices,
            schedule,
            _canonical_contract(),
            expected,
            cadence_sessions=21,
        )
        result = {
            "manifest_type": "ndx_user_preference_whole_lot_schedule_diagnostic",
            "status": "RESEARCH_DIAGNOSTIC_COMPLETE",
            "ab_diagnostic": ab,
            "replay_input_capture": capture,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            first = write_diagnostic_bundle(result, output_dir=output)
            second = write_diagnostic_bundle(result, output_dir=output)
            self.assertEqual(first, second)
            verify_diagnostic_bundle(output / "manifest.json")
            (output / "diagnostic.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxUserPreferenceWholeLotDiagnosticError, "artifact hash changed"
            ):
                verify_diagnostic_bundle(output / "manifest.json")

    def test_sealed_capture_rejects_noncanonical_contract_and_dates(self) -> None:
        prices, schedule = _canonical_bundle_case()
        initial = diagnose_equal_weight_schedule_ab(
            prices, schedule, cadence_sessions=21, **_canonical_contract()
        )
        expected = initial["original_schedule_b"]["summary"]
        ab = diagnose_equal_weight_schedule_ab(
            prices,
            schedule,
            cadence_sessions=21,
            expected_original_summary=expected,
            **_canonical_contract(),
        )
        capture = _serialize_replay_capture(
            prices,
            schedule,
            _canonical_contract(),
            expected,
        )
        attacks = []
        for cadence in (2, "21", True):
            changed = copy.deepcopy(capture)
            changed["cadence_sessions"] = cadence
            attacks.append(changed)
        changed = copy.deepcopy(capture)
        changed["execution_contract"]["top_weight_cap"] = 0.81
        attacks.append(changed)
        changed = copy.deepcopy(capture)
        changed["price_rows"][0]["session_date"] = "2024-01-02T00:00:00"
        attacks.append(changed)
        changed = copy.deepcopy(capture)
        changed["original_schedule"][0]["session_date"] = "2024-01-02+00:00"
        attacks.append(changed)
        for attack in attacks:
            with self.subTest(attack=attack):
                with self.assertRaises(NdxUserPreferenceWholeLotDiagnosticError):
                    _rebuild_ab_from_capture(attack)


if __name__ == "__main__":
    unittest.main()
