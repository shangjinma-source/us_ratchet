import unittest
from types import SimpleNamespace

from backtest.broker_account_reconciliation import BrokerSnapshotError, reconcile_strategy_book


class BrokerAccountReconciliationTests(unittest.TestCase):
    def test_separates_account_truth_from_strategy_book(self):
        portfolio = SimpleNamespace(symbols={
            "MU": SimpleNamespace(shares=1.0, cost_basis=100.0),
            "CDNS": SimpleNamespace(shares=2.0, cost_basis=200.0),
        })
        result = reconcile_strategy_book(portfolio, [
            {"ticker": "MU", "shares": 3, "average_cost": 90, "observed_price": 80},
            {"ticker": "AVGO", "shares": 1, "average_cost": 100, "observed_price": 110},
        ])
        by_ticker = {row["ticker"]: row for row in result["reconciliation"]}
        self.assertEqual(by_ticker["MU"]["status"], "BROKER_OVERRIDES_STALE_STATE")
        self.assertEqual(by_ticker["AVGO"]["scope"], "BROKER_ONLY_OFF_STRATEGY")
        self.assertFalse(by_ticker["AVGO"]["portfolio_optimization_included"])
        self.assertEqual(by_ticker["CDNS"]["status"], "DO_NOT_TREAT_AS_REAL_POSITION")
        self.assertTrue(result["summary"]["strategy_and_account_separated"])

    def test_rejects_fractional_or_duplicate_positions(self):
        portfolio = SimpleNamespace(symbols={})
        with self.assertRaises(BrokerSnapshotError):
            reconcile_strategy_book(portfolio, [{"ticker": "X", "shares": 1.5, "average_cost": 1, "observed_price": 1}])
        with self.assertRaises(BrokerSnapshotError):
            reconcile_strategy_book(portfolio, [
                {"ticker": "X", "shares": 1, "average_cost": 1, "observed_price": 1},
                {"ticker": "X", "shares": 1, "average_cost": 1, "observed_price": 1},
            ])


if __name__ == "__main__":
    unittest.main()
