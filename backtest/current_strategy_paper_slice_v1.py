"""In-memory fixture-only paper slice. No IO, production authority or selector.

Reuses current daily math/difference and the original strict-cross fill kernel.
Its application scope cannot activate a task or authenticate market evidence.
"""
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from backtest.partial_trend_exposure import partial_sma20_target
from backtest.current_quantity_v2_minute_day_fill import evaluate, MODEL, stamp, exact
from core.strategy_account_difference import build_strategy_difference

SCOPE = 'ISOLATED_CURRENT_STRATEGY_PAPER_FIXTURE_ONLY'


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def validate_application(application):
    need(set(application) == {'schema', 'scope', 'account_id', 'initial_cash',
                             'fee_bps', 'model', 'activation'}, 'PAPER_APPLICATION_FIELDS')
    need(application['schema'] == 'CURRENT_STRATEGY_PAPER_FIXTURE_APPLICATION_V1'
         and application['scope'] == SCOPE and application['activation'] is False,
         'PAPER_FIXTURE_SCOPE_REQUIRED')
    need(type(application['account_id']) is str and application['account_id'].startswith('paper-fixture:'),
         'PAPER_ACCOUNT_NAMESPACE_REQUIRED')
    need(exact(application['initial_cash']) == 20000 and
         0 <= exact(application['fee_bps']) <= 10000 and application['model'] == MODEL,
         'PAPER_INITIAL_CAPITAL_OR_MODEL')


def _initial(application):
    validate_application(application)
    return dict(schema='CURRENT_STRATEGY_PAPER_FIXTURE_BOOK_V1', application=deepcopy(application),
                cash='20000', shares={}, orders={}, operations=[], last_observed_at=None,
                last_available_at=None,
                revision=digest(application), real_account=False, selector_verified=False)


def create_book(application):
    return _initial(application)


def _resources(book):
    cash = Fraction(0)
    shares = {}
    for order in book['orders'].values():
        if order['closed'] is not None:
            continue
        if order['side'] == 'BUY':
            cash += order['quantity'] * exact(order['limit_price']) + exact(order['fees'])
        else:
            sid = order['security_id']
            shares[sid] = shares.get(sid, 0) + order['quantity']
    need(exact(book['cash']) >= cash and all(book['shares'].get(s, 0) >= q
                                           for s, q in shares.items()), 'PAPER_RESOURCE_INVARIANT')
    return cash, shares


def _projection(book):
    reserved, sells = _resources(book)
    orders = []
    for order in book['orders'].values():
        if order['closed'] is not None:
            continue
        buy = order['side'] == 'BUY'
        orders.append(dict(order_id=order['order_id'], security_id=order['security_id'],
            account_id=book['application']['account_id'], scope='STRATEGY', side=order['side'],
            quantity=order['quantity'], filled_quantity=0, remaining_quantity=order['quantity'],
            limit_price=order['limit_price'], remaining_fee_reserve=order['fees'] if buy else '0',
            reserved_cash=str(order['quantity'] * exact(order['limit_price']) + exact(order['fees'])) if buy else '0'))
    return dict(schema='PAPER_DECISION_PROJECTION_V1', account_id=book['application']['account_id'],
                revision=book['revision'], cash=book['cash'], available_cash=str(exact(book['cash'])-reserved),
                shares=deepcopy(book['shares']), pending_orders=orders, reserved_shares=sells)


def project(book):
    return _projection(replay(book))


def _preview(book, *, daily_inputs, quotes, now, session_close):
    current, close = stamp(now), stamp(session_close)
    need(book['last_available_at'] is None or current >= stamp(book['last_available_at']),
         'PAPER_PREVIEW_BEFORE_STATE_AVAILABLE')
    need(current < close and current.astimezone(ZoneInfo('America/New_York')).date() ==
         close.astimezone(ZoneInfo('America/New_York')).date(), 'PAPER_SESSION_BOUNDARY')
    need(stamp(daily_inputs['observed_at']) < current and daily_inputs['signal_date'] <
         current.astimezone(ZoneInfo('America/New_York')).date().isoformat(), 'PAPER_COMPLETED_SIGNAL_REQUIRED')
    signal = partial_sma20_target(**deepcopy(daily_inputs))
    effective = dict(signal['target_quantities'])
    for sid in book['shares']:
        effective.setdefault(sid, 0)
    state = _projection(book)
    marks, limits = {}, {}
    needed = {sid for sid, q in effective.items() if q} | {s for s, q in book['shares'].items() if q}
    needed |= {o['security_id'] for o in state['pending_orders']}
    need(set(quotes) == needed, 'PAPER_QUOTE_DOMAIN')
    for sid, quote in quotes.items():
        need(stamp(quote['observed_at']) <= current < stamp(quote['valid_until']) <= close,
             'PAPER_QUOTE_EXPIRED_OR_FUTURE')
        marks[sid] = dict(security_id=sid, currency='USD', price_basis='FIXTURE_USD',
                         observed_at=quote['observed_at'], price=quote['mark'])
        limits[sid] = dict(security_id=sid, price_basis='FIXTURE_USD',
                          observed_at=quote['observed_at'], buy=quote['buy'], sell=quote['sell'])
    result = build_strategy_difference(account_id=state['account_id'], account_revision=state['revision'],
        holdings_revision=state['revision'], cash_confirmed_for_holdings_revision=state['revision'],
        cash_balance=state['cash'], cash_basis='TOTAL_UNINVESTED', strategy_shares=state['shares'],
        legacy_shares={}, pending_orders=state['pending_orders'], marks=marks, limits=limits,
        target_quantities=effective, now=now, maximum_mark_age_seconds=120,
        fee_bps=book['application']['fee_bps'])
    inputs = dict(daily_inputs=deepcopy(daily_inputs), quotes=deepcopy(quotes), now=now,
                  session_close=session_close)
    return dict(schema='PAPER_FIXTURE_PREVIEW_V1', application_sha256=digest(book['application']),
                revision=book['revision'], inputs=inputs, monthly=daily_inputs['base_target']['quantities'],
                effective=effective, diagnostics=signal['diagnostics'], difference=result,
                selector_verified=False, source_authenticated=False)


def preview(book, **inputs):
    return _preview(replay(book), **inputs)


def _accept(book, request):
    proposal, accepted = request['proposal'], request['accepted_at']
    local = stamp(accepted).astimezone(ZoneInfo('America/New_York'))
    need((local.hour, local.minute) == (10, 0), 'PAPER_ACCEPT_OUTSIDE_1000')
    need(book['last_observed_at'] is None or stamp(accepted) >= stamp(book['last_observed_at']),
         'PAPER_ACCEPT_BEFORE_LEDGER_TIME')
    need(proposal['revision'] == book['revision'], 'PAPER_STALE_REVISION')
    need(_preview(book, **proposal['inputs']) == proposal, 'PAPER_PREVIEW_REPLAY_MISMATCH')
    need(stamp(accepted) >= stamp(proposal['inputs']['now']), 'PAPER_ACCEPT_BEFORE_PREVIEW')
    recomputed = _preview(book, **dict(proposal['inputs'], now=accepted))
    need(recomputed['difference']['new_orders'] == proposal['difference']['new_orders'], 'PAPER_ACCEPT_CHANGED')
    need(not proposal['difference']['cancel_before_recalculate'], 'PAPER_PENDING_CONFLICT')
    need(proposal['difference']['new_orders'], 'PAPER_NO_ORDERS')
    for index, row in enumerate(proposal['difference']['new_orders']):
        oid = request['operation_id'] + ':' + str(index)
        need(oid not in book['orders'], 'PAPER_DUPLICATE_ORDER')
        fee = row['quantity'] * exact(row['limit_price']) * exact(book['application']['fee_bps']) / 10000
        book['orders'][oid] = dict(row, order_id=oid, filled_quantity=0, closed=None,
            fees=str(fee), accepted_at=accepted, session_close=proposal['inputs']['session_close'])
    _resources(book)


def _settle(book, request):
    observed, evaluated = stamp(request['observed_through']), stamp(request['evaluated_at'])
    need(observed <= evaluated and (book['last_observed_at'] is None or
         observed > stamp(book['last_observed_at'])), 'PAPER_OBSERVATION_ORDER')
    active = {oid: o for oid, o in book['orders'].items() if o['closed'] is None}
    need(set(request['minutes']) == set(active), 'PAPER_SETTLEMENT_DOMAIN')
    candidates = []
    results = {}
    for oid, order in active.items():
        for bar in request['minutes'][oid]:
            need(bar['security_id'] == order['security_id'], 'PAPER_MINUTE_IDENTITY')
        result = evaluate(model=MODEL, order=order, minutes=request['minutes'][oid],
            observed_through=request['observed_through'], evaluated_at=request['evaluated_at'],
            fees=order['fees'], available_cash=str(order['quantity'] * exact(order['limit_price']) + exact(order['fees'])),
            available_shares=order['quantity'], event_id=request['operation_id']+':'+oid,
            expected_revision=book['revision'])
        results[oid] = result
        if result['event_proposal']:
            candidates.append((stamp(result['event_proposal']['recorded_at']), oid, result))
    for at in sorted({row[0] for row in candidates}):
        group = [row for row in candidates if row[0] == at]
        reserved, reserved_shares = _resources(book)
        start_cash = exact(book['cash'])
        start_shares = dict(book['shares'])
        # Each BUY already reserves its own fees. No sale or expiry within this
        # timestamp can finance another order; all tests use the batch start.
        checked = []
        for _, oid, found in group:
            order = book['orders'][oid]
            event = found['event_proposal']
            if book['last_observed_at'] is not None and at <= stamp(book['last_observed_at']):
                results[oid] = dict(status='UNKNOWN', reason='LATE_EVIDENCE_WOULD_REWRITE_HISTORY')
                continue
            if event['type'] == 'FILL':
                q, price, fee = event['quantity'], exact(event['price']), exact(event['fees'])
                if order['side'] == 'BUY':
                    own = q * exact(order['limit_price']) + exact(order['fees'])
                    need(q*price+fee <= start_cash-reserved+own, 'PAPER_BATCH_BUY_RESOURCES')
                else:
                    sid = order['security_id']
                    need(q <= start_shares.get(sid, 0)-reserved_shares.get(sid, 0)+q
                         and q*price >= fee, 'PAPER_BATCH_SELL_RESOURCES')
            checked.append((oid, event))
        for oid, event in checked:
            order = book['orders'][oid]
            if event['type'] == 'EXPIRE':
                order['closed'] = 'EXPIRED'
                continue
            sid, q = order['security_id'], event['quantity']
            amount, fee = q*exact(event['price']), exact(event['fees'])
            buy = order['side'] == 'BUY'
            book['cash'] = str(exact(book['cash']) + (-amount if buy else amount) - fee)
            book['shares'][sid] = book['shares'].get(sid, 0) + (q if buy else -q)
            order.update(closed='FILLED', filled_quantity=q)
        _resources(book)
    book['last_observed_at'] = request['observed_through']
    return results


def _apply(book, request):
    need(request['expected_revision'] == book['revision'], 'PAPER_STALE_REVISION')
    need(type(request['operation_id']) is str and bool(request['operation_id']), 'PAPER_OPERATION_ID')
    need(request['kind'] in {'ACCEPT', 'SETTLE'}, 'PAPER_OPERATION_KIND')
    before = book['revision']
    available_at = request['accepted_at'] if request['kind'] == 'ACCEPT' else request['evaluated_at']
    need(book['last_available_at'] is None or stamp(available_at) >= stamp(book['last_available_at']),
         'PAPER_OPERATION_AVAILABILITY_REVERSED')
    if request['kind'] == 'ACCEPT':
        _accept(book, request)
        outcome = {'status': 'ACCEPTED_FIXTURE_ORDERS'}
    elif request['kind'] == 'SETTLE':
        outcome = _settle(book, request)
    else:
        raise ValueError('PAPER_OPERATION_KIND')
    book['last_available_at'] = available_at
    book['revision'] = digest(dict(previous=before, request=request, outcome=outcome))
    book['operations'].append(dict(request=deepcopy(request), outcome=outcome, revision=book['revision']))
    return book


def replay(book):
    rebuilt = _initial(book['application'])
    for operation in book['operations']:
        _apply(rebuilt, deepcopy(operation['request']))
        need(rebuilt['operations'][-1] == operation, 'PAPER_EVENT_REPLAY_MISMATCH')
    need(rebuilt == book, 'PAPER_BOOK_REPLAY_MISMATCH')
    return rebuilt


def transact(book, request):
    rebuilt = replay(book)
    for previous in rebuilt['operations']:
        if previous['request']['operation_id'] == request['operation_id']:
            need(previous['request'] == request, 'PAPER_OPERATION_ID_CONFLICT')
            return rebuilt
    return _apply(rebuilt, deepcopy(request))
