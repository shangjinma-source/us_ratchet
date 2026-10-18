"""Contract tests for dynamic security-id conditional whole-lot repair."""
from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_dynamic_whole_lot_path import (
    simulate_dynamic_security_id_whole_lot_path,
)
from backtest.ndx_dynamic_whole_lot_repair_path import (
    NdxDynamicWholeLotRepairPathError,
    simulate_dynamic_security_id_conditional_repair_path,
)


def _target(ticker: str, issuer: str, weight: float) -> dict[str, object]:
    return {"ticker": ticker, "issuer_id": issuer, "target_weight": weight}


def _base_arguments(schedule: list[dict[str, object]]) -> dict[str, object]:
    return {
        "require_separate_execution_prices": True,
        "require_next_session_execution": True,
        "require_issuer_trace": True,
        "risk_chains_by_decision": {
            str(item["decision_date"]): {
                security_id: f"chain:{security_id}"
                for security_id in item["targets"]
            }
            for item in schedule
        },
        "initial_cash_usd": 1_200.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        "valuation_end_date": str(schedule[-1]["execution_date"]),
    }


class DynamicWholeLotRepairPathTests(unittest.TestCase):
    def test_no_trigger_reuses_all_four_frozen_engine_outputs_exactly(self):
        dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
        opens = pd.DataFrame(
            {ticker: [100.0, 101.0] for ticker in ("A", "B", "C", "D")},
            index=dates,
        )
        closes = opens * 1.01
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments.update({
            "execution_prices": opens,
            "valuation_end_date": "2024-01-03",
        })
        expected = simulate_dynamic_security_id_whole_lot_path(
            closes,
            schedule,
            execution_prices=opens,
            require_separate_execution_prices=True,
            require_next_session_execution=True,
            require_issuer_trace=True,
            initial_cash_usd=1_200.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date="2024-01-03",
        )

        actual = simulate_dynamic_security_id_conditional_repair_path(
            closes, schedule, **arguments
        )

        self.assertEqual(actual["status"], "COMPLETE_LEGACY_EXACT_REUSE")
        self.assertTrue(actual["legacy_exact_reuse"])
        self.assertEqual(actual["summary"], expected[0])
        for key, frozen in zip(("rebalances", "trades", "path"), expected[1:]):
            pd.testing.assert_frame_equal(actual[key], frozen)
        self.assertTrue(actual["repair_events"].empty)

    def test_zero_floor_for_high_price_security_is_repaired_to_one_share(self):
        dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
        opens = pd.DataFrame(
            {
                "A": [80.0, 80.0],
                "B": [80.0, 80.0],
                "C": [80.0, 80.0],
                "D": [300.0, 300.0],
            },
            index=dates,
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments.update({"execution_prices": opens, "valuation_end_date": "2024-01-03"})

        result = simulate_dynamic_security_id_conditional_repair_path(
            opens * 1.01, schedule, **arguments
        )

        self.assertEqual(result["status"], "COMPLETE_WITH_CONDITIONAL_REPAIR")
        self.assertTrue(result["path_complete"])
        self.assertEqual(len(result["repair_events"]), 1)
        holdings = result["rebalances"].iloc[0]["holdings"]
        self.assertIn('"D":{"issuer_id":"issuer:D","shares":1', holdings)
        self.assertTrue(result["daily_risk"].iloc[0]["all_constraints_passed"])

    def test_complete_path_with_holding_day_risk_drift_is_not_execution_eligible(self):
        dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"])
        opens = pd.DataFrame(
            {ticker: [100.0, 100.0] for ticker in ("A", "B", "C", "D")},
            index=dates,
        )
        closes = opens.copy()
        closes.loc[pd.Timestamp("2024-01-03"), "A"] = 1_000.0
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments.update({"execution_prices": opens, "valuation_end_date": "2024-01-03"})

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes, schedule, **arguments
        )

        self.assertEqual(result["status"], "COMPLETE_LEGACY_EXACT_REUSE")
        self.assertTrue(result["path_complete"])
        self.assertFalse(result["execution_eligible"])
        self.assertEqual(
            result["daily_risk"]["all_constraints_passed"].tolist(), [True, False]
        )

    def test_dynamic_k_rename_exit_entry_and_open_price_accounting(self):
        dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03", "2024-01-04"])
        opens = pd.DataFrame({
            "OLD": [80.0, 70.0, 70.0],
            "NEW": [85.0, 85.0, 85.0],
            "B": [80.0, 90.0, 90.0],
            "C": [300.0, 300.0, 300.0],
            "E": [80.0, 80.0, 80.0],
            "F": [80.0, 80.0, 80.0],
            "G": [80.0, 80.0, 80.0],
        }, index=dates)
        closes = pd.DataFrame({
            "OLD": [71.0, 72.0, 73.0],
            "NEW": [91.0, 92.0, 93.0],
            "B": [61.0, 62.0, 63.0],
            "C": [310.0, 311.0, 312.0],
            "E": [81.0, 82.0, 83.0],
            "F": [84.0, 85.0, 86.0],
            "G": [87.0, 88.0, 89.0],
        }, index=dates)
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": "2024-01-02",
                "targets": {
                    "A": _target("OLD", "issuer:A", 0.25),
                    "B": _target("B", "issuer:B", 0.25),
                    "E": _target("E", "issuer:E", 0.25),
                    "F": _target("F", "issuer:F", 0.25),
                },
            },
            {
                "decision_date": "2024-01-03",
                "execution_date": "2024-01-04",
                "targets": {
                    "A": _target("NEW", "issuer:A", 0.20),
                    "C": _target("C", "issuer:C", 0.20),
                    "E": _target("E", "issuer:E", 0.20),
                    "F": _target("F", "issuer:F", 0.20),
                    "G": _target("G", "issuer:G", 0.20),
                },
            },
        ]
        arguments = _base_arguments(schedule)
        arguments.update({"execution_prices": opens, "valuation_end_date": "2024-01-04"})

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes, schedule, **arguments
        )

        self.assertTrue(result["path_complete"], result["status"])
        self.assertEqual(result["summary"]["k_path"], [4, 5])
        second = result["trades"][result["trades"]["rebalance_sequence"] == 2]
        rename = second[second["event_type"] == "RENAME_NO_TRADE"]
        self.assertEqual(rename["security_id"].tolist(), ["A"])
        self.assertEqual(rename.iloc[0]["transaction_cost_usd"], 0.0)
        self.assertEqual(second[second["security_id"] == "B"]["action"].tolist(), ["SELL"])
        self.assertEqual(second[second["security_id"] == "B"]["price_usd"].tolist(), [90.0])
        self.assertEqual(second[second["security_id"] == "C"]["action"].tolist(), ["BUY"])
        economic = result["trades"][result["trades"]["event_type"] == "ECONOMIC_TRADE"]
        expected_fees = float((economic["notional_usd"] * 0.001).sum())
        self.assertAlmostEqual(
            result["summary"]["total_transaction_cost_usd"], expected_fees, places=9
        )

    def test_budget_exhaustion_never_returns_a_partial_path(self):
        dates = pd.DatetimeIndex(["2024-01-02"])
        opens = pd.DataFrame(
            {"A": [80.0], "B": [80.0], "C": [80.0], "D": [300.0]},
            index=dates,
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments.update({
            "execution_prices": opens,
            "max_repair_evaluations": 1,
        })

        result = simulate_dynamic_security_id_conditional_repair_path(
            opens, schedule, **arguments
        )

        self.assertEqual(result["status"], "RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        self.assertFalse(result["search_complete"])
        self.assertFalse(result["path_complete"])
        for key in ("summary", "rebalances", "trades", "path", "daily_risk"):
            self.assertIsNone(result[key])

    def test_requires_exact_per_decision_risk_chain_evidence(self):
        dates = pd.DatetimeIndex(["2024-01-02"])
        opens = pd.DataFrame(
            {ticker: [100.0] for ticker in ("A", "B", "C", "D")}, index=dates
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments["execution_prices"] = opens
        for evidence in ({}, {"2024-01-01": {"A": "chain:A"}}, {
            "2024-01-01": {ticker: f"chain:{ticker}" for ticker in ("A", "B", "C", "D")},
            "2023-12-01": {"A": "chain:A"},
        }):
            with self.subTest(evidence=evidence):
                arguments["risk_chains_by_decision"] = evidence
                with self.assertRaises(NdxDynamicWholeLotRepairPathError):
                    simulate_dynamic_security_id_conditional_repair_path(
                        opens, schedule, **arguments
                    )

    def test_strict_dates_duplicate_issuer_and_execution_guards_fail_closed(self):
        valid_dates = pd.DatetimeIndex(["2024-01-02"])
        opens = pd.DataFrame(
            {ticker: [100.0] for ticker in ("A", "B", "C", "D")},
            index=valid_dates,
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                ticker: _target(ticker, f"issuer:{ticker}", 0.25)
                for ticker in ("A", "B", "C", "D")
            },
        }]
        arguments = _base_arguments(schedule)
        arguments["execution_prices"] = opens

        bad_index = opens.copy()
        bad_index.index = pd.DatetimeIndex(["2024-01-02 12:00"])
        with self.assertRaises(NdxDynamicWholeLotRepairPathError):
            simulate_dynamic_security_id_conditional_repair_path(
                bad_index, schedule, **arguments
            )

        duplicated_issuer = [{**schedule[0], "targets": {
            "A": _target("A", "issuer:same", 0.25),
            "B": _target("B", "issuer:same", 0.25),
            "C": _target("C", "issuer:C", 0.25),
            "D": _target("D", "issuer:D", 0.25),
        }}]
        with self.assertRaises(NdxDynamicWholeLotRepairPathError):
            simulate_dynamic_security_id_conditional_repair_path(
                opens, duplicated_issuer, **arguments
            )

        for override in (
            {"require_separate_execution_prices": False},
            {"require_next_session_execution": False},
            {"require_issuer_trace": False},
            {"execution_prices": None},
        ):
            with self.subTest(override=override):
                bad_arguments = dict(arguments)
                bad_arguments.update(override)
                with self.assertRaises(NdxDynamicWholeLotRepairPathError):
                    simulate_dynamic_security_id_conditional_repair_path(
                        opens, schedule, **bad_arguments
                    )


if __name__ == "__main__":
    unittest.main()
