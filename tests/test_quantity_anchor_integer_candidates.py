from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch

from backtest import quantity_anchor_integer_candidates as proposals
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as integer
from backtest import quantity_multi_anchor_bound_prototype as multi


def fixture(one=False, shared=False, flat=False):
    ids = ['A'] if one else ['A', 'B']
    inputs = dict(prices={s: '3' if s == 'A' else '4' for s in ids},
                  metadata={s: dict(ticker=s, issuer_id='same' if shared else s) for s in ids},
                  entered_cash='13', fee_bps='10', minimum_cash_buffer='1',
                  training_scenarios=[{s: '1' if flat else ('1.4' if s == 'A' else '0.9') for s in ids},
                                      {s: '1' if flat else ('0.9' if s == 'A' else '1.3') for s in ids}])
    p = integer.prepare(**inputs)
    box = {s: [0, int(p['spendable']//p['cost'][s])] for s in ids}
    anchor = continuous.from_candidate(inputs=inputs, box=box,
        inherited_evidence=multi.bound(inputs=inputs, box=box, incumbent={}),
        candidate={s: 1.0 for s in ids},
        diagnostics=dict(success=False, status=0, iterations=0, message='synthetic'))
    return inputs, anchor


class CandidateTests(unittest.TestCase):
    def test_exact_feasibility_and_inherited_frontier(self):
        inputs, anchor = fixture()
        with patch('scipy.optimize.minimize', side_effect=AssertionError('NO_OPTIMIZER')):
            result = proposals.generate(inputs=inputs, anchor=anchor,
                                        inherited_candidates=[{}, {'A': 1}, {'A': 1, 'B': 1}])
        self.assertEqual(set(result['best_by_k']), {'0', '1', '2'})
        ranks = []
        for row in result['feasible']:
            q = row['quantities']
            spent = sum(F(inputs['prices'][s])*n for s,n in q.items())
            residual = F(13)-spent*F('1.001')
            value = F(1)
            for scenario in inputs['training_scenarios']:
                value *= (residual + sum(F(inputs['prices'][s])*n*F(scenario[s]) for s,n in q.items()))/13
            self.assertEqual(value, F(row['product']))
            self.assertGreaterEqual(residual, 1)
            ranks.append((value, -spent, tuple(sorted(q.items()))))
        winner = result['selected']
        self.assertEqual((F(winner['product']), -F(winner['notional']),
                          tuple(sorted(winner['quantities'].items()))), max(ranks))
        self.assertFalse(result['objective_value_optimal'])

    def test_changed_cash_or_scenario_rejected(self):
        inputs, anchor = fixture()
        for key in ('entered_cash', 'training_scenarios'):
            changed = deepcopy(inputs)
            changed[key] = '14' if key == 'entered_cash' else [dict(A='2', B='2')]
            with self.assertRaisesRegex(ValueError, 'ANCHOR_INPUT_MISMATCH'):
                proposals.generate(inputs=changed, anchor=anchor, inherited_candidates=[{}])

    def test_tampered_anchor_rejected(self):
        inputs, anchor = fixture()
        anchor['repaired_quantities']['A'] = '3'
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_CHANGED'):
            proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[{}])

    def test_issuer_conflicts_rejected_not_promoted(self):
        inputs, anchor = fixture(shared=True)
        result = proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[{}])
        self.assertTrue(result['rejected'])
        self.assertTrue(all(len(row['quantities']) <= 1 for row in result['feasible']))
        with self.assertRaisesRegex(ValueError, 'ISSUER_CONFLICT'):
            proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[dict(A=1, B=1)])

    def test_one_axis_and_flat_return_cash_preference(self):
        inputs, anchor = fixture(one=True, flat=True)
        inputs['fee_bps'] = '0'
        p = integer.prepare(**inputs)
        box = {'A': [0, int(p['spendable']//p['cost']['A'])]}
        anchor = continuous.from_candidate(inputs=inputs, box=box,
            inherited_evidence=multi.bound(inputs=inputs, box=box, incumbent={}),
            candidate={'A': 1.0}, diagnostics=dict(success=False,status=0,iterations=0,message='synthetic'))
        result = proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[dict(A=1), {}])
        self.assertEqual(result['selected']['quantities'], {})
        self.assertEqual(result['axes'], ['A'])

    def test_cap_and_invalid_integer_fail_closed(self):
        inputs, anchor = fixture()
        for limit in (True, 0, -1, 20001):
            with self.assertRaisesRegex(ValueError, 'CANDIDATE_LIMIT_REQUIRED'):
                proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[{}], candidate_limit=limit)
        with self.assertRaisesRegex(ValueError, 'CANDIDATE_LIMIT_REACHED'):
            proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[{}], candidate_limit=1)
        for q in [dict(A=True), dict(A=-1), dict(A=0.5), dict(Z=1)]:
            with self.assertRaisesRegex(ValueError, 'INVALID_CANDIDATE_QUANTITIES'):
                proposals.generate(inputs=inputs, anchor=anchor, inherited_candidates=[q])


if __name__ == '__main__':
    unittest.main()
