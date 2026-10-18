from copy import deepcopy
import math
import unittest
import numpy as np
from backtest import ndx_multidecision_window_scoring_inspection_research as audit
from backtest import ndx_multidecision_window_scoring_research as producer
from test_ndx_multidecision_window_scoring_research import fixture


class Tests(unittest.TestCase):
    def test_exact_synthetic_parity_all_cardinalities(self):
        for k in range(4, 21):
            args, _, _ = fixture()
            args['securities'] = [dict(security_id=str(i), ticker=str(i), issuer_id=str(i), risk_chain=str(i % 4)) for i in range(k)]
            args['candidate_returns'] = [[float(.009 * np.sin(i / 13 + j)) for j in range(k)] for i in range(504)]
            for j, window in enumerate(args['fitted_windows']):
                raw = [1 + (i + j) % 3 for i in range(k)]
                window['weights'] = [x / sum(raw) for x in raw]
            saved = producer.reduce_fitted_scoring_windows(**args)
            before = deepcopy(args)
            self.assertEqual(audit.inspect_fitted_scoring_windows(**args, saved_score=saved)['status'], 'PASS')
            self.assertEqual(args, before)

    def test_initial_peak_fee_and_buy_hold_compounding(self):
        annual, dd = audit.window_numbers([0.] * 126, .001)
        self.assertEqual(annual, float(np.float64(.999) ** 2 - 1))
        self.assertEqual(dd, 1 - .999)
        annual, dd = audit.window_numbers([.1, -.2] + [0.] * 124, 0.)
        self.assertEqual(annual, float(np.float64(1.1 * .8) ** 2 - 1))
        self.assertEqual(dd, 1 - (1.1 * .8) / 1.1)

    def test_one_ulp_and_full_metadata_rejected(self):
        args, _, _ = fixture()
        saved = producer.reduce_fitted_scoring_windows(**args)
        attacks = [lambda d: d['metrics'].__setitem__('return_p10', math.nextafter(d['metrics']['return_p10'], math.inf)),
                   lambda d: d['windows'][0]['fee_summation_order'].append(d['windows'][0]['fee_summation_order'][0]),
                   lambda d: d['windows'][0]['fee_summation_order'].pop(),
                   lambda d: d['windows'][0].__setitem__('entry_cost', 0.),
                   lambda d: d['windows'][0]['risk_checks'].__setitem__('MIN_SINGLE_WEIGHT', 1),
                   lambda d: d.__setitem__('point_in_time_verified', 0),
                   lambda d: d['windows'][12]['fitted_window_preserved'].__setitem__('projection_relaxed', True)]
        for attack in attacks:
            changed = deepcopy(saved)
            attack(changed)
            with self.assertRaises(ValueError):
                audit.inspect_fitted_scoring_windows(**args, saved_score=changed)

    def test_minimum_weight_and_paired_quantile_not_final_only(self):
        args, _, _ = fixture()
        args['fitted_windows'][1]['weights'] = [.91, .03, .03, .03]
        saved = producer.reduce_fitted_scoring_windows(**args)
        self.assertFalse(saved['fractional_risk_passed'])
        self.assertFalse(saved['windows'][1]['risk_checks']['MIN_SINGLE_WEIGHT'])
        self.assertEqual(audit.inspect_fitted_scoring_windows(**args, saved_score=saved)['status'], 'PASS')
        saved['metrics']['paired_return_p10_vs_incumbent'] = saved['metrics']['return_p10'] - saved['metrics']['incumbent_return_p10']
        with self.assertRaises(ValueError):
            audit.inspect_fitted_scoring_windows(**args, saved_score=saved)


if __name__ == '__main__':
    unittest.main()
