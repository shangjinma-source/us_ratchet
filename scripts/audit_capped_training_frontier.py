"""Rescore only saved baskets before/after the current 50% sizing overlay.

No new basket generator, optimizer or execution simulation is called. A better
training score is not future performance or proof of a constrained optimum.
"""
import argparse
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def evaluate(quantities, arguments):
    cash = F(arguments['entered_cash'])
    fee = F(arguments['fee_bps']) / 10000
    buffer = F(arguments['minimum_cash_buffer'])
    prices = {sid: F(value) for sid, value in arguments['prices'].items()}
    if cash <= 0 or fee < 0 or buffer < 0 or any(value <= 0 for value in prices.values()):
        raise ValueError('Invalid training capital, cost or prices')
    if any(sid not in prices or type(quantity) is not int or quantity <= 0
           for sid, quantity in quantities.items()):
        raise ValueError('Invalid integer basket')
    issuers = [arguments['metadata'][sid]['issuer_id'] for sid in quantities]
    if len(set(issuers)) != len(issuers):
        raise ValueError('Duplicate issuer')
    notional = sum((quantity * prices[sid] for sid, quantity in quantities.items()), F(0))
    residual = cash - notional * (1 + fee)
    if residual < 0 or (quantities and residual < buffer):
        raise ValueError('Basket is not affordable')
    scenarios = arguments['training_scenarios']
    if not scenarios:
        raise ValueError('Nonempty training scenarios required')
    growth = []
    for scenario in scenarios:
        if set(scenario) != set(prices) or any(F(value) <= 0 for value in scenario.values()):
            raise ValueError('Invalid training scenario')
        wealth = residual + sum((quantity * prices[sid] * F(scenario[sid])
                                 for sid, quantity in quantities.items()), F(0))
        growth.append(wealth / cash)
    return dict(product=math.prod(growth), notional=notional, residual_cash=residual,
                mean_log=sum(math.log(value.numerator) - math.log(value.denominator)
                             for value in growth) / len(growth))


def capped(quantities, arguments):
    cash = F(arguments['entered_cash'])
    result = {sid: min(quantity, int(cash / (2 * F(arguments['prices'][sid]))))
              for sid, quantity in quantities.items()}
    return {sid: quantity for sid, quantity in result.items() if quantity}


def validate_binding(raw):
    """Check internal saved provenance; this does not authenticate market data."""
    binding, result = raw['binding'], raw['search_result']
    identity = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    if raw['decision_id'] != identity or raw['research_id'] != identity[:24]:
        raise ValueError('Saved decision hash mismatch')
    arguments = binding['search_arguments']
    if (binding['decision_date'] != raw['decision_date']
            or binding['state_revision'] != raw['state_revision']
            or F(binding['reserved_cash']) != 0
            or F(binding['available_cash']) != F(raw['available_cash'])
            or F(binding['available_cash']) < 0):
        raise ValueError('Saved account binding mismatch')
    marks = binding['valuation_quotes']
    for sid, quote in marks.items():
        if (quote['as_of'] != raw['decision_date'] or F(quote['price']) <= 0
                or not quote['source_references']
                or any(path not in binding['source_hashes'] for path in quote['source_references'])):
            raise ValueError('Saved quote binding mismatch')
    if any(type(quantity) is not int or quantity < 0 for quantity in binding['shares'].values()):
        raise ValueError('Saved account quantity mismatch')
    holdings = {sid: quantity * F(marks[sid]['price']) for sid, quantity in binding['shares'].items() if quantity}
    capital = F(binding['available_cash']) + sum(holdings.values(), F(0))
    if (capital != F(binding['investable_equity']) or capital != F(raw['investable_equity'])
            or capital != F(arguments['entered_cash'])
            or holdings != {sid: F(value) for sid, value in raw['holding_market_values'].items()}):
        raise ValueError('Saved account equity does not reconcile')
    if any(F(price) != F(marks[sid]['price']) for sid, price in arguments['prices'].items()):
        raise ValueError('Training price differs from account mark')
    if (result['objective'] != 'TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH'
            or result['fee_scope'] != 'INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION'
            or result['initial_positions'] != {} or result['scenario_dates'] != arguments['scenario_dates']
            or any(F(result[key]) != F(arguments[key]) for key in ('fee_bps', 'entered_cash', 'minimum_cash_buffer'))):
        raise ValueError('Saved objective context mismatch')
    return arguments


def audit_selection(selection):
    raw = selection['raw_selection']
    arguments, result = validate_binding(raw), raw['search_result']
    if arguments['decision_date'] != raw['decision_date'] or result['decision_date'] != raw['decision_date']:
        raise ValueError('Decision binding mismatch')
    dates = arguments['scenario_dates']
    if (dates != sorted(set(dates)) or len(dates) != len(arguments['training_scenarios'])
            or any(day > raw['decision_date'] for day in dates)):
        raise ValueError('Training dates must precede the decision')
    chosen = result['selected']['quantities']
    if chosen != raw['target_quantities'] or F(raw['investable_equity']) != F(arguments['entered_cash']):
        raise ValueError('Raw selection capital or quantities mismatch')
    actual = {sid: quantity for sid, quantity in selection['target_quantities'].items() if quantity}
    if capped(chosen, arguments) != actual:
        raise ValueError('Saved policy target is not the declared 50 percent overlay')
    chosen_score, actual_score = evaluate(chosen, arguments), evaluate(actual, arguments)
    frontier = result['best_by_k']
    raw_signatures, capped_signatures, stronger = set(), set(), []
    for key, record in frontier.items():
        quantities = record['quantities']
        if int(key) != len(quantities):
            raise ValueError('Saved cardinality differs from its basket')
        score = evaluate(quantities, arguments)
        if (F(record['notional']) != score['notional']
                or F(record['fees']) != score['notional'] * F(arguments['fee_bps']) / 10000
                or F(record['residual_cash']) != score['residual_cash']
                or not math.isclose(record['training_mean_net_log_wealth'], score['mean_log'], abs_tol=1e-12)):
            raise ValueError('Saved training record does not reconcile')
        saved_product = record.get('training_gross_growth_product')
        if saved_product is not None and F(saved_product) != score['product']:
            raise ValueError('Saved exact training product differs')
        if score['product'] > chosen_score['product']:
            raise ValueError('Selected raw basket is not best in saved frontier')
        raw_signatures.add(tuple(sorted(quantities.items())))
        reduced = capped(quantities, arguments)
        signature = tuple(sorted(reduced.items()))
        if signature in capped_signatures:
            continue
        capped_signatures.add(signature)
        reduced_score = evaluate(reduced, arguments)
        if reduced_score['product'] > actual_score['product']:
            stronger.append((reduced_score['product'], dict(quantities=reduced,
                source_cardinality=int(key), training_mean_log=reduced_score['mean_log'],
                residual_cash=str(reduced_score['residual_cash']))))
    if tuple(sorted(chosen.items())) not in raw_signatures:
        raise ValueError('Selected basket missing from saved frontier')
    if result['selected'] != frontier[str(len(chosen))]:
        raise ValueError('Selected record differs from the saved cardinality frontier')
    alternative = max(stronger, key=lambda item: item[0])[1] if stronger else None
    names = {sid: metadata['ticker'] for sid, metadata in arguments['metadata'].items()}
    return dict(decision_date=raw['decision_date'], saved_unique_baskets=len(raw_signatures),
        distinct_capped_baskets=len(capped_signatures), saved_stronger_capped_baskets=len(stronger),
        original_quantities=chosen, implemented_quantities=actual,
        original_training_mean_log=chosen_score['mean_log'], implemented_training_mean_log=actual_score['mean_log'],
        implemented_cash_fraction=str(actual_score['residual_cash'] / F(arguments['entered_cash'])),
        better_saved_capped_example=alternative,
        tickers={sid: names[sid] for sid in set(chosen) | set((alternative or {}).get('quantities', {}))},
        future_return=None, new_generated_baskets=0, execution_simulations=0)


def analyze_path(path):
    source = Path(path)
    data = source.read_bytes()
    book = json.loads(data)
    if book['status'] != 'COMPLETE':
        raise ValueError('Complete saved book required')
    rows = [audit_selection(audit['selection']) for audit in book['provider_audit'] if audit.get('selection')]
    return dict(source=str(source), sha256=hashlib.sha256(data).hexdigest(), decisions=len(rows),
        decisions_with_better_saved_capped_basket=sum(row['saved_stronger_capped_baskets'] > 0 for row in rows),
        rows=rows, new_generated_baskets=0, execution_simulations=0,
        limitation='Rescoring the existing frontier only; not a new policy backtest, global optimum or prediction')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('books', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = [analyze_path(path) for path in args.books]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{key: row[key] for key in ('source', 'decisions', 'decisions_with_better_saved_capped_basket')}
                      for row in result]))


if __name__ == '__main__':
    main()
