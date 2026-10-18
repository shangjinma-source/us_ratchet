from copy import deepcopy
import tempfile
import unittest
from unittest.mock import patch

from test_ndx_dynamic_refit_schedule_research import fixture
from backtest import ndx_corrected_explicit_path_research as m


def seed_for(period):
    return m.adapter.fitter.refit_dynamic_cutoff_weights(returns=period['returns'], cutoff=period['cutoff'],
        selected=period['selected'], weight_spec=period['weight_spec'], previous_target_weights=None,
        **period['parameters'])


class Tests(unittest.TestCase):
    def test_three_period_entry_exit_rename_and_seed_never_refits(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            periods = args['decisions']
            periods[1]['selected']['security:A']['ticker'] = 'RENAMED'
            periods[1]['returns'].rename(columns={'A':'RENAMED'}, inplace=True)
            seed = seed_for(periods[0])
            old_function = m.schedule.fitter.refit_dynamic_cutoff_weights
            with patch.object(m.adapter.fitter, 'refit_dynamic_cutoff_weights', wraps=old_function) as called:
                result = m._run_targets(args['calendar'], periods, seed, m.schedule._verify)
            self.assertEqual(called.call_count, 2)
            self.assertIs(m.schedule.fitter.refit_dynamic_cutoff_weights, old_function)
            second = result['refits'][1]['result']
            self.assertEqual(second['previous_target_weights'], {sid:.25 for sid in periods[0]['selected']})
            self.assertEqual(second['effective_anchor_strength'], .25)
            self.assertEqual(second['anchor_by_security']['security:E'], 0)
            self.assertEqual(result['refits'][2]['result']['surviving_anchor_mass'], 0)
            self.assertFalse(result['anchor_uses_actual_fills_or_holdings'])

    def test_invalid_all_path_checked_before_first_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory);seed = seed_for(args['decisions'][0])
            for kind in ('clock', 'issuer', 'risk'):
                periods = deepcopy(args['decisions'])
                if kind == 'clock': periods[1]['execution_date'] = args['calendar'][-1]
                if kind == 'issuer': periods[1]['selected']['security:A']['issuer_id'] = 'OTHER'
                if kind == 'risk': periods[1]['parameters']['min_single_weight'] = .06
                with self.subTest(kind=kind), patch.object(m.adapter.fitter, 'refit_dynamic_cutoff_weights') as called:
                    with self.assertRaises(m.schedule.RefitScheduleError):
                        m._run_targets(args['calendar'], periods, seed, m.schedule._verify, validate_only=True)
                    called.assert_not_called()

    def test_seed_matrix_or_parameters_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory);seed = seed_for(args['decisions'][0])
            for kind in ('matrix', 'parameter'):
                wrong = deepcopy(seed)
                if kind == 'matrix': wrong['fit_data_sha256'] = '0'*64
                else: wrong['declared_parameters']['shrinkage_intensity'] = .8
                with self.subTest(kind=kind), patch.object(m.adapter.fitter, 'refit_dynamic_cutoff_weights') as called:
                    with self.assertRaises(m.schedule.RefitScheduleError):
                        m._run_targets(args['calendar'], args['decisions'], wrong, m.schedule._verify)
                    called.assert_not_called()

    def test_failure_consumes_path_no_partial_no_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory);seed = seed_for(args['decisions'][0])
            args['decisions'][1]['selected'] = {'security:A':args['decisions'][1]['selected']['security:A']}
            args['decisions'][1]['weight_spec'] = 'equal_weight'
            def verify(extra):
                return m.schedule._verify(m.schedule._merge(args['decisions'][0]['source_hashes'], extra))
            prepared = m._register(dict(calendar=args['calendar'], periods=args['decisions'],
                seed={'result':{'refit':seed}}), verify)
            with self.assertRaises(m.schedule.RefitScheduleError) as caught:
                m.build_path_targets(prepared)
            self.assertFalse(caught.exception.audit['partial_schedule_returned'])
            with patch.object(m.adapter.fitter, 'refit_dynamic_cutoff_weights') as called:
                with self.assertRaisesRegex(ValueError, 'already attempted'):
                    m.build_path_targets(prepared)
                called.assert_not_called()

    def test_prepared_copied_matrix_seed_and_calendar_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory);seed = seed_for(args['decisions'][0])
            for kind in ('matrix','seed','calendar'):
                prepared = m._register(dict(calendar=deepcopy(args['calendar']), periods=deepcopy(args['decisions']),
                    seed={'result':{'refit':deepcopy(seed)}}), lambda extra: None)
                state = m._STATES[prepared]
                if kind == 'matrix':state['periods'][1]['returns'].iloc[-1,0] += .1
                if kind == 'seed':state['seed']['result']['refit']['targets']['security:A']['target_weight'] = .3
                if kind == 'calendar':state['calendar'].pop()
                with self.subTest(kind=kind), patch.object(m.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                    with self.assertRaisesRegex(ValueError,'memory changed'):m.build_path_targets(prepared)
                    fit.assert_not_called()

    def test_calendar_full_hard_observation_required(self):
        value={'schema':'EXPLICIT_OBSERVED_EXECUTION_CALENDAR_V1','source':m.CALENDAR_SOURCE,
               'calendar':['2023-03-31','2023-04-03']}
        parent={'execution':{'daily':[{'session':d} for d in value['calendar']]}}
        with patch.object(m,'_read',return_value=parent):
            self.assertEqual(m._calendar(value),value['calendar'])
            value['calendar']=['2023-03-31']
            with self.assertRaisesRegex(ValueError,'without compression'):m._calendar(value)

    def test_prepare_validation_does_not_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            with patch.object(m.adapter.fitter, 'refit_dynamic_cutoff_weights') as called:
                self.assertIsNone(m._run_targets(args['calendar'], args['decisions'], None,
                    m.schedule._verify, validate_only=True))
                called.assert_not_called()


if __name__ == '__main__': unittest.main()
