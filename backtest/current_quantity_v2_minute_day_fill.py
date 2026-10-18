"""Conditional minute DAY fill proposal; no ledger IO or real-fill assertion."""
from datetime import datetime, timedelta, timezone
from fractions import Fraction

MODEL = 'STRICT_CROSS_FULL_FILL_AT_LIMIT'


def stamp(value):
    if type(value) is not str:
        raise ValueError('AWARE_ISO_TIMESTAMP_REQUIRED')
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError('AWARE_ISO_TIMESTAMP_REQUIRED')
    return result.astimezone(timezone.utc)


def exact(value):
    if type(value) not in (str, int):
        raise ValueError('EXACT_DECIMAL_OR_FRACTION_REQUIRED')
    return Fraction(value)


def evaluate(*, model, order, minutes, observed_through, evaluated_at, fees,
             available_cash, available_shares, event_id, expected_revision):
    """Resources exclude reservations for OTHER orders; SELL proceeds not assumed.

    Only previously unfilled orders are supported; partial fills need a separate
    replay cursor and must not reuse this evaluator from the original acceptance.
    Minutes are [start,end), positive exact OHLC, exactly 60 seconds, sorted,
    unique. An initial partially elapsed minute is outside this model. Coverage
    starts at the next minute boundary, not at any earlier intra-minute touch.
    Synthetic effective time is end-minus-1us; evidence is available only at end.
    This timestamp convention cannot establish real intraminute event ordering.
    """
    if model != MODEL:
        raise ValueError('UNSUPPORTED_FILL_MODEL')
    accepted, close, observed = map(stamp, (order['accepted_at'], order['session_close'], observed_through))
    if accepted >= close or close.second or close.microsecond:
        raise ValueError('INVALID_DAY_BOUNDARY')
    if order['side'] not in ('BUY', 'SELL'):
        raise ValueError('INVALID_SIDE')
    total, filled = order['quantity'], order['filled_quantity']
    if order['closed'] is not None:
        raise ValueError('ORDER_CLOSED')
    if type(total) is not int or type(filled) is not int or not 0 <= filled < total:
        raise ValueError('INVALID_REMAINING_QUANTITY')
    if filled != 0:
        raise ValueError('PARTIALLY_FILLED_ORDER_UNSUPPORTED')
    quantity = total-filled
    if type(available_shares) is not int or available_shares < 0:
        raise ValueError('INVALID_QUANTITY')
    limit, fee, cash = map(exact, (order['limit_price'], fees, available_cash))
    if limit <= 0 or fee < 0 or cash < 0:
        raise ValueError('INVALID_PRICE_FEE_CASH')
    if not all(type(v) is str and v.strip() for v in (event_id, expected_revision, order['order_id'])):
        raise ValueError('EVENT_ID_REVISION_ORDER_REQUIRED')
    if type(minutes) is not list or len(minutes) > 1440:
        raise ValueError('BOUNDED_MINUTE_LIST_REQUIRED')
    parsed = []; previous = None
    for bar in minutes:
        start, end = stamp(bar['start']), stamp(bar['end'])
        if end-start != timedelta(minutes=1) or start.second or start.microsecond or (previous is not None and start <= previous):
            raise ValueError('ORDERED_UNIQUE_COMPLETE_MINUTES_REQUIRED')
        previous = start
        opened, high, low, closed = [exact(bar[k]) for k in ('open','high','low','close')]
        if not 0 < low <= min(opened, closed) <= max(opened, closed) <= high:
            raise ValueError('INVALID_OHLC')
        parsed.append((start,end,low,high))
    first = accepted.replace(second=0,microsecond=0)
    if first < accepted:
        first += timedelta(minutes=1)
    result = dict(model=model, status='UNKNOWN', event_proposal=None, research_only=True,
                  real_fill=False, account_mutated=False, liquidity_verified=False,
                  fee_amount=str(fee), initial_partial_minute_excluded=first!=accepted,
                  first_eligible_minute=first.isoformat(),
                  effective_from=first.isoformat(),
                  limitations=['Strict cross assumes the entire order fills at its limit; no queue, volume or slippage proof.',
                    'Partial acceptance minute is excluded, not inferred unfilled.',
                    'Synthetic time is minute-end minus one microsecond; evidence is unavailable before minute-end.',
                    'Separate order evaluations cannot reuse hypothetical sell proceeds or shared resources.'])
    def unknown(reason):
        return dict(result, reason=reason)
    if observed > stamp(evaluated_at):
        return unknown('FUTURE_OBSERVATION_BOUNDARY')
    if observed < accepted:
        return unknown('OBSERVATION_BEFORE_ACCEPTANCE')
    if first >= close:
        return unknown('NO_COMPLETE_POST_ACCEPTANCE_MINUTE')
    expected = first
    for start,end,low,high in parsed:
        if start < first:
            continue
        if start >= close or end > observed:
            break
        if start != expected:
            return unknown('MISSING_MINUTE_BEFORE_OUTCOME')
        expected = end
        crossed = low < limit if order['side']=='BUY' else high > limit
        if crossed:
            notional = quantity*limit
            delta = -notional-fee if order['side']=='BUY' else notional-fee
            if (order['side']=='BUY' and cash+delta<0) or (order['side']=='SELL' and (available_shares<quantity or cash+delta<0)):
                return unknown('INSUFFICIENT_EXPLICIT_RESOURCES')
            event = dict(type='FILL', event_id=event_id, expected_revision=expected_revision,
                         order_id=order['order_id'], quantity=quantity, price=str(limit), fees=str(fee),
                         executed_at=(end-timedelta(microseconds=1)).isoformat(), recorded_at=end.isoformat())
            return dict(result,status='SIMULATED_FILL',event_proposal=event,
                        evidence_available_at=end.isoformat(),
                        crossing_interval=dict(start=start.isoformat(),end_exclusive=end.isoformat()),
                        cash_change=str(delta),notional=str(notional))
    if observed >= close and expected == close:
        return dict(result,status='EXPIRE', event_proposal=dict(type='EXPIRE',event_id=event_id,
                    expected_revision=expected_revision,order_id=order['order_id'],recorded_at=close.isoformat()),cash_change='0')
    return unknown('INCOMPLETE_DAY_OR_MISSING_MINUTE')
