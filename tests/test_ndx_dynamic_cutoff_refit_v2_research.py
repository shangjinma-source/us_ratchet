from copy import deepcopy
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_cutoff_refit_v2_research as refit
import test_ndx_dynamic_cutoff_refit_research as prior_tests


class CutoffRefitV2Tests(unittest.TestCase):
    def fixture(self):
        return prior_tests.CutoffRefitTests().fixture()

    def test_all_specs_match_original_when_no_recovery(self):
        for spec in ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'):
            arguments = self.fixture(); arguments['weight_spec'] = spec
            arguments['previous_target_weights'] = {'A': .2, 'B': .3, 'OLD': .5}
            old = refit.previous.refit_dynamic_cutoff_weights(**arguments)
            new = refit.refit_dynamic_cutoff_weights(**arguments)
            for key, value in old.items():
                if key not in ('schema', 'source_hashes'): self.assertEqual(new[key], value, key)
            self.assertEqual(new['projection_reconstruction_audit']['attempt_count'], 0)
            self.assertEqual(new['fit_end'], arguments['cutoff'])
            self.assertFalse(new['checkpoint_weights_used'])
            self.assertFalse(new['promotion_allowed'])

    def test_recovery_certificate_and_uncertified_fail_closed(self):
        minimize = refit.v3.probe.projection.minimize

        def fail_status(*args, **kwargs):
            proposal = minimize(*args, **kwargs)
            proposal.success = False
            proposal.message = 'synthetic failed status on optimizer vector'
            return proposal

        with patch.object(refit.v3.probe.projection, 'minimize', side_effect=fail_status):
            result = refit.refit_dynamic_cutoff_weights(**self.fixture())
        audit = result['projection_reconstruction_audit']
        self.assertEqual(audit['attempt_count'], 1)
        self.assertTrue(audit['attempts'][0]['independent_certificate']['certified'])
        with patch.object(refit.v3.probe.projection, 'minimize', side_effect=fail_status), \
             patch.object(refit.v3.probe, 'certify_projection_candidate', return_value={'certified': False}):
            with self.assertRaisesRegex(ValueError, 'independent original-contract certificate'):
                refit.refit_dynamic_cutoff_weights(**self.fixture())

    def test_latest_rows_anchor_identity_and_no_overlap(self):
        arguments = self.fixture(); arguments['previous_target_weights'] = {'A': .2, 'B': .3, 'OLD': .5}
        result = refit.refit_dynamic_cutoff_weights(**arguments)
        self.assertEqual(result['anchor_by_security'], {'A': .4, 'B': .6, 'C': 0., 'D': 0.})
        self.assertEqual(result['effective_anchor_strength'], .25)
        arguments['returns'].iloc[:-126] = .8
        repeated = refit.refit_dynamic_cutoff_weights(**arguments)
        self.assertEqual(repeated['targets'], result['targets'])
        self.assertEqual(repeated['fit_data_sha256'], result['fit_data_sha256'])
        arguments['previous_target_weights'] = {'OLD': 1.}
        self.assertEqual(refit.refit_dynamic_cutoff_weights(**arguments)['effective_anchor_strength'], 0.)

    def test_invalid_future_boolean_identity_and_source(self):
        for fault in ('future', 'bool', 'issuer'):
            arguments = self.fixture()
            if fault == 'future': arguments['cutoff'] = str(arguments['returns'].index[-2].date())
            if fault == 'bool': arguments['returns']['A'] = True
            if fault == 'issuer': arguments['selected']['B']['issuer_id'] = 'issuer:A'
            with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**arguments)
        with patch.object(refit, '_LOADED_SHA', '0' * 64):
            with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**self.fixture())

    def test_small_k_not_admitted_and_no_mutation(self):
        arguments = self.fixture(); before = deepcopy(arguments)
        globals_before = dict(refit.binding._SHRINKAGE.__globals__)
        refit.refit_dynamic_cutoff_weights(**arguments)
        self.assertTrue(arguments['returns'].equals(before['returns']))
        self.assertEqual(arguments['selected'], before['selected'])
        self.assertTrue(all(refit.binding._SHRINKAGE.__globals__[key] is value
                            for key, value in globals_before.items()))
        arguments['selected'] = {'A': arguments['selected']['A']}
        result = refit.refit_dynamic_cutoff_weights(**arguments)
        self.assertFalse(result['declared_constraints_passed'])
        self.assertTrue(result['single_name_projection_relaxed'])


if __name__ == '__main__': unittest.main()
