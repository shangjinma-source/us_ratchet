"""Hash-bound, bounded continuation of an admitted full-root coupled search.

Each new segment processes only its parent's pending DFS stack. Verification
replays the original bounded certificate and prior segments, including their
objective evaluations; that verification cost is not new search progress.
No optimizer, IO, production authority, or claim about objective ties.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json

from backtest import quantity_anchor_coupled_completion as origin_stage
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_coupled_joint_loss_iterator as kernel
from backtest import quantity_coupled_frontier_partition as partition
from backtest import quantity_integer_box_certificate_prototype as core

MAX_HISTORY = 100


def _advance(state, evidence, problem, node_budget, objective_budget):
    core.require(type(node_budget) is int and 0 < node_budget <= origin_stage.MAX_NODES
                 and type(objective_budget) is int and 0 < objective_budget <= origin_stage.MAX_OBJECTIVES,
                 'POSITIVE_FIXED_SEGMENT_BUDGET_REQUIRED')
    core.require(not state['domain_complete'], 'ALREADY_COMPLETE')
    axes = state['axes']
    all_axes = state['necessary_count_evidence']['axes']
    zero = state['zero_axis']
    box = state['original_box']
    multiplier = F(evidence['binding']['dual_lambda'])
    gap = F(evidence['strict_loss_budget'])
    stack = deepcopy(state['unsearched_frontier'])
    ledger, points = [], []
    evaluations = 0
    best = F(state['candidate_product'])
    selected = deepcopy(state['selected_candidate'])
    while stack and len(ledger) < node_budget and evaluations < objective_budget:
        prefix = stack.pop()
        partial = sum((F(axes[i]['penalty']) * d for i, d in enumerate(prefix)), F(0))
        bound = kernel.prefix_bound(problem=problem, all_axes=all_axes, branch_axes=axes,
            prefix=prefix, zero_axis=zero, box=box, dual_lambda=multiplier)
        record = dict(prefix=prefix, partial_coordinate_loss=str(partial), prefix_loss_bound=bound)
        if F(bound['total_loss_lower']) >= gap:
            record['terminal'] = 'CLOSED_BY_PREFIX_BUDGET_AND_COORDINATE_LOSS'
        elif len(prefix) < len(axes):
            axis = axes[len(prefix)]
            record.update(terminal='SPLIT_ALL_ALLOWED_DEVIATIONS', sid=axis['sid'], maximum=axis['max_deviation'])
            stack.extend(prefix + [d] for d in range(axis['max_deviation'], -1, -1))
        else:
            quantities = {axis['sid']: axis['preferred'] for axis in all_axes}
            for axis, deviation in zip(axes, prefix):
                quantities[axis['sid']] += axis['direction'] * deviation
            spend = sum((problem['cost'][sid] * quantity for sid, quantity in quantities.items() if sid != zero), F(0))
            interval = kernel.strict_interval(spendable=problem['spendable'], other_spend=spend,
                loss_budget=gap, other_loss=partial, dual_lambda=multiplier,
                unit_cost=problem['cost'][zero], lo=box[zero][0], hi=box[zero][1])
            record['zero_axis_interval'] = interval
            core.require(interval['last'] - interval['first'] < 1, 'INTERVAL_NOT_SINGLETON')
            if interval['first'] > interval['last']:
                record['terminal'] = 'CLOSED_BY_COUPLED_BUDGET_LOSS'
            else:
                quantities[zero] = interval['first']
                positive = {sid: quantity for sid, quantity in quantities.items() if quantity}
                issuers = [problem['metadata'][sid]['issuer_id'] for sid in positive]
                spent = spend + problem['cost'][zero] * quantities[zero]
                residual = problem['cash'] - spent
                feasible = len(set(issuers)) == len(issuers) and residual >= 0 and (not positive or residual >= problem['buffer'])
                point = dict(quantities=positive, feasible=feasible, fee_inclusive_spend=str(spent), product=None)
                if feasible:
                    value = core.objective(problem, positive)[0]
                    evaluations += 1
                    point['product'] = str(value)
                    if value > best:
                        best, selected = value, positive
                points.append(point)
                record.update(terminal='CHECKED_INTEGER_POINT', point_index=len(points) - 1)
        ledger.append(record)
    return dict(ledger=ledger, points=points, unsearched_frontier=stack,
                selected_candidate=selected, candidate_product=str(best),
                domain_complete=not stack, visited_nodes=len(ledger), checked_points=len(points),
                objective_evaluations=evaluations)


def _merge(state, delta):
    combined = deepcopy(state)
    records = deepcopy(delta['ledger'])
    for record in records:
        if 'point_index' in record:
            record['point_index'] += len(state['points'])
    combined.update(deepcopy(delta))
    combined['ledger'] = state['ledger'] + records
    combined['points'] = state['points'] + delta['points']
    for key in ('visited_nodes', 'checked_points', 'objective_evaluations'):
        combined[key] = state[key] + delta[key]
    partition.verify(combined)
    return combined


def _segment(state, origin, origin_hash, parent_hash, index, problem, node_budget, objective_budget):
    delta = _advance(state, origin['loss'], problem, node_budget, objective_budget)
    merged = _merge(state, delta)
    value = F(delta['candidate_product'])
    core.require(F(state['candidate_product']) <= value <= F(origin['upper_product']), 'SEGMENT_VALUE_OUTSIDE_BOUND')
    return dict(schema='ANCHOR_COUPLED_CONTINUATION_SEGMENT_V1',
                origin_sha256=origin_hash, parent_sha256=parent_hash, segment_index=index,
                node_budget=node_budget, objective_budget=objective_budget, delta=delta,
                lower_product=str(value), upper_product=str(value if delta['domain_complete'] else F(origin['upper_product'])),
                objective_value_covered=delta['domain_complete'],
                tie_break_optimality_established=False, data_authenticated=False,
                optimizer_calls=0, economic_runs=0), merged


def build(*, origin_raw, expected_origin_sha256, history=(), node_budget=5000,
          objective_budget=500, **origin_sources):
    """history is ordered (raw_bytes, expected_sha256) pairs, never mutable state."""
    core.require(type(origin_raw) is bytes and sha256(origin_raw).hexdigest() == expected_origin_sha256, 'ORIGIN_RAW_CHANGED')
    core.require(type(history) in (list, tuple) and len(history) < MAX_HISTORY, 'HISTORY_LIMIT')
    origin = json.loads(origin_raw)
    origin_stage.verify(origin, **origin_sources)
    core.require(origin['status'] == 'UNRESOLVED_COUPLED_FRONTIER', 'UNRESOLVED_COUPLED_ORIGIN_REQUIRED')
    problem = core.prepare(**json.loads(origin_sources['base_raw'])['inputs'])
    state = origin['coupled']
    parent_hash = expected_origin_sha256
    for index, (raw, expected_hash) in enumerate(history, 1):
        core.require(type(raw) is bytes and sha256(raw).hexdigest() == expected_hash, 'HISTORY_RAW_CHANGED')
        saved = json.loads(raw)
        rebuilt, state = _segment(state, origin, expected_origin_sha256, parent_hash, index,
                                 problem, saved['node_budget'], saved['objective_budget'])
        core.require(continuous.canonical(rebuilt) == continuous.canonical(saved), 'HISTORY_SEGMENT_CHANGED')
        parent_hash = expected_hash
    result, _ = _segment(state, origin, expected_origin_sha256, parent_hash, len(history) + 1,
                         problem, node_budget, objective_budget)
    return result


def verify(certificate, **sources):
    rebuilt = build(node_budget=certificate['node_budget'], objective_budget=certificate['objective_budget'], **sources)
    core.require(continuous.canonical(rebuilt) == continuous.canonical(certificate), 'CONTINUATION_CHANGED')
    return dict(status='VERIFIED_FULL_ROOT_CONTINUATION_SEGMENT',
                objective_value_covered=rebuilt['objective_value_covered'],
                tie_break_optimality_established=False)
