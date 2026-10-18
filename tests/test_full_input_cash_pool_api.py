"""Offline endpoint checks; no real account, quotes, or service calls."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

from backtest.parallel_deployment import build_parallel_deployment_plan


class FullInputCashPoolApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "api" / "server.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        endpoint = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef)
                        and node.name == "api_parallel_deployment")
        endpoint.decorator_list = []
        cls.endpoint_code = compile(ast.Module(body=[endpoint], type_ignores=[]),
                                    str(path), "exec")

    def make_plan(self, cash, gaps, *, price=100, min_fee=0, ready=True):
        payload = {
            "account_readiness": {"position_gaps": {"rows": gaps}},
            "symbols": [{"ticker": "AAA", "price": price}],
            "execution_constraints": {"lot_size": 1, "min_fee": min_fee},
            "broker_account": {"available": True},
        }
        namespace = {
            "np": SimpleNamespace(isfinite=math.isfinite),
            "load_portfolio": lambda path: object(),
            "resolve": lambda path: path,
            "STATE_PATH": "unused-offline-path",
            "_state_payload": lambda portfolio: payload,
            "_parallel_deployment_readiness": lambda *args, **kwargs: {
                "ready": ready, "blockers": [] if ready else [{"code": "STALE_ACCOUNT"}],
            },
            "build_parallel_deployment_plan": build_parallel_deployment_plan,
            "CFG": SimpleNamespace(tactical_orders=SimpleNamespace(
                market_gate_enabled=True, bear_reserve_ratio=0.0,
            )),
            "JSONResponse": lambda content, status_code: SimpleNamespace(
                content=content, status_code=status_code,
            ),
        }
        exec(self.endpoint_code, namespace)
        return namespace["api_parallel_deployment"](cash_usd=cash)

    def test_full_pool_survives_zero_bear_budget_and_old_target_limit(self):
        plan = self.make_plan(20000, [{
            "ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
            "position_kind": "real_position",
        }], min_fee=5)
        pool = plan["cash_pool"]
        self.assertEqual(pool["input_pool_usd"], 20000)
        self.assertEqual(pool["reserve_added_usd"], 0)
        self.assertEqual(pool["allocated_notional_usd"], 1000)
        self.assertEqual(pool["estimated_fees_usd"], 5)
        self.assertEqual(pool["draft_cash_used_usd"], 1005)
        self.assertEqual(pool["cash_unallocated_usd"], 18995)
        self.assertEqual(pool["capital_growth_status"], "REQUESTED_NOT_IMPLEMENTED")
        self.assertFalse(pool["dynamic_optimizer_admitted"])
        self.assertFalse(pool["execution_authorized"])

    def test_no_old_gap_does_not_erase_cash_or_invent_capital_growth(self):
        plan = self.make_plan(20000, [])
        self.assertEqual(plan["lines"], [])
        self.assertEqual(plan["cash_pool"]["input_pool_usd"], 20000)
        self.assertEqual(plan["cash_pool"]["cash_unallocated_usd"], 20000)
        self.assertEqual(plan["cash_pool"]["draft_cash_used_usd"], 0)

    def test_minimum_fee_and_account_blocker_preserved(self):
        plan = self.make_plan(305, [{
            "ticker": "AAA", "gap_amount": 1000, "gap_ratio": 1,
        }], min_fee=5, ready=False)
        self.assertEqual(plan["status"], "EXECUTION_READINESS_BLOCKED")
        self.assertEqual(plan["cash_pool"]["allocated_notional_usd"], 300)
        self.assertEqual(plan["cash_pool"]["estimated_fees_usd"], 5)
        self.assertEqual(plan["cash_pool"]["cash_unallocated_usd"], 0)
        self.assertFalse(plan["cash_pool"]["execution_authorized"])

    def test_separately_rounded_components_have_explicit_reconciliation(self):
        plan = self.make_plan(1.01, [{
            "ticker": "AAA", "gap_amount": 0.999, "gap_ratio": 1,
        }], price=0.333, min_fee=0.005)
        pool = plan["cash_pool"]
        self.assertEqual(pool["allocated_notional_usd"], 1)
        self.assertEqual(pool["estimated_fees_usd"], 0.01)
        self.assertEqual(pool["draft_cash_used_usd"], 1)
        self.assertEqual(pool["display_rounding_adjustment_usd"], -0.01)
        self.assertAlmostEqual(pool["input_pool_usd"],
                               pool["draft_cash_used_usd"] + pool["cash_unallocated_usd"]
                               + pool["cash_reconciliation_adjustment_usd"])


if __name__ == "__main__":
    unittest.main()
