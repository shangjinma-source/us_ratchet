from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd

from api.server import (
    _config_health_payload,
    _daily_bar_freshness_payload,
    _execution_payload,
    _latest_closed_session_date,
    _position_gap_payload,
)


def _cfg(**caps):
    return SimpleNamespace(
        symbols=[SimpleNamespace(ticker=ticker, cap_total=cap) for ticker, cap in caps.items()]
    )


class PositionGapModelTests(unittest.TestCase):
    def test_config_health_does_not_present_absent_sgov_as_pending_real_position(self):
        cfg = SimpleNamespace(
            portfolio=SimpleNamespace(
                core_ratio=0.9,
                tiers=SimpleNamespace(thresholds=(-0.25, -0.45), deploy_ratios=(0.4, 0.6)),
            ),
            safe_leg=SimpleNamespace(ticker="SGOV", target_weight=0.26, exec_band=0.15),
            tactical_orders=SimpleNamespace(
                enabled=True, ma_short=5, ma_mid=20, bull_atr_mult=0.6,
                neutral_atr_mult=1.0, bear_atr_mult=1.8,
            ),
            execution=SimpleNamespace(),
        )
        payload = _config_health_payload(cfg, safe=None, market=None, execution=None)
        defense = next(row for row in payload["checks"] if row["name"] == "防御层")
        self.assertEqual(defense["status"], "ignored_legacy_config")
        self.assertIn("不计入真实账户", defense["summary"])
        self.assertNotIn("目标 W=", defense["summary"])

    def test_book_only_holdings_never_reduce_real_gap(self):
        symbols = [
            {
                "ticker": "REAL",
                "entry_date": "2026-01-02",
                "position_status": "real",
                "real_shares": 5,
                "real_market_value": 600,
                "real_cost_basis": 500,
                "book_shares": 5,
                "book_market_value": 600,
                "book_cost_basis": 500,
            },
            {
                "ticker": "BOOK",
                "entry_date": None,
                "position_status": "book_only",
                "real_shares": 0,
                "real_market_value": 0,
                "real_cost_basis": 0,
                "book_shares": 9,
                "book_market_value": 900,
                "book_cost_basis": 810,
            },
            {
                "ticker": "CLOSED",
                "entry_date": "2026-02-02",
                "is_real_position": False,
                "position_status": "broker_reported_closed",
                "reported_closed": True,
                "reported_closed_as_of": "2026-09-04",
                "reported_closed_note": "user reported sold",
                "real_shares": 0,
                "real_market_value": 0,
                "real_cost_basis": 0,
                "book_shares": 4,
                "book_market_value": 800,
                "book_cost_basis": 700,
            },
        ]

        model = _position_gap_payload(
            symbols,
            _cfg(REAL=1000, BOOK=2000, CLOSED=1200),
            _cfg(REAL=1500, BOOK=2000, CLOSED=1200),
        )
        rows = {row["ticker"]: row for row in model["rows"]}

        self.assertEqual(rows["REAL"]["position_kind"], "real_position")
        self.assertEqual(rows["REAL"]["target_amount"], 1000)
        self.assertEqual(rows["REAL"]["configured_reference_target"], 1500)
        self.assertEqual(rows["REAL"]["gap_amount"], 400)
        self.assertEqual(rows["BOOK"]["position_kind"], "pending_entry")
        self.assertEqual(rows["BOOK"]["real_market_value"], 0)
        self.assertEqual(rows["BOOK"]["book_market_value_ignored"], 900)
        self.assertEqual(rows["BOOK"]["gap_amount"], 2000)
        self.assertLess(rows["BOOK"]["gap_rank"], rows["REAL"]["gap_rank"])
        self.assertEqual(rows["CLOSED"]["position_kind"], "reported_closed")
        self.assertEqual(rows["CLOSED"]["position_label"], "已清仓待新信号")
        self.assertFalse(rows["CLOSED"]["core_deployment_eligible"])
        self.assertEqual(model["reported_closed_count"], 1)
        self.assertEqual(model["reported_closed_tickers"], ["CLOSED"])

    def test_broker_snapshot_marks_real_without_strategy_entry_date(self):
        symbols = [{
            "ticker": "MU", "entry_date": None, "is_real_position": True,
            "position_status": "broker_real", "real_shares": 3,
            "real_market_value": 2400, "real_cost_basis": 2650.8,
            "book_shares": 1, "book_market_value": 800, "book_cost_basis": 893.36,
        }]
        model = _position_gap_payload(symbols, _cfg(MU=3000), _cfg(MU=3300))
        row = model["rows"][0]
        self.assertEqual(row["position_kind"], "real_position")
        self.assertEqual(row["real_shares"], 3)
        self.assertEqual(row["gap_amount"], 600)

    def test_book_only_ladder_signals_are_not_share_plan_candidates(self):
        common = {
            "frozen": False,
            "last_close": 100,
            "advice": {
                "action": "BUY_NOW",
                "immediate": [{"amount": 100, "price": 100, "reason": "due"}],
                "triggered": [],
                "next_order": None,
            },
            "tactical": {
                "action": "PLACE_LIMIT",
                "amount": 50,
                "shares": 0.5,
                "limit": 95,
                "live_price": 100,
                "trigger": 95,
                "reason": "test",
                "text": "test",
            },
        }
        payload = _execution_payload(
            [
                {**common, "ticker": "REAL", "entry_date": "2026-01-02", "position_status": "real"},
                {**common, "ticker": "BOOK", "entry_date": None, "position_status": "book_only"},
                {
                    **common,
                    "ticker": "ENTRY",
                    "entry_date": None,
                    "position_status": "book_only",
                    "advice": {"action": "WAIT", "immediate": [], "triggered": [], "next_order": None},
                },
                {
                    **common,
                    "ticker": "CLOSED",
                    "entry_date": "2026-02-02",
                    "is_real_position": False,
                    "reported_closed": True,
                    "position_status": "broker_reported_closed",
                    "advice": {"action": "WAIT", "immediate": [], "triggered": [], "next_order": None},
                },
            ],
            defensive=None,
            price_meta=None,
        )
        by_key = {(item["ticker"], item["source"]): item for item in payload["items"]}

        self.assertTrue(by_key[("REAL", "pending_core")]["share_plan_eligible"])
        self.assertFalse(by_key[("BOOK", "pending_core")]["share_plan_eligible"])
        self.assertTrue(by_key[("ENTRY", "tactical_limit")]["share_plan_eligible"])
        self.assertEqual(by_key[("ENTRY", "tactical_limit")]["position_intent"], "OPEN")
        self.assertFalse(by_key[("CLOSED", "tactical_limit")]["share_plan_eligible"])
        self.assertEqual(by_key[("CLOSED", "tactical_limit")]["account_scope"], "reported_closed")
        self.assertEqual(payload["excluded_book_signal_count"], 2)
        self.assertEqual(payload["counts"]["buy_now"], 1)
        self.assertEqual(payload["strategy_counts"]["buy_now"], 2)
        self.assertEqual(payload["strategy_actionable_count"], 4)
        self.assertEqual(payload["whole_lot_buy_actionable_count"], 1)
        self.assertEqual(payload["actionable_count"], 1)

    def test_next_ratchet_is_reference_not_today_actionable(self):
        payload = _execution_payload(
            [{
                "ticker": "REAL", "entry_date": "2026-01-02", "is_real_position": True,
                "position_status": "broker_real", "frozen": False, "last_close": 100,
                "advice": {
                    "action": "PLACE_LIMIT", "immediate": [], "triggered": [],
                    "next_order": {"tier": 1, "amount": 50, "shares": 0.5, "limit": 80, "threshold": -0.2},
                },
                "tactical": {"action": "WAIT", "amount": 0},
            }],
            defensive=None,
            price_meta=None,
        )
        self.assertEqual(payload["actionable_count"], 0)
        self.assertEqual(payload["counts"]["place_limit"], 0)
        self.assertEqual(payload["deep_reference_count"], 1)

    def test_latest_closed_session_date_uses_common_complete_bar(self):
        cfg = _cfg(REAL=1000, LAGGING=1000)
        bars = {
            "REAL": pd.DataFrame(
                {"Close": [100.0]}, index=pd.to_datetime(["2026-07-14"])
            ),
            "LAGGING": pd.DataFrame(
                {"Close": [100.0]}, index=pd.to_datetime(["2026-07-13"])
            ),
        }
        with patch("api.server._bars_for", side_effect=lambda ticker, _cfg: bars[ticker]):
            self.assertEqual(
                _latest_closed_session_date(cfg).isoformat(),
                "2026-07-13",
            )

    def test_daily_bar_freshness_exposes_quote_session_lag(self):
        cfg = _cfg(REAL=1000, LAGGING=1000)
        cfg.tactical_orders = SimpleNamespace(market_gate_tickers=("QQQ", "SPY"))
        bars = {
            ticker: pd.DataFrame(
                {"Close": [100.0]}, index=pd.to_datetime([last_date])
            )
            for ticker, last_date in {
                "REAL": "2026-07-17", "LAGGING": "2026-07-16",
                "QQQ": "2026-07-16", "SPY": "2026-07-17",
            }.items()
        }
        price_meta = {
            "as_of": "2026-07-18 08:00:00",
            "items": {
                ticker: {"ticker": ticker, "mode": "quote", "market_time": "Jul 17 04:00PM EDT"}
                for ticker in bars
            },
        }
        market = {"items": [
            {"ticker": "QQQ", "as_of": "2026-07-16"},
            {"ticker": "SPY", "as_of": "2026-07-17"},
        ]}
        with patch("api.server._bars_for", side_effect=lambda ticker, _cfg: bars[ticker]):
            result = _daily_bar_freshness_payload(cfg, price_meta, market)

        self.assertEqual(result["status"], "DAILY_BARS_LAG_QUOTE_SESSION")
        self.assertEqual(result["quote_session_date"], "2026-07-17")
        self.assertEqual(result["common_risk_daily_bar_date"], "2026-07-16")
        self.assertEqual(result["lagging_tickers"], ["LAGGING", "QQQ"])
        self.assertIn("不是按最新报价会话收盘数据重算", result["note"])


if __name__ == "__main__":
    unittest.main()
