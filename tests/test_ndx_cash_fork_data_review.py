"""Independent synthetic contract checks; no historical execution."""
import copy
import unittest
from decimal import Decimal, Inexact, localcontext
from backtest import ndx_conditional_new_cash_fork_research as m
from test_ndx_conditional_new_cash_fork_research import fixture


class IndependentCashTests(unittest.TestCase):
    def test_injection_cannot_hide_incumbent_or_class_collision(self):
        a = fixture()
        a['holdings'] = dict(A=100, B=1, C=1, D=1)
        a['cash_event']['amount_usd'] = '100000000'
        a['branches'] = [dict(branch_id='new_class', buy_limits={'E': 1})]
        a['securities']['E'] = dict(issuer_id='A', risk_chain='A')
        a['execution_prices']['E'] = '10'
        r = m.evaluate_branches(**a)
        zero, one = r['branches'][0]['candidates']
        self.assertFalse(zero['risk']['checks']['MAX_SINGLE_WEIGHT'])
        self.assertEqual(one['proposed_holdings']['A'], 100)
        self.assertEqual(one['issuer_conflicts'], {'A': ['A', 'E']})
        self.assertFalse(one['feasible'])
        for row in (zero, one):
            self.assertEqual(Decimal(row['cash_flow_adjusted_pnl_usd']), -Decimal(row['fees_usd']))

    def test_fee_boundary_and_saved_fractional_cash_without_rounding(self):
        a = fixture()
        a.update(starting_cash_usd='1478.4820750045776', minimum_cash_buffer_usd='1478.4820750045776')
        a['cash_event']['amount_usd'] = '10'
        a['branches'] = [dict(branch_id='one', buy_limits={'A': 1})]
        expected = m.evaluate_branches(**a)
        with localcontext() as c:
            c.prec = 2
            c.traps[Inexact] = True
            self.assertEqual(m.evaluate_branches(**a), expected)
        row = expected['branches'][0]['candidates'][1]
        self.assertTrue(row['financial_checks']['NONNEGATIVE_CASH'])
        self.assertFalse(row['financial_checks']['CASH_BUFFER'])
        self.assertEqual(Decimal(row['cash_after_usd']), Decimal('1478.4720750045776'))

    def test_domain_budget_is_not_global_infeasibility(self):
        a = fixture()
        a['branches'] = [dict(branch_id='large', buy_limits={'A': 100000000000}), dict(branch_id='cash', buy_limits={})]
        a['max_evaluations'] = 1
        r = m.evaluate_branches(**a)
        self.assertEqual(r['candidate_count'], 100000000002)
        self.assertEqual(r['evaluated_count'], 1)
        self.assertEqual(r['branches'][1]['unevaluated_count'], 1)
        self.assertTrue(all(x['status'] == 'BUDGET_LIMITED' for x in r['branches']))
        for key in ('global_optimality_claimed', 'full_integer_space_infeasibility_claimed', 'return_series_calculated', 'orders_executed'):
            self.assertIs(r[key], False)

    def test_zero_old_position_still_requires_explicit_union_and_empty_control(self):
        a = fixture(); a['holdings']['D'] = 0
        for key in ('execution_prices', 'securities'):
            b = copy.deepcopy(a); del b[key]['D']
            with self.assertRaises(ValueError): m.evaluate_branches(**b)
        a.update(holdings={}, securities={}, execution_prices={}, branches=[dict(branch_id='cash', buy_limits={})])
        r = m.evaluate_branches(**a)
        self.assertEqual(r['candidate_count'], 1)
        self.assertEqual(Decimal(r['branches'][0]['candidates'][0]['cash_flow_adjusted_pnl_usd']), 0)
        self.assertIs(r['point_in_time_verified'], False)

