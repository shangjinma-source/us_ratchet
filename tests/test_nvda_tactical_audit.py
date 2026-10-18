from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from api import server
from core.config import load_config
from scripts.nvda_tactical_audit import _effective_ratio, _read_local_bars, replay_tactical_signals


ROOT = Path(__file__).resolve().parents[1]


class NvdaTacticalAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config(ROOT / "config" / "config.yaml")
        cls.frames = {
            ticker: _read_local_bars(ROOT / "data" / "cache" / f"{ticker}.csv")
            for ticker in ("NVDA", "QQQ", "SPY")
        }

    def test_bear_ratio_is_fail_closed_and_neutral_limit_is_computed(self):
        signals = replay_tactical_signals(
            self.frames,
            self.cfg,
            start="2026-06-23",
            end="2026-07-14",
        )
        by_date = signals.set_index("signal_date")

        self.assertEqual(_effective_ratio(self.cfg, "BEAR"), 0.0)
        self.assertEqual(by_date.loc["2026-07-02", "regime"], "BEAR")
        self.assertEqual(by_date.loc["2026-07-02", "action"], "WAIT")
        self.assertEqual(by_date.loc["2026-07-14", "regime"], "NEUTRAL")
        self.assertEqual(by_date.loc["2026-07-14", "action"], "PLACE_LIMIT")
        self.assertAlmostEqual(float(by_date.loc["2026-07-14", "limit"]), 202.22, places=2)

    def test_replay_does_not_use_bars_after_signal_date(self):
        signals = replay_tactical_signals(
            self.frames,
            self.cfg,
            start="2026-07-07",
            end="2026-07-07",
        )
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals.iloc[0]["signal_date"], "2026-07-07")
        self.assertEqual(signals.iloc[0]["action"], "WAIT")

    def test_tactical_budget_is_marked_sub_lot_under_whole_share_rule(self):
        context = server._tactical_execution_context(41.0, 202.22, self.cfg)
        self.assertEqual(context["status"], "SUB_LOT_OBSERVATION")
        self.assertFalse(context["whole_lot_ready"])
        self.assertAlmostEqual(context["minimum_lot_notional"], 202.22, places=2)

    def test_market_gate_uses_closed_bar_not_intraday_quote(self):
        dates = pd.date_range("2025-01-01", periods=220, freq="B")
        frame = pd.DataFrame(
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1.0},
            index=dates,
        )
        server._bars_cache.clear()
        server._bars_cache["QQQ"] = frame
        stats = server._market_stats(
            "QQQ",
            self.cfg,
            self.cfg.tactical_orders,
            latest_price=90.0,
            price_info={"source": "sina_quote", "mode": "quote"},
        )
        self.assertEqual(stats["regime"], "BULL")
        self.assertEqual(stats["signal_price_source"], "daily_close")
        self.assertEqual(stats["signal_price"], 100.0)
        self.assertEqual(stats["last"], 90.0)


if __name__ == "__main__":
    unittest.main()
