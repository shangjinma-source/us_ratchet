"""Audit saved search coverage without running a strategy or modifying its inputs."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path


def support_counts(metadata):
    """Count SID supports with at most one share class per issuer, by size."""
    counts = [1]
    for size in Counter(row['issuer_id'] for row in metadata.values()).values():
        counts.append(0)
        for k in range(len(counts) - 1, 0, -1):
            counts[k] += size * counts[k - 1]
    return counts


def audit_selection(selection):
    arguments = selection['binding']['search_arguments']
    result = selection['search_result']
    prices = {sid: Fraction(str(price)) for sid, price in arguments['prices'].items()}
    metadata = arguments['metadata']
    assert prices.keys() == metadata.keys()
    budget = Fraction(arguments['entered_cash']) - Fraction(str(arguments['minimum_cash_buffer']))
    fee = Fraction(str(arguments['fee_bps'])) / 10000
    costs = {sid: price * (1 + fee) for sid, price in prices.items()}
    cheapest = {}
    for sid, cost in costs.items():
        issuer = metadata[sid]['issuer_id']
        cheapest[issuer] = min(cost, cheapest.get(issuer, cost))
    sorted_costs = sorted(cheapest.values())
    upper = support_counts(metadata)
    assert [row['k'] for row in result['per_k']] == list(range(1, len(cheapest) + 1))
    rows = []
    for saved in result['per_k']:
        k = saved['k']
        minimum = sum(sorted_costs[:k], Fraction(0))
        assert Fraction(saved['minimum_purchase_cost']) == minimum
        affordable = minimum <= budget
        assert (saved['structural_status'] == 'AFFORDABLE') == affordable
        # Any k securities each costing <= budget/k form an affordable support.
        # This is a sufficient condition, NOT an exact denominator for k > 1.
        cheap_metadata = {sid: metadata[sid] for sid, cost in costs.items() if cost * k <= budget}
        cheap_counts = support_counts(cheap_metadata)
        lower = cheap_counts[k] if k < len(cheap_counts) else 0
        visited = saved['visited_supports']
        assert 0 <= visited <= saved['visited_states'] and visited <= upper[k]
        if affordable:
            assert saved['initialized'] and saved['visited_states'] > 0
        else:
            assert not saved['initialized'] and saved['visited_states'] == 0
        rows.append(dict(k=k, affordable=affordable,
                         visited_states=saved['visited_states'], visited_supports=visited,
                         structural_support_upper_bound=str(upper[k]),
                         affordable_support_lower_bound=str(lower),
                         affordable_support_count_exact=(k == 1),
                         proven_unvisited_affordable_support_lower_bound=str(max(0, lower - visited)),
                         search_scope=saved['search_scope']))
    assert sum(row['visited_states'] for row in rows) + 1 == result['objective_evaluations']
    return dict(decision_date=arguments['decision_date'], security_count=len(prices),
                issuer_count=len(cheapest), selected_k=len(selection['target_quantities']),
                stop_reason=result['status'], objective_evaluations=result['objective_evaluations'],
                per_k=rows, global_optimum_established=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    callbacks = json.loads(raw)
    reports = [audit_selection(item['response']['selection']) for item in callbacks
               if item['response'].get('selection') is not None]
    report = dict(status='SAVED_COUNTERS_AND_AFFORDABILITY_BOUNDS_VERIFIED',
                  source=str(args.source.resolve()), source_sha256=hashlib.sha256(raw).hexdigest(),
                  months=reports, search_calls=0, book_calls=0,
                  limitations=['Saved counters are checked, not reconstructed from a full visited-state log.',
                               'Support coverage does not prove quantity or weight coverage.',
                               'Input universe authenticity and point-in-time completeness are not established.',
                               'Bounds concern training search, not future performance.'])
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps([dict(date=row['decision_date'], selected_k=row['selected_k'],
                           single_stock_visited=row['per_k'][0]['visited_supports'],
                           single_stock_feasible=row['per_k'][0]['affordable_support_lower_bound'])
                      for row in reports]))


if __name__ == '__main__':
    main()
