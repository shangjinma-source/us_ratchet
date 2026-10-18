"""Pure, explicitly scoped real-strategy records; no broker IO or order placement."""
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json

BASES = {'TOTAL_UNINVESTED', 'AVAILABLE_AFTER_RESERVATIONS'}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def number(value):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), 'EXACT_AMOUNT_REQUIRED')
    require(len(str(value)) <= 128, 'AMOUNT_TOO_LARGE')
    result = Fraction(value)
    require(result >= 0, 'NEGATIVE_AMOUNT')
    return result


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _revision(state):
    return sha256(canonical({k:v for k,v in state.items() if k != 'revision'})).hexdigest()


def _project(state):
    reserved = Fraction(0)
    sells = {}
    for order in state['orders'].values():
        order['reserved_cash'] = '0'
        order['remaining_fee_reserve'] = '0'
        if order['status'] != 'OPEN':
            continue
        remaining = order['remaining_quantity']
        if order['side'] == 'BUY':
            reserved += remaining * (Fraction(order['limit_price']) + Fraction(order['fee_per_share']))
            order['reserved_cash'] = str(remaining * (Fraction(order['limit_price']) + Fraction(order['fee_per_share'])))
            order['remaining_fee_reserve'] = str(remaining * Fraction(order['fee_per_share']))
        else:
            sid = order['security_id']
            sells[sid] = sells.get(sid, 0) + remaining
    state['reserved_cash'] = str(reserved)
    state['reserved_shares'] = sells
    total = Fraction(state['cash'])
    if state['cash_basis'] == 'AVAILABLE_AFTER_RESERVATIONS':
        total += Fraction(state['cash_reservation_basis'])
    state['total_uninvested_cash'] = str(total)
    state['available_cash'] = str(total-reserved) if total >= reserved else None
    state['execution_ready'] = state['cash_confirmation_valid'] and total >= reserved


def create_account(account_id):
    require(isinstance(account_id, str) and bool(account_id.strip()), 'ACCOUNT_ID_REQUIRED')
    state = dict(schema='REAL_STRATEGY_SCOPED_LEDGER_V1', account_id=account_id,
        shares={}, orders={}, events=[], cash='0', cash_basis='TOTAL_UNINVESTED',
        cash_reservation_basis='0', cash_confirmation_valid=False,
        last_cash_confirmation_event=None, last_fill_event=None,
        holdings_revision=0, cash_confirmed_for_holdings_revision=None)
    _project(state)
    state['revision'] = _revision(state)
    return state


def apply_event(state, event, *, expected_revision):
    """Return new state and effect. Idempotent retries return the original effect.

    CASH_CONFIRM amount/basis is the latest manual balance, never a cash flow.
    ORDER_OPEN records an explicitly confirmed real order, not a suggestion.
    FILL records an actual partial/full fill. It never changes manual cash.
    All records are isolated from legacy holdings, even for the same SID.
    """
    require(state.get('schema') == 'REAL_STRATEGY_SCOPED_LEDGER_V1'
            and state.get('revision') == _revision(state), 'STATE_INTEGRITY')
    require(isinstance(event, dict) and isinstance(event.get('event_id'), str)
            and bool(event['event_id'].strip()), 'EVENT_ID_REQUIRED')
    payload = deepcopy(event)
    for previous in state['events']:
        if previous['payload']['event_id'] == event['event_id']:
            require(previous['payload'] == payload, 'EVENT_ID_CONFLICT')
            return deepcopy(state), deepcopy(previous['effect'])
    require(expected_revision == state['revision'], 'STALE_REVISION')
    kind = event.get('kind')
    fields = {
        'CASH_CONFIRM': {'amount', 'cash_basis'},
        'ORDER_OPEN': {'order_id', 'security_id', 'side', 'quantity', 'limit_price', 'fee_per_share'},
        'FILL': {'order_id', 'quantity', 'price', 'fees', 'executed_at'},
        'CANCEL': {'order_id'},
        'DIRECT_FILL': {'security_id', 'side', 'quantity', 'price', 'fees', 'executed_at'},
    }
    optional={'identity_evidence'} if kind in {'DIRECT_FILL','ORDER_OPEN'} and 'identity_evidence' in event else set()
    require(kind in fields and set(event) == fields[kind] | {'event_id', 'kind'} | optional, 'EVENT_FIELDS')
    if optional:
        identity=event['identity_evidence']
        require(isinstance(identity,dict) and set(identity)=={'ticker','security_id','source_references','source_hashes'} and identity['security_id']==event['security_id'] and isinstance(identity['ticker'],str) and bool(identity['ticker']) and isinstance(identity['source_references'],list) and bool(identity['source_references']) and all(isinstance(x,str) and bool(x) for x in identity['source_references']), 'IDENTITY_EVIDENCE_REQUIRED')
        require(isinstance(identity['source_hashes'],dict) and set(identity['source_hashes'])==set(identity['source_references']) and all(isinstance(h,str) and len(h)==64 and all(c in '0123456789abcdef' for c in h) for h in identity['source_hashes'].values()),'IDENTITY_SOURCE_HASHES_REQUIRED')
    if kind in {'FILL','DIRECT_FILL'}:
        require(type(event['executed_at']) is str,'EXECUTION_TIME_REQUIRED')
        executed=datetime.fromisoformat(event['executed_at'])
        require(executed.tzinfo is not None and executed.utcoffset() is not None,'AWARE_EXECUTION_TIME_REQUIRED')
    updated = deepcopy(state)
    effect = dict(event_id=event['event_id'], kind=kind, cash_delta='0', manual_cash_changed=False)
    if kind in {'FILL','DIRECT_FILL'}:effect['executed_at']=event['executed_at']
    if kind == 'CASH_CONFIRM':
        amount = number(event['amount'])
        require(event['cash_basis'] in BASES, 'CASH_BASIS_REQUIRED')
        reserve = Fraction(state['reserved_cash'])
        require(event['cash_basis'] != 'TOTAL_UNINVESTED' or amount >= reserve, 'CASH_BELOW_RESERVATIONS')
        updated.update(cash=str(amount), cash_basis=event['cash_basis'],
            cash_reservation_basis=str(reserve), cash_confirmation_valid=True,
            last_cash_confirmation_event=event['event_id'],
            cash_confirmed_for_holdings_revision=state['holdings_revision'])
        effect['manual_cash_changed'] = True
    elif kind == 'ORDER_OPEN':
        oid, sid = event['order_id'], event['security_id']
        require(all(isinstance(v, str) and bool(v.strip()) for v in (oid, sid)), 'ORDER_IDENTITY_REQUIRED')
        require(oid not in updated['orders'], 'ORDER_ALREADY_EXISTS')
        quantity = event['quantity']
        require(type(quantity) is int and quantity > 0, 'POSITIVE_WHOLE_QUANTITY')
        side = event['side'];require(side in {'BUY', 'SELL'}, 'ORDER_SIDE')
        limit, fee = number(event['limit_price']), number(event['fee_per_share'])
        require(limit > 0, 'POSITIVE_LIMIT')
        if side == 'SELL':
            require(quantity <= state['shares'].get(sid, 0)-state['reserved_shares'].get(sid, 0), 'INSUFFICIENT_STRATEGY_SHARES')
        require(not any(o['status']=='OPEN' and o['security_id']==sid and o['side']!=side for o in state['orders'].values()), 'CONFLICTING_OPEN_ORDERS')
        updated['orders'][oid] = dict(order_id=oid, security_id=sid, side=side,
            scope='STRATEGY',account_id=state['account_id'],
            quantity=quantity, filled_quantity=0, remaining_quantity=quantity,
            cancelled_quantity=0, limit_price=str(limit), fee_per_share=str(fee), status='OPEN')
        # This is an existing broker order, so the previously entered available
        # balance may already exclude its reservation. Record the fact first;
        # require a new absolute balance with the complete pending-order set.
        updated.update(cash_confirmation_valid=False,
            cash_confirmed_for_holdings_revision=None)
    elif kind == 'DIRECT_FILL':
        # A real fill can be entered without inventing a prior tracked order.
        sid, side = event['security_id'], event['side']
        require(type(sid) is str and bool(sid.strip()), 'SECURITY_ID_REQUIRED')
        require(side in {'BUY', 'SELL'}, 'ORDER_SIDE')
        require(type(event['executed_at']) is str, 'EXECUTION_TIME_REQUIRED')
        executed = datetime.fromisoformat(event['executed_at'])
        require(executed.tzinfo is not None and executed.utcoffset() is not None,
                'AWARE_EXECUTION_TIME_REQUIRED')
        quantity = event['quantity']
        require(type(quantity) is int and quantity > 0, 'POSITIVE_WHOLE_QUANTITY')
        price, fees = number(event['price']), number(event['fees'])
        require(price > 0, 'POSITIVE_FILL_PRICE')
        require(not any(order['status'] == 'OPEN' and order['security_id'] == sid
                        for order in state['orders'].values()), 'LINK_FILL_TO_EXISTING_ORDER')
        held = state['shares'].get(sid, 0)
        require(side != 'SELL' or quantity <= held, 'INSUFFICIENT_STRATEGY_SHARES')
        updated['shares'][sid] = held + (quantity if side == 'BUY' else -quantity)
        effect['cash_delta'] = str((quantity*price if side == 'SELL' else -quantity*price)-fees)
        effect['executed_at'] = event['executed_at']
        updated.update(cash_confirmation_valid=False,last_fill_event=event['event_id'],
            holdings_revision=state['holdings_revision']+1)
    else:
        require(event['order_id'] in updated['orders'], 'UNKNOWN_ORDER')
        order = updated['orders'][event['order_id']]
        require(order['status']=='OPEN', 'ORDER_CLOSED')
        if kind == 'CANCEL':
            order['cancelled_quantity'] = order['remaining_quantity']
            order['remaining_quantity'] = 0
            order['status'] = 'CANCELLED'
        else:
            quantity = event['quantity']
            require(type(quantity) is int and 0 < quantity <= order['remaining_quantity'], 'INVALID_FILL_QUANTITY')
            price, fees = number(event['price']), number(event['fees'])
            require(price > 0, 'POSITIVE_FILL_PRICE')
            sid=order['security_id'];held=updated['shares'].get(sid,0)
            if order['side']=='SELL':
                require(quantity <= held, 'INSUFFICIENT_STRATEGY_SHARES')
                updated['shares'][sid]=held-quantity
                effect['cash_delta']=str(quantity*price-fees)
            else:
                updated['shares'][sid]=held+quantity
                effect['cash_delta']=str(-quantity*price-fees)
            order['filled_quantity'] += quantity
            order['remaining_quantity'] -= quantity
            if not order['remaining_quantity']:order['status']='FILLED'
            updated.update(cash_confirmation_valid=False,last_fill_event=event['event_id'],
                holdings_revision=state['holdings_revision']+1)
    _project(updated)
    effect['cash_confirmation_valid']=updated['cash_confirmation_valid']
    updated['events'].append(dict(payload=payload,effect=deepcopy(effect)))
    updated['revision']=_revision(updated)
    return updated,effect


def replay(account_id, events):
    state=create_account(account_id)
    for event in events:
        state,_=apply_event(state,event,expected_revision=state['revision'])
    return state
