"""Exact raw eight-coordinate economic frontier of one complete research date.

No weights are inferred, no security scope is approved and no candidate is
selected. Paired incumbent quantiles remain paired statistics throughout.
"""
from collections import Counter
import hashlib
import json
import math

import numpy as np

from backtest.ndx_dynamic_envelope_policy import DIMENSIONS, FUND_COLUMNS, INCUMBENT_COLUMNS, USER_PREFERENCE
from backtest.ndx_dynamic_research_selector import select_research_lane
from backtest.ndx_fractional_research_gates import fractional_research_gates

ECONOMIC_COLUMNS = tuple(FUND_COLUMNS.values()) + tuple(INCUMBENT_COLUMNS.values())
_DIRECTIONS = np.array([1., 1., -1., -1.] * 2)
_ORIGINS = ('EQUAL_WEIGHT_BASE', 'NON_EQUAL_BASE', 'DELTA')


def exact_pareto_indices(values):
    """Maximize all columns, retain exact ties, and return original row indices.

    Unique vectors are swept in descending lexicographic order. A later vector
    cannot dominate an earlier one; only the current frontier needs testing.
    Comparisons use exact input floats, without tolerances or scalar scores.
    """
    if type(values) is not np.ndarray:
        raise ValueError('Explicit numeric ndarray required; no implicit mixed boolean coercion')
    matrix = values
    if matrix.ndim != 2 or matrix.shape[1] != 8 or matrix.dtype.kind not in 'if':
        raise ValueError('Finite nonboolean eight-dimensional matrix required')
    if not np.isfinite(matrix).all():
        raise ValueError('Nonfinite economic coordinates')
    if not len(matrix):
        return []
    unique, inverse = np.unique(matrix, axis=0, return_inverse=True)
    frontier = np.empty_like(unique)
    retained = np.zeros(len(unique), dtype=bool)
    size = 0
    for index in range(len(unique) - 1, -1, -1):
        candidate = unique[index]
        if size and np.any(np.all(frontier[:size] >= candidate, axis=1)):
            continue
        frontier[size] = candidate
        size += 1
        retained[index] = True
    return np.flatnonzero(retained[inverse]).tolist()


def _number(value, field):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Finite nonboolean metric required: ' + field)
    return value


def _counts(rows):
    return dict(expected_task_count=len(rows), evaluated_count=len(rows),
        fractional_risk_count=sum(row['fractional_risk_passed'] for row in rows),
        liquidity_count=sum(row['liquidity_passed'] for row in rows),
        fractional_risk_liquidity_count=sum(row['fractional_risk_liquidity_passed'] for row in rows),
        technology_scope_unknown_count=sum(row['technology_scope_passed'] is None for row in rows),
        single_dimension_pass_counts={column: sum(row['dimension_passed'][column] for row in rows)
                                      for column in ECONOMIC_COLUMNS},
        fund_four_dimension_pass_count=sum(row['fund_four_dimension_passed'] for row in rows),
        incumbent_four_dimension_pass_count=sum(row['incumbent_four_dimension_passed'] for row in rows),
        dual_benchmark_eight_dimension_pass_count=sum(row['dual_benchmark_eight_dimension_passed'] for row in rows),
        risk_liquidity_dual_benchmark_eight_dimension_pass_count=sum(
            row['fractional_risk_liquidity_passed'] and row['dual_benchmark_eight_dimension_passed'] for row in rows))


def analyze_combined_date(date):
    """Validate a prepare_combined_date object; fail closed on any incomplete row."""
    if type(date) is not dict or date.get('schema') != 'ndx_combined_fractional_date_v1':
        raise ValueError('Explicit prepared combined date required')
    expected, records, semantics = date['expected_date'], date['records'], date['training_semantics']
    if type(records) is not list or date.get('economic_inputs_complete') is not True:
        raise ValueError('INPUT_INVALID: incomplete economic inputs')
    signature = hashlib.sha256(json.dumps(semantics['payload'], sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if (semantics['training_semantics_sha256'] != signature
            or expected['training_semantics_sha256'] != signature
            or semantics['payload'].get('schema') != 'ndx_dynamic_training_semantics_v1'
            or any(semantics['payload'].get(key) != expected[key]
                   for key in ('source_batch', 'universe_track', 'decision_data_end'))):
        raise ValueError('Training semantics content or cutoff differs')
    check = select_research_lane(expected_dates=[expected], records=records, policy_role='RETURN')['rows'][0]
    if check['status'] == 'INPUT_INVALID':
        raise ValueError('INPUT_INVALID: ' + json.dumps(check['input_errors'], sort_keys=True))
    if date.get('technology_scope_status') != 'UNRESOLVED_CURRENT_PURE_TECH_DEFINITION':
        raise ValueError('Unsupported technology scope contract')
    observed = Counter(record.get('origin') for record in records)
    if set(observed) - set(_ORIGINS) or set(date['counts']) != set(_ORIGINS):
        raise ValueError('Unknown or missing origin denominators')
    for origin in _ORIGINS:
        declared = date['counts'][origin]
        if any(type(declared.get(key)) is not int or declared[key] != observed[origin]
               for key in ('planned', 'observed', 'evaluated')):
            raise ValueError('Incomplete origin denominator: ' + origin)
    if sum(observed.values()) != expected['expected_task_count']:
        raise ValueError('Incomplete total denominator')
    rows, definitions = [], set()
    for record in records:
        task, metrics = record['task'], record['result']
        if ((record['origin'] == 'EQUAL_WEIGHT_BASE' and task['weight_spec'] != 'equal_weight')
                or (record['origin'] == 'NON_EQUAL_BASE' and task['weight_spec'] == 'equal_weight')):
            raise ValueError('Origin weight specification differs')
        definition = (tuple(sorted(task['tickers'].split(';'))), task['weight_spec'])
        if definition in definitions:
            raise ValueError('Duplicate portfolio definition')
        definitions.add(definition)
        if task.get('training_semantics_sha256', signature) != signature:
            raise ValueError('Task training semantics differs')
        gates = fractional_research_gates(metrics=metrics, contract=semantics['payload']['contract'],
                                          holding_count=task['holding_count'])
        eligibility = record['eligibility']
        if (eligibility.get('technology_scope_passed', 'MISSING') is not None
                or any(type(eligibility.get(key)) is not bool or eligibility[key] != gates[key]
                       for key in ('fractional_risk_passed', 'liquidity_passed'))):
            raise ValueError('Eligibility differs or unresolved scope was upgraded')
        absolute = {column: _number(metrics[column], column) for column in DIMENSIONS}
        differences = {column: _number(metrics[column], column) for column in ECONOMIC_COLUMNS}
        if (not absolute['return_p50'] >= absolute['return_p10'] >= -1.
                or not 0 <= absolute['max_drawdown_p50'] <= absolute['max_drawdown_p90'] <= 1.
                or differences['paired_return_p50_vs_incumbent'] < differences['paired_return_p10_vs_incumbent']
                or differences['paired_drawdown_cost_p50_vs_incumbent'] > differences['paired_drawdown_cost_p90_vs_incumbent']):
            raise ValueError('Invalid raw or paired quantile ordering')
        passed = {column: value * direction >= 0. for (column, value), direction
                  in zip(differences.items(), _DIRECTIONS.tolist())}
        fund = all(passed[column] for column in FUND_COLUMNS.values())
        incumbent = all(passed[column] for column in INCUMBENT_COLUMNS.values())
        rows.append(dict(job_id=task['job_id'], tickers=task['tickers'], holding_count=task['holding_count'],
            weight_spec=task['weight_spec'], origin=record['origin'], absolute_metrics=absolute,
            benchmark_differences=differences, dimension_passed=passed,
            failed_dimensions=[column for column, value in passed.items() if not value],
            fractional_risk_passed=gates['fractional_risk_passed'], liquidity_passed=gates['liquidity_passed'],
            fractional_risk_liquidity_passed=gates['fractional_risk_passed'] and gates['liquidity_passed'],
            technology_scope_passed=None, fund_four_dimension_passed=fund,
            incumbent_four_dimension_passed=incumbent, dual_benchmark_eight_dimension_passed=fund and incumbent,
            user_preference_reference=set(task['tickers'].split(';')) == USER_PREFERENCE and task['weight_spec'] == 'equal_weight'))
    rows.sort(key=lambda row: row['job_id'])

    def frontier(candidates):
        if not candidates:
            return []
        matrix = np.array([[row['benchmark_differences'][column] for column in ECONOMIC_COLUMNS]
                           for row in candidates]) * _DIRECTIONS
        return [candidates[index] for index in exact_pareto_indices(matrix)]

    raw = frontier(rows)
    risk = frontier([row for row in rows if row['fractional_risk_liquidity_passed']])
    preferences = [row for row in rows if row['user_preference_reference']]
    grouped = {}
    for row in rows:
        grouped.setdefault((row['holding_count'], row['origin'], row['weight_spec']), []).append(row)
    groups = [dict(holding_count=key[0], origin=key[1], weight_spec=key[2], **_counts(values))
              for key, values in sorted(grouped.items())]
    counts = _counts(rows)
    counts.update(raw_frontier_count=len(raw), risk_liquidity_frontier_count=len(risk), user_preference_count=len(preferences))
    return dict(schema='ndx_combined_fractional_frontier_research_v1', expected_date=dict(expected),
        counts=counts, groups=groups, raw_frontier=raw, risk_liquidity_frontier=risk,
        user_preference_references=preferences, economic_columns=list(ECONOMIC_COLUMNS),
        maximize_columns=[column for column, direction in zip(ECONOMIC_COLUMNS, _DIRECTIONS) if direction > 0],
        minimize_columns=[column for column, direction in zip(ECONOMIC_COLUMNS, _DIRECTIONS) if direction < 0],
        dominance_policy='EXACT_RAW_COMPONENTWISE_NONINFERIOR_AND_ONE_STRICT_IMPROVEMENT_KEEP_ALL_TIES',
        dimension_pass_policy='EXACT_ZERO_NONINFERIOR_NO_COMPENSATION_NOT_FORMAL_ADMISSION',
        risk_liquidity_layer_scope='FOUR_FRACTIONAL_CONCENTRATION_CHECKS_PLUS_LIQUIDITY_NOT_FULL_RISK_ADMISSION',
        historical_minimum_single_weight_verified=False, current_whole_lot_execution_verified=False,
        whole_lot_status='NOT_EVALUATED',
        technology_scope_status=date['technology_scope_status'], technology_scope_verified=False,
        paired_quantiles_are_not_marginal_quantile_differences=True, research_only=True,
        execution_performed=False, saved_weights_are_execution_targets=False, cutoff_refit_required=True,
        point_in_time_verified=False, source_authenticity_verified=False, promotion_allowed=False,
        global_optimum_proven=False, global_infeasibility_proven=False, unique_selection_performed=False,
        portfolio_track='portfolio_optimization')
