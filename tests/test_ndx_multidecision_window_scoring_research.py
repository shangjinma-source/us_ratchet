from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from backtest import ndx_multidecision_window_scoring_research as scoring
from backtest.ndx_cardinality_discovery import evaluate_synthetic_portfolio


def fixture():
    dates = pd.bdate_range(end='2026-03-31', periods=504)
    names = list('ABCDEFGH')
    frame = pd.DataFrame({name: [.0001 * (column + 1) + .005 * np.sin(i / 11 + column)
                                for i in range(504)] for column, name in enumerate(names)}, index=dates)
    original = dict(zip(names, [1., 2., 3., 4., 1., 2., 3., 4.]))
    normalized = pd.Series({name: value / sum(original.values()) for name, value in original.items()})
    incumbent = frame[names].mul(normalized, axis=1).sum(axis=1)
    target = frame['H'] * .4
    windows = []
    strings = [value.date().isoformat() for value in dates]
    for index in range(13):
        start = 126 + index * 21
        windows.append(dict(window_index=index, fit_first_return_end=strings[start - 126],
                            fit_last_return_end=strings[start - 1],
                            evaluation_first_return_end=strings[start],
                            evaluation_last_return_end=strings[start + 125],
                            weights=[.25] * 4, projection_relaxed=False))
    securities = [dict(security_id=name, ticker=name, issuer_id=name, risk_chain=name) for name in names[:4]]
    args = dict(cutoff=strings[-1], return_dates=strings, securities=securities,
                candidate_returns=frame[names[:4]].to_numpy().tolist(),
                incumbent_returns=incumbent.tolist(), target_returns=target.tolist(),
                original_incumbent_weights=original, fitted_windows=windows)
    return args, frame, target


class Tests(unittest.TestCase):
    def test_frozen_equal_weight_metric_parity(self):
        args, frame, target = fixture()
        actual = scoring.reduce_fitted_scoring_windows(**args)
        universe = pd.DataFrame([dict(ticker=name, issuer_id=name, risk_chain=name,
                                     synthetic_price=10., median_dollar_volume_usd=100000000.)
                                 for name in frame.columns])
        expected = evaluate_synthetic_portfolio(tuple('ABCD'), universe, frame, target, list('ABCDEFGH'),
                    fit_days=126, window_days=126, step_days=21, transaction_cost_bps=10.,
                    incumbent_weights=args['original_incumbent_weights'])
        for key, value in actual['metrics'].items():
            if key in expected:
                self.assertEqual(value.hex(), float(expected[key]).hex(), key)
        self.assertTrue(actual['fractional_risk_passed'])
        self.assertGreater(actual['windows'][0]['entry_cost'], 0.)
        self.assertTrue(all(row['entry_cost'] == 0 for row in actual['windows'][1:]))
        self.assertFalse(actual['fit_performed'])
        self.assertFalse(actual['whole_lot_gate_evaluated'])

    def test_prior_fee_and_window_risk_are_not_final_weights_only(self):
        args, _, _ = fixture()
        args['fitted_windows'][1]['weights'] = [.85, .05, .05, .05]
        result = scoring.reduce_fitted_scoring_windows(**args)
        self.assertFalse(result['fractional_risk_passed'])
        self.assertEqual(result['windows'][2]['fee_reference_weights'], dict(zip('ABCD', [.85, .05, .05, .05])))
        self.assertGreater(result['windows'][2]['entry_cost'], 0.)
        self.assertEqual(result['windows'][3]['entry_cost'], 0.)

    def test_missing_future_nonfinite_boolean_and_issuer_rejected(self):
        args, _, _ = fixture()
        attacks = [lambda a: a['fitted_windows'].pop(),
                   lambda a: a['return_dates'].__setitem__(-1, '2026-04-01'),
                   lambda a: a['candidate_returns'][0].__setitem__(0, float('nan')),
                   lambda a: a['fitted_windows'][0]['weights'].__setitem__(0, True),
                   lambda a: a['fitted_windows'][0].__setitem__('fit_last_return_end', a['return_dates'][126]),
                   lambda a: a['securities'][1].__setitem__('issuer_id', 'A')]
        for attack in attacks:
            value = deepcopy(args)
            attack(value)
            with self.assertRaises(ValueError):
                scoring.reduce_fitted_scoring_windows(**value)


if __name__ == '__main__':
    unittest.main()
