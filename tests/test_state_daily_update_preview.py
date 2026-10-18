from __future__ import annotations

import unittest
from types import SimpleNamespace

from core.state import Portfolio, SymbolState
from scripts.state_daily_update_preview import portfolio_diff


class StateDailyUpdatePreviewTests(unittest.TestCase):
    def test_diff_reports_state_transition_and_immediate_buys_without_mutating_before(self):
        before = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=1000, shares=2, reserve_cash=100, H=100)},
            flows=[], day_index=1, last_run_date="2026-07-01",
        )
        after = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=1000, shares=3, reserve_cash=50, H=110)},
            flows=[], day_index=2, last_run_date="2026-07-30",
        )
        rows = portfolio_diff(
            before, after,
            [SimpleNamespace(ticker="AAA", immediate_buys=[(50.0, 50.0, "due")])],
        )
        self.assertEqual(rows[0]["field_change_count"], 3)
        self.assertEqual(rows[0]["immediate_buy_count"], 1)
        self.assertEqual(before.symbols["AAA"].shares, 2)
        self.assertEqual(before.last_run_date, "2026-07-01")


if __name__ == "__main__":
    unittest.main()
