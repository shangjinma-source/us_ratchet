import unittest

import numpy as np
import pandas as pd

from backtest.ndx_periodic_execution_clock import build_periodic_execution_schedule


def fixture():
    rng = np.random.default_rng(80)
    frame = pd.DataFrame(rng.normal(0, .01, (306, 4)),
        index=pd.bdate_range('2022-01-01', periods=306), columns=list('ABCD'))
    return dict(returns=frame, tickers=list('ABCD'), fit_days=126, step_days=21,
        execution_end=frame.index[293], weight_spec='constrained_fixed_shrinkage_turnover_anchor',
        risk_chain_by_ticker={t:t for t in frame}, projection_parameters=dict(
            shrinkage_intensity=.35, max_single_weight=.45, min_single_weight=.05,
            top_weight_cap=.8, minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55,
            turnover_anchor_strength=.25))


class ClockTests(unittest.TestCase):
    def test_execution_cadence_not_truncated_by_statistical_horizon(self):
        arguments = fixture()
        result = build_periodic_execution_schedule(**arguments)
        self.assertEqual(len(range(126, 306-126+1, 21)), 3)
        self.assertEqual(len(result['schedule']), 8)
        self.assertEqual([r['execution_date'] for r in result['schedule']],
                         [str(arguments['returns'].index[i].date()) for i in range(126, 294, 21)])
        self.assertTrue(all(r['fit_end'] < r['execution_date'] for r in result['schedule']))

    def test_execution_day_and_future_returns_cannot_change_current_target(self):
        arguments = fixture()
        before = build_periodic_execution_schedule(**arguments)
        arguments['returns'] = arguments['returns'].copy()
        arguments['returns'].iloc[168:] = .5
        after = build_periodic_execution_schedule(**arguments)
        self.assertEqual(before['schedule'][:3], after['schedule'][:3])

    def test_explicit_end_and_typed_inputs_required(self):
        for changes in ({'fit_days':True}, {'execution_end':'2099-01-01'}, {'tickers':['A','A']}):
            arguments = fixture(); arguments.update(changes)
            with self.assertRaises(ValueError):
                build_periodic_execution_schedule(**arguments)


if __name__ == '__main__':
    unittest.main()
