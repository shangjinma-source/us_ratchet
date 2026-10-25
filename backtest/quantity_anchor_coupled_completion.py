"""Extend a verified full-root tail with the existing bounded loss iterator.

Unsupported zero-axis/interval geometry stays unresolved with its evidence.
No IO, optimizer, automatic retry, or production authority. A pending prefix
list is retained for a separately verified continuation, not silently rerun.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json

from backtest import quantity_anchor_domain_completion as base_stage
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_coupled_joint_loss_iterator as coupled
from backtest import quantity_coupled_frontier_partition as frontier_partition
from backtest import quantity_integer_box_certificate_prototype as integer
from backtest import quantity_joint_anchor_loss as loss


MAX_NODES = 5000
MAX_OBJECTIVES = 500


def build(*, base_raw, expected_base_sha256, expected_inputs_sha256,
          expected_anchor_sha256, node_budget=MAX_NODES, objective_budget=MAX_OBJECTIVES):
    require = integer.require
    require(type(base_raw) is bytes and sha256(base_raw).hexdigest() == expected_base_sha256,
            'BASE_RAW_CHANGED')
    require(type(node_budget) is int and 0 <= node_budget <= MAX_NODES
            and type(objective_budget) is int and 0 <= objective_budget <= MAX_OBJECTIVES,
            'FIXED_COUPLED_BUDGET_REQUIRED')
    base = json.loads(base_raw)
    base_stage.verify(base, expected_inputs_sha256=expected_inputs_sha256,
                      expected_anchor_sha256=expected_anchor_sha256)
    result = dict(schema='ANCHOR_FULL_ROOT_COUPLED_COMPLETION_V1',
        binding=dict(base_sha256=expected_base_sha256, inputs_sha256=expected_inputs_sha256,
                     anchor_sha256=expected_anchor_sha256), node_budget=node_budget,
        objective_budget=objective_budget, status='BASE_ALREADY_COMPLETE',
        objective_value_covered=base['objective_value_covered'], selected=deepcopy(base['selected']),
        lower_product=base['lower_product'], upper_product=base['upper_product'],
        admission=None, loss=None, coupled=None, tie_break_optimality_established=False,
        data_authenticated=False, optimizer_calls=0, economic_runs=0)
    if base['objective_value_covered']:
        return result
    anchor, fixed, tail = base['anchor'], base['fixing'], base['tail']
    require(base['selected'] == base['incumbent'] and base['enumeration'] is None,
            'UNEXPECTED_UNRESOLVED_BASE')
    problem = integer.prepare(**base['inputs'])
    bound = tail['remaining_bound']['anchor']
    fractional = [sid for sid, q in bound['linear_extreme'].items() if F(q).denominator != 1]

    def unsupported(reason):
        result.update(status='UNRESOLVED_UNSUPPORTED_COUPLED_GEOMETRY')
        result['admission'] = dict(result['admission'] or {}, admitted=False, reason=reason)
        return result

    if len(fractional) != 1:
        return unsupported('UNIQUE_FRACTIONAL_KNAPSACK_AXIS_REQUIRED')
    sid = fractional[0]
    multiplier = F(bound['linear_coefficients'][sid])/problem['cost'][sid]
    if multiplier <= 0:
        return unsupported('POSITIVE_LAMBDA_REQUIRED')
    evidence = loss.build(inputs=base['inputs'], box=tail['remaining_box'],
        anchor_quantities=anchor['repaired_quantities'], incumbent=base['incumbent'],
        dual_lambda=str(multiplier))
    result['loss'] = evidence
    zero_axes = [key for key in problem['ids'] if tail['remaining_box'][key][0]
        < tail['remaining_box'][key][1] and F(evidence['reduced_coefficients'][key]) == 0]
    width = F(evidence['strict_loss_budget'])/(multiplier*problem['cost'][sid])
    result['admission'] = dict(marginal_sid=sid, zero_axes=zero_axes, strict_interval_width=str(width))
    if zero_axes != [sid]:
        return unsupported('EXACTLY_ONE_ACTIVE_ZERO_AXIS_REQUIRED')
    if not 0 < width < 1:
        return unsupported('STRICT_INTERVAL_WIDTH_BELOW_ONE_REQUIRED')
    result['admission'].update(admitted=True, reason=None)
    anchor_raw = continuous.canonical(anchor)
    fixing_raw = continuous.canonical(fixed)
    tail_raw = continuous.canonical(tail)
    loss_raw = continuous.canonical(evidence)
    target_id = 'FULL_ROOT_REMAINING_TAIL'
    parent = dict(new_rows=[dict(id=target_id, certificate_sha256=sha256(tail_raw).hexdigest())],
        lower_product=tail['lower_product'], integer_selected_unchanged=base['incumbent'],
        inherited_closed_rows=fixed['closed_regions'], inherited_fixing_rows=fixed['rows'])
    parent_raw = continuous.canonical(parent)
    sources = dict(parent_report_raw=parent_raw, expected_parent_report_sha256=sha256(parent_raw).hexdigest(),
        target_id=target_id, tail_raw=tail_raw, expected_tail_sha256=sha256(tail_raw).hexdigest(),
        tail_sources=dict(fixing_raw=fixing_raw, expected_fixing_sha256=sha256(fixing_raw).hexdigest(),
            fixing_sources=dict(anchor_raw=anchor_raw, expected_anchor_sha256=sha256(anchor_raw).hexdigest(),
                expected_anchor_binding_sha256=anchor['binding_sha256'], incumbent=base['incumbent'])),
        loss_raw=loss_raw, expected_loss_sha256=sha256(loss_raw).hexdigest(),
        expected_loss_binding_sha256=evidence['binding_sha256'])
    certificate = coupled.build(node_budget=node_budget, objective_budget=objective_budget, **sources)
    frontier_partition.verify(certificate)
    complete = certificate['domain_complete']
    value = F(certificate['candidate_product'])
    require(value == integer.objective(problem, certificate['selected_candidate'])[0]
            and F(base['lower_product']) <= value <= F(base['upper_product']),
            'COUPLED_VALUE_OUTSIDE_VERIFIED_BASE_BOUND')
    result.update(status='COVERED_BY_COUPLED_TAIL' if complete else 'UNRESOLVED_COUPLED_FRONTIER',
        coupled=certificate, objective_value_covered=complete, selected=certificate['selected_candidate'],
        lower_product=str(value), upper_product=str(value if complete else F(base['upper_product'])))
    return result


def verify(certificate, **sources):
    rebuilt = build(node_budget=certificate['node_budget'],
                    objective_budget=certificate['objective_budget'], **sources)
    integer.require(continuous.canonical(rebuilt) == continuous.canonical(certificate),
                    'COUPLED_COMPLETION_CHANGED')
    return dict(status='VERIFIED_COUPLED_FULL_ROOT_EXTENSION',
                objective_value_covered=rebuilt['objective_value_covered'],
                tie_break_optimality_established=False, optimizer_calls=0)
