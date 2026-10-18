from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from backtest.state_catchup import (
    StateCatchupError,
    build_exact_session_close_panel,
    build_reconciliation_template,
    replay_session_catchup,
    validate_reconciliation_contract,
)
from core.state import Portfolio, SymbolState
from core.config import load_config


ROOT = Path(__file__).resolve().parents[1]


class StateCatchupTests(unittest.TestCase):
    def _portfolio(self):
        return Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, H=10, entry_date="2026-07-15", entry_price=10)},
            flows=[], day_index=2, last_run_date="2026-07-01",
        )

    def test_template_is_incomplete_and_suggests_latest_known_event_date(self):
        template = build_reconciliation_template(self._portfolio())
        self.assertEqual(template["snapshot_as_of"], "2026-07-15")
        result = validate_reconciliation_contract(template, {"AAA"})
        self.assertFalse(result["ready"])

    def test_complete_matching_contract_is_ready(self):
        template = build_reconciliation_template(self._portfolio())
        template["snapshot_as_of_user_confirmed"] = True
        template["holdings"][0].update({
            "actual_position_held": True, "actual_whole_shares": 1,
            "actual_entry_date": "2026-07-15", "actual_average_cost": 10,
            "state_snapshot_matches_account": True,
        })
        result = validate_reconciliation_contract(template, {"AAA"})
        self.assertTrue(result["ready"])

    def test_catchup_advances_every_session_not_one_large_jump(self):
        cfg = load_config(ROOT / "config/config.yaml")
        portfolio = Portfolio(
            symbols={
                symbol.ticker: SymbolState(
                    ticker=symbol.ticker, cap_total=symbol.cap_total,
                    shares=1, reserve_cash=100, reserve_budget=100, H=10,
                    tier_armed=[True, True], entry_date="2026-07-15", entry_price=10,
                )
                for symbol in cfg.symbols
            },
            flows=[], day_index=2, last_run_date="2026-07-01",
        )
        closes_1 = {symbol.ticker: 11.0 for symbol in cfg.symbols}
        closes_2 = {symbol.ticker: 12.0 for symbol in cfg.symbols}
        proposed, ledger = replay_session_catchup(
            portfolio, cfg, snapshot_as_of="2026-07-15",
            session_closes={"2026-07-16": closes_1, "2026-07-17": closes_2},
        )
        self.assertEqual(proposed.last_run_date, "2026-07-17")
        self.assertEqual(proposed.day_index, 4)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(portfolio.last_run_date, "2026-07-01")

    def test_exact_panel_keeps_every_cross_ticker_session(self):
        cfg = SimpleNamespace(symbols=[SimpleNamespace(ticker="AAA"), SimpleNamespace(ticker="BBB")])
        frames = {
            ticker: pd.DataFrame(
                {"Close": values},
                index=pd.to_datetime(["2026-07-31", "2026-08-03", "2026-08-04"]),
            )
            for ticker, values in {"AAA": [10, 11, 12], "BBB": [20, 21, 22]}.items()
        }
        panel, audit = build_exact_session_close_panel(
            cfg, frames, snapshot_as_of="2026-07-30", latest_session="2026-08-04",
        )
        self.assertEqual(list(panel), ["2026-07-31", "2026-08-03", "2026-08-04"])
        self.assertEqual(panel["2026-08-03"], {"AAA": 11.0, "BBB": 21.0})
        self.assertEqual(audit["session_count"], 3)

    def test_exact_panel_fails_closed_on_internal_ticker_gap(self):
        cfg = SimpleNamespace(symbols=[SimpleNamespace(ticker="AAA"), SimpleNamespace(ticker="BBB")])
        frames = {
            "AAA": pd.DataFrame(
                {"Close": [10, 11]}, index=pd.to_datetime(["2026-07-31", "2026-08-03"]),
            ),
            "BBB": pd.DataFrame(
                {"Close": [20]}, index=pd.to_datetime(["2026-08-03"]),
            ),
        }
        with self.assertRaisesRegex(StateCatchupError, "incomplete cross-ticker session panel"):
            build_exact_session_close_panel(
                cfg, frames, snapshot_as_of="2026-07-30", latest_session="2026-08-03",
            )

    def test_exact_twenty_five_session_catchup_advances_one_day_at_a_time(self):
        cfg = load_config(ROOT / "config/config.yaml")
        sessions = pd.bdate_range("2026-07-31", periods=25)
        frames = {
            symbol.ticker: pd.DataFrame(
                {"Close": [100.0 + offset for offset in range(25)]},
                index=sessions,
            )
            for symbol in cfg.symbols
        }
        portfolio = Portfolio(
            symbols={
                symbol.ticker: SymbolState(
                    ticker=symbol.ticker,
                    cap_total=symbol.cap_total,
                    shares=1,
                    reserve_cash=100,
                    reserve_budget=100,
                    H=1_000,
                    tier_armed=[True, True],
                    entry_date="2026-07-15",
                    entry_price=100,
                )
                for symbol in cfg.symbols
            },
            flows=[],
            day_index=22,
            last_run_date="2026-07-30",
        )

        panel, audit = build_exact_session_close_panel(
            cfg,
            frames,
            snapshot_as_of="2026-07-30",
            latest_session=sessions[-1].date().isoformat(),
        )
        proposed, ledger = replay_session_catchup(
            portfolio,
            cfg,
            snapshot_as_of="2026-07-30",
            session_closes=panel,
        )

        self.assertEqual(audit["session_count"], 25)
        self.assertEqual(len(ledger), 25)
        self.assertEqual([row["day_index_after"] for row in ledger], list(range(23, 48)))
        self.assertEqual(proposed.day_index, 47)
        self.assertEqual(proposed.last_run_date, sessions[-1].date().isoformat())
        self.assertEqual(portfolio.day_index, 22)
        self.assertEqual(portfolio.last_run_date, "2026-07-30")


if __name__ == "__main__":
    unittest.main()
