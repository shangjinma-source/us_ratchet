import unittest

import numpy as np
import pandas as pd

from backtest.ndx_projection_certificate_research import certify_projection_candidate as certify


class OriginalConstraintOracleTests(unittest.TestCase):
    def test_hhi_residual_does_not_relax_original_effective_name_floor(self):
        count = 15
        effective_floor = 10.5
        # HHI excess passes the original certificate's 1e-10 tolerance, but
        # its reciprocal implies Neff shortfall > 1e-9 allowed by v2.
        displacement = np.sqrt((1 / effective_floor + 9e-11 - 1 / count) * (count - 1) / count)
        weights = pd.Series([1 / count + displacement] +
                            [1 / count - displacement / (count - 1)] * (count - 1),
                            index=[str(index) for index in range(count)])
        self.assertLess(float(weights @ weights) - 1 / effective_floor, 1e-10)
        self.assertGreater(effective_floor - 1 / float(weights @ weights), 1e-9)
        result = certify(weights, weights, max_weight=1., min_weight=0.,
                         top_weight_count=3, top_weight_cap=1., min_effective_n=effective_floor)
        self.assertFalse(result['certified'])
        self.assertFalse(result['primal_passed'])
        self.assertEqual(result['status'], 'PRIMAL_REJECTED')

    def test_overflowing_target_sum_cannot_certify_a_different_objective_from_v2(self):
        raw = pd.Series([1e308, 1e308, 1e307, 1e307], index=list('ABCD'))
        candidate = pd.Series([5 / 11, 5 / 11, .5 / 11, .5 / 11], index=raw.index)
        self.assertTrue(np.isfinite(raw.to_numpy()).all())
        with np.errstate(over='ignore'), self.assertRaises(ValueError):
            certify(raw, candidate, max_weight=.8, min_weight=0.,
                    top_weight_count=2, top_weight_cap=1.)


if __name__ == '__main__':
    unittest.main()
