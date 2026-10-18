"""Independent saved-output arithmetic only. Never import or invoke search."""
import argparse
import hashlib
import json
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_candidate(candidate, arguments):
    quantities = candidate['quantities']
    prices = {sid: Fraction(value) for sid, value in arguments['prices'].items()}
    metadata = arguments['metadata']
    require(set(quantities) <= set(prices), 'Unknown selected SID')
    require(all(type(q) is int and q > 0 for q in quantities.values()), 'Nonpositive/noninteger quantity')
    require(candidate['actual_k'] == len(quantities), 'Wrong actual k')
    require(len({metadata[sid]['issuer_id'] for sid in quantities}) == len(quantities), 'Duplicate issuer')
    cash = Fraction(arguments['entered_cash'])
    fee_rate = Fraction(arguments['fee_bps']) / 10000
    notional = sum((prices[sid] * q for sid, q in quantities.items()), Fraction(0))
    fees = notional * fee_rate
    remaining = cash - notional - fees
    require(remaining >= 0, 'Overspent budget')
    require(not quantities or remaining >= Fraction(arguments['minimum_cash_buffer']), 'Cash buffer violation')
    for field, value in [('notional', notional), ('fees', fees), ('residual_cash', remaining), ('cash_fraction', remaining/cash)]:
        require(Fraction(candidate[field]) == value, 'Incorrect ' + field)
    expected_weights = {sid: prices[sid] * q / cash for sid, q in quantities.items()}
    require({sid: Fraction(v) for sid, v in candidate['actual_weights'].items()} == expected_weights, 'Incorrect actual weights')
    require(sum(expected_weights.values()) + remaining/cash + fees/cash == 1, 'Wealth conservation failure')
    product = Fraction(1)
    growths = []
    for scenario in arguments['training_scenarios']:
        gross = (remaining + sum((prices[sid] * q * Fraction(scenario[sid]) for sid, q in quantities.items()), Fraction(0))) / cash
        require(gross > 0, 'Nonpositive scenario wealth')
        product *= gross
        growths.append(gross)
    with localcontext() as context:
        context.prec = 70
        independent_score = sum((Decimal(g.numerator)/Decimal(g.denominator)).ln() for g in growths) / len(growths)
    error = abs(Decimal(str(candidate['training_mean_net_log_wealth'])) - independent_score)
    require(error <= Decimal('1e-12'), 'Mean log wealth differs from independent Decimal arithmetic')
    omitted = max(product.numerator.bit_length(), product.denominator.bit_length()) > 4096
    require(candidate['large_exact_product_serialization_omitted'] is omitted, 'Incorrect product omission flag')
    if omitted:
        require(candidate['training_gross_growth_product'] is None, 'Expected omitted huge product')
    else:
        require(Fraction(candidate['training_gross_growth_product']) == product, 'Exact gross product mismatch')
    require(candidate['issuer_unique'] is True and candidate['budget_conservation_exact'] is True and candidate['exact_product_comparison'] is True,
            'Candidate constraint flags differ')
    return (product, -notional, tuple(sorted(quantities.items()))), error


def check_window(window, result):
    arguments = window['search_arguments']
    require(result['decision_date'] == window['decision_cutoff'] == arguments['decision_date'], 'Decision mismatch')
    require(result['scenario_dates'] == arguments['scenario_dates'], 'Scenario dates mismatch')
    require(len(arguments['training_scenarios']) == len(arguments['scenario_dates']) == 12, 'Twelve scenarios required')
    require(arguments['scenario_dates'] == sorted(set(arguments['scenario_dates'])) and max(arguments['scenario_dates']) <= arguments['decision_date'], 'Future or unordered scenario')
    require(set(arguments['prices']) == set(arguments['metadata']) and all(set(s) == set(arguments['prices']) for s in arguments['training_scenarios']), 'Scenario/domain mismatch')
    require(all(Fraction(v) > 0 for v in arguments['prices'].values()) and all(Fraction(v) > 0 for s in arguments['training_scenarios'] for v in s.values()), 'Nonpositive training value')
    for name in ('entered_cash', 'fee_bps', 'minimum_cash_buffer'):
        require(Fraction(result[name]) == Fraction(arguments[name]), 'Policy mismatch: ' + name)
    require(Fraction(arguments['entered_cash']) == 20000 and Fraction(arguments['fee_bps']) == 0 and Fraction(arguments['minimum_cash_buffer']) == 0, 'Registered fixed policy differs')
    require(result['max_objective_evaluations'] == arguments['max_objective_evaluations'] == 8192, 'Evaluation budget differs')
    require(0 < result['objective_evaluations'] <= 8192, 'Evaluation count invalid')
    issuer_costs = {}
    for sid, value in arguments['prices'].items():
        issuer = arguments['metadata'][sid]['issuer_id']
        cost = Fraction(value) * (1 + Fraction(arguments['fee_bps'])/10000)
        issuer_costs[issuer] = min(issuer_costs.get(issuer, cost), cost)
    cheapest = sorted(issuer_costs.values())
    require([r['k'] for r in result['per_k']] == list(range(1, len(cheapest)+1)), 'Per-k domain incomplete')
    affordable = []
    for row in result['per_k']:
        minimum = sum(cheapest[:row['k']], Fraction(0))
        available = minimum <= Fraction(arguments['entered_cash']) - Fraction(arguments['minimum_cash_buffer'])
        require(Fraction(row['minimum_purchase_cost']) == minimum, 'Incorrect issuer affordability bound')
        require(row['structural_status'] == ('AFFORDABLE' if available else 'UNAFFORDABLE_CHEAPEST_ISSUER_BOUND'), 'Structural status differs')
        require(row['global_optimum_established'] is False, 'Unproven global claim')
        if available:
            affordable.append(str(row['k']))
            require(row['initialized'] is True and row['visited_states'] >= row['visited_supports'] > 0, 'Affordable k not evaluated')
        else:
            require(row['visited_states'] == row['visited_supports'] == 0 and row['initialized'] is False, 'Unaffordable k visited')
    require(set(result['best_by_k']) == {'0', *affordable}, 'Available per-k candidates missing or extra')
    ranks, errors = {}, []
    for k, candidate in result['best_by_k'].items():
        require(candidate['actual_k'] == int(k), 'Per-k candidate mislabeled')
        ranks[k], error = check_candidate(candidate, arguments)
        errors.append(error)
    selected_rank, error = check_candidate(result['selected'], arguments)
    errors.append(error)
    winner = max(ranks, key=ranks.get)
    require(result['selected'] == result['best_by_k'][winner] and selected_rank == ranks[winner], 'Selection not best available exact product/tie result')
    require(result['objective_evaluations'] == 1 + sum(r['visited_states'] for r in result['per_k']), 'Visited-state count differs')
    require(result['global_optimum_established'] is False and result['research_only'] is True and result['orders_created'] is False and result['initial_positions'] == {}, 'Research safety boundary differs')
    require(result['all_affordable_k_initialized'] is True and result['forecast_return'] is None, 'Incorrect initialization/forecast flag')
    return dict(decision=window['decision_cutoff'], status='PASS', available_candidates_checked=len(ranks),
                selected_k=int(winner), selected_quantities=result['selected']['quantities'],
                residual_cash=result['selected']['residual_cash'], objective_evaluations=result['objective_evaluations'],
                maximum_mean_log_absolute_error=str(max(errors)), global_optimality_proven=False)


def readback(directory):
    directory = Path(directory)
    require((directory/'result.json').exists(), 'Terminal result required; no partial readback or polling')
    require(not (directory/'failure.json').exists(), 'Run has a failure receipt')
    pins = {}

    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT/path
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(expected is None or digest == expected, 'Changed source: ' + str(path))
        pins[str(path)] = digest
        return raw

    registration = json.loads(read(directory/'registration.json'))
    terminal = json.loads(read(directory/'result.json'))
    require(terminal['status'] == 'COMPLETE_BOUNDED_HISTORICAL_SEARCHES_NOT_OUTCOME_VALIDATION' and terminal['search_calls'] == 12 and terminal['book_calls'] == 0, 'Not completed twelve-search terminal')
    require(terminal['global_optimality_proven'] is False and terminal['adoption_allowed'] is False, 'Terminal boundary differs')
    training = json.loads(read(registration['input_path'], registration['input_sha256']))
    for path, digest in training['source_hashes'].items():
        read(path, digest)
    require([w['decision_cutoff'] for w in training['windows']] == registration['decisions'] == [w['decision_cutoff'] for w in terminal['windows']] and len(terminal['windows']) == 12, 'Window schedule mismatch')
    output = []
    for frozen, summary in zip(training['windows'], terminal['windows']):
        folder = directory/frozen['decision_cutoff']
        window = json.loads(read(folder/'inputs.json'))
        result = json.loads(read(folder/'search.json'))
        require(window == frozen, 'Run input differs from registered frozen input')
        require(summary['selected'] == result['selected'] and summary['status'] == result['status'], 'Terminal summary differs')
        output.append(check_window(window, result))
    protected = json.loads(read(directory/'protected_after.json'))
    require(protected['unchanged'] is True and protected['hashes'] == registration['protected_before'], 'Protected-file receipt differs')
    read(__file__)
    return dict(status='PASS_INDEPENDENT_SAVED_SEARCH_ARITHMETIC', windows=output, source_hashes=pins,
                search_calls=0, book_calls=0, independent_decimal_precision=70, mean_log_tolerance='1e-12',
                limitation='Only emitted best-by-k and selected arithmetic verified; no claim about unrecorded states or global optimum.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    require(not destination.exists() and (ROOT/'tmp').resolve() in destination.parents, 'Create-only tmp receipt required')
    result = readback(args.directory)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(dict(status=result['status'], windows=len(result['windows']), search_calls=0, book_calls=0)))
