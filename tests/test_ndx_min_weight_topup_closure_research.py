from copy import deepcopy
from decimal import Inexact, localcontext
from fractions import Fraction
from itertools import product
import unittest

from backtest import ndx_min_weight_topup_closure_research as module


def fixture():
    return dict(holdings={'A':100,'B':1,'C':1},execution_prices=dict.fromkeys('ABC','1'),
        support_security_ids=list('ABC'),seed_buy_shares=dict.fromkeys('ABC',0),buy_limits=dict.fromkeys('ABC',100),
        min_single_weight='.2',starting_cash_usd='1000',cash_injection_usd='0',transaction_cost_bps='10',
        minimum_cash_buffer_usd='0',max_iterations=100)


def feasible_grid(args):
    sids=sorted(args['holdings']); support=set(args['support_security_ids'])
    prices={sid:Fraction(args['execution_prices'][sid]) for sid in sids}
    threshold=Fraction(args['min_single_weight'])-Fraction(1,10**9)
    room=Fraction(args['starting_cash_usd'])+Fraction(args['cash_injection_usd'])-Fraction(args['minimum_cash_buffer_usd'])
    result=[]
    domains=[range(args['seed_buy_shares'][sid],args['buy_limits'][sid]+1) if sid in support else [0] for sid in sids]
    for quantities in product(*domains):
        buys=dict(zip(sids,quantities)); values={sid:(args['holdings'][sid]+buys[sid])*prices[sid] for sid in sids}
        total=sum(values.values()); cost=sum(buys[sid]*prices[sid] for sid in sids)*(1+Fraction(args['transaction_cost_bps'])/10000)
        if cost<=room and total>0 and all(values[sid]/total>=threshold for sid in support): result.append(buys)
    return result


class ClosureTests(unittest.TestCase):
    def test_small_grid_all_feasible_points_dominate_returned_least_point(self):
        cases=0
        for old_pair, prices, minimum, cash in product(((0,0),(1,3),(4,1)),(('1','1'),('2','3')),('.2','.4','.6'),('2','30')):
            args=dict(holdings=dict(zip('AB',old_pair)),execution_prices=dict(zip('AB',prices)),
                support_security_ids=list('AB'),seed_buy_shares={sid:int(q==0) for sid,q in zip('AB',old_pair)},
                buy_limits=dict.fromkeys('AB',3),min_single_weight=minimum,starting_cash_usd=cash,cash_injection_usd='0',
                transaction_cost_bps='10',minimum_cash_buffer_usd='0',max_iterations=100)
            feasible=feasible_grid(args); result=module.close_min_weight_topups(**args); cases+=1
            if feasible:
                self.assertEqual(result['status'],'FIXED_POINT')
                self.assertIn(result['buy_shares'],feasible)
                for point in feasible:
                    self.assertTrue(all(result['buy_shares'][sid]<=point[sid] for sid in point))
            else:
                self.assertEqual(result['status'],'PROVEN_INFEASIBLE_UPWARD_DOMAIN')
                self.assertIsNotNone(result['failure_certificate'])
        self.assertEqual(cases,36)

    def test_synchronous_cascade_and_budget_unknown(self):
        args=fixture(); before=deepcopy(args)
        result=module.close_min_weight_topups(**args)
        self.assertEqual(result['buy_shares'],{'A':0,'B':33,'C':33})
        self.assertEqual(result['trace'][0]['next_buy_shares'],{'A':0,'B':20,'C':20})
        self.assertGreater(result['iterations'],2); self.assertEqual(args,before)
        self.assertFalse(result['all_risks_evaluated']); self.assertFalse(result['issuer_uniqueness_evaluated'])
        args['max_iterations']=1
        limited=module.close_min_weight_topups(**args)
        self.assertEqual(limited['status'],'UNKNOWN_ITERATION_BUDGET')
        self.assertIsNone(limited['buy_shares']); self.assertIsNone(limited['failure_certificate'])
        args['max_iterations']=0
        self.assertEqual(module.close_min_weight_topups(**args)['iterations'],0)

    def test_cap_and_exact_fee_certificates_exclude_only_upward_domain(self):
        args=fixture(); args['buy_limits']['B']=0
        result=module.close_min_weight_topups(**args)
        cert=result['failure_certificate']; self.assertEqual(cert['kind'],'CAP_EXCEEDED')
        self.assertEqual(cert['violations'][0]['required_buy_shares'],20)
        self.assertEqual(cert['scope'],'FIXED_SUPPORT_SEED_UPWARD_DOMAIN_ONLY')
        args=dict(holdings={'A':10,'B':1},execution_prices={'A':'10','B':'10'},support_security_ids=list('AB'),
            seed_buy_shares={'A':0,'B':0},buy_limits={'A':10,'B':10},min_single_weight='.2',starting_cash_usd='20',
            cash_injection_usd='0',transaction_cost_bps='10',minimum_cash_buffer_usd='0',max_iterations=20)
        result=module.close_min_weight_topups(**args)
        self.assertEqual(result['failure_certificate']['kind'],'CASH_BUFFER_EXCEEDED')
        self.assertEqual(result['failure_certificate']['strict_cost_excess_usd'],module.ratio(Fraction(1,50)))
        args['starting_cash_usd']='20.02'
        self.assertEqual(module.close_min_weight_topups(**args)['buy_shares'],{'A':0,'B':2})

    def test_inactive_new_security_stays_zero_and_no_issuer_claim(self):
        args=fixture(); args['holdings']['D']=0; args['execution_prices']['D']='1'; args['seed_buy_shares']['D']=0; args['buy_limits']['D']=100
        result=module.close_min_weight_topups(**args)
        self.assertEqual(result['buy_shares']['D'],0); self.assertEqual(result['effective_buy_limits']['D'],0)
        self.assertEqual(result['buy_limits']['D'],100)
        args['support_security_ids'].append('D')
        with self.assertRaises(ValueError): module.close_min_weight_topups(**args)
        args['seed_buy_shares']['D']=1
        result=module.close_min_weight_topups(**args)
        self.assertTrue(result['minimum_weight_fixed_point_verified'])
        self.assertFalse(result['eligibility_inferred'])

    def test_hostile_decimal_and_original_tolerance_boundary(self):
        args=fixture(); args['execution_prices']['A']='1.00000000000000002'
        normal=module.close_min_weight_topups(**args)
        with localcontext() as context:
            context.prec=2; context.traps[Inexact]=True
            self.assertEqual(module.close_min_weight_topups(**args),normal)
        args=dict(holdings={'A':1,'B':1},execution_prices={'A':'1','B':'1.000000002'},support_security_ids=list('AB'),
            seed_buy_shares={'A':0,'B':0},buy_limits={'A':0,'B':0},min_single_weight='.5',starting_cash_usd='0',
            cash_injection_usd='0',transaction_cost_bps='0',minimum_cash_buffer_usd='0',max_iterations=2)
        self.assertEqual(module.close_min_weight_topups(**args)['status'],'FIXED_POINT')

    def test_strict_inputs_empty_support_and_seed_failure(self):
        for key,value in [('max_iterations',False),('transaction_cost_bps',0.1),('min_single_weight','NaN')]:
            args=fixture(); args[key]=value
            with self.assertRaises(ValueError): module.close_min_weight_topups(**args)
        args=fixture(); args['support_security_ids']=['B','A','C']
        with self.assertRaises(ValueError): module.close_min_weight_topups(**args)
        args=fixture(); args['support_security_ids']=['A','B']
        with self.assertRaises(ValueError): module.close_min_weight_topups(**args)
        args=fixture(); args['seed_buy_shares']['B']=3; args['buy_limits']['B']=2
        self.assertEqual(module.close_min_weight_topups(**args)['failure_certificate']['stage'],'SEED')
        args=fixture(); args.update(holdings={},execution_prices={},support_security_ids=[],seed_buy_shares={},buy_limits={})
        result=module.close_min_weight_topups(**args)
        self.assertEqual(result['status'],'UNSUPPORTED_EMPTY_SUPPORT'); self.assertFalse(result['minimum_weight_fixed_point_verified'])


if __name__=='__main__':
    unittest.main()
