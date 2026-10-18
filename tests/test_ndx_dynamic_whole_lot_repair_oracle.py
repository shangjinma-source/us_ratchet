"""Independent rational cash-flow oracle for dynamic composition repair."""
from fractions import Fraction
from itertools import product
import json
import unittest

import pandas as pd

from backtest.ndx_dynamic_whole_lot_repair_path import (
    simulate_dynamic_security_id_conditional_repair_path,
)


def _fraction(value):
    return Fraction(str(value))


def _fixture():
    dates = pd.bdate_range("2024-01-02", periods=3)
    opens = pd.DataFrame({
        "A": [350., 350., 350.], "B": [100., 100., 110.],
        "C": [50., 50., 45.], "D": [25., 25., 30.],
        "E": [140., 140., 140.], "F": [90., 90., 90.],
    }, index=dates)
    closes = opens * 1.07
    definitions = [
        ("2024-01-01", "2024-01-02", {"A": .4, "B": .2, "C": .2, "D": .2}),
        ("2024-01-03", "2024-01-04", {"B": .15, "C": .15, "D": .1, "E": .45, "F": .15}),
    ]
    schedule = [{
        "decision_date": decision, "execution_date": execution,
        "targets": {ticker: {"ticker": ticker, "issuer_id": "issuer:" + ticker,
                              "target_weight": weight}
                    for ticker, weight in weights.items()},
    } for decision, execution, weights in definitions]
    arguments = dict(
        execution_prices=opens,
        require_separate_execution_prices=True,
        require_next_session_execution=True,
        require_issuer_trace=True,
        risk_chains_by_decision={item["decision_date"]: {
            security: "chain:" + security for security in item["targets"]
        } for item in schedule},
        initial_cash_usd=1000., minimum_cash_buffer_usd=20.,
        transaction_cost_bps=100., valuation_end_date="2024-01-04",
    )
    return closes, schedule, arguments


class DynamicRepairCashOracleTests(unittest.TestCase):
    def test_complete_but_infeasible_neighborhood_is_not_a_completed_path(self):
        closes, schedule, arguments = _fixture()
        arguments["execution_prices"]["A"] = 390.
        closes["A"] = 390. * 1.07
        feasible = []
        for quantities in product((1, 2), (1, 2), (3, 4), (7, 8)):
            notionals = [Fraction(quantity * price) for quantity, price
                         in zip(quantities, (390, 100, 50, 25))]
            invested = sum(notionals)
            if 1000 - invested * Fraction(101, 100) < 20:
                continue
            weights = sorted(value / invested for value in notionals)
            if (weights[-1] <= Fraction(45, 100)
                    and weights[0] >= Fraction(5, 100)
                    and sum(weights[-3:]) <= Fraction(80, 100)
                    and 1 / sum(value * value for value in weights) >= Fraction(28, 10)
                    and weights[-1] <= Fraction(55, 100)):
                feasible.append(quantities)
        self.assertEqual(feasible, [])
        result = simulate_dynamic_security_id_conditional_repair_path(closes, schedule, **arguments)
        self.assertTrue(result["search_complete"])
        self.assertFalse(result["path_complete"])
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])
        for key in ("summary", "rebalances", "trades", "path"):
            self.assertIsNone(result[key])

    def test_cross_composition_cash_and_nav_rebuild_from_integer_trades(self):
        closes, schedule, arguments = _fixture()
        result = simulate_dynamic_security_id_conditional_repair_path(
            closes, schedule, **arguments)
        self.assertTrue(result["path_complete"], result["status"])
        self.assertFalse(result["legacy_exact_reuse"])
        self.assertEqual(len(result["repair_events"]), 2)
        self.assertEqual(result["repair_events"].iloc[1]["removed_sell_notional_usd"], 350.)
        self.assertEqual(result["summary"]["k_path"], [4, 5])
        cash = Fraction(1000)
        total_fees = Fraction(0)
        shares = {}
        values = [Fraction(1000)]
        trades = result["trades"].to_dict("records")
        for row in result["path"].to_dict("records"):
            day = row["date"]
            for trade in [value for value in trades if value["execution_date"] == day]:
                self.assertEqual(trade["event_type"], "ECONOMIC_TRADE")
                security = trade["security_id"]
                delta = int(trade["share_delta"])
                self.assertEqual(delta, trade["share_delta"])
                self.assertEqual(shares.get(security, 0), trade["shares_before"])
                price = _fraction(arguments["execution_prices"].at[
                    pd.Timestamp(day), trade["trade_ticker"]])
                notional = abs(delta) * price
                fee = notional / 100
                self.assertAlmostEqual(float(price), trade["price_usd"], places=8)
                self.assertAlmostEqual(float(notional), trade["notional_usd"], places=8)
                self.assertAlmostEqual(float(fee), trade["transaction_cost_usd"], places=8)
                cash -= delta * price + fee
                total_fees += fee
                shares[security] = shares.get(security, 0) + delta
                self.assertGreaterEqual(shares[security], 0)
                self.assertEqual(shares[security], trade["shares_after"])
            holdings = json.loads(row["holdings"])
            self.assertEqual({key: value for key, value in shares.items() if value},
                             {key: value["shares"] for key, value in holdings.items()})
            value = cash + sum(_fraction(closes.at[pd.Timestamp(day), holding["ticker"]])
                               * holding["shares"] for holding in holdings.values())
            values.append(value)
            self.assertGreaterEqual(cash, Fraction(20))
            self.assertAlmostEqual(float(cash), row["cash_usd"], places=8)
            self.assertAlmostEqual(float(value), row["total_value_usd"], places=8)
        self.assertEqual(shares.get("A"), 0)
        self.assertGreater(shares.get("E", 0), 0)
        self.assertGreater(shares.get("F", 0), 0)
        summary = result["summary"]
        self.assertAlmostEqual(float(total_fees), summary["total_transaction_cost_usd"], places=8)
        self.assertAlmostEqual(float(values[-1] / 1000 - 1), summary["path_return_net"], places=8)
        peak = values[0]
        drawdown = Fraction(0)
        for value in values:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        self.assertAlmostEqual(float(drawdown), summary["path_max_drawdown"], places=8)

    def test_future_values_cannot_change_the_completed_path(self):
        closes, schedule, arguments = _fixture()
        baseline = simulate_dynamic_security_id_conditional_repair_path(closes, schedule, **arguments)
        self.assertTrue(baseline["path_complete"], baseline["status"])
        closes.loc[pd.Timestamp("2024-01-05")] = float("nan")
        arguments["execution_prices"].loc[pd.Timestamp("2024-01-05")] = 1e12
        changed = simulate_dynamic_security_id_conditional_repair_path(closes, schedule, **arguments)
        self.assertEqual(baseline["summary"], changed["summary"])
        for key in ("rebalances", "trades", "path", "daily_risk", "repair_events"):
            pd.testing.assert_frame_equal(baseline[key], changed[key])


if __name__ == "__main__":
    unittest.main()
