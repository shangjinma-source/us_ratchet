from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backtest import ndx_joint_weight_evaluation_v2 as binding
from backtest import ndx_joint_weight_evaluation_v3 as full
from backtest import ndx_non_equal_fractional_research as fractional
from test_ndx_joint_weight_evaluation import fixture


def full_with_observed_windows(task, inputs):
    """Observe fits in the full v3 engine, leaving its whole-lot path enabled."""
    windows = []

    def bind(function, **dependencies):
        if function is binding._PORTFOLIO:
            fitter = dependencies['constrained_fixed_shrinkage_weights']

            def record(history, combo, **parameters):
                weights = fitter(history, combo, **parameters)
                windows.append((str(history.index[-1].date()), weights.to_dict()))
                return weights

            dependencies['constrained_fixed_shrinkage_weights'] = record
        return binding._bind(function, **dependencies)

    proxy = SimpleNamespace(**dict(vars(binding), _bind=bind))
    reconstructed = binding._bind(full.probe.evaluate_reconstructed, evaluator=proxy)
    evaluator = binding._bind(full.evaluate_joint_weight_task_v3,
        probe=SimpleNamespace(**dict(vars(full.probe), evaluate_reconstructed=reconstructed)))
    return evaluator(task, **inputs), windows


class NonEqualFractionalTests(unittest.TestCase):
    def test_both_specs_full_v3_overlap_and_window_weights(self):
        for spec in ('constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'):
            task, inputs = fixture(); task['weight_spec'] = spec
            expected, windows = full_with_observed_windows(task, inputs)
            actual = fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)
            for field, value in actual['result'].items():
                self.assertEqual(value, expected[field], field)
            self.assertEqual([(row['fit_end'], row['weights']) for row in actual['historical_window_weights']], windows)
            self.assertEqual(actual['projection_reconstruction_audit'], expected['projection_reconstruction_audit'])
            self.assertIn('whole_lot_path_return_net', expected)
            self.assertFalse(any(key.startswith('whole_lot_') for key in actual['result']))
            self.assertNotIn('declared_constraints_passed', actual['result'])
            self.assertNotIn('constraint_failure_reasons', actual['result'])

    def test_full_nominal_and_future_validation_not_skipped(self):
        for mutation in (lambda i: i.pop('nominal_prices'),
                         lambda i: i.update(nominal_prices=i['nominal_prices'].iloc[1:]),
                         lambda i: i['nominal_prices'].iloc.__setitem__((0, 0), float('nan'))):
            task, inputs = fixture(); mutation(inputs)
            with self.assertRaises(ValueError): fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)
        task, inputs = fixture(); task['decision_data_end'] = '2020-09-08'
        with self.assertRaises(ValueError): fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)

    def test_no_continuous_whole_lot_and_no_global_or_input_mutation(self):
        task, inputs = fixture(); before = deepcopy(inputs)
        old_globals = dict(binding._PORTFOLIO.__globals__)
        def fail(*a, **k): raise AssertionError('Continuous whole-lot must not run')
        isolated = binding._bind(binding._PORTFOLIO, simulate_continuous_whole_lot_rebalance=fail)
        with patch.object(binding, '_PORTFOLIO', isolated):
            result = fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)
        self.assertFalse(result['continuous_whole_lot_executed'])
        self.assertTrue(all(binding._PORTFOLIO.__globals__[k] is v for k, v in old_globals.items()))
        self.assertTrue(inputs['returns'].equals(before['returns']))
        self.assertTrue(inputs['nominal_prices'].equals(before['nominal_prices']))

    def test_source_drift_rejected(self):
        task, inputs = fixture()
        with patch.object(fractional, '_LOADED_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'source drift'):
                fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)

    def test_reconstruction_path_matches_full_and_uncertified_failure_propagates(self):
        task, inputs = fixture()
        minimize = full.probe.projection.minimize

        def force_failed_status(*arguments, **parameters):
            # A real optimizer vector with a deliberately failed status tests
            # recovery wiring; this is not evidence of a natural solver failure.
            proposal = minimize(*arguments, **parameters)
            proposal.success = False
            proposal.message = 'synthetic failed-status recovery wiring test'
            return proposal

        with patch.object(full.probe.projection, 'minimize', side_effect=force_failed_status):
            expected, _ = full_with_observed_windows(task, inputs)
            actual = fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)
        self.assertGreater(actual['projection_reconstruction_audit']['attempt_count'], 0)
        self.assertEqual(actual['projection_reconstruction_audit'], expected['projection_reconstruction_audit'])
        self.assertEqual(actual['result'], {key: expected[key] for key in actual['result']})
        with patch.object(full.probe.projection, 'minimize', side_effect=force_failed_status), \
                patch.object(full.probe, 'certify_projection_candidate', return_value={'certified': False}):
            with self.assertRaisesRegex(ValueError, 'independent original-contract certificate'):
                fractional.evaluate_non_equal_fractional(task=task, inputs=inputs)


if __name__ == '__main__': unittest.main()
