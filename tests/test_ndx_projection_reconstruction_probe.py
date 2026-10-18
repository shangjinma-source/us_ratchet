import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import ndx_projection_reconstruction_probe as probe


class ReconstructionProbeIsolationTests(unittest.TestCase):
    def setUp(self):
        self.raw = pd.Series([.6, .2, .2], index=list('ABC'))
        self.parameters = dict(max_weight=.6, min_weight=.05,
                               top_weight_count=2, top_weight_cap=.9)
        self.original = pd.Series([.5, .25, .25], index=self.raw.index)
        self.proposal = SimpleNamespace(success=False, x=np.r_[self.original, np.zeros(4)], message='failed')

    def execute(self, modes, *, reconstruction=None, certificate=None):
        modes = iter(modes)
        self.returned = []

        def bind(function, **dependencies):
            if function is probe.projection.project_concentration_envelope_weights_v2:
                def solver(raw, **parameters):
                    mode = next(modes)
                    if mode == 'success':
                        return self.original
                    if mode == 'value_error':
                        raise ValueError('unrelated exception')
                    if mode == 'invalid_input':
                        raise probe.projection.ProjectionError('bad input')
                    dependencies['minimize']()
                    raise probe.projection.ProjectionError('Projection failed')
                return solver
            if function is probe.evaluator._SHRINKAGE:
                return dependencies['project_concentration_envelope_weights']
            if function is probe.evaluator._PORTFOLIO:
                return dependencies['constrained_fixed_shrinkage_weights']
            if function is probe.evaluator._EVALUATE:
                projected = dependencies['evaluate_synthetic_portfolio']
                def evaluate(task, **inputs):
                    for _ in range(task['calls']):
                        self.returned.append(projected(self.raw, **self.parameters))
                    return {'sentinel_economic_result': 42}
                return evaluate
            self.fail('Unexpected private binding edge')

        with ExitStack() as stack:
            stack.enter_context(patch.object(probe.evaluator, '_bind', side_effect=bind))
            self.minimize_mock = stack.enter_context(patch.object(probe.projection, 'minimize', return_value=self.proposal))
            self.reconstruct_mock = stack.enter_context(patch.object(probe, 'reconstruct_projection_candidate',
                return_value=reconstruction if reconstruction is not None else
                {'certified': True, 'weights': self.original.to_dict()}))
            self.certificate_mock = stack.enter_context(patch.object(probe, 'certify_projection_candidate',
                return_value=certificate if certificate is not None else {'certified': True}))
            return probe.evaluate_reconstructed({'calls': self.calls}, {})

    def test_original_success_is_returned_unchanged_without_reconstruction(self):
        self.calls = 1
        result = self.execute(['success'])
        self.assertIs(self.returned[0], self.original)
        self.assertEqual(result['result'], {'sentinel_economic_result': 42})
        self.assertEqual(result['reconstruction_attempts'], [])
        self.reconstruct_mock.assert_not_called()
        self.certificate_mock.assert_not_called()

    def test_uncertified_reconstruction_is_rejected(self):
        self.calls = 1
        with self.assertRaisesRegex(ValueError, 'was not certified'):
            self.execute(['failed'], reconstruction={'certified': False})
        self.certificate_mock.assert_not_called()

    def test_forged_certified_flag_does_not_bypass_independent_certificate(self):
        self.calls = 1
        with self.assertRaisesRegex(ValueError, 'independent original-contract'):
            self.execute(['failed'], certificate={'certified': False})
        self.certificate_mock.assert_called_once()
        pd.testing.assert_series_equal(self.certificate_mock.call_args.args[0], self.raw)
        self.assertEqual(self.certificate_mock.call_args.kwargs, self.parameters)

    def test_unrelated_exception_and_input_error_are_not_repaired(self):
        self.calls = 1
        for mode in ('value_error', 'invalid_input'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.execute([mode])
            self.reconstruct_mock.assert_not_called()

    def test_previous_failed_proposal_is_not_reused_for_next_input_error(self):
        self.calls = 2
        with self.assertRaisesRegex(probe.projection.ProjectionError, 'bad input'):
            self.execute(['failed', 'invalid_input'])
        self.reconstruct_mock.assert_called_once()
        self.minimize_mock.assert_called_once()

    def test_failed_proposal_shape_and_finiteness_are_checked(self):
        self.calls = 1
        for vector in (np.zeros(3), np.zeros(8), np.r_[np.nan, np.zeros(6)]):
            self.proposal.x = vector
            with self.subTest(shape=vector.shape), self.assertRaisesRegex(ValueError, 'Invalid failed optimizer proposal'):
                self.execute(['failed'])
            self.reconstruct_mock.assert_not_called()

    def test_successful_but_invalid_optimizer_point_is_not_repaired(self):
        self.calls = 1
        self.proposal.success = True
        with self.assertRaises(probe.projection.ProjectionError):
            self.execute(['failed'])
        self.reconstruct_mock.assert_not_called()

    def test_repaired_result_records_full_failed_vector_and_independent_certificate(self):
        self.calls = 1
        result = self.execute(['failed'])
        attempt = result['reconstruction_attempts'][0]
        self.assertEqual(attempt['failed_optimizer_vector'], self.proposal.x.tolist())
        self.assertIs(attempt['independent_certificate']['certified'], True)
        pd.testing.assert_series_equal(self.returned[0], self.original)

    def test_loaded_runner_source_mismatch_rejected_before_context_read(self):
        with patch.object(probe.runner, 'source_hashes', return_value={'changed': 'source'}), \
                patch.object(probe, 'Snapshot') as snapshot:
            with self.assertRaisesRegex(ValueError, 'sources changed since import'):
                probe.run('a' * 64, 'b' * 64)
            snapshot.assert_not_called()

    def test_loaded_research_source_mismatch_rejected_before_context_read(self):
        with patch.object(probe, 'LOADED_RESEARCH_SOURCES', {'changed': 'source'}), \
                patch.object(probe, 'Snapshot') as snapshot:
            with self.assertRaisesRegex(ValueError, 'sources changed since import'):
                probe.run('a' * 64, 'b' * 64)
            snapshot.assert_not_called()

    def test_loaded_evaluator_source_mismatch_rejected_before_context_read(self):
        with patch.object(probe.evaluator, 'source_hashes', return_value={'changed': 'source'}), \
                patch.object(probe, 'Snapshot') as snapshot:
            with self.assertRaisesRegex(ValueError, 'sources changed since import'):
                probe.run('a' * 64, 'b' * 64)
            snapshot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
