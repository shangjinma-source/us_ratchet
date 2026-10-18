from copy import deepcopy
from decimal import Context, Inexact, Rounded, localcontext
import unittest
from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors


def fixture():
    return dict(holdings={}, starting_cash_usd='100', injection_usd='0',
                execution_prices={'A':'10','B':'10'}, target_weights={'A':'1','B':'1'},
                buy_limits={'A':10,'B':10}, transaction_cost_bps='0',
                minimum_cash_buffer_usd='0', max_generated_plans=20)


class NeighborsTests(unittest.TestCase):
    def test_exact_target_and_zero_are_unique(self):
        inputs=fixture(); before=deepcopy(inputs); result=generate_target_neighbors(**inputs)
        self.assertEqual(result['plans'], [{'A':0,'B':0},{'A':5,'B':5}])
        self.assertEqual(result['distinct_supplied_domain_count'],2)
        self.assertEqual(result['original_target_sum'],{'numerator':'2','denominator':'1'})
        self.assertEqual(inputs,before)

    def test_keep_overweight_old_position_and_scale_only_buy_deficits(self):
        inputs=fixture(); inputs.update(holdings={'A':10}, buy_limits={'B':20}, target_weights={'B':'1'})
        result=generate_target_neighbors(**inputs)
        self.assertEqual(result['deficit_scaling_factor'],{'numerator':'1','denominator':'2'})
        self.assertEqual(result['plans'],[{'B':0},{'B':10}])
        self.assertFalse(result['old_holdings_sold'])

    def test_fee_buffer_ceil_not_claimed_feasible_and_budget(self):
        inputs=fixture(); inputs.update(transaction_cost_bps='100', minimum_cash_buffer_usd='10')
        result=generate_target_neighbors(**inputs)
        self.assertEqual(result['gross_buy_budget_usd'],{'numerator':'9000','denominator':'101'})
        self.assertEqual(result['plans'],[{'A':0,'B':0},{'A':4,'B':4},{'A':4,'B':5},{'A':5,'B':4},{'A':5,'B':5}])
        inputs['max_generated_plans']=1; limited=generate_target_neighbors(**inputs)
        self.assertEqual(limited['ungenerated_count'],4)
        self.assertFalse(limited['portfolio_feasibility_asserted'])

    def test_zero_budget_clipping_and_invalid_inputs(self):
        inputs=fixture(); inputs['minimum_cash_buffer_usd']='200'
        self.assertEqual(generate_target_neighbors(**inputs)['plans'],[{'A':0,'B':0}])
        inputs=fixture(); inputs['buy_limits']={'A':1,'B':1}
        self.assertEqual(generate_target_neighbors(**inputs)['plans'],[{'A':0,'B':0},{'A':1,'B':1}])
        for key,value in [('injection_usd',1.0),('max_generated_plans',True),('target_weights',{}),('buy_limits',{'A':True,'B':1})]:
            inputs=fixture(); inputs[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): generate_target_neighbors(**inputs)

    def test_decimal_context_cannot_change_saved_literal_output(self):
        inputs=fixture(); inputs['target_weights']['A']='1.00000000000000002'
        expected=generate_target_neighbors(**inputs)
        context=Context(prec=2); context.traps[Inexact]=True; context.traps[Rounded]=True
        with localcontext(context):
            self.assertEqual(generate_target_neighbors(**inputs),expected)
