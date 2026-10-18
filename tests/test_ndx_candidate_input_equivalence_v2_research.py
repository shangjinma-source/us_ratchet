from copy import deepcopy
import tempfile
import unittest

from test_ndx_candidate_input_equivalence_research import fixture
from backtest import ndx_candidate_input_equivalence_v2_research as proof


def evaluate(arguments):
    old = proof.previous
    if arguments['engine'] == 'equal_weight_fractional_v1':
        inputs = {key: value for key, value in arguments['inputs'].items() if key != 'nominal_prices'}
        return old.equal.evaluate_equal_weight_fractional_batch(
            combinations=[tuple(arguments['task']['tickers'].split(';'))], **inputs)
    if arguments['engine'] == 'non_equal_fractional_v1':
        return old.fractional.evaluate_non_equal_fractional(task=arguments['task'], inputs=arguments['inputs'])
    return old.joint.evaluate_joint_weight_task_v3(arguments['task'], **arguments['inputs'])


class WindowAwareEquivalenceTests(unittest.TestCase):
    def test_real_three_engines_incumbent_only_and_target_pre_forward_unused(self):
        with tempfile.TemporaryDirectory() as directory:
            for engine in sorted(proof.previous.ENGINES):
                old = fixture(directory, engine)
                changed = deepcopy(old)
                changed['inputs']['returns'].iloc[0, 4] += .3
                changed['inputs']['target_returns'].iloc[0] += .4
                result = proof.compare_candidate_numerical_inputs(left=old, right=changed)
                self.assertTrue(result['numerical_input_equivalent'], engine)
                self.assertFalse(result['v1_conservative_projection_equal'])
                self.assertEqual(evaluate(old), evaluate(changed), engine)
                forward = deepcopy(old)
                forward['inputs']['returns'].iloc[70, 4] += .03
                self.assertFalse(proof.compare_candidate_numerical_inputs(left=old, right=forward)['numerical_input_equivalent'])
                self.assertNotEqual(evaluate(old), evaluate(forward), engine)

    def test_selected_goog_fit_used_only_by_fitting_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            for engine in sorted(proof.previous.ENGINES):
                old = fixture(directory, engine)
                old['inputs']['returns'] = old['inputs']['returns'].rename(columns={'AAA': 'GOOG'})
                old['inputs']['nominal_prices'] = old['inputs']['nominal_prices'].rename(columns={'AAA': 'GOOG'})
                old['inputs']['universe'].loc[0, 'ticker'] = 'GOOG'
                old['task']['tickers'] = 'BBB;CCC;DDD;GOOG'
                changed = deepcopy(old)
                changed['inputs']['returns'].loc[changed['inputs']['returns'].index[0], 'GOOG'] += .3
                expected_equal = engine == 'equal_weight_fractional_v1'
                self.assertEqual(proof.compare_candidate_numerical_inputs(left=old, right=changed)['numerical_input_equivalent'], expected_equal)
                self.assertEqual(evaluate(old) == evaluate(changed), expected_equal)

    def test_v3_nominal_starts_at_first_forward_not_previous_close(self):
        with tempfile.TemporaryDirectory() as directory:
            for engine in sorted(proof.previous.ENGINES):
                old = fixture(directory, engine)
                changed = deepcopy(old)
                changed['inputs']['nominal_prices'].iloc[62, 0] *= 1.5
                self.assertTrue(proof.compare_candidate_numerical_inputs(left=old, right=changed)['numerical_input_equivalent'])
                self.assertEqual(evaluate(old), evaluate(changed))
                changed['inputs']['nominal_prices'].iloc[63, 0] *= 1.5
                expected_equal = engine != 'joint_weight_v3'
                self.assertEqual(proof.compare_candidate_numerical_inputs(left=old, right=changed)['numerical_input_equivalent'], expected_equal)
                self.assertEqual(evaluate(old) == evaluate(changed), expected_equal)

    def test_unused_cells_still_require_full_legality_and_calendar_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            old = fixture(directory)
            changed = deepcopy(old)
            changed['inputs']['returns'].iloc[0, 4] = float('nan')
            with self.assertRaises(ValueError): proof.candidate_numerical_input_fingerprint(**changed)
            result = proof.candidate_numerical_input_fingerprint(**old)
            self.assertEqual(len(result['payload']['full_calendar']), 105)
            self.assertEqual(result['dependency_row_offsets']['selected_fit'], [])
            self.assertFalse(result['result_reuse_authorized'])


if __name__ == '__main__':
    unittest.main()
