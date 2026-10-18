"""Independent chronological, identity and source refusal checks for schedules."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest import ndx_dynamic_refit_schedule_research as builder


def fixture(directory):
    source = Path(directory) / 'explicit-synthetic-input-evidence.txt'
    source.write_text('synthetic schedule source')
    sources = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    parameters = dict(fit_days=126, shrinkage_intensity=.35, turnover_anchor_strength=.25,
        max_single_weight=.45, min_single_weight=.05, top_weight_cap=.8,
        minimum_effective_n_ratio=.7, risk_chain_top1_cap=.55)
    rows = []
    for index, (decision, execution, names) in enumerate((
            ('2024-01-31', '2024-02-01', 'ABCD'),
            ('2024-02-29', '2024-03-01', 'BCDE'),
            ('2024-03-27', '2024-03-28', 'ABDE'))):
        dates = pd.bdate_range(end=decision, periods=126)
        returns = pd.DataFrame(np.random.default_rng(index + 54).normal(.001, .01, (126, 5)),
            index=dates, columns=list('ABCDE'))
        selected = {'security:' + name: dict(ticker=name, issuer_id='issuer:' + name,
                    risk_chain='chain:' + name) for name in names}
        rows.append(dict(decision_date=decision, execution_date=execution, cutoff=decision,
            returns=returns, selected=selected,
            weight_spec='equal_weight' if index == 0 else 'constrained_fixed_shrinkage_turnover_anchor',
            parameters=dict(parameters), source_hashes=dict(sources)))
    calendar = [day.date().isoformat() for day in pd.bdate_range('2024-01-31', '2024-03-28')]
    return calendar, rows, source


class IndependentRefitScheduleTests(unittest.TestCase):
    def test_each_later_fit_receives_previous_target_and_new_sid_zero_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, _ = fixture(directory)
            original = builder.fitter.refit_dynamic_cutoff_weights
            calls, fitted = [], []
            def observe(**kwargs):
                calls.append(deepcopy({key: value for key, value in kwargs.items() if key != 'returns'}))
                result = original(**kwargs)
                fitted.append(deepcopy(result))
                return result
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=observe):
                result = builder.build_refit_schedule_research(calendar=calendar, decisions=rows)
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(result['schedule']), 3)
            self.assertIsNone(calls[0]['previous_target_weights'])
            for index in (1, 2):
                prior = {sid: value['target_weight'] for sid, value in fitted[index - 1]['targets'].items()}
                self.assertEqual(calls[index]['previous_target_weights'], prior)
            self.assertEqual(fitted[1]['surviving_anchor_mass'], .75)
            self.assertEqual(fitted[1]['anchor_by_security']['security:E'], 0.)
            for name in 'BCD':
                self.assertAlmostEqual(fitted[1]['anchor_by_security']['security:' + name], 1. / 3.)
            self.assertEqual(fitted[1]['effective_anchor_strength'], .25)

    def test_middle_fit_failure_never_skips_or_returns_partial_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, _ = fixture(directory)
            original = builder.fitter.refit_dynamic_cutoff_weights
            calls = []
            def fail_second(**kwargs):
                calls.append(kwargs['cutoff'])
                if len(calls) == 2:
                    raise RuntimeError('synthetic middle-date failure')
                return original(**kwargs)
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=fail_second):
                with self.assertRaises((ValueError, RuntimeError)):
                    builder.build_refit_schedule_research(calendar=calendar, decisions=rows)
            self.assertEqual(calls, ['2024-01-31', '2024-02-29'])

    def test_next_session_future_cutoff_issuer_change_and_risk_contract_change_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, baseline, _ = fixture(directory)
            for fault in ('late_execution', 'future_cutoff', 'issuer', 'risk_contract', 'missing_date', 'duplicate'):
                rows = deepcopy(baseline)
                if fault == 'late_execution': rows[0]['execution_date'] = '2024-02-02'
                if fault == 'future_cutoff': rows[0]['cutoff'] = '2024-02-01'
                if fault == 'issuer': rows[1]['selected']['security:B']['issuer_id'] = 'issuer:OTHER'
                if fault == 'risk_contract': rows[1]['parameters']['min_single_weight'] = .04
                if fault == 'missing_date': rows[1]['decision_date'] = '2024-02-28'
                if fault == 'duplicate': rows[1] = deepcopy(rows[0])
                with self.assertRaises((ValueError, RuntimeError), msg=fault):
                    builder.build_refit_schedule_research(calendar=calendar, decisions=rows)

    def test_drift_of_later_period_source_during_first_fit_aborts(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, source = fixture(directory)
            original = builder.fitter.refit_dynamic_cutoff_weights
            def drift(**kwargs):
                result = original(**kwargs)
                source.write_text('source drift after fit')
                return result
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=drift):
                with self.assertRaises(ValueError):
                    builder.build_refit_schedule_research(calendar=calendar, decisions=rows)

    def test_unrecognised_actual_holdings_or_checkpoint_input_not_silently_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, baseline, _ = fixture(directory)
            for field in ('actual_shares', 'previous_target_weights', 'checkpoint_weights'):
                rows = deepcopy(baseline)
                rows[1][field] = {'security:B': 1.}
                with self.assertRaises(ValueError, msg=field):
                    builder.build_refit_schedule_research(calendar=calendar, decisions=rows)

    def test_fitter_window_risk_identity_and_parameters_are_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, _ = fixture(directory)
            original = builder.fitter.refit_dynamic_cutoff_weights
            for fault in ('end', 'rows', 'risk_chain', 'parameters', 'anchor_mass', 'strength', 'false_passed_risks'):
                def corrupt(**kwargs):
                    result = original(**kwargs)
                    if fault == 'end': result['fit_end'] = '2024-01-30'
                    if fault == 'rows': result['fit_row_count'] = 125
                    if fault == 'risk_chain': result['risk_chains_by_security']['security:A'] = 'OTHER'
                    if fault == 'parameters': result['declared_parameters']['max_single_weight'] = 1.
                    if fault == 'anchor_mass': result['surviving_anchor_mass'] = .9
                    if fault == 'strength': result['effective_anchor_strength'] = .9
                    if fault == 'false_passed_risks':
                        for index, target in enumerate(result['targets'].values()):
                            target['target_weight'] = .7 if index == 0 else .1
                    return result
                with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=corrupt):
                    with self.assertRaises(ValueError, msg=fault):
                        builder.build_refit_schedule_research(calendar=calendar, decisions=rows)

    def test_same_sid_rename_preserves_prior_security_mass(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, _ = fixture(directory)
            rows = rows[:2]
            rows[1]['selected']['security:B']['ticker'] = 'Z'
            rows[1]['returns'] = rows[1]['returns'].rename(columns={'B': 'Z'})
            original = builder.fitter.refit_dynamic_cutoff_weights
            fitted = []
            def observe(**kwargs):
                result = original(**kwargs)
                fitted.append(deepcopy(result))
                return result
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=observe):
                result = builder.build_refit_schedule_research(calendar=calendar, decisions=rows)
            self.assertEqual(fitted[1]['surviving_anchor_mass'], .75)
            self.assertAlmostEqual(fitted[1]['anchor_by_security']['security:B'], 1. / 3.)
            self.assertEqual(result['schedule'][1]['targets']['security:B']['ticker'], 'Z')
            self.assertFalse(result['decision_ticker_authenticity_verified'])
            self.assertTrue(result['downstream_price_identity_bridge_required'])

    def test_no_surviving_sid_disables_anchor_without_inventing_old_holdings(self):
        with tempfile.TemporaryDirectory() as directory:
            calendar, rows, _ = fixture(directory)
            rows = rows[:2]
            rows[1]['returns'] = rows[1]['returns'].rename(columns=dict(zip('ABCDE', 'EFGHI')))
            rows[1]['selected'] = {'security:' + name: dict(ticker=name, issuer_id='issuer:' + name,
                risk_chain='chain:' + name) for name in 'EFGH'}
            original = builder.fitter.refit_dynamic_cutoff_weights
            fitted = []
            def observe(**kwargs):
                result = original(**kwargs)
                fitted.append(deepcopy(result))
                return result
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=observe):
                builder.build_refit_schedule_research(calendar=calendar, decisions=rows)
            self.assertEqual(fitted[1]['surviving_anchor_mass'], 0.)
            self.assertEqual(fitted[1]['effective_anchor_strength'], 0.)
            self.assertEqual(set(fitted[1]['previous_target_weights']), {'security:' + name for name in 'ABCD'})
            self.assertTrue(all(value == 0. for value in fitted[1]['anchor_by_security'].values()))


if __name__ == '__main__':
    unittest.main()
