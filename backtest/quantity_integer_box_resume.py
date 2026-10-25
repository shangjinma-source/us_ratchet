"""Continue a verified saved research frontier without searching its root again."""
from copy import deepcopy
from fractions import Fraction

from backtest.quantity_integer_box_certificate_prototype import (
    box_bound, objective, prepare, require, verify,
)


def resume(certificate, *, expected_input_sha256, additional_nodes, split_policy='widest'):
    require(type(additional_nodes) is int and additional_nodes >= 0,
            'ADDITIONAL_NODE_BUDGET_REQUIRED')
    require(split_policy in ('widest', 'anchor_impact'), 'UNKNOWN_SPLIT_POLICY')
    verify(certificate, expected_input_sha256=expected_input_sha256)
    result = deepcopy(certificate)
    problem = prepare(**result['inputs'])
    incumbent = result['selected']
    best, _, notional = objective(problem, incumbent)
    rank = lambda quantities, value, cost: (value, -cost, tuple(sorted(quantities.items())))
    best_rank = rank(incumbent, best, notional)
    pending = result['unsearched_frontier']
    ledger = result['coverage_ledger']
    processed = 0
    while pending and processed < additional_nodes:
        node = pending.pop(0)
        processed += 1
        box, bound = node['box'], node['bound']
        if bound['empty']:
            ledger.append(dict(node, terminal='INFEASIBLE'))
            continue
        if Fraction(bound['upper']) < best:
            ledger.append(dict(node, terminal='UPPER_STRICTLY_BELOW_INCUMBENT',
                               incumbent_product=str(best)))
            continue
        axes = [sid for sid in problem['ids'] if box[sid][0] < box[sid][1]]
        if not axes:
            quantities = {sid: box[sid][0] for sid in problem['ids'] if box[sid][0]}
            value, _, cost = objective(problem, quantities)
            if rank(quantities, value, cost) > best_rank:
                incumbent, best = quantities, value
                best_rank = rank(quantities, value, cost)
            ledger.append(dict(node, terminal='EVALUATED', product=str(value)))
            continue
        if split_policy == 'anchor_impact':
            # Ordering only: exact bounds, partition coverage and feasibility
            # are unchanged. No domain is removed by this heuristic.
            _, wealth, _ = objective(problem, incumbent)
            impact = {sid: abs(sum((problem['prices'][sid] *
                      (row[sid] - 1 - problem['fee']) / value
                      for row, value in zip(problem['scenarios'], wealth)), Fraction(0)))
                      * (box[sid][1] - box[sid][0]) for sid in axes}
            axis = min(axes, key=lambda sid: (-impact[sid], sid))
            anchor = incumbent.get(axis, 0)
            midpoint = anchor if box[axis][0] <= anchor < box[axis][1] else sum(box[axis]) // 2
        else:
            axis = min(axes, key=lambda sid: (-(box[sid][1] - box[sid][0]), sid))
            midpoint = sum(box[axis]) // 2
        children = []
        for label, bounds in [('0', [box[axis][0], midpoint]),
                              ('1', [midpoint + 1, box[axis][1]])]:
            child = deepcopy(box)
            child[axis] = bounds
            identifier = node['id'] + label
            pending.append(dict(id=identifier, box=child,
                                bound=box_bound(problem, child, incumbent)))
            children.append(identifier)
        ledger.append(dict(node, terminal='SPLIT', axis=axis,
                           midpoint=midpoint, children=children))
    upper = max([best] + [Fraction(n['bound']['upper']) for n in pending
                          if not n['bound']['empty']])
    result.update(
        selected=incumbent, lower_product=str(best), upper_product=str(upper),
        product_gap=str(upper - best), processed_nodes=len(ledger),
        node_budget=result['node_budget'] + additional_nodes,
        objective_value_optimal=not pending,
        status='NODE_BUDGET_STOPPED_UNRESOLVED' if pending else 'COMPLETE_INTEGER_DOMAIN_COVERAGE',
    )
    verify(result, expected_input_sha256=expected_input_sha256)
    return result
