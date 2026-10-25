"""Attribute two saved baskets' training score gap; do not search or trade."""
import argparse
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.audit_capped_training_frontier import validate_binding


def growth_factors(quantities, arguments):
    capital = Fraction(arguments['entered_cash'])
    prices = {key: Fraction(value) for key, value in arguments['prices'].items()}
    fee = Fraction(arguments['fee_bps']) / 10000
    if capital <= 0 or fee < 0 or any(value <= 0 for value in prices.values()):
        raise ValueError('POSITIVE_CAPITAL_PRICES_AND_NONNEGATIVE_FEE_REQUIRED')
    if any(key not in prices or type(value) is not int or value < 0
           for key, value in quantities.items()):
        raise ValueError('NONNEGATIVE_INTEGER_QUANTITIES_REQUIRED')
    notional = sum((quantity * prices[key] for key, quantity in quantities.items()), Fraction(0))
    residual = capital - notional * (1 + fee)
    if residual < 0:
        raise ValueError('UNAFFORDABLE_TRAINING_BASKET')
    factors = []
    for scenario in arguments['training_scenarios']:
        if set(scenario) != set(prices) or any(Fraction(value) <= 0 for value in scenario.values()):
            raise ValueError('COMPLETE_POSITIVE_SCENARIO_REQUIRED')
        wealth = residual + sum((quantity * prices[key] * Fraction(scenario[key])
                                 for key, quantity in quantities.items()), Fraction(0))
        factors.append(wealth / capital)
    if len(factors) < 2:
        raise ValueError('AT_LEAST_TWO_SCENARIOS_REQUIRED')
    return factors


def decompose(base_factors, chosen_factors):
    if len(base_factors) != len(chosen_factors) or len(base_factors) < 2:
        raise ValueError('EQUAL_NONTRIVIAL_SCENARIO_LENGTH_REQUIRED')
    if any(value <= 0 for value in base_factors + chosen_factors):
        raise ValueError('POSITIVE_WEALTH_REQUIRED')
    ratios = [chosen / base for chosen, base in zip(chosen_factors, base_factors)]
    ratio = math.prod(ratios)
    logs = [math.log(value.numerator) - math.log(value.denominator) for value in ratios]
    rows = [dict(base_growth=str(base), chosen_growth=str(chosen),
                 log_score_difference=log_value,
                 chosen_strictly_ahead_without_this_scenario=ratio / relative > 1,
                 exact_product_ratio_without_this_scenario=str(ratio / relative))
            for base, chosen, relative, log_value in zip(base_factors, chosen_factors, ratios, logs)]
    return dict(exact_full_product_ratio=str(ratio), full_strict_improvement=ratio > 1,
                mean_log_gain=sum(logs) / len(logs),
                omission_cases_still_strictly_ahead=sum(row['chosen_strictly_ahead_without_this_scenario'] for row in rows),
                scenarios=len(rows), rows=rows)


def analyze_selection(selection):
    arguments = validate_binding(selection['raw_selection'])
    audit = selection['rerank_audit']
    if not audit['strict_improvement']:
        raise ValueError('ONLY_ACTUAL_STRICT_RERANKS_ARE_IN_SCOPE')
    base = growth_factors(selection['base_capped_target_quantities'], arguments)
    chosen = growth_factors(selection['target_quantities'], arguments)
    for key, factors in [('base_product_sha256', base), ('selected_product_sha256', chosen)]:
        product = math.prod(factors)
        identity = sha256(f'{product.numerator:x}/{product.denominator:x}'.encode()).hexdigest()
        if identity != audit[key]:
            raise ValueError('SAVED_EXACT_SCORE_HASH_MISMATCH')
    dates = arguments['scenario_dates']
    if (len(dates) != len(base) or dates != sorted(set(dates))
            or any(day > arguments['decision_date'] for day in dates)):
        raise ValueError('PREDECISION_SCENARIOS_REQUIRED')
    result = decompose(base, chosen)
    if not result['full_strict_improvement']:
        raise ValueError('SAVED_STRICT_IMPROVEMENT_NOT_REPRODUCED')
    for row, day in zip(result['rows'], dates):
        row['scenario_end_date'] = day
    result.update(decision_date=arguments['decision_date'],
                  base_target=selection['base_capped_target_quantities'],
                  chosen_target=selection['target_quantities'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('book', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = args.book.read_bytes()
    book = json.loads(data)
    if book['status'] != 'COMPLETE':
        raise ValueError('COMPLETE_SAVED_BOOK_REQUIRED')
    rows = [analyze_selection(entry['selection']) for entry in book['provider_audit']
            if (entry.get('selection') or {}).get('rerank_audit', {}).get('strict_improvement')]
    report = dict(book=str(args.book), book_sha256=sha256(data).hexdigest(),
                  source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), rows=rows,
                  optimization_calls=0, execution_simulations=0, future_performance_computed=False,
                  limitation='Fixed full-sample baskets only; omission arithmetic is not cross-validation, '
                             'independent evidence, a new ranking policy or a probability estimate')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(report, output, indent=2, ensure_ascii=False)
    print(json.dumps([{key: row[key] for key in ('decision_date', 'mean_log_gain',
                      'omission_cases_still_strictly_ahead', 'scenarios')} for row in rows]))


if __name__ == '__main__':
    main()
