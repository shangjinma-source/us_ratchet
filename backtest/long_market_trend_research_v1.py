"""One fixed monthly QQQ trend rule; isolated research process only."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json
from threading import RLock
from backtest import historical_dividend_frontier_research as frontier

LOCK = RLock()
OFF_SCHEMA = 'QQQ_10_MONTH_OFF_CASH_DECISION_V1'


def signal_proof(record):
    decision = record['decision_date']
    date.fromisoformat(decision)
    rows = record['completed_month_end_prices']
    if len(rows) != 10:
        raise ValueError('TEN_COMPLETED_MONTH_ENDS_REQUIRED')
    dates = [row['date'] for row in rows]
    if dates != sorted(set(dates)) or dates[-1] != decision:
        raise ValueError('SIGNAL_DATE_BINDING')
    ordinals = [date.fromisoformat(day).year * 12 + date.fromisoformat(day).month for day in dates]
    if ordinals != list(range(ordinals[0], ordinals[0]+10)):
        raise ValueError('TEN_CONSECUTIVE_MONTHS_REQUIRED')
    values = []
    for row in rows:
        if isinstance(row['close'], bool) or not row['source']:
            raise ValueError('SIGNAL_PRICE_OR_SOURCE')
        value = Fraction(str(row['close']))
        if value <= 0:
            raise ValueError('POSITIVE_SIGNAL_PRICE_REQUIRED')
        values.append(value)
    average = sum(values) / 10
    return dict(decision_date=decision, rule='QQQ_MONTH_END_CLOSE_GT_10_MONTH_SMA_PRICE',
                completed_month_end_prices=deepcopy(rows), average=str(average),
                last_close=str(values[-1]), risk_on=values[-1] > average)


def off_decision(arguments, proof, signal_source_hashes):
    if proof['risk_on'] or proof['decision_date'] != arguments['decision_date']:
        raise ValueError('OFF_SIGNAL_REQUIRED')
    quotes = {row['security_id']:row for row in arguments['valuation_quotes']}
    account = arguments['account_state']
    capital = Fraction(account['cash']) + sum((quantity * Fraction(quotes[sid]['price'])
        for sid, quantity in account['shares'].items() if quantity), Fraction(0))
    binding = dict(arguments=deepcopy(arguments), signal=deepcopy(proof), signal_source_hashes=deepcopy(signal_source_hashes))
    encoded = json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return dict(schema=OFF_SCHEMA, decision_date=arguments['decision_date'], binding=binding,
                decision_id=sha256(encoded.encode()).hexdigest(), investable_equity=str(capital),
                target_quantities={}, optimizer_calls=0)


def run_trend(*, signals, assembled, signal_source_hashes, decision_callback=None, selector=None, **kwargs):
    """Use a dedicated process: temporary research hooks are restored on exit.

    Existing verified_prefix selection replay is forbidden until it has its own
    signal/account binding verifier. This prevents reusing a baseline account.
    """
    if kwargs.get('verified_prefix'):
        raise ValueError('TREND_PREFIX_REUSE_NOT_IMPLEMENTED')
    if set(signals) != {p['decision_date'] for p in assembled['monthly_inputs']}:
        raise ValueError('EXACT_DECISION_SIGNAL_DOMAIN_REQUIRED')
    proofs = {day:signal_proof(record) for day,record in signals.items()}
    for plan in assembled['monthly_inputs']:
        for row in proofs[plan['decision_date']]['completed_month_end_prices']:
            if row['source'] not in signal_source_hashes:
                raise ValueError('SIGNAL_SOURCE_NOT_PINNED')
    with LOCK:
        original_decide, original_rerank = frontier.decide_continuous_guided_for_account, frontier.rerank
        counts = dict(on_optimizer_calls=0, off_decisions=0)
        current_arguments = {}
        def decide(**arguments):
            current_arguments[arguments['decision_date']] = deepcopy(arguments)
            proof = proofs[arguments['decision_date']]
            if not proof['risk_on']:
                counts['off_decisions'] += 1
                return off_decision(arguments, proof, signal_source_hashes)
            counts['on_optimizer_calls'] += 1
            return (selector or original_decide)(**arguments)
        def rerank(raw):
            if raw.get('schema') == OFF_SCHEMA:
                result = raw
                arguments = raw['binding']['arguments']
            else:
                result = original_rerank(raw)
                result['trend_signal'] = deepcopy(proofs[raw['decision_date']])
                result['trend_signal_source_hashes'] = deepcopy(signal_source_hashes)
                arguments = current_arguments[raw['decision_date']]
            if decision_callback is not None:
                decision_callback(deepcopy(arguments), deepcopy(result))
            return result
        try:
            frontier.decide_continuous_guided_for_account, frontier.rerank = decide, rerank
            result = frontier.run_frontier_capped_next_open(assembled=assembled, **kwargs)
        finally:
            frontier.decide_continuous_guided_for_account, frontier.rerank = original_decide, original_rerank
    result['trend_diagnostics'] = dict(counts, rule='QQQ_MONTH_END_CLOSE_GT_10_MONTH_SMA_PRICE',
        note='Wrapper new_searches counts decision callbacks; only on_optimizer_calls are optimizer invocations.')
    return result
