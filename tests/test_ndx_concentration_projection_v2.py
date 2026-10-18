import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.optimize import OptimizeResult

from backtest.ndx_concentration_projection_v2 import (
    project_concentration_envelope_weights_v2 as project, ProjectionError,
    _box_simplex_hhi_projection)


class ProjectionV2Tests(unittest.TestCase):
    def test_actual_failed_target_matches_independent_closed_form_kkt(self):
        target = pd.Series([.041666666666666664, .19896540255095393, .10930547427376339,
                            .054776954822652726, .09086766911124666, .5044178325747165],
                           index=['AMAT', 'AVGO', 'CDNS', 'FTNT', 'SNPS', 'TXN'])
        labels = dict(zip(target.index, ['semiconductor_equipment', 'diversified_technology',
                                        'eda_ip', 'cybersecurity', 'eda_ip', 'analog_power']))
        result = project(target, max_weight=.45, min_weight=.05, top_weight_count=3,
                         top_weight_cap=.8, min_effective_n=4.199999999999999,
                         group_labels=labels, max_group_weight=.55)
        normalized = target.to_numpy() / target.sum()
        uniform = np.full(6, 1. / 6)
        alpha = np.sqrt((1. / 4.199999999999999 - 1. / 6) / np.sum((normalized - uniform) ** 2))
        oracle = uniform + alpha * (normalized - uniform)
        multiplier = 1. / alpha - 1.
        stationarity = 2 * (oracle - normalized) + 2 * multiplier * oracle - 2 * multiplier / 6
        self.assertGreater(multiplier, 0)
        self.assertLess(np.max(np.abs(stationarity)), 1e-14)
        self.assertAlmostEqual(oracle @ oracle, 1 / 4.199999999999999, places=14)
        self.assertTrue((oracle > .05).all() and (oracle < .45).all())
        self.assertLess(np.sort(oracle)[-3:].sum(), .8)
        self.assertLess(oracle[2] + oracle[4], .55)
        np.testing.assert_allclose(result, oracle, atol=2e-10, rtol=0.)

    def test_active_group_cap_has_closed_form_transfer_oracle(self):
        raw = pd.Series([.5, .3, .1, .1], index=list('ABCD'))
        result = project(raw, max_weight=.9, min_weight=.01, top_weight_count=2, top_weight_cap=1.,
                         group_labels=dict(A='X', B='X', C='Y', D='Y'), max_group_weight=.55)
        np.testing.assert_allclose(result, [.375, .175, .225, .225], atol=1e-8, rtol=0.)

    def test_active_single_name_cap_matches_simplex_projection(self):
        result = project(pd.Series([.8, .1, .1]), max_weight=.4, min_weight=.05,
                         top_weight_count=2, top_weight_cap=.9)
        np.testing.assert_allclose(result, [.4, .3, .3], atol=1e-8, rtol=0.)

    def test_active_top_group_cap_and_permutation(self):
        raw = pd.Series([.7, .2, .08, .02], index=list('ABCD'))
        kwargs = dict(max_weight=.9, min_weight=.01, top_weight_count=2, top_weight_cap=.6)
        result = project(raw, **kwargs)
        self.assertAlmostEqual(result.nlargest(2).sum(), .6, places=9)
        self.assertAlmostEqual(result.sum(), 1., places=9)
        reordered = project(raw.iloc[::-1], **kwargs).reindex(raw.index)
        np.testing.assert_allclose(result, reordered, atol=1e-8, rtol=0.)

    def test_unique_equal_boundary_and_infeasible_group_rejected(self):
        result = project(pd.Series([.9, .1]), max_weight=.5, min_weight=.05,
                         top_weight_count=1, top_weight_cap=.8)
        np.testing.assert_array_equal(result, [.5, .5])
        with self.assertRaises(ProjectionError):
            project(pd.Series([.9, .1], index=['A', 'B']), max_weight=.5, min_weight=.05,
                    top_weight_count=1, top_weight_cap=.8, group_labels={'A': 'same', 'B': 'same'},
                    max_group_weight=.55)

    def test_failed_solver_is_not_accepted_even_with_feasible_vector(self):
        failed = OptimizeResult(success=False, message='forced failure', x=np.r_[np.full(3, 1/3), 1/3, np.zeros(3)])
        with patch('backtest.ndx_concentration_projection_v2.minimize', return_value=failed):
            with self.assertRaisesRegex(ProjectionError, 'forced failure'):
                project(pd.Series([.8, .1, .1]), max_weight=.9, min_weight=.05,
                        top_weight_count=2, top_weight_cap=.7)

    def test_closed_form_optimum_does_not_need_numerical_solver(self):
        with patch('backtest.ndx_concentration_projection_v2.minimize', side_effect=AssertionError('not needed')):
            result = project(pd.Series([.6, .2, .2]), max_weight=.8, min_weight=.01,
                             top_weight_count=2, top_weight_cap=.95, min_effective_n=2.8)
        self.assertAlmostEqual(1. / float(result @ result), 2.8, places=12)

    def test_real_overlap_failure_active_floor_and_hhi_kkt(self):
        target = np.array([.3412615617790578, .012500000000000002, .35486992370386855,
                           .1672069040360446, .023028791303246882, .10113281917778215])
        target /= target.sum()
        weights, alpha, threshold = _box_simplex_hhi_projection(target, .05, .45, 4.199999999999999)
        multiplier = 1. / alpha - 1.
        gradient = (1. + multiplier) * weights - target + threshold / alpha
        interior = (weights > .05 + 1e-12) & (weights < .45 - 1e-12)
        self.assertLess(np.max(np.abs(gradient[interior])), 1e-12)
        self.assertTrue((gradient[weights <= .05 + 1e-12] >= -1e-12).all())
        self.assertGreater(multiplier, 0)
        self.assertAlmostEqual(1. / float(weights @ weights), 4.2, places=12)
        with patch('backtest.ndx_concentration_projection_v2.minimize', side_effect=AssertionError('dual solution suffices')):
            result = project(pd.Series(target, index=list('ABCDEF')), max_weight=.45, min_weight=.05,
                             top_weight_count=3, top_weight_cap=.8, min_effective_n=4.199999999999999,
                             group_labels=dict(A='a', B='b', C='c', D='eda', E='d', F='eda'), max_group_weight=.55)
        np.testing.assert_allclose(result, weights, atol=1e-12, rtol=0.)


if __name__ == '__main__':
    unittest.main()
