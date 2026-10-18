import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest.ndx_projection_reconstruction_research import reconstruct_projection_candidate as reconstruct
from backtest import ndx_projection_reconstruction_research as module


class ProjectionReconstructionTests(unittest.TestCase):
    def setUp(self):
        fixture_path = Path(__file__).resolve().parents[1] / 'data/cache/research/ndx_joint_weight_experiment_v2/projection_failure_active_set_fixture.json'
        fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
        names = fixture['raw_target_ticker_order']
        self.raw = pd.Series(fixture['raw_target'], index=names)
        self.optimum = pd.Series(fixture['independent_active_set_reconstruction']['weights'], index=names)
        self.bounds = fixture['constraints']

    def test_perturbed_july_point_reconstructed_not_accepted(self):
        proposed = self.optimum+pd.Series([2e-8, -1e-8, 1e-8, -1e-8, -1e-8], index=self.raw.index)
        result = reconstruct(self.raw, proposed, **self.bounds)
        self.assertTrue(result['certified'])
        self.assertFalse(result['proposed_certificate']['certified'])
        np.testing.assert_allclose(list(result['weights'].values()), self.optimum, atol=1e-12, rtol=0)
        self.assertEqual(result['affine_rank'], 3)
        self.assertLess(result['certificate']['stationarity_max_abs'], 1e-12)

    def test_exact_kkt_fixture_still_reconstructed(self):
        result = reconstruct(self.raw, self.optimum, **self.bounds)
        self.assertTrue(result['certified'])
        self.assertIn('reconstructed_affine_residuals', result)
        self.assertEqual(result['weights'], result['certificate']['candidate'])

    def test_wrong_face_is_unresolved_not_infeasible(self):
        result = reconstruct(self.raw, pd.Series(.2, index=self.raw.index), **self.bounds)
        self.assertFalse(result['certified'])
        self.assertIsNone(result['weights'])
        self.assertFalse(result['primal_infeasibility_proven'])

    def test_rank_deficient_tied_top_and_groups(self):
        names = list('ABCD')
        raw = pd.Series([.7, .1, .1, .1], index=names)
        proposed = pd.Series(.25, index=names)
        bounds = dict(max_weight=.5, min_weight=.05, top_weight_count=2,
                      top_weight_cap=.5, group_labels=dict(A='X', B='X', C='Y', D='Y'), max_group_weight=.5)
        result = reconstruct(raw, proposed, **bounds)
        self.assertTrue(result['certified'])
        self.assertLess(result['affine_rank'], len(result['affine_constraints']))
        permuted = reconstruct(raw.iloc[::-1], proposed.iloc[::-1], **bounds)
        self.assertTrue(permuted['certified'])
        for name in names:
            self.assertAlmostEqual(result['weights'][name], permuted['weights'][name])

    def test_budget_and_invalid_inputs(self):
        result = reconstruct(self.raw, self.optimum, max_top_subsets=1, **self.bounds)
        self.assertFalse(result['certified'])
        self.assertEqual(result['status'], 'SUBSET_BUDGET_EXCEEDED')
        for overrides in ({'activity_tolerance': True}, {'activity_tolerance': .1},
                          {'rank_relative_tolerance': float('nan')}, {'max_weight': True}):
            with self.assertRaises(ValueError):
                reconstruct(self.raw, self.optimum, **{**self.bounds, **overrides})
        poison = self.optimum.astype(object)
        poison.iloc[0] = True
        with self.assertRaises(ValueError):
            reconstruct(self.raw, poison, **self.bounds)

    def test_certificate_rejection_is_not_overridden(self):
        real = module.certify_projection_candidate
        calls = []

        def reject_second(*args, **kwargs):
            result = real(*args, **kwargs)
            calls.append(result)
            if len(calls) == 2:
                result['certified'] = False
            return result

        with patch.object(module, 'certify_projection_candidate', side_effect=reject_second):
            result = reconstruct(self.raw, self.optimum, **self.bounds)
        self.assertEqual(result['status'], 'RECONSTRUCTION_NOT_CERTIFIED')
        self.assertIsNone(result['weights'])

    def test_source_drift_is_rejected_before_or_after(self):
        with patch.object(module, '_source_hashes', return_value={}):
            with self.assertRaises(ValueError):
                reconstruct(self.raw, self.optimum, **self.bounds)
        with patch.object(module, '_source_hashes', side_effect=[module._LOADED_SOURCES, {}]):
            with self.assertRaises(ValueError):
                reconstruct(self.raw, self.optimum, **self.bounds)


if __name__ == '__main__':
    unittest.main()
