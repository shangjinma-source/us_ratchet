from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from api import server
from core.state import Portfolio, SymbolState
from core.state_readiness import state_clock_readiness


class StateReadinessTests(unittest.TestCase):
    def test_position_event_after_clock_blocks_daily_update(self):
        portfolio = Portfolio(
            symbols={
                "AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-07-15"),
                "BBB": SymbolState(ticker="BBB", cap_total=100, shares=2),
            },
            flows=[], last_run_date="2026-07-01",
        )
        result = state_clock_readiness(portfolio, "2026-07-30")
        self.assertFalse(result["safe_to_apply_daily_update"])
        self.assertEqual(result["blockers"][0]["code"], "POSITION_EVENT_AFTER_STATE_CLOCK")
        self.assertEqual(result["warnings"][0]["code"], "POSITION_CHRONOLOGY_UNCONFIRMED")

    def test_consistent_clock_is_ready(self):
        portfolio = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-06-01")},
            flows=[], last_run_date="2026-07-01",
        )
        result = state_clock_readiness(portfolio, "2026-07-30")
        self.assertTrue(result["safe_to_apply_daily_update"])
        self.assertEqual(result["status"], "READY")

    def test_daily_update_endpoint_fails_closed_before_writing_state(self):
        portfolio = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-07-15")},
            flows=[], last_run_date="2026-07-01",
        )
        with (
            patch.object(server, "load_portfolio", return_value=portfolio),
            patch.object(server, "_cfg_for_portfolio", return_value=server.CFG),
            patch.object(server, "_daily_closes", return_value={"AAA": 100.0}),
            patch.object(server, "_latest_closed_session_date", return_value=date(2026, 7, 30)),
            patch.object(server, "save_portfolio") as save,
            patch.object(server, "backup_state") as backup,
        ):
            response = server.api_daily_update()
        self.assertEqual(response.status_code, 409)
        save.assert_not_called()
        backup.assert_not_called()

    def test_daily_update_requires_separate_one_time_approval_contract(self):
        portfolio = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-06-01")},
            flows=[], day_index=2, last_run_date="2026-07-01",
        )
        proposed = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-06-01")},
            flows=[], day_index=5, last_run_date="2026-07-06",
        )
        catchup = {
            "session_count": 3, "first_session": "2026-07-02",
            "last_session": "2026-07-06", "day_index_before": 2,
            "day_index_after": 5,
        }
        with (
            patch.object(server, "load_portfolio", return_value=portfolio),
            patch.object(server, "_cfg_for_portfolio", return_value=server.CFG),
            patch.object(server, "_latest_closed_session_date", return_value=date(2026, 7, 6)),
            patch.object(server, "_state_session_catchup", return_value=(proposed, [], catchup)),
            patch.object(server, "_state_payload", return_value={"ok": True}),
            patch.object(server, "save_portfolio") as save,
            patch.object(server, "backup_state") as backup,
            patch.object(server, "audit_log"),
        ):
            response = server.api_daily_update()
        self.assertEqual(response.status_code, 409)
        backup.assert_not_called()
        save.assert_not_called()

    def test_daily_update_blocks_unreconciled_historical_actions(self):
        portfolio = Portfolio(
            symbols={"AAA": SymbolState(ticker="AAA", cap_total=100, shares=1, entry_date="2026-06-01")},
            flows=[], day_index=2, last_run_date="2026-07-01",
        )
        ledger = [{"session_date": "2026-07-02", "immediate_buys": {
            "AAA": [{"amount": 10, "price": 9, "reason": "到期分批"}],
        }}]
        with (
            patch.object(server, "load_portfolio", return_value=portfolio),
            patch.object(server, "_cfg_for_portfolio", return_value=server.CFG),
            patch.object(server, "_latest_closed_session_date", return_value=date(2026, 7, 2)),
            patch.object(server, "_state_session_catchup", return_value=(portfolio, ledger, {"session_count": 1})),
            patch.object(server, "save_portfolio") as save,
            patch.object(server, "backup_state") as backup,
        ):
            response = server.api_daily_update()
        self.assertEqual(response.status_code, 409)
        backup.assert_not_called()
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
