"""Independent refusal and complete-denominator checks for frontier refits."""
from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_frontier_cutoff_refit_research as runner
from test_ndx_frontier_cutoff_refit_research import fixture, run, write_report


class IndependentFrontierRefitReviewTests(unittest.TestCase):
    def test_every_fit_error_is_retained_and_never_classed_as_risk_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=RuntimeError('numeric failure')):
                result = run(path, prepared)
            self.assertEqual(result['counts']['candidate_count'], 2)
            self.assertEqual(len(result['results']), 2)
            self.assertEqual(result['counts']['fit_error_count'], 2)
            self.assertEqual(result['counts']['fitted_count'], 0)
            self.assertEqual(result['counts']['five_risk_fail_count'], 0)
            self.assertTrue(all(row['status'] == 'FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY' for row in result['results']))
            self.assertFalse(result['numerical_failure_is_economic_infeasibility'])
            self.assertFalse(result['promotion_allowed'])

    def test_corrupt_fitter_identity_cutoff_or_anchor_result_rejects_entire_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            original = runner.refit.refit_dynamic_cutoff_weights
            for fault in ('sid', 'issuer', 'ticker', 'fit_end', 'rows', 'anchor', 'checkpoint'):
                def corrupt(**kwargs):
                    result = original(**kwargs)
                    sid = next(iter(result['targets']))
                    if fault == 'sid': result['targets']['security:OTHER'] = result['targets'].pop(sid)
                    if fault == 'issuer': result['targets'][sid]['issuer_id'] = 'issuer:OTHER'
                    if fault == 'ticker': result['targets'][sid]['ticker'] = 'OTHER'
                    if fault == 'fit_end': result['fit_end'] = '2024-01-30'
                    if fault == 'rows': result['fit_row_count'] = 125
                    if fault == 'anchor': result['effective_anchor_strength'] = .25
                    if fault == 'checkpoint': result['checkpoint_weights_used'] = True
                    return result
                with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=corrupt):
                    with self.assertRaises(ValueError, msg=fault):
                        run(path, prepared)

    def test_fitter_source_failure_cannot_be_recorded_as_numeric_error(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            original_sources = runner.refit._sources()
            with patch.object(runner.refit, '_sources', side_effect=[original_sources, ValueError('source closure drift')]):
                with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=ValueError('source closure drift')):
                    with self.assertRaisesRegex(ValueError, 'source closure drift'):
                        run(path, prepared)

    def test_frontier_weight_payload_is_never_used_and_no_candidate_carries_prior_target(self):
        with tempfile.TemporaryDirectory() as directory:
            report, path, prepared = fixture(directory)
            # A bound report may carry unused fields, but they must never become
            # input weights or prior targets for this explicitly first fit.
            for key in ('risk_liquidity_frontier', 'user_preference_references'):
                for row in report['analysis'][key]:
                    row['checkpoint_weights'] = {'unrelated': 1.}
            write_report(path, report)
            original = runner.refit.refit_dynamic_cutoff_weights
            calls = []
            def observe(**kwargs):
                calls.append(deepcopy({key: value for key, value in kwargs.items() if key != 'returns'}))
                return original(**kwargs)
            with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=observe):
                result = run(path, prepared)
            self.assertEqual(len(calls), result['counts']['candidate_count'])
            for call in calls:
                self.assertIsNone(call['previous_target_weights'])
                for key in runner._PARAMETERS:
                    self.assertEqual(call[key], prepared['inputs']['contract'][key])
                self.assertNotIn('checkpoint_weights', call)
            self.assertFalse(result['previous_targets_carried_between_candidates'])


if __name__ == '__main__':
    unittest.main()
