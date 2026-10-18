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
    source = Path(directory) / 'synthetic-input.txt'
    source.write_text('synthetic independent inputs')
    sources = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    calendar = ['2024-01-31', '2024-02-01', '2024-02-02', '2024-02-05', '2024-02-06', '2024-02-07']
    decisions = []
    for index, tickers in zip((0, 2, 4), ('ABCD', 'ABCDE', 'FGHIJ')):
        day = calendar[index]
        values = np.random.default_rng(903).normal(.001, .01, (150, len(tickers)))
        selected = {'security:' + ticker: dict(ticker=ticker, issuer_id='issuer:' + ticker,
                     risk_chain='chain:' + ticker) for ticker in tickers}
        decisions.append(dict(decision_date=day, execution_date=calendar[index+1], cutoff=day,
            returns=pd.DataFrame(values, columns=list(tickers), index=pd.bdate_range(end=day, periods=150)),
            selected=selected, weight_spec='constrained_fixed_shrinkage_turnover_anchor',
            parameters=dict(fit_days=126, shrinkage_intensity=.35, turnover_anchor_strength=.25,
                max_single_weight=.45, min_single_weight=.05, top_weight_cap=.80,
                minimum_effective_n_ratio=.70, risk_chain_top1_cap=.55), source_hashes=dict(sources)))
    decisions[0]['weight_spec'] = 'equal_weight'
    return dict(calendar=calendar, decisions=decisions)


class DynamicRefitScheduleTests(unittest.TestCase):
    def test_original_risk_contract_k4_to5_entry_and_no_overlap_anchor(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            original = deepcopy(args)
            result = builder.build_refit_schedule_research(**args)
            self.assertEqual([len(row['targets']) for row in result['schedule']], [4, 5, 5])
            self.assertEqual(result['decision_count'], 3)
            self.assertIsNone(result['refits'][0]['previous_schedule_target_by_security'])
            second = result['refits'][1]['result']
            self.assertEqual(second['previous_target_weights'], {key: .25 for key in args['decisions'][0]['selected']})
            self.assertEqual(second['anchor_by_security']['security:E'], 0.)
            self.assertEqual(second['surviving_anchor_mass'], 1.)
            self.assertEqual(second['effective_anchor_strength'], .25)
            third = result['refits'][2]['result']
            self.assertEqual(third['surviving_anchor_mass'], 0.)
            self.assertEqual(third['effective_anchor_strength'], 0.)
            self.assertTrue(third['previous_target_weights'])
            self.assertTrue(all(row['result']['declared_constraints_passed'] for row in result['refits']))
            self.assertTrue(all(len(row['result']['declared_constraint_checks']) == 5 for row in result['refits']))
            self.assertFalse(result['anchor_uses_actual_fills_or_holdings'])
            self.assertFalse(result['promotion_allowed'])
            for old, new in zip(original['decisions'], args['decisions']):
                self.assertEqual(old['selected'], new['selected'])
                self.assertTrue(old['returns'].equals(new['returns']))

    def test_sid_rename_preserves_anchor_and_issuer_change_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            period = args['decisions'][1]
            period['selected']['security:A']['ticker'] = 'X'
            period['returns'].rename(columns={'A': 'X'}, inplace=True)
            result = builder.build_refit_schedule_research(**args)
            self.assertEqual(result['schedule'][1]['targets']['security:A']['ticker'], 'X')
            self.assertEqual(result['refits'][1]['result']['anchor_by_security']['security:A'], .25)
            self.assertFalse(result['decision_ticker_authenticity_verified'])
            period['selected']['security:A']['issuer_id'] = 'issuer:OTHER'
            with self.assertRaisesRegex(builder.RefitScheduleError, 'Permanent SID issuer'):
                builder.build_refit_schedule_research(**args)

    def test_midpath_five_risk_failure_rejects_all_without_later_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            args['decisions'][1]['selected'] = {'security:A': args['decisions'][1]['selected']['security:A']}
            args['decisions'][1]['weight_spec'] = 'equal_weight'
            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights',
                              wraps=builder.fitter.refit_dynamic_cutoff_weights) as fit:
                with self.assertRaises(builder.RefitScheduleError) as caught:
                    builder.build_refit_schedule_research(**args)
            self.assertEqual(fit.call_count, 2)
            self.assertEqual(caught.exception.audit['stage'], 'ORIGINAL_FIVE_RISKS_FAILED')
            self.assertFalse(caught.exception.audit['partial_schedule_returned'])
            self.assertIn('SECURITY_TOP3_WEIGHT', caught.exception.audit['detail'])

    def test_fit_error_rejects_entire_schedule_without_economic_infeasibility_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            original = builder.fitter.refit_dynamic_cutoff_weights

            def fail_middle(**kwargs):
                if kwargs['cutoff'] == '2024-02-02':
                    raise ValueError('synthetic numerical error')
                return original(**kwargs)

            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=fail_middle):
                with self.assertRaises(builder.RefitScheduleError) as caught:
                    builder.build_refit_schedule_research(**args)
            self.assertEqual(caught.exception.audit['stage'], 'REFIT_ERROR_NOT_ECONOMIC_INFEASIBILITY')

    def test_explicit_dates_future_cutoff_non_next_and_injected_prior_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for fault in ('future', 'non_next', 'reorder', 'prior', 'risk_change', 'missing_parameter'):
                args = fixture(directory)
                if fault == 'future': args['decisions'][0]['cutoff'] = '2024-02-01'
                if fault == 'non_next': args['decisions'][0]['execution_date'] = '2024-02-02'
                if fault == 'reorder': args['decisions'].reverse()
                if fault == 'prior': args['decisions'][0]['previous_target_weights'] = {'security:A': 1.}
                if fault == 'risk_change': args['decisions'][1]['parameters']['max_single_weight'] = .5
                if fault == 'missing_parameter': del args['decisions'][1]['parameters']['fit_days']
                with self.assertRaises(ValueError, msg=fault): builder.build_refit_schedule_research(**args)

    def test_digest_covers_full_history_beyond_actual_fit_window(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            before = builder.build_refit_schedule_research(**args)
            args['decisions'][0]['returns'].iloc[0, 0] += .1
            after = builder.build_refit_schedule_research(**args)
            self.assertNotEqual(before['refits'][0]['input_sha256'], after['refits'][0]['input_sha256'])
            self.assertEqual(before['refits'][0]['result']['fit_data_sha256'], after['refits'][0]['result']['fit_data_sha256'])
            self.assertEqual(before['schedule'], after['schedule'])

    def test_bound_source_changes_during_fit_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory)
            source = Path(next(iter(args['decisions'][0]['source_hashes'])))
            original = builder.fitter.refit_dynamic_cutoff_weights

            def changed(**kwargs):
                result = original(**kwargs)
                source.write_text('changed')
                return result

            with patch.object(builder.fitter, 'refit_dynamic_cutoff_weights', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'source drift'):
                    builder.build_refit_schedule_research(**args)


if __name__ == '__main__':
    unittest.main()
