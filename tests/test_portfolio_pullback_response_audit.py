import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import load_config
from core.state import Portfolio, SymbolState
from scripts.portfolio_pullback_response_audit import (
    current_gap_snapshot,
    replay_portfolio_response,
)


ROOT = Path(__file__).resolve().parents[1]


class PortfolioPullbackResponseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config(ROOT / "config" / "config.yaml")

    def _frames(self):
        dates = pd.bdate_range("2025-01-02", periods=230)
        base = np.linspace(100.0, 130.0, len(dates))
        frames = {}
        names = [s.ticker for s in self.cfg.symbols] + list(self.cfg.tactical_orders.market_gate_tickers)
        for name in names:
            close = base.copy()
            close[-1] = close[-2] * (0.92 if name == "MU" else 0.98)
            if name in {"QQQ", "SPY"}:
                close[-1] = close[-2] * (0.85 if name == "QQQ" else 1.001)
            frames[name] = pd.DataFrame({
                "Open": close, "High": close * 1.01,
                "Low": close * 0.99, "Close": close,
            }, index=dates)
        return frames

    def _portfolio(self):
        return Portfolio(symbols={
            symbol.ticker: SymbolState(
                ticker=symbol.ticker,
                cap_total=symbol.cap_total,
                H=150.0,
                reserve_cash=100.0,
                entry_date="2025-01-02" if symbol.ticker == "NVDA" else None,
            )
            for symbol in self.cfg.symbols
        }, flows=[])

    def test_market_bear_blocks_all_tactical_orders_and_marks_dead_zone(self):
        frames = self._frames()
        end = frames["QQQ"].index[-1].strftime("%Y-%m-%d")
        detail, daily, gate = replay_portfolio_response(
            frames, self.cfg, portfolio=self._portfolio(), start=end, end=end
        )
        self.assertEqual(len(detail), len(self.cfg.symbols))
        self.assertTrue((detail["action"] == "WAIT").all())
        self.assertTrue(detail["blocked_by_market_bear"].all())
        self.assertEqual(daily.iloc[0]["market_regime"], "BEAR")
        self.assertTrue(bool(daily.iloc[0]["pullback_dead_zone"]))
        self.assertTrue(any(row["ticker"] == "QQQ" and row["distance_to_ma50"] < 0 for row in gate))

    def test_current_gap_uses_state_h_without_reconstructing_history(self):
        frames = self._frames()
        end = frames["QQQ"].index[-1].strftime("%Y-%m-%d")
        portfolio = self._portfolio()
        detail, _, _ = replay_portfolio_response(
            frames, self.cfg, portfolio=portfolio, start=end, end=end
        )
        snapshot = current_gap_snapshot(detail, self.cfg, portfolio)
        nvda = snapshot[snapshot["ticker"] == "NVDA"].iloc[0]
        self.assertAlmostEqual(nvda["first_ratchet_limit"], 112.5)
        self.assertEqual(nvda["position_status"], "real_position")


if __name__ == "__main__":
    unittest.main()
