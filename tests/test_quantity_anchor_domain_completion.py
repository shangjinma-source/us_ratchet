from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import unittest
from unittest.mock import patch

from backtest import quantity_anchor_domain_completion as completion
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as integer
from backtest import quantity_multi_anchor_bound_prototype as multi


def fixture(shared=False, falling=False):
    inputs = dict(prices=dict(A='3', B='4'),
        metadata={s: dict(ticker=s, issuer_id='same' if shared else s) for s in ['A','B']},
        entered_cash='20', fee_bps='10', minimum_cash_buffer='1',
        training_scenarios=[dict(A='0.9' if falling else '1.8', B='0.8' if falling else '1.2'),
                            dict(A='0.8' if falling else '0.9', B='0.9' if falling else '1.7')])
    p = integer.prepare(**inputs)
    box = {s: [0, int(p['spendable']//p['cost'][s])] for s in p['ids']}
    anchor = continuous.from_candidate(inputs=inputs, box=box,
        inherited_evidence=multi.bound(inputs=inputs, box=box, incumbent={}),
        candidate=dict(A=0.0,B=0.0),
        diagnostics=dict(success=False,status=0,iterations=0,message='synthetic'))
    return inputs, anchor


def independent_oracle(inputs, box):
    best = F(0)
    for counts in product(*(range(lo, hi+1) for lo,hi in box.values())):
        q = {s:n for s,n in zip(box,counts) if n}
        issuers = [inputs['metadata'][s]['issuer_id'] for s in q]
        if len(set(issuers)) != len(issuers):
            continue
        cash = F(inputs['entered_cash'])
        fee = F(inputs['fee_bps'])/10000
        cost = sum(F(inputs['prices'][s])*n*(1+fee) for s,n in q.items())
        if cost > cash or (q and cash-cost < F(inputs['minimum_cash_buffer'])):
            continue
        value = F(1)
        for scenario in inputs['training_scenarios']:
            value *= (cash + sum(F(inputs['prices'][s])*n*(F(scenario[s])-1-fee) for s,n in q.items()))/cash
        best = max(best,value)
    return best


class CompletionTests(unittest.TestCase):
    def test_full_root_matches_independent_oracle(self):
        for shared in (False, True):
            inputs, anchor = fixture(shared=shared)
            with patch('scipy.optimize.minimize', side_effect=AssertionError('NO_SOLVER')):
                result = completion.build(inputs=inputs,anchor=anchor,incumbent={})
                reviewed = completion.verify(result,expected_inputs_sha256=continuous.digest(inputs),
                                             expected_anchor_sha256=continuous.digest(anchor))
            self.assertTrue(reviewed['objective_value_covered'])
            self.assertEqual(F(result['lower_product']),independent_oracle(inputs,result['root_box']))
            self.assertEqual(result['lower_product'],result['upper_product'])
            self.assertFalse(result['tie_break_optimality_established'])

    def test_large_tail_retains_unresolved_state(self):
        inputs, anchor = fixture()
        result = completion.build(inputs=inputs,anchor=anchor,incumbent={},max_tail_points=1)
        self.assertEqual(result['status'],'UNRESOLVED_LARGE_TAIL')
        self.assertFalse(result['objective_value_covered'])
        self.assertIsNone(result['enumeration'])
        self.assertIsNotNone(result['unresolved_box'])
        optimum = independent_oracle(inputs,result['root_box'])
        self.assertLessEqual(F(result['lower_product']),optimum)
        self.assertGreaterEqual(F(result['upper_product']),optimum)

    def test_bound_closed_needs_no_enumeration(self):
        inputs, anchor = fixture(falling=True)
        result = completion.build(inputs=inputs,anchor=anchor,incumbent={})
        self.assertEqual(result['status'],'COVERED_BY_EXACT_BOUND')
        self.assertIsNone(result['enumeration'])
        self.assertEqual(result['selected'],{})

    def test_summary_mutations_rejected(self):
        inputs, anchor = fixture()
        result = completion.build(inputs=inputs,anchor=anchor,incumbent={})
        for field,value in [('selected',{}),('lower_product','999'),('tie_break_optimality_established',True),
                            ('enumeration',None),('root_box',{})]:
            changed = deepcopy(result)
            changed[field] = value
            with self.assertRaisesRegex(ValueError,'DOMAIN_COMPLETION_CERTIFICATE_CHANGED'):
                completion.verify(changed,expected_inputs_sha256=continuous.digest(inputs),
                                  expected_anchor_sha256=continuous.digest(anchor))

    def test_input_and_cap_rejected(self):
        inputs, anchor = fixture()
        changed = dict(inputs,entered_cash='21')
        with self.assertRaisesRegex(ValueError,'ANCHOR_INPUT_MISMATCH'):
            completion.build(inputs=changed,anchor=anchor,incumbent={})
        for cap in (False,0,10001):
            with self.assertRaisesRegex(ValueError,'TAIL_POINT_CAP_REQUIRED'):
                completion.build(inputs=inputs,anchor=anchor,incumbent={},max_tail_points=cap)


if __name__ == '__main__':
    unittest.main()
