"""Portable exact value coverage after candidate generation; research only.

A verified full-root continuous anchor excludes regions below a feasible lower
bound. The remaining tail is enumerated only within a fixed hard point cap.
Large unresolved tails remain explicit. No optimizer, filesystem or trading IO.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import product
from math import prod

from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as integer
from backtest import quantity_saved_anchor_coordinate_fixing as fixing
from backtest import quantity_saved_anchor_tail_tightening as tightening


SCHEMA = 'ANCHOR_FULL_DOMAIN_SMALL_TAIL_VALUE_CERTIFICATE_V1'
MAX_TAIL_POINTS = 10000


def build(*, inputs, anchor, incumbent, max_tail_points=MAX_TAIL_POINTS):
    require = integer.require
    require(type(max_tail_points) is int and 0 < max_tail_points <= MAX_TAIL_POINTS,
            'TAIL_POINT_CAP_REQUIRED')
    require(continuous.canonical(inputs) == continuous.canonical(anchor['binding']['inputs']),
            'ANCHOR_INPUT_MISMATCH')
    continuous.verify(anchor, expected_binding_sha256=continuous.digest(anchor['binding']))
    problem = integer.prepare(**inputs)
    root = {sid: [0, int(problem['spendable']//problem['cost'][sid])] for sid in problem['ids']}
    require(not anchor['empty'] and anchor['binding']['box'] == root, 'FULL_ROOT_ANCHOR_REQUIRED')
    best, _, notional = integer.objective(problem, incumbent)
    selected = deepcopy(incumbent)
    rank = (best, -notional, tuple(sorted(selected.items())))
    anchor_raw = continuous.canonical(anchor)
    sources = dict(anchor_raw=anchor_raw, expected_anchor_sha256=sha256(anchor_raw).hexdigest(),
                   expected_anchor_binding_sha256=anchor['binding_sha256'], incumbent=deepcopy(incumbent))
    fixed = fixing.build(**sources)
    fixed_raw = continuous.canonical(fixed)
    tail = tightening.build(fixing_raw=fixed_raw, expected_fixing_sha256=sha256(fixed_raw).hexdigest(),
                            fixing_sources=sources)
    box = tail['remaining_box']
    size = prod(high-low+1 for low, high in box.values())
    enumeration = None
    complete = tail['objective_value_covered']
    status = 'COVERED_BY_EXACT_BOUND' if complete else 'UNRESOLVED_LARGE_TAIL'
    if not complete and size <= max_tail_points:
        visited = feasible = 0
        for values in product(*(range(box[sid][0], box[sid][1]+1) for sid in problem['ids'])):
            visited += 1
            quantities = {sid: q for sid, q in zip(problem['ids'], values) if q}
            issuers = [problem['metadata'][sid]['issuer_id'] for sid in quantities]
            if len(set(issuers)) != len(issuers):
                continue
            cost = sum((problem['cost'][sid]*q for sid,q in quantities.items()), Fraction(0))
            if cost > problem['cash'] or (quantities and cost > problem['spendable']):
                continue
            feasible += 1
            value, _, amount = integer.objective(problem, quantities)
            proposed_rank = (value, -amount, tuple(sorted(quantities.items())))
            if proposed_rank > rank:
                rank, best, selected = proposed_rank, value, quantities
        require(visited == size, 'INCOMPLETE_TAIL_ENUMERATION')
        enumeration = dict(visited=visited, feasible=feasible)
        complete, status = True, 'COVERED_BY_COMPLETE_TAIL'
    return deepcopy(dict(schema=SCHEMA, status=status, inputs=inputs, anchor=anchor,
        inputs_sha256=continuous.digest(inputs), anchor_sha256=continuous.digest(anchor),
        incumbent=incumbent, max_tail_points=max_tail_points, root_box=root,
        fixing=fixed, tail=tail, tail_cartesian_points=size, enumeration=enumeration,
        selected=selected, lower_product=str(best),
        upper_product=str(best if complete else max(best, Fraction(tail['upper_product']))),
        objective_value_covered=complete, tie_break_optimality_established=False,
        unresolved_box=None if complete else box, data_authenticated=False,
        future_performance_guaranteed=False, optimizer_calls=0, economic_runs=0))


def verify(certificate, *, expected_inputs_sha256, expected_anchor_sha256):
    """Replay exact exclusions/enumeration against caller-authenticated bindings."""
    integer.require(certificate['inputs_sha256'] == expected_inputs_sha256
                    == continuous.digest(certificate['inputs']), 'INPUT_BINDING_CHANGED')
    integer.require(certificate['anchor_sha256'] == expected_anchor_sha256
                    == continuous.digest(certificate['anchor']), 'ANCHOR_BINDING_CHANGED')
    rebuilt = build(inputs=certificate['inputs'], anchor=certificate['anchor'],
                    incumbent=certificate['incumbent'], max_tail_points=certificate['max_tail_points'])
    integer.require(continuous.canonical(rebuilt) == continuous.canonical(certificate),
                    'DOMAIN_COMPLETION_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_FULL_ROOT_VALUE_COVERAGE' if rebuilt['objective_value_covered']
                else 'VERIFIED_UNRESOLVED_TAIL', objective_value_covered=rebuilt['objective_value_covered'],
                tie_break_optimality_established=False, optimizer_calls=0)
