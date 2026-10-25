"""Fixed saved-basket omission sensitivity; no refit, simulation or trading."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path

from scripts.audit_capped_training_frontier import capped, evaluate, validate_binding
from scripts.explain_capped_frontier_training_gain import growth_factors


def validate_dates(arguments, result, decision_date):
    dates = arguments['scenario_dates']
    if (len(dates) != 12 or len(arguments['training_scenarios']) != 12 or
            dates != sorted(set(dates)) or any(day > decision_date for day in dates) or
            arguments['decision_date'] != decision_date or result['decision_date'] != decision_date):
        raise ValueError('TWELVE_PREDECISION_SCENARIOS_REQUIRED')
    return dates


def omission_ranks(factors, selected):
    if not factors or selected not in factors:
        raise ValueError('SELECTED_BASKET_REQUIRED')
    count = len(factors[selected])
    if count < 2 or any(len(row) != count or any(value <= 0 for value in row)
                        for row in factors.values()):
        raise ValueError('MATCHING_POSITIVE_SCENARIOS_REQUIRED')
    products = {key: math.prod(row) for key, row in factors.items()}
    if products[selected] != max(products.values()):
        raise ValueError('SAVED_FULL_SAMPLE_WINNER_MISMATCH')
    ranks = []
    for index in range(count):
        score = products[selected] / factors[selected][index]
        ranks.append(1 + sum(product / factors[key][index] > score
                             for key, product in products.items()))
    return ranks


def analyze_selection(selection):
    raw = selection['raw_selection']
    arguments = validate_binding(raw)
    dates = validate_dates(arguments, raw['search_result'], raw['decision_date'])
    baskets = {}
    for record in raw['search_result']['best_by_k'].values():
        evaluate(record['quantities'], arguments)
        quantities = capped(record['quantities'], arguments)
        signature = tuple(sorted(quantities.items()))
        evaluate(quantities, arguments)
        baskets[signature] = quantities
    selected = tuple(sorted((sid, quantity) for sid, quantity in
                           selection['target_quantities'].items() if quantity))
    factors = {key: growth_factors(value, arguments) for key, value in baskets.items()}
    ranks = omission_ranks(factors, selected)
    capital = Fraction(arguments['entered_cash'])
    selected_score = evaluate(dict(selected), arguments)
    return dict(decision_date=raw['decision_date'], baskets=len(baskets),
        selected_tickers=[arguments['metadata'][sid]['ticker'] for sid, _ in selected],
        selected_cash_fraction=float(selected_score['residual_cash'] / capital),
        omission_ranks=ranks, scenario_end_dates=dates,
        strict_displacements=sum(rank > 1 for rank in ranks), worst_rank=max(ranks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('books', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    windows = []
    for path in args.books:
        raw = path.read_bytes()
        book = json.loads(raw)
        if book['status'] != 'COMPLETE':
            raise ValueError('COMPLETE_BOOK_REQUIRED')
        rows = [analyze_selection(entry['selection']) for entry in book['provider_audit']
                if entry.get('selection')]
        windows.append(dict(source=str(path), sha256=sha256(raw).hexdigest(), rows=rows,
            decisions=len(rows), unstable_decisions=sum(row['strict_displacements'] > 0 for row in rows),
            strict_displacements=sum(row['strict_displacements'] for row in rows)))
    result = dict(windows=windows, optimization_calls=0, execution_simulations=0,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        limitation='Full-sample-generated fixed candidates: omission sensitivity is not cross-validation, '
                   'probability estimation, new-policy returns or independent data verification.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{key: value[key] for key in
        ('source', 'decisions', 'unstable_decisions', 'strict_displacements')} for value in windows]))


if __name__ == '__main__':
    main()
