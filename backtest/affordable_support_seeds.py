"""Lazy issuer-exclusive affordable support enumeration; no objective calls."""
from fractions import Fraction


def affordable_support_seeds(*, ordered_sids, metadata, unit_costs, spendable, k):
    """One deterministic integer seed per affordable support of exactly k SIDs.

    Each member starts at one share. Remaining cash is split equally in dollars
    before rounding extra shares down. Pruning uses cheapest remaining issuers,
    not future returns; it cannot remove an affordable support. Enumeration
    completion proves support coverage only, never coverage of all quantities.
    Inputs here are validated by the search caller.
    """
    groups = {}
    for sid in ordered_sids:
        groups.setdefault(metadata[sid]['issuer_id'], []).append(sid)
    groups = list(groups.values())
    cheapest = [min(unit_costs[sid] for sid in members) for members in groups]
    suffix = [sorted(cheapest[index:]) for index in range(len(groups)+1)]

    def visit(start, needed, chosen, cost):
        if needed == 0:
            allowance = (spendable-cost)/k
            yield {sid: 1+int(allowance//unit_costs[sid]) for sid in chosen}
            return
        if len(groups)-start < needed or cost+sum(suffix[start][:needed], Fraction(0)) > spendable:
            return
        for index in range(start, len(groups)-needed+1):
            for sid in groups[index]:
                next_cost = cost+unit_costs[sid]
                if next_cost <= spendable:
                    yield from visit(index+1, needed-1, chosen+(sid,), next_cost)

    if type(k) is not int or k < 1:
        raise ValueError('Positive integer cardinality required')
    yield from visit(0, k, (), Fraction(0))
