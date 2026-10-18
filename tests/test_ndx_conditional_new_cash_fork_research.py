import copy
import unittest
from decimal import Decimal, localcontext, Inexact, ROUND_DOWN
from backtest import ndx_conditional_new_cash_fork_research as kernel


def fixture():
    return dict(cash_event={"decision_date": "2023-04-28", "execution_date": "2023-05-01", "amount_usd": "100"},
                starting_cash_usd="100", holdings={sid: 10 for sid in "ABCD"},
                securities={sid: {"issuer_id": sid, "risk_chain": sid} for sid in "ABCD"},
                execution_prices={sid: "10" for sid in "ABCD"},
                branches=[{"branch_id": "buy", "buy_limits": {"A": 2}}, {"branch_id": "cash", "buy_limits": {}}],
                risk_parameters=dict(zip(kernel.RISK_KEYS, (".45", ".05", ".8", ".7", ".55"))),
                transaction_cost_bps="10", minimum_cash_buffer_usd="100", max_evaluations=100)


class CashForkTests(unittest.TestCase):
    def test_empty_cash_control_and_full_observed_union_capacity(self):
        inputs = fixture()
        inputs.update(holdings={}, securities={}, execution_prices={},
                      branches=[{"branch_id": "cash", "buy_limits": {}}])
        result = kernel.evaluate_branches(**inputs)
        row = result["branches"][0]["candidates"][0]
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(row["risk"]["reason"], "ALL_CASH")
        self.assertFalse(row["feasible"])
        self.assertEqual(Decimal(row["cash_after_usd"]), Decimal(200))
        self.assertEqual(Decimal(row["cash_flow_adjusted_pnl_usd"]), Decimal(0))
        inputs["execution_prices"] = {"unexpected": "1"}
        with self.assertRaises(ValueError):
            kernel.evaluate_branches(**inputs)
        inputs = fixture()
        sids = [str(index) for index in range(110)]
        inputs.update(holdings={sid: 1 for sid in sids},
                      securities={sid: dict(issuer_id=sid, risk_chain=sid) for sid in sids},
                      execution_prices={sid: "1" for sid in sids},
                      branches=[{"branch_id": "cash", "buy_limits": {}}])
        result = kernel.evaluate_branches(**inputs)
        self.assertEqual(result["baseline_risk"]["positive_holding_count"], 110)
        self.assertFalse(result["security_resource_cap_is_eligibility_or_k_limit"])

    def test_cash_and_fees_are_exact_no_deposit_return_or_mutation(self):
        inputs = fixture()
        before = copy.deepcopy(inputs)
        result = kernel.evaluate_branches(**inputs)
        self.assertEqual(inputs, before)
        self.assertEqual(result["candidate_count"], 4)
        rows = result["branches"][0]["candidates"]
        self.assertEqual(Decimal(rows[0]["cash_flow_adjusted_pnl_usd"]), 0)
        self.assertEqual(Decimal(rows[2]["fees_usd"]), Decimal(".02"))
        self.assertEqual(Decimal(rows[2]["cash_flow_adjusted_pnl_usd"]), Decimal("-.02"))
        self.assertEqual(rows[2]["proposed_holdings"], dict(A=12, B=10, C=10, D=10))
        self.assertTrue(rows[2]["feasible"])
        self.assertFalse(result["time_series_return_evaluated"])

    def test_saved_cash_literal_not_rounded(self):
        inputs = fixture()
        inputs["starting_cash_usd"] = "1478.4820750045776"
        result = kernel.evaluate_branches(**inputs)
        self.assertEqual(result["starting_cash_usd"], "1478.4820750045776")
        row = result["branches"][1]["candidates"][0]
        self.assertEqual(Decimal(row["cash_after_usd"]), Decimal("1578.4820750045776"))
        self.assertEqual(Decimal(row["cash_flow_adjusted_pnl_usd"]), Decimal(0))

    def test_lex_budget_and_zero_dont_claim_infeasible(self):
        inputs = fixture()
        inputs["branches"][0]["buy_limits"] = {"B": 2, "A": 1}
        inputs["max_evaluations"] = 4
        result = kernel.evaluate_branches(**inputs)
        self.assertEqual(result["candidate_count"], 7)
        self.assertEqual([row["buy_shares"] for row in result["branches"][0]["candidates"]],
                         [dict(A=0, B=0), dict(A=0, B=1), dict(A=0, B=2), dict(A=1, B=0)])
        self.assertEqual(result["branches"][0]["unevaluated_count"], 2)
        self.assertEqual(result["branches"][1]["evaluated_count"], 0)
        self.assertFalse(result["full_integer_space_infeasibility_claimed"])
        inputs["max_evaluations"] = 0
        self.assertEqual(kernel.evaluate_branches(**inputs)["evaluated_count"], 0)

    def test_cash_does_not_dilute_whole_old_stock_risk(self):
        inputs = fixture()
        inputs["holdings"] = dict(A=100, B=1, C=1, D=1)
        inputs["cash_event"]["amount_usd"] = "1000000"
        result = kernel.evaluate_branches(**inputs)
        self.assertFalse(result["baseline_risk"]["checks"]["MAX_SINGLE_WEIGHT"])
        self.assertFalse(result["branches"][1]["candidates"][0]["feasible"])
        inputs = fixture()
        for sid in "ABC":
            inputs["securities"][sid]["risk_chain"] = "shared"
        self.assertFalse(kernel.evaluate_branches(**inputs)["baseline_risk"]["checks"]["RISK_CHAIN_TOP1_WEIGHT"])

    def test_same_issuer_checked_per_positive_candidate_and_baseline(self):
        inputs = fixture()
        inputs["securities"]["E"] = dict(issuer_id="A", risk_chain="A")
        inputs["execution_prices"]["E"] = "10"
        inputs["branches"][0]["buy_limits"] = {"E": 1}
        result = kernel.evaluate_branches(**inputs)
        zero, positive = result["branches"][0]["candidates"]
        self.assertTrue(zero["issuer_unique"])
        self.assertEqual(positive["issuer_conflicts"], {"A": ["A", "E"]})
        self.assertFalse(positive["feasible"])
        inputs["holdings"]["E"] = 1
        self.assertEqual(kernel.evaluate_branches(**inputs)["baseline_issuer_conflicts"], {"A": ["A", "E"]})

    def test_price_gap_buffer_and_all_cash(self):
        inputs = fixture()
        del inputs["execution_prices"]["D"]
        with self.assertRaises(ValueError):
            kernel.evaluate_branches(**inputs)
        inputs = fixture()
        inputs["branches"][0]["buy_limits"] = {"A": 20}
        self.assertFalse(kernel.evaluate_branches(**inputs)["branches"][0]["candidates"][-1]["financial_checks"]["CASH_BUFFER"])
        inputs = fixture()
        inputs["holdings"] = {sid: 0 for sid in "ABCD"}
        self.assertEqual(kernel.evaluate_branches(**inputs)["baseline_risk"]["reason"], "ALL_CASH")

    def test_hostile_decimal_context_and_resource_limits(self):
        expected = kernel.evaluate_branches(**fixture())
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            context.traps[Inexact] = True
            self.assertEqual(kernel.evaluate_branches(**fixture()), expected)
        for value in (True, 1.2, "NaN", "1e999999", "1e-99999", "-1"):
            inputs = fixture()
            inputs["cash_event"]["amount_usd"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                kernel.evaluate_branches(**inputs)

    def test_bool_dates_unknown_parameters_and_limits_fail_before_search(self):
        changes = [("max_evaluations", True), ("max_evaluations", 10001)]
        for key, value in changes:
            inputs = fixture()
            inputs[key] = value
            with self.assertRaises(ValueError):
                kernel.evaluate_branches(**inputs)
        for change in (lambda x: x["holdings"].update(A=True),
                       lambda x: x["branches"][0]["buy_limits"].update(A=-1),
                       lambda x: x["cash_event"].update(execution_date="2023-04-28"),
                       lambda x: x["risk_parameters"].update(extra="1")):
            inputs = fixture()
            change(inputs)
            with self.assertRaises(ValueError):
                kernel.evaluate_branches(**inputs)


if __name__ == "__main__":
    unittest.main()
