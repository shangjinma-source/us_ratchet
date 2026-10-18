"""Independent complete-input four-lane rank check; never calls the selector or fit."""
from fractions import Fraction
import hashlib
import json
import math

CUTOFFS = ('2026-03-31', '2026-04-30', '2026-05-29', '2026-06-30', '2026-07-31', '2026-08-31')
MODES = ('STRICT_SAME_SESSION_FX', 'BACKWARD_LATEST_VALID_FX')
ORDERS = (
    ('RETURN', (('return_p50', -1), ('return_p10', -1), ('max_drawdown_p90', 1), ('target_012922_distance', 1))),
    ('BAD_TAIL', (('return_p10', -1), ('return_p50', -1), ('max_drawdown_p90', 1), ('target_012922_distance', 1))),
    ('DRAWDOWN', (('max_drawdown_p90', 1), ('max_drawdown_p50', 1), ('return_p10', -1), ('target_012922_distance', 1))),
    ('TARGET_ENVELOPE', (('target_012922_distance', 1), ('return_p10', -1), ('max_drawdown_p90', 1), ('return_p50', -1))),
)
GATES = ('fractional_risk_passed', 'liquidity_passed', 'conditional_member_scope_passed')
POLICY = 'FULL_NDX_FOUR_LANE_RESEARCH_SELECTOR_JOB_ID_TIE_V1'
FALSE = ('source_bytes_authenticated', 'eligibility_source_authenticity_verified', 'point_in_time_verified',
         'complete_ndx_universe_verified', 'full_universe_search_verified', 'sector_filter_applied',
         'mode_selected_using_results', 'saved_weights_are_execution_targets', 'prior_resolved',
         'numerical_task_ids_generated', 'implicit_carry_forward', 'fit_performed', 'account_executed',
         'promotion_allowed', 'execution_authorized', 'formal_benchmark_passed')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def same(left, right, message):
    require(encoded(left) == encoded(right), message)


def count(value, expected):
    require(type(value) is int and value == expected, 'Exact typed count')


def numeric(value):
    require(type(value) in (int, float) and (type(value) is int or math.isfinite(value)), 'Finite nonboolean metric')
    return Fraction(str(value))


def inspect_complete_selection(*, registration, records, saved_selection):
    """Requires complete well-formed supplied scores, including legitimate risk rejects.

    Invalid/partial input results are rejected, not certified as successful rankings.
    Source-blocked registered coordinates are retained without scores.
    """
    result = saved_selection
    require(result['schema'] == 'FULL_NDX_MULTIDECISION_FOUR_LANE_SELECTION_V1', 'Selection schema')
    require(registration['schema'] == 'FULL_NDX_MULTIDECISION_SELECTION_REGISTRATION_V1', 'Registration schema')
    require(result['policy_id'] == registration['policy_id'] == POLICY, 'Fixed lane policy')
    for key in FALSE:
        require(result[key] is False, 'No authority promotion ' + key)
    require(result['cutoff_refit_required'] is True, 'Fresh cutoff refit remains necessary')
    require(result['portfolio_track'] == 'portfolio_optimization', 'Primary portfolio track')
    same(result['evaluation_tracks'], ['continuous', 'whole_lot'], 'Both later evaluation tracks')
    require(result['ranking_arithmetic'] == 'EXACT_FRACTION_OF_SAVED_NUMERIC_LITERAL_NOT_RECOMPUTED_SCORES', 'Exact rank arithmetic')
    same(result['registration_preserved'], registration, 'Full registration retained')
    same(result['records_preserved'], records, 'All supplied records retained')
    require(result['global_input_errors'] == [], 'No invalid global inputs accepted')
    same(registration['decision_cutoffs'], list(CUTOFFS), 'Six fixed decisions')
    same(registration['fx_modes'], list(MODES), 'Two separate FX modes')
    require(registration['universe_scope'] == 'ALL_CONDITIONAL_NDX_MEMBERS_ALL_INDUSTRIES' and registration['sector_filter_applied'] is False, 'Full supplied industry scope')
    inventory = {row['security_id']: row for row in registration['universe']}
    require(len(inventory) == len(registration['universe']) and inventory, 'Unique full inventory')
    issuers = {}
    for row in inventory.values():
        issuers[row['issuer_id']] = issuers.get(row['issuer_id'], 0) + 1
    polynomial = [1]
    for multiplicity in issuers.values():
        previous = polynomial
        polynomial = [0] * (len(previous) + 1)
        for index, value in enumerate(previous):
            polynomial[index] += value
            polynomial[index + 1] += value * multiplicity
    domain = [dict(holding_count=index, combination_count=value) for index, value in enumerate(polynomial) if index]
    same(registration['all_k_denominators'], domain, 'Independent all-k issuer polynomial')
    same(result['all_k_denominators_preserved'], domain, 'Full domain preserved')
    coordinates = registration['coordinates']
    require(len(coordinates) == len(result['rows']) == 12, 'All twelve coordinates')
    grouped = {(cutoff, mode): [] for cutoff in CUTOFFS for mode in MODES}
    for index, record in enumerate(records):
        key = (record['task']['cutoff'], record['task']['fx_mode'])
        require(key in grouped, 'No foreign coordinate')
        grouped[key].append((index, record))
    selected_count = 0
    blocked_count = 0
    for coordinate, row, key in zip(coordinates, result['rows'], grouped):
        same((coordinate['cutoff'], coordinate['fx_mode']), key, 'Registered coordinate order')
        same(row['coordinate_preserved'], coordinate, 'Complete coordinate retained')
        expected = coordinate['expected_job_ids']
        require(len(expected) == len(set(expected)), 'Unique expected jobs')
        group = grouped[key]
        blocked = coordinate['source_status'] == 'SOURCE_BLOCKED'
        require(blocked or coordinate['source_status'] == 'READY_FOR_SCORING', 'Explicit source state')
        require(bool(coordinate['source_blockers']) == blocked, 'Source blocker evidence')
        require(row['input_errors'] == [], 'Partial/invalid selection is not a complete rank')
        count(row['expected_task_count'], len(expected))
        count(row['received_task_count'], len(group))
        count(row['source_blocked_task_count'], len(expected) if blocked else 0)
        same(row['unreceived_job_ids'], expected if blocked else [], 'Blocked and missing are distinct')
        if blocked:
            require(not group, 'No scores substituted for blocked mode')
            blocked_count += len(expected)
        else:
            require(len(group) == len(expected) and {record['task']['job_id'] for _, record in group} == set(expected), 'Complete registered score denominator')
        coverage = coordinate['budget_coverage']
        for name, value in (('full_combination_count', sum(polynomial[1:])), ('full_three_spec_task_denominator', sum(polynomial[1:]) * 3), ('registered_task_count', len(expected)), ('unscored_full_domain_task_count', sum(polynomial[1:]) * 3 - len(expected))):
            count(coverage[name], value)
        eligible = []
        rejected = []
        semantics = set()
        for index, record in group:
            task, metrics = record['task'], record['result']
            require(record['status'] == 'EVALUATED' and task['decision_date'] == coordinate['cutoff'], 'Saved evaluated coordinate')
            require(record['training_semantics_sha256'] == coordinate['training_semantics_sha256'], 'Same training semantics')
            sids = task['security_ids']
            require(sids and sids == sorted(set(sids)) and all(sid in inventory for sid in sids), 'Canonical security identity')
            count(task['holding_count'], len(sids))
            require(len({inventory[sid]['issuer_id'] for sid in sids}) == len(sids), 'One class per issuer')
            require(task['tickers'] == ';'.join(sorted(inventory[sid]['ticker'] for sid in sids)), 'Original ticker identity')
            require(task['weight_spec'] in ('equal_weight', 'constrained_fixed_shrinkage', 'constrained_fixed_shrinkage_turnover_anchor'), 'Three registered specs')
            identity = (tuple(sids), task['weight_spec'])
            require(identity not in semantics, 'No duplicate semantic candidates')
            semantics.add(identity)
            for name in ('security_ids', 'holding_count', 'tickers', 'weight_spec'):
                same(metrics[name], task[name], 'Metric identity')
            for name in ('return_p50', 'return_p10', 'max_drawdown_p50', 'max_drawdown_p90', 'target_012922_distance'):
                value = numeric(metrics[name])
                if name not in ('return_p50', 'return_p10'):
                    require(value >= 0, 'Nonnegative cost metric')
            gates = record['eligibility']
            require(all(type(gates[name]) is bool for name in GATES) and 'technology_scope_passed' not in gates, 'Exact independent gates')
            failed = [name for name in GATES if not gates[name]]
            if failed:
                rejected.append(dict(job_id=task['job_id'], record_index=index, reasons=failed))
            else:
                eligible.append((index, record))
        same(row['rejections'], rejected, 'All gate rejections retained')
        count(row['eligible_count'], len(eligible))
        require(len(row['choices']) == 4, 'All four lanes')
        for choice, (lane, order) in zip(row['choices'], ORDERS):
            require(choice['lane'] == lane, 'Frozen lane order')
            status = 'SOURCE_BLOCKED' if blocked else 'NO_REGISTERED_CANDIDATES' if not expected else 'NO_ELIGIBLE_CANDIDATE' if not eligible else 'SELECTED_REQUIRES_NEW_CUTOFF_REFIT'
            require(choice['status'] == status, 'Exact independent outcome')
            if not eligible:
                require(choice['selected'] is None, 'No invented fallback selection')
                continue
            def rank(pair):
                task, values = pair[1]['task'], pair[1]['result']
                return tuple(numeric(values[name]) * direction for name, direction in order) + (task['holding_count'], task['tickers'], task['weight_spec'], task['job_id'])
            index, record = min(eligible, key=rank)
            same(choice['selected'], dict(job_id=record['task']['job_id'], record_index=index, record_preserved=record), 'Independent lane minimum with exact tie-break')
            selected_count += 1
    require(result['content_sha256'] == hashlib.sha256(encoded({key: value for key, value in result.items() if key != 'content_sha256'})).hexdigest(), 'Saved selection digest')
    return dict(schema='FULL_NDX_COMPLETE_SELECTION_INSPECTION_V1', status='PASS', coordinate_count=12,
                selected_lane_count=selected_count, source_blocked_task_count=blocked_count,
                record_count=len(records), arithmetic='EXACT_FRACTION_OF_SAVED_LITERAL',
                source_bytes_authenticated=False, upstream_scoring_windows_reaudited=False,
                selector_called=False, fit_performed=False, point_in_time_verified=False,
                promotion_allowed=False, execution_authorized=False)
