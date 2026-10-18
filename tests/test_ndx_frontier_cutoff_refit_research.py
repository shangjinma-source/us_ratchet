from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from scripts import ndx_frontier_cutoff_refit_research as runner
import test_ndx_combined_fractional_frontier_research as frontier_tests


def fixture(directory):
    date = frontier_tests.fixture(2)
    tickers = ['A1', 'AMAT', 'AVGO', 'CDNS', 'GOOG']
    dates = pd.bdate_range(end='2024-01-31', periods=126)
    returns = pd.DataFrame(np.random.default_rng(11).normal(.001, .01, (126, 5)), index=dates, columns=tickers)
    contract = dict(date['training_semantics']['payload']['contract'], fit_days=126, shrinkage_intensity=.35,
                    turnover_anchor_strength=.25, min_single_weight=.05)
    inputs = dict(returns=returns, nominal_prices=(1. + returns).cumprod() * 100.,
        target_returns=pd.Series(.001, index=dates), contract=contract, incumbent_weights={'AMAT': 1.},
        universe=pd.DataFrame([dict(ticker=ticker, security_id='security:' + ticker, issuer_id='issuer:' + ticker,
            risk_chain='chain:' + ticker) for ticker in tickers]))
    semantic = runner.semantics.training_semantics(inputs=inputs, decision_data_end='2024-01-31',
        source_batch='SYNTHETIC', universe_track='strict_technology')
    date['training_semantics'] = semantic
    date['expected_date']['training_semantics_sha256'] = semantic['training_semantics_sha256']
    for row in date['records']:
        row['training_semantics_sha256'] = semantic['training_semantics_sha256']
    date['records'][1]['task']['weight_spec'] = 'constrained_fixed_shrinkage_turnover_anchor'
    date['records'][1]['result']['weight_spec'] = 'constrained_fixed_shrinkage_turnover_anchor'
    date['records'][1]['origin'] = 'NON_EQUAL_BASE'
    date['counts']['EQUAL_WEIGHT_BASE'] = dict(planned=1, observed=1, evaluated=1)
    date['counts']['NON_EQUAL_BASE'] = dict(planned=1, observed=1, evaluated=1)
    analysis = frontier_tests.frontier.analyze_combined_date(date)
    source = Path(directory) / 'prices-evidence.txt'
    source.write_text('synthetic source data')
    sources = {str(source): hashlib.sha256(source.read_bytes()).hexdigest()}
    report = dict(schema='ndx_combined_fractional_frontier_report_v1', analysis=analysis, source_hashes=sources,
        records_sha256='a' * 64, training_rerun=False, cutoff_refit_performed=False,
        execution_performed=False, point_in_time_verified=False, promotion_allowed=False)
    path = Path(directory) / 'frontier.json'
    write_report(path, report)
    prepared = dict(inputs=inputs, training_semantics=semantic, source_hashes=sources)
    return report, path, prepared


def write_report(path, report):
    raw = json.dumps(report, allow_nan=False).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def run(path, prepared):
    with patch.object(runner.preparation, 'prepare_equal_base_date', return_value=prepared):
        return runner.run_date(frontier_path=path, frontier_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               selection_date='2024-02-01')


class FrontierCutoffRefitTests(unittest.TestCase):
    def test_real_fitter_complete_denominator_identity_no_prior_anchor_and_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            report, path, prepared = fixture(directory)
            original = deepcopy(prepared)
            result = run(path, prepared)
            self.assertEqual(result['counts']['candidate_count'], 2)
            self.assertEqual(result['counts']['fitted_count'], 2)
            self.assertEqual(result['counts']['user_preference_count'], 1)
            self.assertEqual(result['counts']['risk_liquidity_frontier_count'], 2)
            self.assertEqual(result['counts']['fit_error_count'], 0)
            self.assertEqual(result['historical_cutoff'], '2024-01-31')
            self.assertEqual(result['latest_archived_selection_date'], '2024-02-01')
            self.assertFalse(result['promotion_allowed'])
            self.assertFalse(result['execution_performed'])
            self.assertFalse(result['checkpoint_weights_used'])
            self.assertTrue(prepared['inputs']['returns'].equals(original['inputs']['returns']))
            self.assertEqual(prepared['training_semantics'], original['training_semantics'])
            for row in result['results']:
                fitted = row['refit']
                self.assertEqual(fitted['effective_anchor_strength'], 0.)
                self.assertEqual(fitted['previous_target_weights'], {})
                self.assertEqual(fitted['fit_row_count'], 126)
                self.assertEqual(fitted['fit_end'], '2024-01-31')
                self.assertEqual(len(fitted['declared_constraint_checks']), 5)
                self.assertEqual(fitted['declared_parameters']['turnover_anchor_strength'], .25)
                self.assertEqual(fitted['risk_chains_by_security'],
                    {sid: item['risk_chain'] for sid, item in row['selected_identity'].items()})
            self.assertEqual(result['results'][0]['roles'], ['RISK_LIQUIDITY_FRONTIER', 'USER_PREFERENCE_REFERENCE'])
            json.dumps(result, allow_nan=False)

    def test_fit_exception_retained_separately_from_five_risk_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            original = runner.refit.refit_dynamic_cutoff_weights

            def fail_one(**kwargs):
                if kwargs['weight_spec'] != 'equal_weight':
                    raise ValueError('synthetic uncertified projection')
                return original(**kwargs)

            with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=fail_one):
                result = run(path, prepared)
            self.assertEqual(result['counts']['fit_error_count'], 1)
            failed = result['results'][1]
            self.assertEqual(failed['status'], 'FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY')
            self.assertIsNone(failed['refit'])
            self.assertFalse(failed['numerical_failure_is_economic_infeasibility'])

    def test_risk_failure_is_explicit_and_does_not_drop_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            report, path, prepared = fixture(directory)
            prepared['inputs']['contract']['min_single_weight'] = .3
            semantic = runner.semantics.training_semantics(inputs=prepared['inputs'], decision_data_end='2024-01-31',
                source_batch='SYNTHETIC', universe_track='strict_technology')
            prepared['training_semantics'] = semantic
            report['analysis']['expected_date']['training_semantics_sha256'] = semantic['training_semantics_sha256']
            write_report(path, report)
            result = run(path, prepared)
            preference = result['results'][0]
            self.assertEqual(preference['status'], 'FITTED_FIVE_RISKS_FAILED')
            self.assertIn('MIN_SINGLE_WEIGHT', preference['failed_risk_checks'])
            self.assertEqual(result['counts']['candidate_count'], 2)

    def test_missing_or_conflicting_frontier_denominator_scope_and_date_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, path, prepared = fixture(directory)
            for fault in ('missing', 'conflict', 'scope', 'date', 'duplicate', 'preference'):
                report = json.loads(json.dumps(baseline))
                analysis = report['analysis']
                if fault == 'missing': analysis['risk_liquidity_frontier'].pop()
                if fault == 'conflict': analysis['user_preference_references'][0]['origin'] = 'DELTA'
                if fault == 'scope': analysis['risk_liquidity_frontier'][0]['technology_scope_passed'] = True
                if fault == 'date': analysis['expected_date']['selection_date'] = '2024-02-02'
                if fault == 'duplicate': analysis['risk_liquidity_frontier'][1] = deepcopy(analysis['risk_liquidity_frontier'][0])
                if fault == 'preference': analysis['user_preference_references'] = []
                write_report(path, report)
                with self.assertRaises(ValueError, msg=fault): run(path, prepared)

    def test_changed_inputs_even_rehashed_semantics_and_missing_contract_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            for fault in ('returns', 'universe', 'contract'):
                changed = deepcopy(prepared)
                if fault == 'returns': changed['inputs']['returns'].iloc[-1, 0] += .01
                if fault == 'universe': changed['inputs']['universe'].loc[0, 'issuer_id'] = 'issuer:OTHER'
                if fault == 'contract': changed['inputs']['contract'].pop('fit_days')
                changed['training_semantics'] = runner.semantics.training_semantics(inputs=changed['inputs'],
                    decision_data_end='2024-01-31', source_batch='SYNTHETIC', universe_track='strict_technology')
                with self.assertRaises(ValueError, msg=fault): run(path, changed)

    def test_source_drift_during_fit_not_swallowed_as_numeric_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            original = runner.refit.refit_dynamic_cutoff_weights
            source = Path(next(iter(prepared['source_hashes'])))

            def drift(**kwargs):
                source.write_text('changed')
                return original(**kwargs)

            with patch.object(runner.refit, 'refit_dynamic_cutoff_weights', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'Source closure differs'): run(path, prepared)

    def test_create_only_output_readback_and_outside_research_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            _, path, prepared = fixture(directory)
            result = run(path, prepared)
            with patch.object(runner, 'ROOT', Path(directory)):
                output = Path(directory) / 'data/cache/research/result.json'
                digest = runner.save_new(result, output)
                self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), digest)
                self.assertEqual(json.loads(output.read_text())['counts'], result['counts'])
                with self.assertRaises(FileExistsError): runner.save_new(result, output)
                with self.assertRaises(ValueError): runner.save_new(result, Path(directory) / 'config.json')


if __name__ == '__main__':
    unittest.main()
