import unittest

from backtest.parallel_deployment import build_parallel_deployment_plan


GAPS = [
    {"ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1.0, "gap_rank": 1,
     "target_amount": 1000, "real_market_value": 0, "position_kind": "pending_entry"},
    {"ticker": "BBB", "gap_amount": 900, "gap_ratio": 0.9, "gap_rank": 2,
     "target_amount": 1000, "real_market_value": 100, "position_kind": "real_position"},
    {"ticker": "CCC", "gap_amount": 800, "gap_ratio": 0.8, "gap_rank": 3,
     "target_amount": 1000, "real_market_value": 200, "position_kind": "real_position"},
]


class ParallelDeploymentTests(unittest.TestCase):
    def test_strategy_selects_names_without_broker_activity_constraint(self):
        result = build_parallel_deployment_plan(
            GAPS, {"AAA": 100, "BBB": 100, "CCC": 100}, cash_usd=1000,
            max_names=2, broker_confirmed=True,
        )
        self.assertEqual(result["status"], "READY_FOR_USER_REVIEW")
        self.assertEqual([row["ticker"] for row in result["lines"]], ["AAA", "BBB"])
        self.assertEqual(result["strategy_selected_name_count"], 2)
        self.assertFalse(result["broker_activity_requirement_used"])
        self.assertTrue(result["plan_id"].startswith("core-deployment:"))
        self.assertTrue(all(row["shares"] >= 1 and row["shares"] == int(row["shares"])
                            for row in result["lines"]))
        self.assertLessEqual(result["cash_deployed"], 1000)

    def test_recently_reported_exit_is_not_mechanically_rebought(self):
        result = build_parallel_deployment_plan(
            GAPS, {"AAA": 100, "BBB": 100, "CCC": 100}, cash_usd=500,
            excluded_tickers=["AAA"], max_names=3, broker_confirmed=True,
        )
        self.assertNotIn("AAA", [row["ticker"] for row in result["lines"]])
        self.assertEqual(result["excluded_rows"][0]["reason"],
                         "RECENTLY_REPORTED_EXIT_REQUIRES_NEW_STRATEGY_ENTRY_SIGNAL")

    def test_gap_level_ineligibility_is_enforced_without_api_side_list(self):
        result = build_parallel_deployment_plan(
            [{**GAPS[0], "core_deployment_eligible": False}],
            {"AAA": 100}, cash_usd=500, max_names=1, broker_confirmed=True,
        )
        self.assertEqual(result["status"], "NO_AFFORDABLE_WHOLE_LOT")
        self.assertEqual(result["excluded_rows"][0]["reason"],
                         "POSITION_GAP_NOT_ELIGIBLE_FOR_CORE_DEPLOYMENT")

    def test_never_allocates_more_notional_than_gap(self):
        result = build_parallel_deployment_plan(
            [{**GAPS[0], "gap_amount": 250}], {"AAA": 100}, cash_usd=1000,
            max_names=4, broker_confirmed=True,
        )
        self.assertEqual(result["lines"][0]["shares"], 2)
        self.assertEqual(result["lines"][0]["gap_after"], 50)

    def test_unconfirmed_snapshot_never_becomes_execution_ready(self):
        result = build_parallel_deployment_plan(
            GAPS, {"AAA": 100, "BBB": 100, "CCC": 100}, cash_usd=500,
            max_names=2, broker_confirmed=False, broker_snapshot_as_of="2026-09-04",
        )
        self.assertEqual(result["status"], "ACCOUNT_CONFIRMATION_REQUIRED")
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["orders_created"])

    def test_minimum_fee_is_charged_once_per_ticker_order(self):
        result = build_parallel_deployment_plan(
            [{**GAPS[0], "gap_amount": 1000}], {"AAA": 100}, cash_usd=305,
            max_names=1, broker_confirmed=True, min_fee=5,
        )
        line = result["lines"][0]
        self.assertEqual(line["shares"], 3)
        self.assertEqual(line["estimated_fee"], 5)
        self.assertEqual(line["cash_cost"], 305)
        self.assertEqual(result["cash_deployed"], 305)
        self.assertEqual(result["cash_remaining"], 0)

    def test_plan_identity_is_stable_and_input_sensitive(self):
        kwargs = dict(cash_usd=500, max_names=2, broker_confirmed=True)
        first = build_parallel_deployment_plan(GAPS, {"AAA": 100, "BBB": 100}, **kwargs)
        repeat = build_parallel_deployment_plan(GAPS, {"AAA": 100, "BBB": 100}, **kwargs)
        changed = build_parallel_deployment_plan(GAPS, {"AAA": 101, "BBB": 100}, **kwargs)
        self.assertEqual(first["plan_id"], repeat["plan_id"])
        self.assertNotEqual(first["plan_id"], changed["plan_id"])


if __name__ == "__main__":
    unittest.main()
