from __future__ import annotations

import math
import unittest

from backtest.ndx_dynamic_shadow_new_money_preview import (
    NdxDynamicShadowNewMoneyPreviewError,
    build_new_money_preview,
    simulate_research_new_money_preview,
)


SESSION = "2026-09-04"
OBSERVED = "2026-09-05T02:00:00+00:00"


def target_rows(count: int) -> list[dict]:
    return [
        {
            "security_id": f"SEC_{index:02d}",
            "issuer_id": f"ISS_{index:02d}",
            "ticker": f"T{index:02d}",
            "target_weight": 1.0 / count,
        }
        for index in range(count)
    ]


def price_rows(targets: list[dict], extra: list[dict] | None = None, price: float = 10.0) -> list[dict]:
    identities = [*targets, *(extra or [])]
    return [
        {
            "security_id": row["security_id"],
            "issuer_id": row["issuer_id"],
            "ticker": row["ticker"],
            "price_usd": price,
            "session_date": SESSION,
            "observed_at": OBSERVED,
        }
        for row in identities
    ]


def simulate(
    current: list[dict], targets: list[dict], prices: list[dict], money: float = 1000.0,
    **kwargs,
):
    return simulate_research_new_money_preview(
        current, targets, prices, new_money_usd=money,
        valuation_session_date=SESSION, valuation_timestamp=OBSERVED,
        **kwargs,
    )


class NdxDynamicShadowNewMoneyPreviewTests(unittest.TestCase):
    def test_canonical_wrapper_is_blocked_and_rejects_self_reported_authority(self):
        result = build_new_money_preview()
        self.assertEqual(result["status"], "BLOCKED_NO_CANONICAL_P4_ADMISSION_ADAPTER")
        self.assertEqual(result["plan_rows"], [])
        self.assertFalse(result["caller_supplied_admission_authority_accepted"])
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            build_new_money_preview(admission_authority={"eligible": True})
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            build_new_money_preview(admission_authority=True)

    def test_dynamic_k_one_four_and_more_than_eight_have_no_fixed_name_limit(self):
        for count in (1, 4, 9):
            with self.subTest(count=count):
                targets = target_rows(count)
                result = simulate([], targets, price_rows(targets), money=1000.0)
                self.assertEqual(result["target_k"], count)
                self.assertNotIn("max_names", result)
                self.assertLessEqual(result["buy_action_count"], count)
                self.assertTrue(result["target_k_is_not_buy_action_count"])
                self.assertFalse(result["algorithm_is_portfolio_optimizer"])
                self.assertFalse(result["portfolio_optimality_claimed"])
                self.assertEqual(result["research_track"], "migration_control")
                self.assertEqual(result["upstream_target_research_track"], "portfolio_optimization")
                self.assertTrue(result["migration_control_included"])

    def test_non_target_holding_is_frozen_and_never_sold(self):
        targets = target_rows(2)
        extra = [{"security_id": "LEGACY", "issuer_id": "LEGACY_ISS", "ticker": "OLD"}]
        current = [{**extra[0], "quantity": 7}]
        result = simulate(current, targets, price_rows(targets, extra), money=500.0)
        legacy = next(row for row in result["position_changes"] if row["security_id"] == "LEGACY")
        self.assertEqual(legacy["quantity_before"], 7)
        self.assertEqual(legacy["quantity_after"], 7)
        self.assertEqual(legacy["buy_shares"], 0)
        self.assertEqual(legacy["sell_shares"], 0)
        self.assertTrue(legacy["non_target_frozen"])
        self.assertTrue(all(row["sell_shares"] == 0 for row in result["position_changes"]))

    def test_zero_and_sub_lot_money_remain_cash_without_forced_trade(self):
        targets = target_rows(1)
        prices = price_rows(targets, price=200.0)
        for money in (0.0, 250.0):
            with self.subTest(money=money):
                result = simulate([], targets, prices, money=money)
                self.assertEqual(result["buy_plan"], [])
                self.assertEqual(result["uninvested_new_money_usd"], money)
                self.assertFalse(result["forced_cash_deployment"])
                self.assertFalse(result["target_l1_strictly_improved"])

    def test_whole_shares_fees_buffer_and_fund_reconciliation(self):
        targets = target_rows(4)
        result = simulate([], targets, price_rows(targets, price=25.0), money=1000.0)
        self.assertTrue(result["buy_plan"])
        self.assertTrue(all(row["shares"] == int(row["shares"]) and row["shares"] > 0
                            for row in result["buy_plan"]))
        self.assertAlmostEqual(
            result["gross_buy_notional_usd"] * 10.0 / 10_000.0,
            result["estimated_fees_usd"], places=9,
        )
        self.assertAlmostEqual(
            result["new_money_cash_used_usd"] + result["uninvested_new_money_usd"],
            result["new_money_usd"], places=9,
        )
        self.assertGreaterEqual(result["uninvested_new_money_usd"], 100.0 - 1e-9)
        self.assertAlmostEqual(
            result["initial_total_equity_usd"] - result["final_total_equity_usd"],
            result["estimated_fees_usd"], places=9,
        )
        self.assertLess(result["target_l1_error_after"], result["target_l1_error_before"])

    def test_identity_timestamp_and_finite_values_fail_closed(self):
        targets = target_rows(2)
        duplicate_issuer = [dict(targets[0]), {**targets[1], "issuer_id": targets[0]["issuer_id"]}]
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], duplicate_issuer, price_rows(duplicate_issuer))
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, price_rows(targets), money=math.nan)
        bad_price = price_rows(targets)
        bad_price[0]["price_usd"] = math.inf
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, bad_price)
        stale = price_rows(targets)
        stale[0]["session_date"] = "2026-09-03"
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, stale)
        shifted = price_rows(targets)
        shifted[0]["observed_at"] = "2026-09-05T02:00:01+00:00"
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, shifted)
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate_research_new_money_preview(
                [], targets, price_rows(targets), new_money_usd=1000.0,
                valuation_session_date="2026-09-04",
                valuation_timestamp="2020-09-05T02:00:00+00:00",
            )

    def test_output_is_deterministic_and_contains_no_live_capability(self):
        targets = target_rows(4)
        prices = price_rows(targets, price=30.0)
        first = simulate([], targets, prices)
        second = simulate([], list(reversed(targets)), list(reversed(prices)))
        self.assertEqual(first["preview_id"], second["preview_id"])
        self.assertEqual(first["buy_plan"], second["buy_plan"])
        for field in (
            "orders_created", "config_changed", "state_changed", "broker_snapshot_changed",
            "today_advice_changed", "execution_eligible", "candidate_admission_performed",
        ):
            self.assertFalse(first[field])
        self.assertEqual(
            first["risk_limit_status"],
            "RISK_LIMIT_POLICY_NOT_SUPPLIED_NOT_EXECUTION_ELIGIBLE",
        )

    def test_current_same_issuer_multiple_security_is_explicitly_unsupported(self):
        targets = target_rows(1)
        current = [
            {"security_id": "A", "issuer_id": "ONE", "ticker": "A", "quantity": 1},
            {"security_id": "B", "issuer_id": "ONE", "ticker": "B", "quantity": 1},
        ]
        prices = price_rows(targets, current)
        with self.assertRaisesRegex(
            NdxDynamicShadowNewMoneyPreviewError, "duplicate security, issuer, or ticker",
        ):
            simulate(current, targets, prices)

    def test_large_low_price_case_stops_at_explicit_search_budget(self):
        targets = target_rows(1)
        result = simulate(
            [], targets, price_rows(targets, price=0.01), money=1_000_000.0,
            max_iterations=3, max_candidate_evaluations=10,
        )
        self.assertEqual(result["status"], "RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        self.assertFalse(result["search_complete"])
        self.assertEqual(result["search_budget"]["completed_iterations"], 3)
        self.assertTrue(result["search_budget"]["budget_exhausted"])
        self.assertFalse(result["portfolio_optimality_claimed"])

    def test_overflow_and_invalid_search_budget_fail_closed(self):
        targets = target_rows(1)
        current = [{
            "security_id": targets[0]["security_id"],
            "issuer_id": targets[0]["issuer_id"],
            "ticker": targets[0]["ticker"],
            "quantity": 10**308,
        }]
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate(current, targets, price_rows(targets, price=10.0))
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, price_rows(targets), max_iterations=0)
        with self.assertRaises(NdxDynamicShadowNewMoneyPreviewError):
            simulate([], targets, price_rows(targets), max_candidate_evaluations=10_000_001)


if __name__ == "__main__":
    unittest.main()
