"""General exact integer-box fallback for a verified unresolved root tail.

No unique-zero-axis or interval-width admission. Midpoint splits partition all
integer points; empty boxes and rational bounds close branches. Each segment
is bounded, hash-linked and replay-verifiable. Ties, PIT and economics remain
outside this value-only research certificate. No optimizer or IO.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json

from backtest import quantity_anchor_domain_completion as base_stage
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as core
from backtest import quantity_multi_anchor_bound_prototype as anchor_bound

MAX_NODES = 2000
MAX_SEGMENTS = 100


def _step(base, state, node_budget):
    core.require(type(node_budget) is int and 0 < node_budget <= MAX_NODES, 'PARTITION_NODE_CAP_REQUIRED')
    core.require(bool(state['pending']), 'PARTITION_ALREADY_COMPLETE')
    problem = core.prepare(**base['inputs'])
    stack = deepcopy(state['pending'])
    selected = deepcopy(state['selected'])
    best = F(state['lower_product'])
    ledger = []
    leaves = 0
    while stack and len(ledger) < node_budget:
        node = stack.pop()
        box = node['box']
        ordinary = core.box_bound(problem, box, selected)
        record = dict(id=node['id'], box=box, inherited_upper=node['upper_product'], ordinary_bound=ordinary)
        if ordinary['empty']:
            record.update(terminal='EMPTY', anchor_bound=None)
        else:
            bound = anchor_bound.anchor_bound(problem, box, base['anchor']['repaired_quantities'])
            upper = min(F(node['upper_product']), F(ordinary['upper']), F(bound['upper_product']))
            record.update(anchor_bound=bound, upper_product=str(upper), lower_product=str(best))
            if upper <= best:
                record['terminal'] = 'VALUE_BOUND_CLOSED'
            else:
                axes = [sid for sid in problem['ids'] if box[sid][0] < box[sid][1]]
                if not axes:
                    quantities = {sid: box[sid][0] for sid in problem['ids'] if box[sid][0]}
                    value = core.objective(problem, quantities)[0]
                    core.require(value <= upper, 'LEAF_EXCEEDS_BOUND')
                    leaves += 1
                    if value > best:
                        best, selected = value, quantities
                    record.update(terminal='LEAF_EVALUATED', product=str(value))
                else:
                    sid = min(axes, key=lambda key: (-(box[key][1] - box[key][0]), key))
                    midpoint = sum(box[sid]) // 2
                    children = []
                    for label, interval in [('0', [box[sid][0], midpoint]), ('1', [midpoint + 1, box[sid][1]])]:
                        child = deepcopy(box)
                        child[sid] = interval
                        children.append(dict(id=node['id'] + label, box=child, upper_product=str(upper)))
                    stack.extend(reversed(children))
                    record.update(terminal='SPLIT', axis=sid, midpoint=midpoint, children=[child['id'] for child in children])
        ledger.append(record)
    upper = max([best] + [F(node['upper_product']) for node in stack])
    core.require(F(state['lower_product']) <= best <= upper <= F(state['upper_product']), 'PARTITION_BOUNDS_NOT_MONOTONE')
    return dict(pending=stack, selected=selected, lower_product=str(best), upper_product=str(upper),
                ledger=ledger, visited_nodes=len(ledger), evaluated_leaves=leaves,
                objective_value_covered=not stack)


def _certificate(base, state, node_budget, base_hash, parent_hash, index):
    result = _step(base, state, node_budget)
    return dict(schema='FULL_ROOT_INTEGER_PARTITION_SEGMENT_V1', base_sha256=base_hash,
                parent_sha256=parent_hash, segment_index=index, node_budget=node_budget, **result,
                tie_break_optimality_established=False, data_authenticated=False,
                optimizer_calls=0, economic_runs=0)


def build(*, base_raw, expected_base_sha256, expected_inputs_sha256,
          expected_anchor_sha256, history=(), node_budget=MAX_NODES):
    core.require(type(base_raw) is bytes and sha256(base_raw).hexdigest() == expected_base_sha256, 'PARTITION_BASE_CHANGED')
    core.require(type(history) in (tuple, list) and len(history) < MAX_SEGMENTS, 'PARTITION_HISTORY_CAP')
    base = json.loads(base_raw)
    base_stage.verify(base, expected_inputs_sha256=expected_inputs_sha256,
                      expected_anchor_sha256=expected_anchor_sha256)
    core.require(not base['objective_value_covered'], 'PARTITION_BASE_ALREADY_COMPLETE')
    state = dict(pending=[dict(id='r', box=base['unresolved_box'], upper_product=base['upper_product'])],
                 selected=base['selected'], lower_product=base['lower_product'], upper_product=base['upper_product'])
    parent_hash = expected_base_sha256
    for index, (raw, digest) in enumerate(history, 1):
        core.require(type(raw) is bytes and sha256(raw).hexdigest() == digest, 'PARTITION_HISTORY_CHANGED')
        saved = json.loads(raw)
        rebuilt = _certificate(base, state, saved['node_budget'], expected_base_sha256, parent_hash, index)
        core.require(continuous.canonical(rebuilt) == continuous.canonical(saved), 'PARTITION_SEGMENT_CHANGED')
        state, parent_hash = rebuilt, digest
    return _certificate(base, state, node_budget, expected_base_sha256, parent_hash, len(history) + 1)


def verify(certificate, **sources):
    rebuilt = build(node_budget=certificate['node_budget'], **sources)
    core.require(continuous.canonical(rebuilt) == continuous.canonical(certificate), 'PARTITION_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_FULL_ROOT_PARTITION_SEGMENT',
                objective_value_covered=rebuilt['objective_value_covered'],
                tie_break_optimality_established=False)
