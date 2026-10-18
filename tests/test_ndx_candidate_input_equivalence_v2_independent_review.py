from copy import deepcopy
import tempfile
import unittest

from test_ndx_candidate_input_equivalence_research import fixture
from backtest import ndx_candidate_input_equivalence_v2_research as proof


class IndependentDependencyReview(unittest.TestCase):
    def test_v3_nominal_between_forward_windows_remains_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            for engine in sorted(proof.previous.ENGINES):
                original = fixture(directory, engine)
                original['inputs']['contract'].update(window_days=7, step_days=21)
                changed = deepcopy(original)
                changed['inputs']['nominal_prices'].iloc[75, 0] *= 1.2
                result = proof.compare_candidate_numerical_inputs(left=original, right=changed)
                self.assertNotIn(75, result['left']['dependency_row_offsets']['selected_forward'])
                self.assertEqual(result['numerical_input_equivalent'], engine != 'joint_weight_v3')
                if engine == 'joint_weight_v3':
                    self.assertIn(75, result['left']['dependency_row_offsets']['continuous_execution_nominal'])

    def test_prior_fit_history_retained_for_anchor_carry_and_next_turnover(self):
        with tempfile.TemporaryDirectory() as directory:
            for engine in ('joint_weight_v3', 'non_equal_fractional_v1'):
                original = fixture(directory, engine)
                changed = deepcopy(original)
                changed['inputs']['returns'].iloc[0, 0] += .02
                result = proof.compare_candidate_numerical_inputs(left=original, right=changed)
                self.assertFalse(result['numerical_input_equivalent'])
                self.assertIn(0, result['left']['dependency_row_offsets']['selected_fit'])
                self.assertFalse(result['result_reuse_authorized'])

    def test_ignored_prices_must_be_valid_and_runtime_incumbent_not_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            original = fixture(directory)
            invalid = deepcopy(original)
            invalid['inputs']['nominal_prices'].iloc[0, 4] = float('inf')
            with self.assertRaises(ValueError): proof.candidate_numerical_input_fingerprint(**invalid)
            runtime = deepcopy(original); runtime['runtime']['scipy'] += '-different'
            self.assertFalse(proof.compare_candidate_numerical_inputs(left=original, right=runtime)['numerical_input_equivalent'])
            benchmark = deepcopy(original)
            benchmark['inputs']['incumbent_weights'] = {'INC': .9, 'AAA': .1}
            self.assertFalse(proof.compare_candidate_numerical_inputs(left=original, right=benchmark)['numerical_input_equivalent'])


if __name__ == '__main__': unittest.main()
