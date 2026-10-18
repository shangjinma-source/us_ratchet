"""Independent V3: conditional mixed-merger rights remain nontradable."""
from fractions import Fraction
from copy import deepcopy
from backtest.return_priority_cash_stock_entitlements import convert_cash_stock_entitlement, value_cash_stock_entitlements


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


def run_limit_book_v3(*, session_dates, orders=None, ohlc, initial_cash,
                   initial_shares=None, events=(), fee_bps='0', order_provider=None,
                   cash_stock_merger_events=(), fractional_settlements=None, price_source_references=None):
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
    entitlement_state = dict(cash=str(cash),shares=dict(shares),merger_entitlements=[],applied_event_ids=[])
    rights_valuation = None

    def finish(status, reason=None):
        return dict(status=status, reason=reason, state_date=state_date,
                    cash=str(cash), shares=dict(shares), receivable=str(receivable),
                    merger_entitlements=deepcopy(entitlement_state['merger_entitlements']), rights_valuation=deepcopy(rights_valuation),
                    limitations=['Ordinary dividends and taxes/unconfirmed costs excluded; zero commission only.', 'Conditional end-session merger; unavailable rights never fund orders.'],
                    order_log=logs, daily_ledger=ledger, fees='0', external_flows='0',
                    research_only=True, real_orders=False,
                    split_limit_policy='CONSERVATIVE_CENT_ROUNDING_RESEARCH_ASSUMPTION_NOT_BROKER_RULE',
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

    for event in cash_stock_merger_events:
        if event['effective_date'] <= session_dates[0] or event['effective_date'] > session_dates[-1]:
            continue
        if event['effective_date'] not in session_dates:
            return finish('BLOCKED', 'INVALID_MIXED_EVENT_SCHEDULE')

    for index, day in enumerate(session_dates[1:], 1):
        state_date = day
        previous = session_dates[index - 1]
        mixed_today = [e for e in cash_stock_merger_events if e['effective_date'] == day]
        mixed_old = {e['old_sid'] for e in mixed_today}
        mixed_successors = {e['new_sid'] for e in mixed_today}
        if len(mixed_old) != len(mixed_today):
            return finish('BLOCKED', 'DUPLICATE_MIXED_EVENT')
        active, used = [], set()
        reserved = Fraction(0)
        supplied_orders = static_orders
        if order_provider is not None:
            state = dict(asof=previous, cash=str(cash), shares=dict(shares),
                         receivable=str(receivable), merger_entitlements=deepcopy(entitlement_state['merger_entitlements']),
                         rights_valuation=deepcopy(rights_valuation), terminated_security_ids=sorted(terminated),
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
        for order in list(active):
            if order['security_id'] in mixed_old:
                logs.append(dict(date=day,id=order['id'],event='CANCELLED_CONDITIONAL_MIXED_SESSION',
                    released_reservation=str(order['quantity']*order['limit']) if order['side']=='BUY' else '0',cash_credited='0'))
                active.remove(order)
        day_events = []
        event_sids = set()
        for event in events:
            if event['date'] != day:
                continue
            sid = event['security_id']
            rights_sids = {r['new_sid'] for r in entitlement_state['merger_entitlements'] if r['converted_old_shares']}
            if sid in rights_sids or sid in mixed_old or sid in mixed_successors:
                return finish('BLOCKED', 'ACTION_ON_PENDING_RIGHTS_OR_MIXED_SESSION_UNSUPPORTED')
            if not shares.get(sid, 0) and sid not in used and event['type'] not in ('merger', 'split_identity', 'cash_stock_merger'):
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
            if kind in ('split', 'split_identity'):
                successor = sid
                if kind == 'split_identity':
                    successor = event.get('new_security_id')
                    if not isinstance(successor, str) or not successor or successor == sid or successor in terminated:
                        return finish('BLOCKED', 'INVALID_SUCCESSOR_SECURITY')
                    if shares.get(successor, 0) or any(o['security_id'] == successor for o in active):
                        return finish('BLOCKED', 'SUCCESSOR_POSITION_OR_ORDER_CONFLICT')
                    if successor in event_sids:
                        return finish('BLOCKED', 'SIMULTANEOUS_SUCCESSOR_ACTION_UNSUPPORTED')
                ratio = number(event['new_shares'], True) / number(event['old_shares'], True)
                adjusted = shares.get(sid, 0) * ratio
                if adjusted.denominator != 1:
                    return finish('BLOCKED', 'FRACTIONAL_SPLIT_HOLDING')
                changes = [(order, order['quantity'] * ratio, order['limit'] / ratio) for order in relevant]
                if any(q.denominator != 1 for _, q, _ in changes):
                    return finish('BLOCKED', 'NONINTEGER_SPLIT_ORDER')
                rounded_changes = []
                for order, q, raw_limit in changes:
                    rounded = (Fraction(raw_limit * 100 // 1, 100) if order['side']=='BUY'
                               else Fraction(-(-raw_limit * 100 // 1), 100))
                    if rounded <= 0:
                        return finish('BLOCKED', 'NONPOSITIVE_ROUNDED_SPLIT_LIMIT')
                    if order['side']=='BUY' and q * rounded > order['quantity'] * order['limit']:
                        return finish('BLOCKED', 'SPLIT_ROUNDING_INCREASED_RESERVATION')
                    rounded_changes.append((order,q,rounded,raw_limit))
                shares[sid] = 0 if successor != sid else int(adjusted)
                shares[successor] = int(adjusted)
                if successor != sid:
                    terminated.add(sid)
                for order, q, price, raw_limit in rounded_changes:
                    logs.append(dict(date=day,id=order['id'],event='SPLIT_LIMIT_ADJUSTED',side=order['side'],
                        prior_limit=str(order['limit']),raw_adjusted_limit=str(raw_limit),rounded_limit=str(price),
                        quantity_after=int(q),policy='CONSERVATIVE_CENT_ROUNDING_RESEARCH_ASSUMPTION_NOT_BROKER_RULE'))
                    order.update(quantity=int(q), limit=price, security_id=successor)
            elif kind == 'cash_stock_merger':
                # V2 increment does not pretend pending stock rights are delivered.
                # Even without current exposure terminate the old security so a
                # later order cannot resurrect it from stale prices.
                terminated.add(sid)
                if shares.get(sid, 0) or relevant:
                    return finish('BLOCKED', 'CASH_STOCK_ENTITLEMENT_ENGINE_NOT_CONNECTED')
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
        required = {sid for sid, q in shares.items() if q and sid not in mixed_old} | {o['security_id'] for o in active}
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
        entitlement_state.update(cash=str(cash),shares=dict(shares))
        for event in mixed_today:
            rights_sids = {r['new_sid'] for r in entitlement_state['merger_entitlements'] if r['converted_old_shares']}
            if event['old_sid'] in rights_sids or event['new_sid'] in mixed_old:
                return finish('BLOCKED', 'MIXED_SUCCESSOR_ACTION_UNSUPPORTED')
            try:
                entitlement_state = convert_cash_stock_entitlement(state=entitlement_state,event=event,as_of=day)
            except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
                return finish('BLOCKED', dict(reason='INVALID_MIXED_EVENT',detail=str(error)))
            shares = dict(entitlement_state['shares'])
            terminated.add(event['old_sid'])
            logs.append(dict(date=day,event='CONDITIONAL_END_SESSION_ENTITLEMENT',action_details=deepcopy(event),cash_credited='0'))
        stock_value = sum(q * bars[sid]['close'] for sid, q in shares.items() if q)
        pending_value = Fraction(0)
        if entitlement_state['merger_entitlements']:
            marks = {}
            needed = {sid for sid,q in shares.items() if q} | {r['new_sid'] for r in entitlement_state['merger_entitlements'] if r['pending_whole_shares']}
            for sid in needed:
                try:
                    marks[sid] = dict(date=day,price=str(number(ohlc[sid][day]['close'],True)),source_references=price_source_references[sid])
                except (KeyError, TypeError, ValueError):
                    pass  # Existing valuation reports the missing mark and preserves rights.
            rights_valuation = value_cash_stock_entitlements(state=entitlement_state,marks=marks,as_of=day,fractional_settlements=fractional_settlements)
            if rights_valuation['status']=='BLOCKED':
                return finish('BLOCKED','ENTITLEMENT_VALUATION_BLOCKED')
            pending_value = Fraction(rights_valuation['total_equity'])-cash-stock_value
        ledger.append(dict(date=day, cash=str(cash), shares=dict(shares), receivable=str(receivable),
                           stock_value=str(stock_value), equity=str(cash + stock_value + receivable + pending_value),
                           nontradable_entitlement_value=str(pending_value),merger_entitlements=deepcopy(entitlement_state['merger_entitlements']),rights_valuation=deepcopy(rights_valuation),
                           reserved_cash_end='0', external_flow='0'))
    return finish('COMPLETE')

