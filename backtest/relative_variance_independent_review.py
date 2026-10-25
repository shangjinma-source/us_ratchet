"""Independent relative-variance target proof and existing cash/risk replay."""
from datetime import date
from fractions import Fraction as F
from hashlib import sha256
import json
from unittest.mock import patch

from backtest import capped_frontier_independent_review as frontier

_review_v27 = frontier.review_selection
METHOD = 'V27_RELATIVE_VARIANCE21_252_MONTHLY_RESEARCH_V1'


def canonical(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def encoded(value):
    return dict(numerator_hex=format(value.numerator, 'x'), denominator_hex=format(value.denominator, 'x'))


def variance(values):
    n = len(values)
    return sum((x*x for x in values), F(0))/(n-1) - sum(values, F(0))**2/(n*(n-1))


def review_selection(selection, window):
    original = selection['v27_selection']
    proof = _review_v27(original, rerank_enabled=True)
    args = original['raw_selection']['binding']['search_arguments']
    day = args['decision_date']
    days = window['training_dates']
    require(window.get('decision_date', window.get('decision_cutoff')) == day,
            'RISK_WINDOW_DATE')
    require(len(days) == 253 and days == sorted(set(days)) and days[-1] == day
            and all(date.fromisoformat(d).isoformat() == d and d <= day for d in days), 'RISK_DATES')
    require(args['scenario_dates'] == days[21::21] and len(args['training_scenarios']) == 12,
            'RISK_SCENARIO_DATES')
    target = proof['target_quantities']
    positive = {sid: q for sid, q in target.items() if q}
    candidates = [r for r in window['candidates'] if r.get('security_id') in positive]
    by_id = {r['security_id']: r for r in candidates}
    require(len(by_id) == len(candidates) and set(by_id) == set(positive), 'RISK_DOMAIN')
    total = sum((q*F(args['prices'][sid]) for sid, q in positive.items()), F(0))
    returns = [F(0)]*252
    for sid, q in positive.items():
        row = by_id[sid]
        values = [F(v) for v in row['training_close']]
        price = F(args['prices'][sid])
        require(price > 0 and F(row['decision_cost']) == price, 'RISK_PRICE')
        require(len(values) == 253 and all(v > 0 for v in values), 'RISK_CLOSES')
        require([values[i+21]/values[i] for i in range(0,252,21)] ==
                [F(s[sid]) for s in args['training_scenarios']], 'RISK_SCENARIOS')
        for i in range(252):
            returns[i] += q*price/total*(values[i+1]/values[i]-1)
    short, long = variance(returns[-21:]), variance(returns)
    multiplier = F(1) if short == 0 else min(F(1),long/short)
    scaled = {sid: (q*multiplier).numerator//(q*multiplier).denominator for sid,q in target.items()}
    risk = dict(multiplier=encoded(multiplier), short_variance=encoded(short), long_variance=encoded(long),
        multiplier_approx=float(multiplier), exact_encoding='HEX_NUMERATOR_DENOMINATOR',
        short_returns=21, long_returns=252, weighting='CURRENT_V27_STOCK_NOTIONAL_NORMALIZED_NO_CASH_RETURN',
        frequency='MONTHLY_ONLY_NO_INTRAMONTH_RESTORE', zero_short_variance='KEEP_FULL_V27_TARGET',
        rounding='FLOOR_EACH_SHARE', empty_basket=not bool(positive), all_targets_zero=not any(scaled.values()))
    require(selection['relative_risk'] == risk, 'RISK_EXACT_ARITHMETIC')
    require(selection['target_quantities'] == scaled and all(type(q) is int for q in selection['target_quantities'].values()), 'RISK_TARGET')
    require(selection['method'] == METHOD and selection['production_adopted'] is False, 'RISK_METHOD')
    require(selection['raw_selection'] == original['raw_selection'] and
            selection['investable_equity'] == original['investable_equity'], 'RISK_RAW_BINDING')
    require(selection['v27_rerank_decision_id'] == original['rerank_decision_id'] and
            selection['v27_rerank_binding'] == original['rerank_binding'], 'RISK_V27_BINDING')
    require(not any(k in selection for k in ('rerank_audit','rerank_binding','rerank_decision_id',
                                           'base_capped_target_quantities','frontier_reranked_after_cap')), 'STALE_V27_FIELDS')
    binding = dict(schema=METHOD, decision_date=day, v27_selection_sha256=canonical(original),
        training_input_sha256=canonical(dict(dates=days,candidates=sorted(candidates,key=lambda r:r['security_id']))),
        original_target_quantities=target,target_quantities=scaled,relative_risk=risk)
    require(selection['relative_binding'] == binding and selection['relative_decision_id'] == canonical(binding), 'RISK_DECISION_BINDING')
    return dict(proof, target_quantities=scaled)


def review_book(book, assembled, bars, windows):
    """Use only in an isolated worker: the temporary patch is process-local."""
    by_day = windows if isinstance(windows, dict) else {
        w.get('decision_date',w.get('decision_cutoff')):w for w in windows}
    if not isinstance(windows, dict):
        require(len(by_day) == len(windows), 'DUPLICATE_RISK_WINDOWS')
    def selected_review(selection, *, rerank_enabled):
        require(rerank_enabled, 'RISK_REQUIRES_V27')
        day = selection['raw_selection']['decision_date']
        return review_selection(selection, by_day[day])
    with patch.object(frontier, 'review_selection', selected_review):
        result = frontier.review_book(book, assembled, bars, rerank_enabled=True)
    return result
