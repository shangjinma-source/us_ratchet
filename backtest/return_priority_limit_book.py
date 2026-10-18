"""Pure DAY-limit order accounting; touching a price is an explicit fill assumption."""
from fractions import Fraction
from copy import deepcopy


def number(value, positive=False):
    if isinstance(value, bool):
        raise ValueError('Boolean amount')
    value = Fraction(str(value))
    if value < 0 or positive and not value:
        raise ValueError('Invalid amount')
    return value


def quantity(value):
    if type(value) is not int or value < 0:
        raise ValueError('Nonnegative integer shares required')
    return value


def run_limit_book(*, session_dates, orders=None, ohlc, initial_cash,
                   initial_shares=None, events=(), fee_bps='0', order_provider=None):
    """First session is initial close; process subsequent sessions through last.

    orders: id/security_id/decision_date/active_date/side/quantity/limit.
    ohlc: {sid: {date: {open, high, low, close}}}. Events: date/security_id/
    type/source_references, plus split new_shares/old_shares or merger share_cash.
    All cash and prices in one currency. No strategy, IO, broker or search calls.
    Every order's limit and quantity MUST use decision_date nominal share units;
    caller must not pre-adjust for an active-date split. This engine applies
    intervening split events once before orders can trade. Every order is DAY.
    initial_shares use initial-session close units; events on/before that close
    are already reflected. In-window off-session events block, never roll forward.
    Alternatively order_provider(decision_date, active_date, state) returns
    {'status': 'READY', 'orders': [...]}. Its copied state contains only prior
    executions/valuations; no active-session OHLC is passed to the provider.
    """
    if session_dates != sorted(set(session_dates)) or len(session_dates) < 2:
        raise ValueError('Ordered unique sessions including initial close required')
    if number(fee_bps) != 0:
        raise ValueError('Only zero commission supported')
    if (orders is None) == (order_provider is None):
        raise ValueError('Provide exactly one order list or causal order provider')
    if orders is not None and not isinstance(orders, (list, tuple)):
        raise ValueError('Explicit static order sequence required')
    static_orders = orders if orders is not None else []
    cash = number(initial_cash)
    shares = {sid: quantity(q) for sid, q in (initial_shares or {}).items()}
    receivable = Fraction(0)
    logs, ledger = [], []
    seen_ids = set()
    state_date = session_dates[0]
    terminated = set()

    def finish(status, reason=None):
        return dict(status=status, reason=reason, state_date=state_date,
                    cash=str(cash), shares=dict(shares), receivable=str(receivable),
                    order_log=logs, daily_ledger=ledger, fees='0', external_flows='0',
                    research_only=True, real_orders=False,
                    execution_assumption='Complete fill on daily OHLC touch with opening price improvement; queue priority, liquidity, partial fills and intraday sequence are unproven.',
                    last_valued_date=ledger[-1]['date'] if ledger else None)

    for order in static_orders:
        active_date = order['active_date']
        if active_date > session_dates[-1]:
            continue  # Do not inspect future order contents.
        if active_date <= session_dates[0] or active_date not in session_dates:
            return finish('BLOCKED', 'INVALID_ORDER_SCHEDULE')
    for event in events:
        event_date = event['date']
        if event_date <= session_dates[0] or event_date > session_dates[-1]:
            continue  # Initial units already incorporate past events; no future payload read.
        if event_date not in session_dates:
            return finish('BLOCKED', 'INVALID_EVENT_SCHEDULE')

    for index, day in enumerate(session_dates[1:], 1):
        state_date = day
        previous = session_dates[index - 1]
        active, used = [], set()
        reserved = Fraction(0)
        supplied_orders = static_orders
        if order_provider is not None:
            state = dict(asof=previous, cash=str(cash), shares=dict(shares),
                         receivable=str(receivable), terminated_security_ids=sorted(terminated),
                         order_log=deepcopy(logs), daily_ledger=deepcopy(ledger))
            supplied = order_provider(decision_date=previous, active_date=day, state=state)
            if not isinstance(supplied, dict) or supplied.get('status') != 'READY':
                return finish('BLOCKED', 'ORDER_PROVIDER_NOT_READY')
            supplied_orders = supplied.get('orders')
            if not isinstance(supplied_orders, list):
                return finish('BLOCKED', 'INVALID_ORDER_PROVIDER_RESULT')
            if any(order.get('active_date') != day for order in supplied_orders):
                return finish('BLOCKED', 'PROVIDER_ORDER_NOT_ACTIVE_SESSION')
        # Reservation uses prior-close available cash, before any same-day sales.
        for original in supplied_orders:
            if original['active_date'] != day:
                continue
            order = dict(original)
            sid, identifier = order['security_id'], order['id']
            if order['decision_date'] != previous:
                return finish('BLOCKED', 'ORDER_NOT_NEXT_SESSION')
            if identifier in seen_ids or sid in used:
                return finish('BLOCKED', 'DUPLICATE_ID_OR_MULTIPLE_ORDERS_PER_SECURITY')
            seen_ids.add(identifier)
            used.add(sid)
            q, price = quantity(order['quantity']), number(order['limit'], True)
            if not q or (price * 100).denominator != 1 or order['side'] not in ('BUY', 'SELL'):
                return finish('BLOCKED', 'INVALID_ORDER_QUANTITY_SIDE_OR_CENT_PRICE')
            if sid in terminated:
                return finish('BLOCKED', 'TERMINATED_SECURITY_ORDER')
            if order['side'] == 'BUY':
                reserved += q * price
            elif q > shares.get(sid, 0):
                return finish('BLOCKED', 'SELL_EXCEEDS_PRIOR_HOLDINGS')
            order.update(quantity=q, limit=price)
            active.append(order)
        if reserved > cash:
            return finish('BLOCKED', 'BUY_RESERVATIONS_EXCEED_AVAILABLE_CASH')
        logs.append(dict(date=previous, event='RESERVED_FOR_NEXT_SESSION', active_date=day,
                         reserved_cash=str(reserved), available_cash=str(cash), order_ids=[o['id'] for o in active]))
        day_events = []
        event_sids = set()
        for event in events:
            if event['date'] != day:
                continue
            sid = event['security_id']
            if not shares.get(sid, 0) and sid not in used and event['type'] != 'merger':
                continue
            if not isinstance(event.get('source_references'), list) or not event['source_references'] or not all(event['source_references']):
                return finish('BLOCKED', 'EVENT_EVIDENCE_REQUIRED')
            if sid in event_sids:
                return finish('BLOCKED', 'SIMULTANEOUS_EVENTS_REQUIRE_RESOLUTION')
            event_sids.add(sid)
            day_events.append(event)
        for event in day_events:
            sid, kind = event['security_id'], event['type']
            relevant = [order for order in active if order['security_id'] == sid]
            if kind == 'split':
                ratio = number(event['new_shares'], True) / number(event['old_shares'], True)
                adjusted = shares.get(sid, 0) * ratio
                if adjusted.denominator != 1:
                    return finish('BLOCKED', 'FRACTIONAL_SPLIT_HOLDING')
                changes = [(order, order['quantity'] * ratio, order['limit'] / ratio) for order in relevant]
                if any(q.denominator != 1 or (price * 100).denominator != 1 for _, q, price in changes):
                    return finish('BLOCKED', 'NONINTEGER_OR_SUBCENT_SPLIT_ORDER')
                shares[sid] = int(adjusted)
                for order, q, price in changes:
                    order.update(quantity=int(q), limit=price)
            elif kind == 'merger':
                receivable += shares.get(sid, 0) * number(event['share_cash'])
                shares[sid] = 0
                terminated.add(sid)
                for order in relevant:
                    logs.append(dict(date=day, id=order['id'], event='CANCELLED_TERMINATION'))
                    active.remove(order)
            else:
                return finish('BLOCKED', 'UNMODELLED_HELD_OR_ORDERED_ACTION')
            logs.append(dict(date=day, security_id=sid, event='CORPORATE_ACTION', type=kind,
                             action_details=deepcopy(event),
                             source_references=list(event['source_references'])))
        # Preflight every required bar before executing any order on this day.
        required = {sid for sid, q in shares.items() if q} | {o['security_id'] for o in active}
        bars = {}
        for sid in sorted(required):
            try:
                bar = {key: number(ohlc[sid][day][key], True) for key in ('open', 'high', 'low', 'close')}
                if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
                    return finish('BLOCKED', 'INCONSISTENT_OHLC')
                bars[sid] = bar
            except (KeyError, TypeError, ValueError, ZeroDivisionError):
                return finish('BLOCKED', 'MISSING_OR_INVALID_REQUIRED_OHLC')
        # Stable order, with no proceeds needed to fund reserved buys.
        for order in sorted(active, key=lambda o: o['id']):
            sid, q, limit = order['security_id'], order['quantity'], order['limit']
            bar = bars[sid]
            buy = order['side'] == 'BUY'
            touched = bar['low'] <= limit if buy else bar['high'] >= limit
            if touched:
                fill = min(bar['open'], limit) if buy else max(bar['open'], limit)
                cash += (-1 if buy else 1) * q * fill
                shares[sid] = shares.get(sid, 0) + (q if buy else -q)
                logs.append(dict(date=day, id=order['id'], security_id=sid, side=order['side'],
                                 event='ASSUMED_FILLED', quantity=q, limit=str(limit), price=str(fill)))
            else:
                logs.append(dict(date=day, id=order['id'], event='EXPIRED_UNFILLED', quantity=q, limit=str(limit)))
        stock_value = sum(q * bars[sid]['close'] for sid, q in shares.items() if q)
        ledger.append(dict(date=day, cash=str(cash), shares=dict(shares), receivable=str(receivable),
                           stock_value=str(stock_value), equity=str(cash + stock_value + receivable),
                           reserved_cash_end='0', external_flow='0'))
    return finish('COMPLETE')
