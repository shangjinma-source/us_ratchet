"""Describe risk estimates on saved V27 baskets; never simulate a new portfolio."""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import variance

from scripts.audit_capped_training_frontier import validate_binding
from scripts.review_relative_volatility_training_inputs import check_series


def multipliers(returns):
    if len(returns) != 252 or any(not math.isfinite(value) for value in returns):
        raise ValueError('FINITE_252_RETURNS_REQUIRED')
    short, long = variance(returns[-21:]), variance(returns)
    twenty = variance(returns[-20:])
    return dict(short_variance=short, long_variance=long,
        relative_multiplier=1.0 if short == 0 else min(1.0, long / short),
        old_fixed20_multiplier=1.0 if twenty == 0 else min(1.0, .2 / math.sqrt(252 * twenty)))


def analyze(book, prepared):
    if book['status'] != 'COMPLETE':
        raise ValueError('COMPLETE_V27_EQUIVALENT_BOOK_REQUIRED')
    windows = {window.get('decision_date', window.get('decision_cutoff')): window
               for window in prepared['windows']}
    rows = []
    for entry in book['provider_audit']:
        selection = entry.get('selection')
        if not selection:
            continue
        raw = selection['raw_selection']
        arguments = validate_binding(raw)
        day = raw['decision_date']
        window = windows[day]
        quantities = {sid: quantity for sid, quantity in selection['target_quantities'].items() if quantity}
        candidates = {row['security_id']: row for row in window['candidates']
                      if row.get('security_id') in quantities}
        prices = {sid: F(arguments['prices'][sid]) for sid in quantities}
        notional = sum((quantities[sid] * prices[sid] for sid in quantities), F(0))
        if not quantities:
            rows.append(dict(decision_date=day, status='EMPTY_BASKET'))
            continue
        paths = {}
        for sid in quantities:
            candidate = candidates[sid]
            if F(candidate['decision_cost']) != prices[sid]:
                raise ValueError('DECISION_COST_BINDING')
            check_series(window['training_dates'], candidate['training_close'], day,
                         [scenario[sid] for scenario in arguments['training_scenarios']], prices[sid])
            values = [F(value) for value in candidate['training_close']]
            paths[sid] = [float(values[i] / values[i - 1] - 1) for i in range(1, 253)]
        weights = {sid: float(quantities[sid] * prices[sid] / notional) for sid in quantities}
        returns = [sum(weights[sid] * paths[sid][i] for sid in quantities) for i in range(252)]
        rows.append(dict(decision_date=day, status='RISK_ESTIMATE_ONLY', **multipliers(returns),
                         base_stock_fraction=float(notional / F(arguments['entered_cash']))))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    paths = [
        ('earlier', 'tmp/capped_earlier_reselection_20261024_v1/cap50_exit20/outcome.json',
         'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'),
        ('later', 'tmp/capped_frontier_rerank_20261025_v2/run_v1/later-candidate.json',
         'tmp/next12_training_prepare_20261014_v1/prepared.json')]
    windows, sources = {}, {}
    for label, book, prepared in paths:
        documents = []
        for path in (book, prepared):
            raw = Path(path).read_bytes()
            sources[path] = sha256(raw).hexdigest()
            documents.append(json.loads(raw))
        windows[label] = analyze(*documents)
    result = dict(windows=windows, input_sha256=sources,
        script_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        optimization_calls=0, execution_simulations=0, future_performance_computed=False,
        limitation='Float risk diagnostics on original V27 quantities, not integer orders or branch returns. '
                   'Current basket projected through past prices is not actual account history. '
                   'No PIT or corporate-action authenticity upgrade.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({key: dict(decisions=len(rows), relative_reductions=sum(
        row.get('relative_multiplier', 1) < 1 for row in rows), old_reductions=sum(
        row.get('old_fixed20_multiplier', 1) < 1 for row in rows)) for key, rows in windows.items()}))


if __name__ == '__main__':
    main()
