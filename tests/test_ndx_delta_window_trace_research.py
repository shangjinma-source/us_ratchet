from copy import deepcopy
import unittest
from unittest.mock import patch

from backtest import ndx_delta_window_trace_research as trace
from test_ndx_joint_weight_evaluation import fixture
from test_ndx_non_equal_fractional_research import full_with_observed_windows


class DeltaWindowTraceTests(unittest.TestCase):
    def test_complete_original_economics_and_actual_anchor_windows(self):
        for spec in ('constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'):
            task, inputs = fixture()
            task['weight_spec'] = spec
            original_inputs = deepcopy(inputs)
            globals_before = dict(trace.binding._PORTFOLIO.__globals__)
            expected, windows = full_with_observed_windows(task, inputs)
            actual = trace.evaluate_with_window_trace(task=task, inputs=inputs)
            self.assertEqual(actual['result'], expected)
            self.assertEqual([(r['fit_end'], r['weights']) for r in actual['historical_window_weights']], windows)
            self.assertTrue(all(trace.binding._PORTFOLIO.__globals__[k] is v for k, v in globals_before.items()))
            for field in ('returns', 'nominal_prices', 'universe', 'target_returns'):
                self.assertTrue(inputs[field].equals(original_inputs[field]))
            self.assertFalse(actual['original_checkpoint_equivalence_verified'])
            self.assertFalse(actual['no_fit_reuse'])

    def test_source_and_original_validation_fail_closed(self):
        task, inputs = fixture()
        with patch.object(trace, 'LOADED', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                trace.evaluate_with_window_trace(task=task, inputs=inputs)
        for field in ('nominal_prices', 'returns'):
            malformed = deepcopy(inputs)
            malformed[field].iloc[0, 0] = float('nan')
            with self.assertRaises(ValueError):
                trace.evaluate_with_window_trace(task=task, inputs=malformed)
        task['decision_data_end'] = '2020-09-08'
        with self.assertRaises(ValueError):
            trace.evaluate_with_window_trace(task=task, inputs=inputs)

    def test_certified_reconstruction_and_failure_propagation(self):
        task, inputs = fixture()
        minimize = trace.full.probe.projection.minimize

        def failed_status(*args, **kwargs):
            result = minimize(*args, **kwargs)
            result.success = False
            result.message = 'synthetic status failure'
            return result

        with patch.object(trace.full.probe.projection, 'minimize', side_effect=failed_status):
            expected, windows = full_with_observed_windows(task, inputs)
            actual = trace.evaluate_with_window_trace(task=task, inputs=inputs)
        self.assertGreater(actual['result']['projection_reconstruction_audit']['attempt_count'], 0)
        self.assertEqual(actual['result'], expected)
        self.assertEqual(len(actual['historical_window_weights']), len(windows))
        with patch.object(trace.full.probe.projection, 'minimize', side_effect=failed_status), patch.object(
                trace.full.probe, 'certify_projection_candidate', return_value={'certified': False}):
            with self.assertRaisesRegex(ValueError, 'independent original-contract certificate'):
                trace.evaluate_with_window_trace(task=task, inputs=inputs)
