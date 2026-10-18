"""Date-complete research ranking, independent of historical whole-lot gates.

Eligibility assertions are caller-supplied research inputs, not authenticated
PIT evidence. This module cannot admit portfolios or generate execution weights.
"""
from copy import deepcopy
from datetime import date
import math
import re

_KEYS = ('source_batch', 'universe_track', 'selection_date')
_GATES = ('fractional_risk_passed', 'liquidity_passed', 'technology_scope_passed')
_METRICS = ('return_p50', 'return_p10', 'max_drawdown_p50', 'max_drawdown_p90', 'target_012922_distance')
_ORDER = {
    'RETURN': (('return_p50', -1), ('return_p10', -1), ('max_drawdown_p90', 1), ('target_012922_distance', 1)),
    'BAD_TAIL': (('return_p10', -1), ('return_p50', -1), ('max_drawdown_p90', 1), ('target_012922_distance', 1)),
    'DRAWDOWN': (('max_drawdown_p90', 1), ('max_drawdown_p50', 1), ('return_p10', -1), ('target_012922_distance', 1)),
    'TARGET_ENVELOPE': (('target_012922_distance', 1), ('return_p10', -1), ('max_drawdown_p90', 1), ('return_p50', -1)),
}


def _coordinate(value):
    key = tuple(value[name] for name in _KEYS)
    if any(type(item) is not str or not item or item != item.strip() for item in key):
        raise ValueError('Canonical coordinate strings required')
    if date.fromisoformat(key[-1]).isoformat() != key[-1]:
        raise ValueError('Canonical selection date required')
    return key


def select_research_lane(*, expected_dates, records, policy_role):
    if policy_role not in (*_ORDER, 'USER_PREFERENCE'):
        raise ValueError('Explicit supported policy role required')
    expected = {}
    for row in expected_dates:
        key = _coordinate(row)
        count = row['expected_task_count']
        if key in expected or type(count) is not int or count < 0:
            raise ValueError('Unique dates and nonnegative task denominators required')
        cutoff = row['decision_data_end']
        signature = row['training_semantics_sha256']
        if (date.fromisoformat(cutoff).isoformat() != cutoff or cutoff >= key[-1]
                or type(signature) is not str or re.fullmatch('[0-9a-f]{64}',signature) is None):
            raise ValueError('Explicit cutoff and training semantics digest required')
        expected[key] = dict(count=count, cutoff=cutoff, signature=signature)
    if not expected:
        raise ValueError('Explicit date denominator required')
    groups = {key: [] for key in expected}
    for record in records:
        key = _coordinate(record['task'])
        if key not in groups:
            raise ValueError('Task outside explicit date denominator')
        groups[key].append(record)
    output = []
    for key in sorted(expected):
        group, required = groups[key], expected[key]['count']
        row = dict(zip(_KEYS, key))
        row.update(expected_task_count=required, observed_task_count=len(group),
                   policy_role=policy_role, selected=None, rejections=[],
                   decision_data_end=expected[key]['cutoff'],
                   training_semantics_sha256=expected[key]['signature'])
        errors = []
        valid, seen = [], set()
        for record in group:
            task, result = record['task'], record.get('result')
            identifier = task.get('job_id')
            try:
                if type(identifier) is not str or not identifier or identifier in seen:
                    raise ValueError('Missing/duplicate job identity')
                seen.add(identifier)
                if record.get('status') != 'EVALUATED' or not isinstance(result, dict):
                    raise ValueError('Missing evaluated result')
                if date.fromisoformat(task['decision_data_end']).isoformat() != task['decision_data_end'] or task['decision_data_end'] >= key[-1]:
                    raise ValueError('Invalid decision cutoff')
                if (task['decision_data_end'] != expected[key]['cutoff']
                        or record.get('training_semantics_sha256') != expected[key]['signature']):
                    raise ValueError('Incomparable cutoff or training semantics')
                if task['weight_spec'] not in ('equal_weight','constrained_fixed_shrinkage','constrained_fixed_shrinkage_turnover_anchor'):
                    raise ValueError('Unsupported weight specification')
                if any(result.get(field) != task[field] for field in ('tickers','holding_count','weight_spec')):
                    raise ValueError('Result and task portfolio identities differ')
                names = task['tickers'].split(';')
                if (type(task['holding_count']) is not int or task['holding_count'] != len(names)
                        or len(set(names)) != len(names) or any(not name or name != name.strip() for name in names)):
                    raise ValueError('Invalid cardinality/identities')
                if any(type(result.get(field)) not in (float, int) or not math.isfinite(result[field]) for field in _METRICS):
                    raise ValueError('Missing/nonfinite ranking metric')
                gates = record.get('eligibility', {})
                if not isinstance(gates, dict):
                    raise ValueError('Eligibility must be an explicit mapping')
                failures = [gate for gate in _GATES if gates.get(gate) is not True]
                if policy_role == 'USER_PREFERENCE':
                    if set(names) != {'AMAT','AVGO','CDNS','GOOG'} or task['weight_spec'] != 'equal_weight':
                        failures.append('NOT_USER_PREFERENCE_REFERENCE')
                    else:
                        # Preserve the reference even when its research gates fail.
                        failures = []
                if failures:
                    row['rejections'].append(dict(job_id=identifier, reasons=failures))
                else:
                    valid.append(record)
            except (ValueError, TypeError, KeyError) as error:
                errors.append(dict(job_id=identifier, error=str(error)))
        if len(group) != required:
            errors.append(dict(error='Task denominator incomplete'))
        row['input_errors'] = errors
        row['eligible_count'] = len(valid)
        if errors:
            row['status'] = 'INPUT_INVALID'
        elif required == 0:
            row['status'] = 'NO_DELTA'
        elif not valid:
            row['status'] = 'NO_ELIGIBLE_CANDIDATE'
        elif policy_role == 'USER_PREFERENCE' and len(valid) != 1:
            row['status'] = 'INPUT_INVALID'
            row['input_errors'].append(dict(error='Ambiguous preference reference'))
        else:
            def order(record):
                task, result = record['task'], record['result']
                metrics = tuple(result[field]*direction for field, direction in _ORDER.get(policy_role, ()))
                return metrics + (task['holding_count'], task['tickers'], task['weight_spec'], task['job_id'])
            row['status'] = 'SELECTED'
            row['selected'] = deepcopy(min(valid, key=order))
        output.append(row)
    return dict(rows=output, portfolio_track='portfolio_optimization',
        saved_weights_are_execution_targets=False, cutoff_refit_required=True,
        eligibility_source_authenticity_verified=False, implicit_carry_forward=False,
        full_universe_search_verified=False, scalar_distance_is_admission=False,
        promotion_allowed=False)
