from copy import deepcopy
import unittest
from unittest.mock import patch

import pandas as pd

from backtest import ndx_multidecision_rolling_fit_research as rolling
from test_ndx_multidecision_window_scoring_research import fixture


def inputs():
    values, _, _ = fixture()
    return {key: values[key] for key in ('cutoff', 'return_dates', 'securities', 'candidate_returns')}


class Tests(unittest.TestCase):
    def test_inner_anchor_none_still_has_strength_and_only_past_returns(self):
        args = inputs()
        frame = rolling.prepare_panel(**args, weight_spec=rolling.SPECS[2])
        calls = []
        def fitter(history, tickers, **kwargs):
            calls.append((history.copy(), kwargs))
            return pd.Series([.2, .25, .25, .3], index=tickers)
        windows = rolling.fit_windows_with_fitter(frame, args['securities'], rolling.SPECS[2], fitter)
        self.assertEqual(len(calls), 13)
        self.assertIsNone(calls[0][1]['anchor_weights'])
        self.assertTrue(all(call[1]['turnover_anchor_strength'] == .25 for call in calls))
        self.assertEqual(calls[1][1]['anchor_weights'].tolist(), [.2, .25, .25, .3])
        for index, (history, _) in enumerate(calls):
            self.assertTrue(history.equals(frame.iloc[index * 21:index * 21 + 126]))
            self.assertLess(windows[index]['fit_last_return_end'], windows[index]['evaluation_first_return_end'])

    def test_equal_weight_actual_private_closure_no_optimizer(self):
        args = inputs()
        with patch.object(rolling.v3.probe.projection, 'minimize', side_effect=AssertionError('Unexpected fit')):
            result = rolling.fit_causal_scoring_windows(**args, weight_spec='equal_weight')
        self.assertEqual(len(result['windows']), 13)
        self.assertEqual(result['windows'][0]['weights'], [.25] * 4)
        self.assertEqual(result['reconstruction_attempts'], [])
        self.assertFalse(result['fit_performed'])
        self.assertFalse(result['outer_lane_prior_applied'])

    def test_unanchored_and_invalid_input(self):
        args = inputs()
        frame = rolling.prepare_panel(**args, weight_spec=rolling.SPECS[1])
        def fitter(history, tickers, **kwargs):
            self.assertIsNone(kwargs['anchor_weights'])
            self.assertEqual(kwargs['turnover_anchor_strength'], 0.)
            return pd.Series(.25, index=tickers)
        rolling.fit_windows_with_fitter(frame, args['securities'], rolling.SPECS[1], fitter)
        for field, value in [('return_dates', args['return_dates'][:-1]),
                             ('candidate_returns', args['candidate_returns'][:-1])]:
            bad = deepcopy(args)
            bad[field] = value
            with self.assertRaises(ValueError):
                rolling.prepare_panel(**bad, weight_spec=rolling.SPECS[1])


if __name__ == '__main__':
    unittest.main()
