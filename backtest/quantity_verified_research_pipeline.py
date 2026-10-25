"""Unified bounded saved-anchor research path; never a production decision.

Full-input hashes are mandatory. Preserves candidate evidence and every proof
stage, and leaves an explicit frontier when the fixed segment budget expires.
Value coverage does not authenticate data, certify tie breaking, prove returns,
or reverify inherited per-k search coverage. Verification repeats computations.
"""
from copy import deepcopy
from hashlib import sha256

from backtest import quantity_anchor_integer_candidates as candidates
from backtest import quantity_anchor_domain_completion as small_tail
from backtest import quantity_anchor_coupled_completion as coupled
from backtest import quantity_anchor_coupled_continuation as continuation
from backtest import quantity_anchor_partition_completion as partition
from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as core


def _saved(certificate):
    raw = continuous.canonical(certificate)
    return raw, sha256(raw).hexdigest()


def build(*, inputs, anchor, inherited_candidates, expected_inputs_sha256,
          expected_anchor_sha256, expected_inherited_sha256, max_tail_points=10000,
          node_budget=2000, objective_budget=500, max_segments=4):
    core.require(continuous.digest(inputs) == expected_inputs_sha256, 'PIPELINE_INPUT_CHANGED')
    core.require(continuous.digest(anchor) == expected_anchor_sha256, 'PIPELINE_ANCHOR_CHANGED')
    core.require(continuous.digest(inherited_candidates) == expected_inherited_sha256, 'PIPELINE_INHERITED_CHANGED')
    core.require(type(node_budget) is int and 0 < node_budget <= 2000
                 and type(objective_budget) is int and 0 < objective_budget <= 500
                 and type(max_segments) is int and 1 <= max_segments <= 100,
                 'PIPELINE_FIXED_BUDGET_REQUIRED')
    proposal = candidates.generate(inputs=inputs, anchor=anchor, inherited_candidates=inherited_candidates)
    base = small_tail.build(inputs=inputs, anchor=anchor,
                            incumbent=proposal['selected']['quantities'], max_tail_points=max_tail_points)
    base_raw, base_hash = _saved(base)
    sources = dict(base_raw=base_raw, expected_base_sha256=base_hash,
                   expected_inputs_sha256=expected_inputs_sha256, expected_anchor_sha256=expected_anchor_sha256)
    stages = dict(candidates=proposal, base=base, coupled=None, segments=[])
    route = 'SMALL_TAIL'
    selected = base['selected']
    lower, upper = base['lower_product'], base['upper_product']
    complete = base['objective_value_covered']
    if not complete:
        origin = coupled.build(**sources, node_budget=node_budget, objective_budget=objective_budget)
        stages['coupled'] = origin
        route = 'COUPLED'
        selected, lower, upper = origin['selected'], origin['lower_product'], origin['upper_product']
        complete = origin['objective_value_covered']
        if not complete:
            history = []
            if origin['status'] == 'UNRESOLVED_COUPLED_FRONTIER':
                origin_raw, origin_hash = _saved(origin)
                # The initial coupled run is the first segment of the fixed budget.
                for _ in range(max_segments - 1):
                    result = continuation.build(**sources, origin_raw=origin_raw,
                        expected_origin_sha256=origin_hash, history=history,
                        node_budget=node_budget, objective_budget=objective_budget)
                    stages['segments'].append(result)
                    selected = result['delta']['selected_candidate']
                    lower, upper = result['lower_product'], result['upper_product']
                    complete = result['objective_value_covered']
                    if complete:
                        break
                    history.append(_saved(result))
            else:
                core.require(origin['status'] == 'UNRESOLVED_UNSUPPORTED_COUPLED_GEOMETRY', 'UNKNOWN_COUPLED_STATUS')
                route = 'INTEGER_PARTITION'
                # Admission rejected before any coupled traversal; partition gets the budget.
                for _ in range(max_segments):
                    result = partition.build(**sources, history=history, node_budget=node_budget)
                    stages['segments'].append(result)
                    selected = result['selected']
                    lower, upper = result['lower_product'], result['upper_product']
                    complete = result['objective_value_covered']
                    if complete:
                        break
                    history.append(_saved(result))
    return deepcopy(dict(schema='VERIFIED_SAVED_ANCHOR_RESEARCH_PIPELINE_V1',
        binding=dict(inputs_sha256=expected_inputs_sha256, anchor_sha256=expected_anchor_sha256,
                     inherited_sha256=expected_inherited_sha256),
        budgets=dict(max_tail_points=max_tail_points, node_budget=node_budget,
                     objective_budget=objective_budget, max_segments=max_segments),
        route=route, status='VALUE_DOMAIN_COVERED' if complete else 'BUDGET_STOPPED_UNRESOLVED',
        selected=selected, lower_product=lower, upper_product=upper,
        objective_value_covered=complete, stages=stages,
        tie_break_optimality_established=False, inherited_per_k_coverage_reverified=False,
        data_authenticated=False, production_ready=False, optimizer_calls=0, economic_runs=0))


def verify(certificate, **sources):
    rebuilt = build(**sources, **certificate['budgets'])
    core.require(continuous.canonical(rebuilt) == continuous.canonical(certificate), 'PIPELINE_CERTIFICATE_CHANGED')
    return dict(status='VERIFIED_BOUNDED_RESEARCH_PIPELINE',
                objective_value_covered=rebuilt['objective_value_covered'], production_ready=False)
