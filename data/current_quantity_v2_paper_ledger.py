"""Pure single-activation V2 paper ledger; no store, broker, search or IO.

Declared source evidence is frozen for replay, not externally authenticated.
Closing an order rejects subsequent late entry, even if its claimed execution
predates closure; this does not establish that a real-world fill never happened.
"""
from copy import deepcopy
from hashlib import sha256
import json
from data.current_quantity_v2_difference_plan import build_account_difference_plan, require, stamp, number

SCHEMA='QUANTITY_V2_PAPER_LEDGER_V1'


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def reserves(state):
    cash=number('0');shares={}
    for order in state['orders'].values():
        if order['closed']:continue
        q=order['quantity']-order['filled_quantity']
        if order['side']=='BUY':cash+=q*number(order['limit_price'])
        else:shares[order['security_id']]=shares.get(order['security_id'],0)+q
    require(number(state['cash'])>=cash,'REMAINING_BUY_RESERVE_NOT_FUNDED')
    require(all(state['shares'].get(sid,0)>=q for sid,q in shares.items()),'REMAINING_SELL_RESERVE_NOT_FUNDED')
    state.update(reserved_cash=str(cash),reserved_shares=shares)


def initial(evidence):
    proposal=evidence['proposal'];inputs=proposal['causal_inputs'];accepted=stamp(evidence['accepted_at'])
    current_cash=proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION'
    if current_cash:
        from data.current_quantity_v2_current_cash_ledger_adapter import build_recorded_cash_proposal
        builder=build_recorded_cash_proposal
    else:builder=build_account_difference_plan
    require(builder(**inputs)==proposal and proposal['status']=='READY','PROPOSAL_RECONSTRUCTION_MISMATCH')
    require(inputs['account_state']==evidence['account_state'],'ACCOUNT_CHANGED')
    require(stamp(inputs['now'])<=accepted,'ACCEPTANCE_BEFORE_PROPOSAL')
    current=builder(**dict(inputs,now=accepted.isoformat()))
    require(current['status']=='READY' and current['orders']==proposal['orders'],'REFERENCE_NOT_ACCEPTABLE')
    require(proposal['orders'],'NO_ORDERS_TO_ACCEPT')
    identifier=digest(evidence);orders={}
    for index,row in enumerate(proposal['orders']):
        ref=(proposal['execution_references'] if current_cash else inputs['execution_references'])[row['security_id']]
        require(stamp(ref['session_open'])<=accepted<stamp(ref['session_close']),'OUTSIDE_ORDER_SESSION')
        oid=identifier+':'+str(index)
        orders[oid]=dict(row,order_id=oid,filled_quantity=0,closed=None,
            accepted_at=accepted.isoformat(),session_close=ref['session_close'],time_in_force='DAY')
    account=evidence['account_state']
    state=dict(schema=SCHEMA,acceptance=deepcopy(evidence),account_id=account['account_id'],
        initial_account_revision=account['revision'],revision=identifier,cash=str(number(account['cash'])),
        shares=deepcopy(account['shares']),recorded_fees='0',orders=orders,events=[],
        target_quantities=deepcopy(proposal['target_quantities']),last_recorded_at=accepted.isoformat(),
        last_effective_at=accepted.isoformat(),research_only=True,execution_blocked=True,
        real_account=False,source_authenticated=False,subsequent_activation_supported=False)
    if current_cash:
        state.update(target_scope=proposal['target_scope'],execution_target_id=proposal['execution_target_id'],
            historical_target_quantities=deepcopy(proposal['historical_target_quantities']),
            current_execution_bytes_verified=True,historical_source_bytes_reverified=False)
    reserves(state)
    return state


def accept_proposal(proposal, *, account_state, now):
    """Caller supplies current verified state/time; raw authenticity is upstream."""
    if proposal.get('target_scope')=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
        require('execution_month_mandate' in proposal['causal_inputs']['frozen_execution_package']['documents'],'MONTH_MANDATE_REQUIRED')
    return initial(dict(proposal=deepcopy(proposal),account_state=deepcopy(account_state),accepted_at=stamp(now).isoformat()))


def apply(state,event):
    kind=event.get('type');common={'event_id','type','order_id','expected_revision','recorded_at'}
    extra={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
    require(kind in extra and set(event)==common|extra[kind],'INVALID_EVENT_FIELDS')
    require(type(event['event_id']) is str and bool(event['event_id'].strip()),'EVENT_ID_REQUIRED')
    for saved in state['events']:
        if saved['event_id']==event['event_id']:
            require(saved==event,'EVENT_ID_CONFLICT')
            return state
    require(event['expected_revision']==state['revision'],'STALE_REVISION')
    require(event['order_id'] in state['orders'],'UNKNOWN_ORDER')
    order=state['orders'][event['order_id']]
    require(not order['closed'],'ORDER_CLOSED')
    recorded=stamp(event['recorded_at']);accepted=stamp(order['accepted_at']);close=stamp(order['session_close'])
    effective=stamp(event['executed_at'] if kind=='FILL' else event['cancelled_at'] if kind=='CANCEL' else event['recorded_at'])
    require(stamp(state['last_recorded_at'])<=recorded and stamp(state['last_effective_at'])<=effective<=recorded,'EVENT_TIME_ORDER')
    require(effective>=accepted,'EVENT_BEFORE_ACCEPTANCE')
    if kind=='FILL':
        require(effective<close,'FILL_OUTSIDE_DAY')
        q=event['quantity'];price=number(event['price']);fees=number(event['fees'])
        require(type(q) is int and 0<q<=order['quantity']-order['filled_quantity'] and price>0 and fees>=0,'INVALID_FILL')
        limit=number(order['limit_price']);sid=order['security_id'];cash=number(state['cash'])
        if order['side']=='BUY':
            require(price<=limit,'BUY_ABOVE_LIMIT');cash-=q*price+fees
            state['shares'][sid]=state['shares'].get(sid,0)+q
        else:
            require(price>=limit and state['shares'].get(sid,0)>=q,'SELL_LIMIT_OR_SHARES')
            cash+=q*price-fees;state['shares'][sid]-=q
        state['cash']=str(cash);state['recorded_fees']=str(number(state['recorded_fees'])+fees)
        order['filled_quantity']+=q
        if order['filled_quantity']==order['quantity']:order['closed']='FILLED'
    elif kind=='CANCEL':
        require(effective<close,'CANCEL_OUTSIDE_DAY');order['closed']='CANCELLED'
    else:
        require(recorded>=close,'SESSION_NOT_CLOSED');order['closed']='EXPIRED'
    reserves(state)
    state['events'].append(deepcopy(event));state['revision']=digest(dict(previous=state['revision'],event=event))
    state.update(last_recorded_at=recorded.isoformat(),last_effective_at=effective.isoformat())
    return state


def review_ledger(state):
    require(type(state) is dict and state.get('schema')==SCHEMA,'INVALID_LEDGER_SCHEMA')
    rebuilt=initial(state['acceptance'])
    for event in state['events']:apply(rebuilt,deepcopy(event))
    require(rebuilt==state,'LEDGER_REPLAY_MISMATCH')
    return deepcopy(rebuilt)


def record_event(state,event,*,now):
    rebuilt=review_ledger(state)
    # Exact retries remain valid after closure; no new clock is assigned.
    for saved in rebuilt['events']:
        if saved['event_id']==event.get('event_id'):
            require(saved==event,'EVENT_ID_CONFLICT');return rebuilt
    require(stamp(event['recorded_at'])<=stamp(now),'FUTURE_RECORD_TIME')
    return apply(rebuilt,deepcopy(event))
