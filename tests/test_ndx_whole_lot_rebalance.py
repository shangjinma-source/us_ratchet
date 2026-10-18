import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_whole_lot_rebalance import (
    load_point_in_time_security_bars,
    simulate_continuous_whole_lot_rebalance,
)
from data.ndx_security_identity import load_security_lifecycle


class NdxWholeLotRebalanceTests(unittest.TestCase):
    def test_fisv_fi_lifecycle_is_stitched_by_security_identity(self):
        lifecycle = load_security_lifecycle("config/ndx_security_lifecycle.yaml")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pd.DataFrame([
                {"Date": "2023-06-05", "Close": 112.0, "Volume": 10},
                {"Date": "2023-06-06", "Close": 114.0, "Volume": 11},
            ]).to_csv(root / "FISV.csv", index=False)
            pd.DataFrame([
                {"Date": "2023-06-05", "Close": 112.0, "Volume": 10},
                {"Date": "2023-06-06", "Close": 114.0, "Volume": 11},
                {"Date": "2023-06-07", "Close": 115.0, "Volume": 12},
                {"Date": "2023-06-08", "Close": 116.0, "Volume": 13},
            ]).to_csv(root / "FI.csv", index=False)
            bars, audit = load_point_in_time_security_bars(
                ticker="FI",
                security_id="security:0000798354:337738108",
                return_cache_dir=root,
                lifecycle=lifecycle,
                end_exclusive=pd.Timestamp("2023-06-09"),
            )
        self.assertEqual(bars.index.strftime("%Y-%m-%d").tolist(), [
            "2023-06-05", "2023-06-06", "2023-06-07", "2023-06-08",
        ])
        self.assertEqual(audit["source_tickers"], "FISV;FI")
        self.assertTrue(audit["cross_ticker_stitched"])

    def test_whole_lot_rebalance_carries_shares_cash_and_costs(self):
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        prices = pd.DataFrame({
            "A": [100, 102, 101, 104, 105],
            "B": [80, 79, 81, 82, 83],
            "C": [50, 51, 52, 51, 53],
            "D": [40, 41, 42, 43, 44],
        }, index=dates)
        schedule = [
            (dates[0], {"A": .25, "B": .25, "C": .25, "D": .25}),
            (dates[2], {"A": .40, "B": .20, "C": .20, "D": .20}),
        ]
        summary, ledger = simulate_continuous_whole_lot_rebalance(
            prices, schedule,
            risk_chain_by_ticker={"A": "a", "B": "b", "C": "c", "D": "d"},
            portfolio_cash_usd=1000.0,
            minimum_cash_buffer_usd=100.0,
            transaction_cost_bps=10.0,
            max_single_weight=.45,
            min_single_weight=.05,
            top_weight_cap=.85,
            minimum_effective_n_ratio=.70,
            risk_chain_top1_cap=.55,
        )
        self.assertEqual(len(ledger), 2)
        self.assertEqual(summary["whole_lot_rebalance_count"], 2)
        self.assertGreater(summary["whole_lot_total_transaction_cost_usd"], 0)
        self.assertGreater(summary["whole_lot_share_change_count"], 0)
        self.assertGreaterEqual(summary["whole_lot_min_cash_usd"], 100.0 - 1e-9)
        self.assertTrue(summary["whole_lot_cash_buffer_preserved"])
        self.assertEqual(len(summary["whole_lot_rebalance_trace_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
