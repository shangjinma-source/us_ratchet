"""Fixed monthly 21/252 relative-variance sizing, isolated research only."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json

from scripts.review_relative_volatility_training_inputs import check_series

METHOD = 'V27_RELATIVE_VARIANCE21_252_MONTHLY_RESEARCH_V1'


def canonical_hash(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                            ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def exact_ratio(value):
    """Bound decimal conversion work without weakening exact share rounding."""
    return dict(numerator_hex=format(value.numerator, 'x'),
                denominator_hex=format(value.denominator, 'x'))


def sample_variance(values):
    mean = sum(values, F(0)) / len(values)
    return sum(((value - mean) ** 2 for value in values), F(0)) / (len(values) - 1)


def scale_selection(selection, window):
    """Use completed training prices; preserve raw V27 decision as evidence."""
    arguments = selection['raw_selection']['binding']['search_arguments']
    day = arguments['decision_date']
    if window.get('decision_date', window.get('decision_cutoff')) != day:
        raise ValueError('RELATIVE_RISK_DECISION_BINDING')
    # Validate the date grid even for an all-cash selection.
    check_series(window['training_dates'], ['1'] * 253, day, ['1'] * 12, '1')
    if ('scenario_dates' in arguments and
            arguments['scenario_dates'] != window['training_dates'][21::21]):
        raise ValueError('RELATIVE_RISK_SCENARIO_DATES')
    quantities = selection['target_quantities']
    if any(type(quantity) is not int or quantity < 0 for quantity in quantities.values()):
        raise ValueError('WHOLE_NONNEGATIVE_TARGET_REQUIRED')
    positive = {sid: quantity for sid, quantity in quantities.items() if quantity}
    prices = {sid: F(arguments['prices'][sid]) for sid in positive}
    candidates = [row for row in window['candidates'] if row.get('security_id') in positive]
    by_id = {row['security_id']: row for row in candidates}
    if len(by_id) != len(candidates) or set(by_id) != set(positive):
        raise ValueError('RELATIVE_RISK_HISTORY_DOMAIN')
    total = sum((quantity * prices[sid] for sid, quantity in positive.items()), F(0))
    basket_returns = [F(0)] * 252
    for sid, quantity in positive.items():
        row = by_id[sid]
        if F(row['decision_cost']) != prices[sid]:
            raise ValueError('RELATIVE_RISK_PRICE_BINDING')
        check_series(window['training_dates'], row['training_close'], day,
                     [scenario[sid] for scenario in arguments['training_scenarios']], prices[sid])
        values = [F(value) for value in row['training_close']]
        weight = quantity * prices[sid] / total
        for i in range(252):
            basket_returns[i] += weight * (values[i + 1] / values[i] - 1)
    short = sample_variance(basket_returns[-21:])
    long = sample_variance(basket_returns)
    multiplier = F(1) if short == 0 else min(F(1), long / short)
    scaled = {sid: int(quantity * multiplier) for sid, quantity in quantities.items()}
    result = deepcopy(selection)
    result.update(method=METHOD,
        target_quantities=scaled, v27_selection=deepcopy(selection),
        relative_risk=dict(multiplier=exact_ratio(multiplier), short_variance=exact_ratio(short),
            long_variance=exact_ratio(long), multiplier_approx=float(multiplier),
            exact_encoding='HEX_NUMERATOR_DENOMINATOR', short_returns=21, long_returns=252,
            weighting='CURRENT_V27_STOCK_NOTIONAL_NORMALIZED_NO_CASH_RETURN',
            frequency='MONTHLY_ONLY_NO_INTRAMONTH_RESTORE', zero_short_variance='KEEP_FULL_V27_TARGET',
            rounding='FLOOR_EACH_SHARE', empty_basket=not bool(positive),
            all_targets_zero=not any(scaled.values())),
        production_adopted=False)
    # Old rerank identity describes v27_selection only, not the scaled target.
    result['v27_rerank_decision_id'] = result.pop('rerank_decision_id', None)
    result['v27_rerank_binding'] = result.pop('rerank_binding', None)
    for key in ('rerank_audit', 'base_capped_target_quantities',
                'frontier_reranked_after_cap'):
        result.pop(key, None)  # These describe only the preserved v27_selection.
    binding = dict(schema=METHOD, decision_date=day,
        v27_selection_sha256=canonical_hash(selection),
        training_input_sha256=canonical_hash(dict(
            dates=window['training_dates'], candidates=sorted(candidates, key=lambda row: row['security_id']))),
        original_target_quantities=deepcopy(quantities),
        target_quantities=deepcopy(scaled), relative_risk=deepcopy(result['relative_risk']))
    result.update(relative_binding=binding, relative_decision_id=canonical_hash(binding))
    return result
