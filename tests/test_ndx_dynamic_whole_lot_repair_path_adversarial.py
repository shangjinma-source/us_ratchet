"""Independent behavioral checks for the dynamic whole-lot repair path."""
from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from backtest.ndx_dynamic_whole_lot_repair_path import (
    NdxDynamicWholeLotRepairPathError,
    simulate_dynamic_security_id_conditional_repair_path,
)


def _target(ticker: str, issuer: str, weight: float) -> dict[str, object]:
    return {
        "ticker": ticker,
        "issuer_id": issuer,
        "target_weight": weight,
    }


def _decision_chains(schedule: list[dict[str, object]]) -> dict[str, dict[str, str]]:
    return {
        str(item["decision_date"]): {
            security_id: f"chain:{security_id}"
            for security_id in item["targets"]
        }
        for item in schedule
    }


class DynamicWholeLotRepairBehaviorTests(unittest.TestCase):
    def test_repaired_branch_preserves_rename_while_exiting_and_entering(self):
        dates = pd.DatetimeIndex(
            [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04")]
        )
        closes = pd.DataFrame(
            {
                "A": [100.0, 100.0, 100.0],
                "B": [100.0, 100.0, 100.0],
                "C": [100.0, 100.0, 100.0],
                "D_OLD": [300.0, 300.0, np.nan],
                "D_NEW": [np.nan, np.nan, 300.0],
                "E": [100.0, 100.0, 100.0],
                "F": [100.0, 100.0, 100.0],
            },
            index=dates,
        )
        opens = closes.copy()
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": "2024-01-02",
                "targets": {
                    "security:a": _target("A", "issuer:a", 0.25),
                    "security:b": _target("B", "issuer:b", 0.25),
                    "security:c": _target("C", "issuer:c", 0.25),
                    "security:d": _target("D_OLD", "issuer:d", 0.25),
                },
            },
            {
                "decision_date": "2024-01-03",
                "execution_date": "2024-01-04",
                "targets": {
                    "security:b": _target("B", "issuer:b", 0.20),
                    "security:c": _target("C", "issuer:c", 0.20),
                    "security:d": _target("D_NEW", "issuer:d", 0.20),
                    "security:e": _target("E", "issuer:e", 0.20),
                    "security:f": _target("F", "issuer:f", 0.20),
                },
            },
        ]

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes,
            schedule,
            execution_prices=opens,
            risk_chains_by_decision=_decision_chains(schedule),
            initial_cash_usd=1_000.0,
            minimum_cash_buffer_usd=90.0,
            transaction_cost_bps=10.0,
            valuation_end_date="2024-01-04",
        )

        self.assertEqual(result["status"], "COMPLETE_WITH_CONDITIONAL_REPAIR")
        self.assertFalse(result["legacy_exact_reuse"])
        self.assertEqual(result["summary"]["k_path"], [4, 5])
        self.assertEqual(len(result["repair_events"]), 2)
        second = result["trades"][result["trades"]["rebalance_sequence"].eq(2)]
        rename = second[second["event_type"].eq("RENAME_NO_TRADE")]
        self.assertEqual(rename["security_id"].tolist(), ["security:d"])
        self.assertEqual(rename["notional_usd"].tolist(), [0.0])
        self.assertEqual(rename["transaction_cost_usd"].tolist(), [0.0])
        economic = second[second["event_type"].eq("ECONOMIC_TRADE")].set_index("security_id")
        self.assertNotIn("security:d", economic.index)
        self.assertEqual(economic.at["security:a", "action"], "SELL")
        self.assertEqual(economic.at["security:e", "action"], "BUY")
        self.assertEqual(economic.at["security:f", "action"], "BUY")
        final_holdings = json.loads(result["path"].iloc[-1]["holdings"])
        self.assertEqual(final_holdings["security:d"]["ticker"], "D_NEW")
        self.assertEqual(final_holdings["security:d"]["shares"], 1)

    def test_rename_exit_entry_and_changed_k_trade_once_at_next_open(self):
        dates = pd.DatetimeIndex(
            [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-04")]
        )
        closes = pd.DataFrame(
            {
                "OLD": [100.0, 100.0, np.nan],
                "NEW": [np.nan, np.nan, 125.0],
                "B": [100.0, 90.0, 79.0],
                "C": [100.0, 102.0, 106.0],
                "D": [100.0, 98.0, 96.0],
                "E": [np.nan, np.nan, 151.0],
                "F": [np.nan, np.nan, 76.0],
            },
            index=dates,
        )
        opens = pd.DataFrame(
            {
                "OLD": [100.0, np.nan, np.nan],
                "NEW": [np.nan, np.nan, 120.0],
                "B": [100.0, np.nan, 80.0],
                "C": [100.0, np.nan, 105.0],
                "D": [100.0, np.nan, 95.0],
                "E": [np.nan, np.nan, 150.0],
                "F": [np.nan, np.nan, 75.0],
            },
            index=dates,
        )
        schedule = [
            {
                "decision_date": "2024-01-01",
                "execution_date": "2024-01-02",
                "targets": {
                    "security:a": _target("OLD", "issuer:a", 0.25),
                    "security:b": _target("B", "issuer:b", 0.25),
                    "security:c": _target("C", "issuer:c", 0.25),
                    "security:d": _target("D", "issuer:d", 0.25),
                },
            },
            {
                "decision_date": "2024-01-03",
                "execution_date": "2024-01-04",
                "targets": {
                    "security:a": _target("NEW", "issuer:a", 0.30),
                    "security:c": _target("C", "issuer:c", 0.25),
                    "security:d": _target("D", "issuer:d", 0.20),
                    "security:e": _target("E", "issuer:e", 0.15),
                    "security:f": _target("F", "issuer:f", 0.10),
                },
            },
        ]

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes,
            schedule,
            execution_prices=opens,
            risk_chains_by_decision=_decision_chains(schedule),
            initial_cash_usd=25_000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            valuation_end_date="2024-01-04",
        )

        self.assertEqual(result["status"], "COMPLETE_LEGACY_EXACT_REUSE")
        self.assertEqual(result["summary"]["k_path"], [4, 5])
        second = result["trades"][result["trades"]["rebalance_sequence"].eq(2)]
        rename = second[second["event_type"].eq("RENAME_NO_TRADE")]
        self.assertEqual(rename["security_id"].tolist(), ["security:a"])
        self.assertEqual(rename["notional_usd"].tolist(), [0.0])
        self.assertEqual(rename["transaction_cost_usd"].tolist(), [0.0])
        economic = second[second["event_type"].eq("ECONOMIC_TRADE")].set_index("security_id")
        self.assertEqual(economic.at["security:b", "action"], "SELL")
        self.assertEqual(economic.at["security:e", "action"], "BUY")
        self.assertEqual(economic.at["security:f", "action"], "BUY")
        self.assertNotIn("security:a", economic.index)
        self.assertEqual(economic.at["security:b", "price_usd"], 80.0)
        self.assertEqual(economic.at["security:e", "price_usd"], 150.0)
        self.assertEqual(economic.at["security:f", "price_usd"], 75.0)
        expected_fee = float(economic["notional_usd"].sum()) * 10.0 / 10_000.0
        second_rebalance = result["rebalances"].iloc[1]
        self.assertAlmostEqual(second_rebalance["transaction_cost_usd"], expected_fee)
        self.assertEqual(second_rebalance["removed_security_ids"], '["security:b"]')
        self.assertEqual(second_rebalance["added_security_ids"], '["security:e","security:f"]')
        final_holdings = json.loads(result["path"].iloc[-1]["holdings"])
        self.assertEqual(final_holdings["security:a"]["ticker"], "NEW")

    def test_zero_floor_target_is_rescued_by_one_share_ceil(self):
        date = pd.Timestamp("2024-01-02")
        closes = pd.DataFrame(
            {"A": [100.0], "B": [100.0], "C": [100.0], "D": [300.0]},
            index=[date],
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                "security:a": _target("A", "issuer:a", 0.25),
                "security:b": _target("B", "issuer:b", 0.25),
                "security:c": _target("C", "issuer:c", 0.25),
                "security:d": _target("D", "issuer:d", 0.25),
            },
        }]

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes,
            schedule,
            execution_prices=closes.copy(),
            risk_chains_by_decision=_decision_chains(schedule),
            initial_cash_usd=1_000.0,
            minimum_cash_buffer_usd=90.0,
            transaction_cost_bps=10.0,
            valuation_end_date="2024-01-02",
        )

        self.assertEqual(result["status"], "COMPLETE_WITH_CONDITIONAL_REPAIR")
        self.assertTrue(result["search_complete"])
        self.assertTrue(result["path_complete"])
        self.assertEqual(len(result["repair_events"]), 1)
        self.assertIn("ZERO_TARGET_SHARE", result["repair_events"].iloc[0]["trigger_reasons"])
        holdings = json.loads(result["path"].iloc[0]["holdings"])
        self.assertEqual(holdings["security:d"]["shares"], 1)
        self.assertGreaterEqual(result["path"].iloc[0]["cash_usd"], 90.0)

    def test_budget_exhaustion_never_commits_a_partial_path(self):
        date = pd.Timestamp("2024-01-02")
        closes = pd.DataFrame(
            {"A": [100.0], "B": [100.0], "C": [100.0], "D": [300.0]},
            index=[date],
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                "security:a": _target("A", "issuer:a", 0.25),
                "security:b": _target("B", "issuer:b", 0.25),
                "security:c": _target("C", "issuer:c", 0.25),
                "security:d": _target("D", "issuer:d", 0.25),
            },
        }]

        result = simulate_dynamic_security_id_conditional_repair_path(
            closes,
            schedule,
            execution_prices=closes.copy(),
            risk_chains_by_decision=_decision_chains(schedule),
            initial_cash_usd=1_000.0,
            minimum_cash_buffer_usd=90.0,
            transaction_cost_bps=10.0,
            valuation_end_date="2024-01-02",
            max_repair_evaluations=1,
        )

        self.assertEqual(result["status"], "RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        self.assertFalse(result["search_complete"])
        self.assertFalse(result["path_complete"])
        for key in ("summary", "rebalances", "trades", "path", "daily_risk"):
            self.assertIsNone(result[key])
        self.assertEqual(len(result["repair_events"]), 1)
        self.assertFalse(bool(result["repair_events"].iloc[0]["search_complete"]))
        self.assertGreater(result["repair_events"].iloc[0]["search_space_size"], 1)
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])

    def test_risk_chain_evidence_must_be_exact_for_every_decision(self):
        dates = pd.DatetimeIndex([pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")])
        closes = pd.DataFrame(
            {ticker: [100.0, 100.0] for ticker in ("A", "B", "C", "D")},
            index=dates,
        )
        schedule = [{
            "decision_date": "2024-01-01",
            "execution_date": "2024-01-02",
            "targets": {
                "security:a": _target("A", "issuer:a", 0.25),
                "security:b": _target("B", "issuer:b", 0.25),
                "security:c": _target("C", "issuer:c", 0.25),
                "security:d": _target("D", "issuer:d", 0.25),
            },
        }]
        missing_target = _decision_chains(schedule)
        del missing_target["2024-01-01"]["security:d"]
        with self.assertRaisesRegex(
            NdxDynamicWholeLotRepairPathError,
            "cover exactly that decision's targets",
        ):
            simulate_dynamic_security_id_conditional_repair_path(
                closes,
                schedule,
                execution_prices=closes.copy(),
                risk_chains_by_decision=missing_target,
                initial_cash_usd=25_000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date="2024-01-03",
            )

        stale_union = {
            "2024-01-01": _decision_chains(schedule)["2024-01-01"],
            "2023-12-29": _decision_chains(schedule)["2024-01-01"],
        }
        with self.assertRaisesRegex(
            NdxDynamicWholeLotRepairPathError,
            "cover exactly the scheduled decision dates",
        ):
            simulate_dynamic_security_id_conditional_repair_path(
                closes,
                schedule,
                execution_prices=closes.copy(),
                risk_chains_by_decision=stale_union,
                initial_cash_usd=25_000.0,
                minimum_cash_buffer_usd=100.0,
                valuation_end_date="2024-01-03",
            )


if __name__ == "__main__":
    unittest.main()
