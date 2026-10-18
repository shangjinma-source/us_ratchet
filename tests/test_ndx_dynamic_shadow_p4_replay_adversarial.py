"""Independent rejection tests for economic replay inputs, not gate summaries."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from backtest.ndx_dynamic_shadow_p4_replay import (
    NdxDynamicShadowP4ReplayError,
    _parse_price_bytes,
    _read_target,
    _regime,
    replay_cohort_evaluations,
)


class EconomicReplayInputAdversarialTests(unittest.TestCase):
    def _replay_fixture(self, *, missing_first_price=False, zero_shares=False):
        from test_ndx_dynamic_shadow_p4_replay import _active_and_cohort, _economic_inputs
        active, cohort, original8 = _active_and_cohort()
        prices, target = _economic_inputs()
        if missing_first_price:
            after_observation = prices["B"].index > pd.Timestamp(cohort["observation_date"])
            first = prices["B"].index[after_observation][0]
            prices["B"] = prices["B"].drop(first)
        if zero_shares:
            mask = cohort["positions"]["track_role"].eq("CHALLENGER")
            cohort["positions"].loc[mask, "cohort_whole_lot_shares"] = 0
        return replay_cohort_evaluations(
            active, [cohort], prices, target,
            {"primary_horizon_trading_days": 3,
             "standardized_execution_cash_usd": 25000,
             "minimum_cash_buffer_usd": 100, "transaction_cost_bps": 10},
            original8,
        )

    def test_missing_first_session_cannot_shift_one_track_entry(self):
        with self.assertRaises(NdxDynamicShadowP4ReplayError):
            self._replay_fixture(missing_first_price=True)

    def test_zero_self_reported_shares_cannot_pass_as_executable(self):
        with self.assertRaises(NdxDynamicShadowP4ReplayError):
            self._replay_fixture(zero_shares=True)

    def test_price_parser_rejects_invalid_rows_instead_of_silently_cleaning(self):
        invalid_rows = (
            "2026-09-01,100,101\n2026-09-01,100,102\n",
            "2026-09-01,100,101\nnot-a-date,100,102\n",
            "2026-09-01,100,101\n2026-09-02,NaN,102\n",
            "2026-09-01,100,101\n2026-09-02,100,inf\n",
            "2026-09-01,100,101\n2026-09-02,0,102\n",
            "2026-09-01,100,101\n2026-09-02,100,-1\n",
        )
        for rows in invalid_rows:
            with self.subTest(rows=rows):
                with self.assertRaises(NdxDynamicShadowP4ReplayError):
                    _parse_price_bytes(("Date,Open,Close\n" + rows).encode(), "QQQ")

    def test_target_parser_rejects_duplicate_invalid_or_nonpositive_nav(self):
        invalid_rows = (
            "2026-09-01,1\n2026-09-01,2\n",
            "2026-09-01,1\nnot-a-date,2\n",
            "2026-09-01,1\n2026-09-02,NaN\n",
            "2026-09-01,1\n2026-09-02,0\n",
            "2026-09-01,1\n2026-09-02,-1\n",
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "012922.csv"
            for rows in invalid_rows:
                with self.subTest(rows=rows):
                    path.write_text("Date,Close\n" + rows, encoding="utf-8")
                    with self.assertRaises(NdxDynamicShadowP4ReplayError):
                        _read_target(path)

    def test_regime_excludes_prices_after_observation_date(self):
        dates = pd.bdate_range("2025-01-01", periods=205)
        prices = pd.DataFrame({"Close": list(range(100, 300)) + [1] * 5}, index=dates)
        self.assertEqual(_regime(prices, dates[199].strftime("%Y-%m-%d")), "BULL")
        self.assertEqual(_regime(prices, dates[198].strftime("%Y-%m-%d")), "INSUFFICIENT_HISTORY")


if __name__ == "__main__":
    unittest.main()
