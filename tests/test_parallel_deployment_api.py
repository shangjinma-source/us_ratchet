import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from api.server import api_parallel_deployment


class ParallelDeploymentApiTests(unittest.TestCase):
    def test_non_finite_and_negative_cash_fail_closed_before_loading_state(self):
        for cash in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(cash=cash), patch("api.server.load_portfolio") as load_portfolio:
                response = api_parallel_deployment(cash_usd=cash)
                body = json.loads(response.body)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(body["status"], "INVALID_CASH_INPUT")
                self.assertFalse(body["promotion_allowed"])
                self.assertFalse(body["orders_created"])
                self.assertFalse(body["config_or_state_write"])
                load_portfolio.assert_not_called()

    @patch("api.server._state_payload")
    @patch("api.server.load_portfolio")
    def test_endpoint_is_read_only_and_exposes_dead_zone(self, load_portfolio, state_payload):
        load_portfolio.return_value = SimpleNamespace()
        state_payload.return_value = {
            "as_of": "2026-09-04",
            "execution_session_date": "2026-09-03",
            "latest_closed_session_date": "2026-09-03",
            "state_freshness": {"status": "CURRENT"},
            "daily_bar_freshness": {
                "status": "CURRENT_TO_QUOTE_SESSION",
                "common_risk_daily_bar_date": "2026-09-03",
            },
            "symbols": [{
                "ticker": "AAA", "price": 100,
                "tactical": {"execution_context": {"status": "NO_TACTICAL_BUDGET"}},
            }],
            "market": {"regime": "BEAR", "label": "熊市/破趋势"},
            "execution": {"actionable_count": 0},
            "execution_constraints": {"lot_size": 1, "fee_bps": 0, "min_fee": 0},
            "broker_account": {
                "available": True,
                "snapshot_as_of": "2026-09-03",
                "reported_closed_positions": [{"ticker": "CCC"}],
                "deployable_cash_usd": 500,
                "deployable_cash_session_date": "2026-09-03",
                "deployable_cash_persistence": "until_user_update",
                "positions_confirmed_session_date": "2026-09-03",
                "account_fingerprint": "account-v1",
            },
            "account_readiness": {"position_gaps": {
                "totals": {"gap_amount": 1000},
                "rows": [{"ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
                          "gap_rank": 1, "position_kind": "pending_entry"}],
            }},
        }
        with patch("api.server.CFG") as cfg:
            cfg.tactical_orders.market_gate_enabled = True
            cfg.tactical_orders.bear_reserve_ratio = 0.0
            result = api_parallel_deployment(
                cash_usd=500, broker_confirmed=True,
                account_fingerprint="account-v1",
            )

        self.assertEqual(result["status"], "READY_FOR_USER_REVIEW")
        self.assertEqual(result["strategy_selected_name_count"], 1)
        self.assertFalse(result["broker_activity_requirement_used"])
        self.assertEqual(result["tactical_dead_zone_diagnostic"]["market_regime"], "BEAR")
        self.assertFalse(result["read_only_guards"]["orders_created"])
        self.assertFalse(result["read_only_guards"]["config_or_state_write"])

    @patch("api.server._state_payload")
    @patch("api.server.load_portfolio")
    def test_stale_state_and_cash_mismatch_never_become_ready(
        self, load_portfolio, state_payload,
    ):
        load_portfolio.return_value = SimpleNamespace()
        state_payload.return_value = {
            "as_of": "2026-09-04",
            "execution_session_date": "2026-09-03",
            "latest_closed_session_date": "2026-09-03",
            "state_freshness": {"status": "DAILY_UPDATE_REQUIRED"},
            "daily_bar_freshness": {
                "status": "CURRENT_TO_QUOTE_SESSION",
                "common_risk_daily_bar_date": "2026-09-03",
            },
            "symbols": [{"ticker": "AAA", "price": 100, "tactical": {}}],
            "market": {"regime": "BEAR", "label": "熊市/破趋势"},
            "execution": {"actionable_count": 0},
            "execution_constraints": {"lot_size": 1, "fee_bps": 0, "min_fee": 0},
            "broker_account": {
                "available": True,
                "snapshot_as_of": "2026-09-03",
                "reported_closed_positions": [],
                "deployable_cash_usd": 500,
                "deployable_cash_session_date": "2026-09-03",
                "deployable_cash_persistence": "until_user_update",
                "positions_confirmed_session_date": "2026-09-03",
                "account_fingerprint": "account-v1",
            },
            "account_readiness": {"position_gaps": {
                "totals": {"gap_amount": 1000},
                "rows": [{"ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
                          "gap_rank": 1, "position_kind": "pending_entry"}],
            }},
        }
        with patch("api.server.CFG") as cfg:
            cfg.tactical_orders.market_gate_enabled = True
            cfg.tactical_orders.bear_reserve_ratio = 0.0
            result = api_parallel_deployment(
                cash_usd=1000,
                broker_confirmed=True,
                account_fingerprint="account-v1",
            )

        self.assertEqual(result["status"], "EXECUTION_READINESS_BLOCKED")
        self.assertFalse(result["promotion_allowed"])
        codes = {row["code"] for row in result["deployment_readiness"]["blockers"]}
        self.assertIn("STATE_CATCHUP_REQUIRED", codes)
        self.assertIn("DECLARED_CASH_MISMATCH", codes)

    @patch("api.server._state_payload")
    @patch("api.server.load_portfolio")
    def test_stale_account_fingerprint_never_becomes_ready(
        self, load_portfolio, state_payload,
    ):
        load_portfolio.return_value = SimpleNamespace()
        state_payload.return_value = {
            "as_of": "2026-09-04",
            "execution_session_date": "2026-09-03",
            "latest_closed_session_date": "2026-09-03",
            "state_freshness": {"status": "CURRENT"},
            "daily_bar_freshness": {
                "status": "CURRENT_TO_QUOTE_SESSION",
                "common_risk_daily_bar_date": "2026-09-03",
            },
            "symbols": [{"ticker": "AAA", "price": 100, "tactical": {}}],
            "market": {"regime": "NEUTRAL", "label": "中性"},
            "execution": {"actionable_count": 0},
            "execution_constraints": {"lot_size": 1, "fee_bps": 0, "min_fee": 0},
            "broker_account": {
                "available": True, "snapshot_as_of": "2026-09-03",
                "reported_closed_positions": [], "deployable_cash_usd": 500,
                "deployable_cash_session_date": "2026-09-03",
                "deployable_cash_persistence": "until_user_update",
                "positions_confirmed_session_date": "2026-09-03",
                "account_fingerprint": "account-v2",
            },
            "account_readiness": {"position_gaps": {
                "rows": [{"ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
                          "gap_rank": 1, "position_kind": "pending_entry"}],
            }},
        }
        with patch("api.server.CFG") as cfg:
            cfg.tactical_orders.market_gate_enabled = True
            cfg.tactical_orders.bear_reserve_ratio = 0.0
            result = api_parallel_deployment(
                cash_usd=500,
                broker_confirmed=True,
                account_fingerprint="account-v1",
            )
        self.assertEqual(result["status"], "EXECUTION_READINESS_BLOCKED")
        self.assertIn(
            "BROKER_ACCOUNT_FINGERPRINT_MISMATCH",
            {row["code"] for row in result["deployment_readiness"]["blockers"]},
        )

    @patch("api.server._state_payload")
    @patch("api.server.load_portfolio")
    def test_stale_position_confirmation_never_becomes_ready(
        self, load_portfolio, state_payload,
    ):
        load_portfolio.return_value = SimpleNamespace()
        state_payload.return_value = {
            "as_of": "2026-09-04",
            "execution_session_date": "2026-09-03",
            "latest_closed_session_date": "2026-09-03",
            "state_freshness": {"status": "CURRENT"},
            "daily_bar_freshness": {
                "status": "CURRENT_TO_QUOTE_SESSION",
                "common_risk_daily_bar_date": "2026-09-03",
            },
            "symbols": [{"ticker": "AAA", "price": 100, "tactical": {}}],
            "market": {"regime": "NEUTRAL", "label": "中性"},
            "execution": {"actionable_count": 0},
            "execution_constraints": {"lot_size": 1, "fee_bps": 0, "min_fee": 0},
            "broker_account": {
                "available": True,
                "snapshot_as_of": "2026-09-03",
                "reported_closed_positions": [],
                "deployable_cash_usd": 500,
                "deployable_cash_session_date": "2026-09-03",
                "deployable_cash_persistence": "until_user_update",
                "positions_confirmed_session_date": "2026-09-02",
                "account_fingerprint": "account-v1",
            },
            "account_readiness": {"position_gaps": {
                "rows": [{"ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
                          "gap_rank": 1, "position_kind": "pending_entry"}],
            }},
        }
        with patch("api.server.CFG") as cfg:
            cfg.tactical_orders.market_gate_enabled = True
            cfg.tactical_orders.bear_reserve_ratio = 0.0
            result = api_parallel_deployment(
                cash_usd=500,
                broker_confirmed=True,
                account_fingerprint="account-v1",
            )

        self.assertEqual(result["status"], "EXECUTION_READINESS_BLOCKED")
        self.assertIn(
            "BROKER_POSITION_SESSION_CONFIRMATION_REQUIRED",
            {row["code"] for row in result["deployment_readiness"]["blockers"]},
        )


if __name__ == "__main__":
    unittest.main()
