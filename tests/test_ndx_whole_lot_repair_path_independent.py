"""Independent intervention-boundary checks for continuous lot repair."""
import unittest

import pandas as pd

from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from backtest.ndx_whole_lot_repair_path import simulate_conditional_whole_lot_repair_path


class ConditionalRepairPathIndependentTests(unittest.TestCase):
    def contract(self):
        return dict(
            risk_chain_by_ticker={name: name for name in "ABCD"},
            portfolio_cash_usd=10000, minimum_cash_buffer_usd=100,
            transaction_cost_bps=10, max_single_weight=.45, min_single_weight=.05,
            top_weight_cap=.8, minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55,
        )

    def test_noncanonical_daily_coordinates_are_rejected(self):
        for coordinate in (
            ["2024-01-02", "2024-01-02"],
            ["2024-01-03", "2024-01-02"],
            ["2024-01-02 15:00", "2024-01-03 15:00"],
        ):
            with self.subTest(coordinate=coordinate):
                prices = pd.DataFrame({name: [100., 100.] for name in "ABCD"},
                                      index=pd.to_datetime(coordinate))
                with self.assertRaises(ValueError):
                    simulate_conditional_whole_lot_repair_path(
                        prices, [(pd.Timestamp("2024-01-02"), {name: .25 for name in "ABCD"})],
                        **self.contract(),
                    )

    def test_holding_day_risk_failure_does_not_invent_a_rebalance(self):
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        prices = pd.DataFrame({name: [100., 100., 100.] for name in "ABCD"}, index=dates)
        prices.loc[dates[1], "D"] = 30.
        schedule = [(dates[0], {name: .25 for name in "ABCD"}),
                    (dates[2], {name: .25 for name in "ABCD"})]
        expected, expected_ledger = simulate_continuous_whole_lot_rebalance(prices, schedule, **self.contract())
        actual, actual_ledger = simulate_conditional_whole_lot_repair_path(prices, schedule, **self.contract())
        self.assertEqual(actual["summary"], expected)
        pd.testing.assert_frame_equal(actual_ledger, expected_ledger)
        self.assertEqual(actual["repair_invocation_count"], 0)
        self.assertFalse(actual["execution_eligible"])
        self.assertTrue(actual["search_complete"])
        self.assertEqual(actual["daily_risk_audit"]["failure_session_count"], 1)

    def test_exhausted_repair_does_not_publish_partial_economic_summary(self):
        prices = pd.DataFrame({"A": [400.], "B": [200.], "C": [120.], "D": [150.]},
                              index=pd.to_datetime(["2024-01-02"]))
        contract = self.contract()
        contract["portfolio_cash_usd"] = 1000
        result, _ = simulate_conditional_whole_lot_repair_path(
            prices, [(prices.index[0], {name: .25 for name in "ABCD"})],
            max_repair_evaluations=1, **contract,
        )
        self.assertFalse(result["search_complete"])
        self.assertIsNone(result["summary"])
        self.assertIsNone(result["daily_risk_audit"])
        self.assertFalse(result["execution_eligible"])


if __name__ == "__main__":
    unittest.main()
