from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from itertools import product
import unittest
from unittest.mock import patch

from backtest import quantity_anchor_coupled_completion as completion
from backtest import quantity_anchor_domain_completion as base_stage
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as integer
from backtest import quantity_multi_anchor_bound_prototype as multi


def fixture(cash='5/2', symmetric=False, small_tail=1, seed=None):
    values = ('1.5','1.1','1.1','1.5') if symmetric else ('2','1.1','0.8','1.8')
    inputs = dict(prices=dict(A='1',B='1'),metadata={s:dict(ticker=s,issuer_id=s) for s in 'AB'},
        entered_cash=cash,fee_bps='0',minimum_cash_buffer='0',
        training_scenarios=[dict(A=values[0],B=values[1]),dict(A=values[2],B=values[3])])
    problem = integer.prepare(**inputs)
    box = {s:[0,int(F(cash))] for s in 'AB'}
    # Independent direct wealth oracle, used solely as synthetic known lower.
    points = []
    for a,b in product(range(int(F(cash))+1), repeat=2):
        if a+b > F(cash):
            continue
        value = F(1)
        for scenario in inputs['training_scenarios']:
            value *= (F(cash)-a-b+a*F(scenario['A'])+b*F(scenario['B']))/F(cash)
        points.append((value,{s:q for s,q in [('A',a),('B',b)] if q}))
    optimum, incumbent = max(points,key=lambda item:item[0])
    if seed is not None:
        incumbent = seed
    anchor = continuous.from_candidate(inputs=inputs,box=box,
        inherited_evidence=multi.bound(inputs=inputs,box=box,incumbent=incumbent),
        candidate={s:float(F(cash)/2) for s in 'AB'},
        diagnostics=dict(success=False,status=0,iterations=0,message='synthetic'))
    base = base_stage.build(inputs=inputs,anchor=anchor,incumbent=incumbent,max_tail_points=small_tail)
    raw = continuous.canonical(base)
    sources = dict(base_raw=raw,expected_base_sha256=sha256(raw).hexdigest(),
        expected_inputs_sha256=continuous.digest(inputs),expected_anchor_sha256=continuous.digest(anchor))
    return sources,optimum


class CoupledCompletionTests(unittest.TestCase):
    def test_improves_original_lower_and_preserves_root_coverage(self):
        sources,optimum = fixture(seed={'B':2})
        result = completion.build(**sources)
        self.assertEqual(result['status'],'COVERED_BY_COUPLED_TAIL')
        self.assertEqual(result['selected'],{'A':1,'B':1})
        self.assertEqual(F(result['lower_product']),optimum)
        self.assertGreater(F(result['lower_product']),F(result['coupled']['original_lower_product']))
        completion.verify(result,**sources)

    def test_full_chain_closes_and_matches_oracle(self):
        sources,optimum = fixture()
        with patch('scipy.optimize.minimize',side_effect=AssertionError('NO_SOLVER')):
            result = completion.build(**sources)
            review = completion.verify(result,**sources)
        self.assertEqual(result['status'],'COVERED_BY_COUPLED_TAIL')
        self.assertTrue(review['objective_value_covered'])
        self.assertEqual(F(result['lower_product']),optimum)
        self.assertEqual(result['lower_product'],result['upper_product'])
        self.assertFalse(result['tie_break_optimality_established'])

    def test_degeneracies_remain_unresolved(self):
        for kwargs,reason in [({'symmetric':True},'EXACTLY_ONE_ACTIVE_ZERO_AXIS_REQUIRED'),
                              ({'cash':'11/2'},'STRICT_INTERVAL_WIDTH_BELOW_ONE_REQUIRED')]:
            sources,optimum = fixture(**kwargs)
            result = completion.build(**sources)
            self.assertFalse(result['objective_value_covered'])
            self.assertEqual(result['admission']['reason'],reason)
            self.assertIsNone(result['coupled'])
            self.assertLessEqual(F(result['lower_product']),optimum)
            self.assertGreaterEqual(F(result['upper_product']),optimum)
            completion.verify(result,**sources)

    def test_zero_budget_preserves_frontier(self):
        sources,_ = fixture()
        for budgets in [dict(node_budget=0),dict(objective_budget=0)]:
            result = completion.build(**sources,**budgets)
            self.assertEqual(result['status'],'UNRESOLVED_COUPLED_FRONTIER')
            self.assertEqual(result['coupled']['unsearched_frontier'],[[]])
            self.assertFalse(result['objective_value_covered'])
            completion.verify(result,**sources)

    def test_complete_base_skips_iterator(self):
        sources,optimum = fixture(small_tail=10000)
        with patch.object(completion.coupled,'build',side_effect=AssertionError('ALREADY_COMPLETE')):
            result = completion.build(**sources)
        self.assertEqual(result['status'],'BASE_ALREADY_COMPLETE')
        self.assertTrue(result['objective_value_covered'])
        self.assertEqual(F(result['lower_product']),optimum)

    def test_hash_budget_and_forged_summary(self):
        sources,_ = fixture()
        for key,value in [('expected_base_sha256','0'*64),('expected_inputs_sha256','0'*64),
                          ('expected_anchor_sha256','0'*64)]:
            with self.assertRaises(ValueError):
                completion.build(**dict(sources,**{key:value}))
        for budgets in [dict(node_budget=True),dict(node_budget=5001),dict(objective_budget=501)]:
            with self.assertRaisesRegex(ValueError,'FIXED_COUPLED_BUDGET_REQUIRED'):
                completion.build(**sources,**budgets)
        result = completion.build(**sources,node_budget=0)
        for key,value in [('objective_value_covered',True),('upper_product','0'),('selected',{})]:
            changed = deepcopy(result)
            changed[key] = value
            with self.assertRaisesRegex(ValueError,'COUPLED_COMPLETION_CHANGED'):
                completion.verify(changed,**sources)


if __name__ == '__main__':
    unittest.main()
