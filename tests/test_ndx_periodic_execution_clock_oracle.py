import unittest
from unittest.mock import patch

import pandas as pd

from backtest import ndx_periodic_execution_clock as clock
from test_ndx_periodic_execution_clock import fixture


class ClockOracleTests(unittest.TestCase):
    def test_every_fit_slice_and_anchor_are_previous_target_only(self):
        arguments = fixture()
        before = arguments['returns'].copy(deep=True)
        seen = []

        def weights(history, names, **kwargs):
            expected_start = 126 + len(seen) * 21
            pd.testing.assert_frame_equal(history, before.iloc[expected_start-126:expected_start])
            if seen:
                pd.testing.assert_series_equal(kwargs['anchor_weights'], seen[-1])
                self.assertIsNot(kwargs['anchor_weights'], seen[-1])
            else:
                self.assertIsNone(kwargs['anchor_weights'])
            values = [.1, .2, .3, .4]
            shift = len(seen) % 4
            result = pd.Series(values[shift:] + values[:shift], index=names)
            seen.append(result)
            return result

        with patch.object(clock.evaluation, '_SHRINKAGE', side_effect=weights):
            result = clock.build_periodic_execution_schedule(**arguments)
        self.assertEqual(len(seen), 8)
        self.assertEqual([row['weights'] for row in result['schedule']], [value.to_dict() for value in seen])
        pd.testing.assert_frame_equal(arguments['returns'], before)

    def test_nonanchored_model_does_not_receive_previous_target(self):
        arguments = fixture()
        arguments['weight_spec'] = 'constrained_fixed_shrinkage'

        def weights(history, names, **kwargs):
            self.assertIsNone(kwargs['anchor_weights'])
            self.assertEqual(kwargs['turnover_anchor_strength'], 0.)
            return pd.Series(.25, index=names)

        with patch.object(clock.evaluation, '_SHRINKAGE', side_effect=weights):
            self.assertEqual(len(clock.build_periodic_execution_schedule(**arguments)['schedule']), 8)

    def test_evaluator_source_change_during_clock_rejected(self):
        arguments = fixture()
        arguments['weight_spec'] = 'equal_weight'
        hashes = dict(clock.evaluation._LOADED_SOURCES)
        changed = dict(hashes)
        changed[next(iter(changed))] = '0' * 64
        with patch.object(clock.evaluation, 'source_hashes', side_effect=[hashes, changed]):
            with self.assertRaisesRegex(ValueError, 'changed during fit'):
                clock.build_periodic_execution_schedule(**arguments)

    def test_equal_weight_still_rejects_invalid_explicit_risk_contract(self):
        for changes in ({'max_single_weight': 0}, {'risk_chain_top1_cap': 0},
                        {'min_single_weight': .5, 'max_single_weight': .4}):
            arguments = fixture()
            arguments['weight_spec'] = 'equal_weight'
            arguments['projection_parameters'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                clock.build_periodic_execution_schedule(**arguments)


if __name__ == '__main__':
    unittest.main()
