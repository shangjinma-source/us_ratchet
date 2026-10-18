from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_dynamic_refit_schedule_research import fixture
from test_ndx_corrected_explicit_path_research import seed_for
from backtest import ndx_corrected_explicit_path_research as m


class Tests(unittest.TestCase):
    def test_failed_memory_check_consumes_attempt_even_after_restoring_input(self):
        with tempfile.TemporaryDirectory() as directory:
            args=fixture(directory);seed=seed_for(args['decisions'][0])
            prepared=m._register(dict(calendar=deepcopy(args['calendar']),periods=deepcopy(args['decisions']),seed={'result':{'refit':seed}},
                bindings=[{'job_id':'original'}]),lambda extra:None)
            state=m._STATES[prepared];state['bindings'][0]['job_id']='another'
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaisesRegex(ValueError,'memory changed'):m.build_path_targets(prepared)
                state['bindings'][0]['job_id']='original'
                with self.assertRaisesRegex(ValueError,'already attempted'):m.build_path_targets(prepared)
                fit.assert_not_called()

    def test_second_target_cannot_claim_fill_based_or_reset_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            args=fixture(directory);seed=seed_for(args['decisions'][0])
            real=m.adapter.fitter.refit_dynamic_cutoff_weights
            def wrong_prior(**kwargs):
                self.assertEqual(kwargs['previous_target_weights'],{sid:.25 for sid in args['decisions'][0]['selected']})
                fitted=real(**kwargs);fitted['previous_target_weights']={};return fitted
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=wrong_prior) as fit:
                with self.assertRaises(m.schedule.RefitScheduleError) as caught:
                    m._run_targets(args['calendar'],args['decisions'],seed,m.schedule._verify)
                self.assertEqual(fit.call_count,1)
                self.assertFalse(caught.exception.audit['partial_schedule_returned'])
                self.assertFalse(caught.exception.audit['implicit_hold_or_cash_policy_applied'])

    def test_source_drift_during_second_fit_rejects_whole_path(self):
        with tempfile.TemporaryDirectory() as directory:
            args=fixture(directory);seed=seed_for(args['decisions'][0]);real=m.adapter.fitter.refit_dynamic_cutoff_weights
            source=Path(next(iter(args['decisions'][0]['source_hashes'])))
            self.assertTrue(source.is_relative_to(Path(directory)))
            def drift(**kwargs):
                value=real(**kwargs);source.write_text('independent simulated source drift');return value
            def full_verify(extra):
                return m.schedule._verify(m.schedule._merge(*(p['source_hashes'] for p in args['decisions']),extra))
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=drift) as fit:
                with self.assertRaises(ValueError):m._run_targets(args['calendar'],args['decisions'],seed,full_verify)
                self.assertEqual(fit.call_count,1)

    def test_late_invalid_cutoff_rejects_before_any_new_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            args=fixture(directory);seed=seed_for(args['decisions'][0]);periods=deepcopy(args['decisions'])
            periods[-1]['cutoff']=args['calendar'][-1]
            with patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(m.schedule.RefitScheduleError):m._run_targets(args['calendar'],periods,seed,m.schedule._verify)
                fit.assert_not_called()


if __name__=='__main__':unittest.main()
