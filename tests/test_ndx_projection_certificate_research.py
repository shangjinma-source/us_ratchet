import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest.ndx_projection_certificate_research import certify_projection_candidate as certify


class ProjectionCertificateTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'data/cache/research/ndx_joint_weight_experiment_v2/projection_failure_active_set_fixture.json'
        fixture = json.loads(path.read_text(encoding='utf-8'))
        names = fixture['raw_target_ticker_order']
        self.raw = pd.Series(fixture['raw_target'], index=names)
        self.candidate = pd.Series(fixture['independent_active_set_reconstruction']['weights'], index=names)
        self.bounds = fixture['constraints']

    def test_real_fixture_certificate_and_gradient_convention(self):
        result = certify(self.raw, self.candidate, **self.bounds)
        self.assertTrue(result['certified'])
        self.assertLess(result['stationarity_max_abs'], 1e-12)
        self.assertLess(result['complementarity_max_abs'], 1e-12)
        multipliers = {a['name']: a['multiplier'] for a in result['active_constraints']}
        self.assertAlmostEqual(multipliers['HHI'], 0.02085230771358626, places=10)
        self.assertFalse(result['task_recomputed'])

    def test_feasible_uniform_is_not_optimal(self):
        result = certify(self.raw, pd.Series(.2, index=self.raw.index), **self.bounds)
        self.assertTrue(result['primal_passed'])
        self.assertFalse(result['certified'])
        self.assertEqual(result['status'], 'KKT_NOT_CERTIFIED')

    def test_interior_target_and_nonpositive_preprocessing(self):
        raw = pd.Series([.21, .24, .26, .29], index=list('ABCD'))
        bounds = dict(max_weight=.6, min_weight=.01, top_weight_count=2,
                      top_weight_cap=.9, min_effective_n=2)
        result = certify(raw, raw, **bounds)
        self.assertTrue(result['certified'])
        self.assertEqual(result['active_constraints'], [])
        result = certify(raw*0-1, pd.Series(.25, index=raw.index), **bounds)
        self.assertTrue(result['certified'])

    def test_all_tied_subsets_and_redundant_groups_order_invariant(self):
        names = list('ABCD')
        raw = pd.Series([.7, .1, .1, .1], index=names)
        candidate = pd.Series(.25, index=names)
        bounds = dict(max_weight=.5, min_weight=.05, top_weight_count=2,
                      top_weight_cap=.5, group_labels=dict(A='X', B='X', C='Y', D='Y'), max_group_weight=.5)
        result = certify(raw, candidate, **bounds)
        self.assertTrue(result['certified'])
        self.assertEqual(sum(a['name'].startswith('TOP:') for a in result['active_constraints']), 6)
        names.reverse()
        permuted = certify(raw[names], candidate[names], **bounds)
        self.assertTrue(permuted['certified'])

    def test_primal_violation_and_budget_fail_closed(self):
        bad = self.candidate.copy()
        bad.iloc[1] -= .001
        bad.iloc[0] += .001
        self.assertEqual(certify(self.raw, bad, **self.bounds)['status'], 'PRIMAL_REJECTED')
        result = certify(self.raw, self.candidate, max_top_subsets=1, **self.bounds)
        self.assertEqual(result['status'], 'SUBSET_BUDGET_EXCEEDED')
        self.assertFalse(result['certified'])

    def test_input_poison(self):
        for poison in (True, float('nan'), float('inf')):
            bad = self.raw.astype(object)
            bad.iloc[0] = poison
            with self.assertRaises(ValueError):
                certify(bad, self.candidate, **self.bounds)
        for override in ({'max_weight': True}, {'primal_tolerance': .1},
                         {'group_labels': {'ADBE': 'X'}}, {'max_top_subsets': True}):
            with self.assertRaises(ValueError):
                certify(self.raw, self.candidate, **{**self.bounds, **override})

    def test_untrusted_multiplier_output_rejected(self):
        for bad in (np.zeros(3), np.full(3, -1.), np.full(3, np.nan), np.zeros(4)):
            with patch('backtest.ndx_projection_certificate_research.nnls', return_value=(bad, 0.)):
                result = certify(self.raw, self.candidate, **self.bounds)
            self.assertFalse(result['certified'])

    def test_degenerate_hhi_is_not_falsely_certified(self):
        result = certify(self.raw, pd.Series(.2, index=self.raw.index),
                         **{**self.bounds, 'min_effective_n': 5})
        self.assertTrue(result['primal_passed'])
        self.assertFalse(result['certified'])
        self.assertFalse(result['primal_infeasibility_proven'])


if __name__ == '__main__':
    unittest.main()
