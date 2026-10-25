"""Research-only integer proposals from a verified, same-input full-box anchor.

Preserves supplied baseline candidates. Does not establish full-domain coverage,
authenticate market data, run an optimizer, read files, or place orders.
"""
from copy import deepcopy
from fractions import Fraction

from backtest import quantity_continuous_anchor_bound as continuous
from backtest import quantity_integer_box_certificate_prototype as integer


VERSION = 'VERIFIED_ANCHOR_TWO_AXIS_INTEGER_PROPOSALS_V1'
MAX_CANDIDATES = 20000


def generate(*, inputs, anchor, inherited_candidates, candidate_limit=20000):
    """Rank feasible proposals by exact product, lower notional, then SID tuple.

    The cap counts all distinct attempted candidates, including rejected issuer
    conflicts. Exceeding it raises; an incomplete candidate set is not returned.
    Caller must separately preserve the inherited search coverage/provenance.
    """
    require = integer.require
    require(type(candidate_limit) is int and 0 < candidate_limit <= MAX_CANDIDATES,
            'CANDIDATE_LIMIT_REQUIRED')
    require(type(inherited_candidates) is list and inherited_candidates, 'INHERITED_CANDIDATES_REQUIRED')
    require(continuous.canonical(anchor['binding']['inputs']) == continuous.canonical(inputs),
            'ANCHOR_INPUT_MISMATCH')
    continuous.verify(anchor, expected_binding_sha256=continuous.digest(anchor['binding']))
    problem = integer.prepare(**inputs)
    identifiers = problem['ids']
    root_box = {sid: [0, int(problem['spendable'] // problem['cost'][sid])] for sid in identifiers}
    require(anchor['binding']['box'] == root_box and not anchor['empty'], 'FULL_ROOT_ANCHOR_REQUIRED')
    floor = {sid: int(Fraction(anchor['repaired_quantities'][sid])) for sid in identifiers}
    axes = sorted(identifiers, key=lambda sid: (
        -Fraction(anchor['repaired_quantities'][sid]) * problem['prices'][sid], sid))[:2]
    seen, feasible, rejected, by_k = set(), [], [], {}

    def evaluate(quantities, inherited=False):
        require(type(quantities) is dict and all(
            sid in root_box and type(q) is int and q >= 0 for sid, q in quantities.items()),
            'INVALID_CANDIDATE_QUANTITIES')
        quantities = {sid: q for sid, q in quantities.items() if q}
        signature = tuple(sorted(quantities.items()))
        if signature in seen:
            return
        require(len(seen) < candidate_limit, 'CANDIDATE_LIMIT_REACHED')
        seen.add(signature)
        try:
            value, _, notional = integer.objective(problem, quantities)
        except ValueError as error:
            if inherited:
                raise
            rejected.append(dict(quantities=quantities, reason=str(error)))
            return
        record = dict(quantities=quantities, product=str(value), notional=str(notional),
                      residual_cash=str(problem['cash']-notional*(1+problem['fee'])))
        rank = (value, -notional, signature)
        feasible.append(record)
        cardinality = len(quantities)
        if cardinality not in by_k or rank > by_k[cardinality][0]:
            by_k[cardinality] = (rank, record)

    def fill(quantities, sid):
        result = dict(quantities)
        remaining = problem['spendable'] - sum(
            (problem['cost'][key]*q for key, q in result.items()), Fraction(0))
        require(remaining >= 0, 'ANCHOR_FLOOR_OVER_BUDGET')
        result[sid] = result.get(sid, 0) + int(remaining // problem['cost'][sid])
        return result

    for quantities in inherited_candidates:
        evaluate(quantities, inherited=True)
    evaluate(floor)
    for sid in identifiers:
        evaluate(fill(floor, sid))
    fixed = {sid: q for sid, q in floor.items() if sid not in axes}
    budget = problem['spendable'] - sum(
        (problem['cost'][sid]*q for sid, q in fixed.items()), Fraction(0))
    for quantity in range(int(budget // problem['cost'][axes[0]]) + 1):
        candidate = dict(fixed)
        candidate[axes[0]] = quantity
        if len(axes) == 2:
            candidate[axes[1]] = int((budget-problem['cost'][axes[0]]*quantity)
                                     // problem['cost'][axes[1]])
        evaluate(candidate)
        for sid in identifiers:
            evaluate(fill(candidate, sid))
    selected = max(by_k.values(), key=lambda item: item[0])[1]
    return deepcopy(dict(
        schema=VERSION, inputs_sha256=continuous.digest(inputs),
        anchor_sha256=continuous.digest(anchor), axes=axes,
        candidate_limit=candidate_limit, unique_attempts=len(seen),
        feasible=feasible, rejected=rejected, selected=selected,
        best_by_k={str(k): item[1] for k, item in sorted(by_k.items())},
        tie_rule='EXACT_PRODUCT_THEN_LOWER_NOTIONAL_THEN_LEXICOGRAPHIC_SID_QUANTITY',
        inherited_coverage_reverified=False, objective_value_optimal=False,
        research_only=True, optimizer_calls=0, economic_runs=0))
