"""Refit a complete bound research frontier at its cutoff without selecting it."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_dynamic_cutoff_refit_v2_research as refit
from backtest import ndx_dynamic_training_semantics as semantics
from scripts import ndx_combined_fractional_frontier as frontier_report
from scripts import ndx_equal_weight_base_inputs as preparation

_PARAMETERS = ('fit_days', 'shrinkage_intensity', 'turnover_anchor_strength', 'max_single_weight',
               'min_single_weight', 'top_weight_cap', 'minimum_effective_n_ratio', 'risk_chain_top1_cap')
_CHECKS = ('MAX_SINGLE_WEIGHT', 'MIN_SINGLE_WEIGHT', 'SECURITY_TOP3_WEIGHT',
           'MINIMUM_EFFECTIVE_N', 'RISK_CHAIN_TOP1_WEIGHT')
_POLICY = 'FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC'
_LOADED = {str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
           for module in (refit, semantics, frontier_report, preparation)}
_LOADED[str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_LOADED = frontier_report.combined._merge_sources(_LOADED, frontier_report.LOADED, preparation._LOADED)


def _verify(sources):
    if type(sources) is not dict or not sources:
        raise ValueError('Nonempty bound source closure required')
    for path, digest in sources.items():
        if (type(path) is not str or not Path(path).is_absolute() or type(digest) is not str
                or re.fullmatch('[0-9a-f]{64}', digest) is None):
            raise ValueError('Canonical absolute source and SHA256 required')
    frontier_report.combined._check_sources(sources)


def _candidates(report, selection_date):
    if (report.get('schema') != 'ndx_combined_fractional_frontier_report_v1'
            or any(report.get(key) is not False for key in
                   ('training_rerun', 'cutoff_refit_performed', 'execution_performed', 'point_in_time_verified', 'promotion_allowed'))):
        raise ValueError('Bound fractional frontier research report required')
    analysis = report['analysis']
    if (analysis.get('schema') != 'ndx_combined_fractional_frontier_research_v1'
            or analysis.get('technology_scope_status') != 'UNRESOLVED_CURRENT_PURE_TECH_DEFINITION'
            or analysis.get('whole_lot_status') != 'NOT_EVALUATED'
            or any(analysis.get(key) is not False for key in
                   ('technology_scope_verified', 'execution_performed', 'saved_weights_are_execution_targets',
                    'point_in_time_verified', 'promotion_allowed', 'global_optimum_proven', 'unique_selection_performed'))):
        raise ValueError('Unchanged research-only frontier contract required')
    expected = analysis['expected_date']
    if (type(expected.get('expected_task_count')) is not int or expected['expected_task_count'] < 1
            or any(type(analysis['counts'].get(key)) is not int
                   or analysis['counts'][key] != expected['expected_task_count']
                   for key in ('expected_task_count', 'evaluated_count'))
            or type(report.get('records_sha256')) is not str
            or re.fullmatch('[0-9a-f]{64}', report['records_sha256']) is None):
        raise ValueError('Complete original frontier denominator and records SHA required')
    frontier_report.combined.select_research_lane(expected_dates=[dict(expected, expected_task_count=0)],
                                                 records=[], policy_role='RETURN')
    if expected['selection_date'] != selection_date:
        raise ValueError('Requested date differs from bound frontier')
    groups = (('RISK_LIQUIDITY_FRONTIER', 'risk_liquidity_frontier', 'risk_liquidity_frontier_count'),
              ('USER_PREFERENCE_REFERENCE', 'user_preference_references', 'user_preference_count'))
    candidates = {}
    for role, key, count_key in groups:
        rows = analysis[key]
        if (type(rows) is not list or type(analysis['counts'][count_key]) is not int
                or len(rows) != analysis['counts'][count_key] or len(rows) > expected['expected_task_count']):
            raise ValueError('Incomplete frontier/reference denominator')
        seen = set()
        for row in rows:
            job = row['job_id']
            if type(job) is not str or not job or job != job.strip() or job in seen:
                raise ValueError('Missing or duplicate frontier job identity')
            seen.add(job)
            if row.get('technology_scope_passed', 'MISSING') is not None:
                raise ValueError('Unresolved scope was upgraded')
            if role == 'RISK_LIQUIDITY_FRONTIER' and any(row.get(gate) is not True for gate in
                    ('fractional_risk_passed', 'liquidity_passed', 'fractional_risk_liquidity_passed')):
                raise ValueError('Invalid risk/liquidity frontier member')
            if role == 'USER_PREFERENCE_REFERENCE' and (row.get('user_preference_reference') is not True
                    or set(row['tickers'].split(';')) != {'AMAT', 'AVGO', 'CDNS', 'GOOG'}
                    or row['weight_spec'] != 'equal_weight'):
                raise ValueError('Invalid user preference reference')
            if job in candidates:
                if candidates[job]['candidate'] != row:
                    raise ValueError('Conflicting duplicate reference candidate')
                candidates[job]['roles'].append(role)
            else:
                candidates[job] = dict(candidate=deepcopy(row), roles=[role])
    if len(analysis['user_preference_references']) != 1:
        raise ValueError('Exactly one explicit user preference reference required')
    definitions = set()
    for entry in candidates.values():
        row = entry['candidate']
        names = row['tickers'].split(';')
        if (type(row['holding_count']) is not int or row['holding_count'] != len(names)
                or len(set(names)) != len(names)
                or any(not name or name != name.strip().upper() for name in names)
                or row['weight_spec'] not in ('equal_weight', 'constrained_fixed_shrinkage',
                                             'constrained_fixed_shrinkage_turnover_anchor')):
            raise ValueError('Invalid frontier portfolio identity')
        definition = (tuple(sorted(names)), row['weight_spec'])
        if definition in definitions:
            raise ValueError('Duplicate frontier portfolio under different job IDs')
        definitions.add(definition)
    return expected, [candidates[job] for job in sorted(candidates)]


def _identity_map(universe):
    columns = ('ticker', 'security_id', 'issuer_id', 'risk_chain')
    if (not isinstance(universe, pd.DataFrame) or universe.empty or not universe.columns.is_unique
            or not set(columns).issubset(universe.columns)):
        raise ValueError('Explicit training identity universe required')
    rows = universe[list(columns)].to_dict('records')
    for row in rows:
        if (any(type(value) is not str or not value or value != value.strip() for value in row.values())
                or row['ticker'] != row['ticker'].upper()
                or not row['security_id'].startswith('security:') or not row['issuer_id'].startswith('issuer:')):
            raise ValueError('Noncanonical training identity')
    if len({row['ticker'] for row in rows}) != len(rows) or len({row['security_id'] for row in rows}) != len(rows):
        raise ValueError('Ambiguous ticker/security mapping')
    return {row['ticker']: row for row in rows}


def run_date(*, frontier_path, frontier_sha256, selection_date):
    """Perform independent first-decision fits for every member, with no winner."""
    _verify(_LOADED)
    if type(frontier_sha256) is not str or re.fullmatch('[0-9a-f]{64}', frontier_sha256) is None:
        raise ValueError('Exact frontier SHA256 required')
    path = Path(frontier_path).resolve()
    report = frontier_report.read_bound(path, frontier_sha256)
    expected, candidates = _candidates(report, selection_date)
    _verify(report['source_hashes'])
    coordinate = {key: expected[key] for key in ('source_batch', 'universe_track', 'selection_date')}
    prepared = preparation.prepare_equal_base_date(**coordinate)
    inputs = prepared['inputs']
    checked_semantics = semantics.training_semantics(inputs=inputs, decision_data_end=expected['decision_data_end'],
        source_batch=expected['source_batch'], universe_track=expected['universe_track'])
    if (checked_semantics != prepared['training_semantics']
            or checked_semantics['training_semantics_sha256'] != expected['training_semantics_sha256']):
        raise ValueError('Prepared inputs differ from bound frontier training semantics')
    parameters = {key: inputs['contract'][key] for key in _PARAMETERS}
    if type(parameters['fit_days']) is not int or parameters['fit_days'] < 20:
        raise ValueError('Explicit valid fit_days required')
    numeric_parameters = {key: refit.previous._number(value) for key, value in parameters.items() if key != 'fit_days'}
    if (not all(0 <= value <= 1 for value in numeric_parameters.values())
            or numeric_parameters['min_single_weight'] > numeric_parameters['max_single_weight']
            or numeric_parameters['risk_chain_top1_cap'] <= 0
            or len(inputs['returns']) < parameters['fit_days'] or (inputs['returns'] <= -1.).any().any()):
        raise ValueError('Invalid original fit contract or return history')
    identities = _identity_map(inputs['universe'])
    selections = []
    for entry in candidates:
        selected = {}
        for ticker in entry['candidate']['tickers'].split(';'):
            if ticker not in identities:
                raise ValueError('Frontier ticker missing from training universe')
            row = identities[ticker]
            selected[row['security_id']] = {key: row[key] for key in ('ticker', 'issuer_id', 'risk_chain')}
        if len({row['issuer_id'] for row in selected.values()}) != len(selected):
            raise ValueError('Duplicate issuer inside candidate')
        selections.append(selected)
    fit_sources = refit._sources()
    sources = frontier_report.combined._merge_sources(_LOADED, report['source_hashes'], prepared['source_hashes'],
        fit_sources, {str(path): frontier_sha256})
    _verify(sources)
    results = []
    for index, (entry, selected) in enumerate(zip(candidates, selections), 1):
        row = dict(entry, selected_identity=selected, diagnostic_policy=_POLICY,
                   previous_target_weights=None, effective_anchor_strength=0.,
                   technology_scope_verified=False, promotion_allowed=False)
        try:
            fitted = refit.refit_dynamic_cutoff_weights(returns=inputs['returns'], cutoff=expected['decision_data_end'],
                selected=selected, weight_spec=entry['candidate']['weight_spec'], previous_target_weights=None, **parameters)
        except (ValueError, ArithmeticError, RuntimeError) as error:
            row.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY', refit=None,
                       error_type=type(error).__name__, error=str(error), numerical_failure_is_economic_infeasibility=False)
        else:
            if (fitted['source_hashes'] != fit_sources or fitted['cutoff'] != expected['decision_data_end']
                    or fitted['fit_end'] != expected['decision_data_end'] or fitted['fit_row_count'] != parameters['fit_days']
                    or fitted['checkpoint_weights_used'] is not False or fitted['previous_target_weights'] != {}
                    or fitted['effective_anchor_strength'] != 0. or fitted['surviving_anchor_mass'] != 0.
                    or set(fitted['targets']) != set(selected)
                    or any(fitted['targets'][sid][key] != selected[sid][key]
                           for sid in selected for key in ('ticker', 'issuer_id'))
                    or fitted['risk_chains_by_security'] != {sid: value['risk_chain'] for sid, value in selected.items()}):
                raise ValueError('Unexpected cutoff refit identity or first-decision semantics')
            checks = fitted['declared_constraint_checks']
            if (set(checks) != set(_CHECKS) or any(type(value) is not bool for value in checks.values())
                    or type(fitted['declared_constraints_passed']) is not bool
                    or fitted['declared_constraints_passed'] != all(checks.values())):
                raise ValueError('Invalid five-risk refit result')
            row.update(status='FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED',
                       refit={key: value for key, value in fitted.items() if key != 'source_hashes'},
                       failed_risk_checks=[key for key, value in checks.items() if not value])
        finally:
            _verify(_LOADED)
            if refit._sources() != fit_sources:
                raise ValueError('Cutoff fitter source closure changed')
        results.append(row)
        if index == 1 or index % 25 == 0 or index == len(candidates):
            logging.info('Latest-cutoff refit %s %d/%d status=%s', selection_date, index, len(candidates), row['status'])
    _verify(sources)
    statuses = Counter(row['status'] for row in results)
    return dict(schema='ndx_frontier_cutoff_refit_research_v1', expected_date=dict(expected),
        latest_archived_selection_date=selection_date, historical_cutoff=expected['decision_data_end'],
        cutoff_scope='EXPLICIT_ARCHIVED_HISTORICAL_DATE_NOT_CURRENT_LIVE_AS_OF_DATE',
        training_semantics=checked_semantics, source_hashes=sources, frontier_path=str(path), frontier_sha256=frontier_sha256,
        records_sha256=report['records_sha256'], diagnostic_policy=_POLICY, declared_fit_parameters=parameters,
        counts=dict(candidate_count=len(candidates), fitted_count=statuses['FITTED_FIVE_RISKS_PASSED'] + statuses['FITTED_FIVE_RISKS_FAILED'],
            five_risk_pass_count=statuses['FITTED_FIVE_RISKS_PASSED'], five_risk_fail_count=statuses['FITTED_FIVE_RISKS_FAILED'],
            fit_error_count=statuses['FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY'],
            risk_liquidity_frontier_count=report['analysis']['counts']['risk_liquidity_frontier_count'],
            user_preference_count=report['analysis']['counts']['user_preference_count']), results=results,
        all_frontier_and_preference_candidates_included=True, latest_cutoff_refit_performed=True,
        historical_task_evaluation_performed=False, checkpoint_weights_used=False, previous_targets_carried_between_candidates=False,
        effective_anchor_strength=0., numerical_failure_is_economic_infeasibility=False,
        technology_scope_status='UNRESOLVED_CURRENT_PURE_TECH_DEFINITION', technology_scope_verified=False,
        point_in_time_verified=False, source_authenticity_verified=False, promotion_allowed=False,
        historical_frontier_risk_liquidity_is_not_latest_fit_risk_admission=True,
        execution_performed=False, order_generation_allowed=False, unique_selection_performed=False,
        forward_oos_evaluation_performed=False, whole_lot_status='NOT_EVALUATED', global_optimum_proven=False,
        portfolio_track='portfolio_optimization')


def save_new(report, path):
    path = Path(path).resolve()
    if (ROOT / 'data/cache/research').resolve() not in path.parents:
        raise ValueError('Research output directory required')
    _verify(report['source_hashes'])
    raw = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('Saved refit report readback differs')
    _verify(report['source_hashes'])
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontier', required=True)
    parser.add_argument('--frontier-sha256', required=True)
    parser.add_argument('--selection-date', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        raise FileExistsError('Create-only research output already exists')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    result = run_date(frontier_path=args.frontier, frontier_sha256=args.frontier_sha256, selection_date=args.selection_date)
    digest = save_new(result, args.output)
    logging.info('Saved latest-cutoff refit sha256=%s counts=%s', digest, json.dumps(result['counts'], sort_keys=True))


if __name__ == '__main__':
    main()
