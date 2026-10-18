"""One monthly multi-order paper activation. Pure declared evidence, no raw authentication."""
from copy import deepcopy
from fractions import Fraction
from zoneinfo import ZoneInfo
from data.current_research_intraday_buy_plan import _require, _time, _cash
from data.current_research_intraday_paper_ledger import _hash
from data.current_research_intraday_continuation_ledger import review_continuation_ledger
from data.current_research_intraday_retarget_sizing import build_intraday_retarget_sizing

SCHEMA='INTRADAY_MULTI_ORDER_RETARGET_LEDGER_V3'


def _reserves(state):
    cash=Fraction(0);shares={}
    for order in state['orders'].values():
        if order['closed']:continue
        remaining=order['quantity']-order['filled_quantity']
        if order['side']=='BUY':cash+=remaining*Fraction(order['limit_price'])
        else:shares[order['security_id']]=shares.get(order['security_id'],0)+remaining
    _require(Fraction(state['cash'])>=cash,'INSUFFICIENT_CASH_FOR_REMAINING_BUYS')
    _require(all(state['shares'].get(sid,0)>=q for sid,q in shares.items()),'INSUFFICIENT_SHARES_FOR_REMAINING_SELLS')
    state['reserved_cash']=str(cash);state['reserved_shares']=shares


def _initial(genesis,evidence):
    old=review_continuation_ledger(genesis)
    _require(old.get('closed') is not None or old['filled_quantity']==old['order']['quantity'],'OPEN_PRIOR_ORDER')
    _require(Fraction(old['reserved_cash'])==0,'PRIOR_RESERVE_NOT_ZERO')
    inputs=evidence['sizing_inputs'];proposal=evidence['proposal'];accepted=_time(evidence['accepted_at'])
    _require(not {'state','now'} & set(inputs),'SIZING_INPUT_SCHEMA')
    created=_time(proposal['binding']['proposed_at'])
    rebuilt=build_intraday_retarget_sizing(old,now=created,**inputs)
    _require(rebuilt==proposal and rebuilt['status']=='READY','PROPOSAL_RECONSTRUCTION_MISMATCH')
    _require(created<=accepted,'ACCEPTANCE_BEFORE_PROPOSAL')
    current=build_intraday_retarget_sizing(old,now=accepted,**inputs)
    _require(current['status']=='READY','CURRENT_REFERENCE_NOT_ACCEPTABLE')
    _require(current['orders']==proposal['orders'] and current['target_quantities']==proposal['target_quantities'],'CURRENT_TARGET_CHANGED')
    _require(proposal['orders'],'NO_ORDERS_TO_ACCEPT')
    market=evidence['market_session'];opening=_time(market['open_at']);close=_time(market['close_at'])
    session=accepted.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    _require(market['date']==session and market['timezone']=='America/New_York' and opening<=accepted<close,'INVALID_MARKET_SESSION')
    _require(all(t.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session for t in (opening,close)),'SESSION_DATE_MISMATCH')
    _require(all(_time(ref['session_open'])==opening and _time(ref['session_close'])==close for ref in inputs['execution_references'].values()),'REFERENCE_MARKET_SESSION_MISMATCH')
    refs=market['source_references'];_require(isinstance(refs,list) and refs and all(p in inputs['source_hashes'] for p in refs),'SESSION_SOURCE_NOT_PINNED')
    _require(isinstance(evidence['operation_id'],str) and evidence['operation_id'].strip(),'OPERATION_ID_REQUIRED')
    acceptance_id=_hash(evidence);orders={};seen=set()
    for i,row in enumerate(proposal['orders']):
        sid=row['security_id'];q=row['quantity'];_require(sid not in seen,'MULTIPLE_DIRECTIONS_SAME_SECURITY');seen.add(sid)
        _require(type(q) is int and q>0 and row['side'] in ('BUY','SELL'),'INVALID_ORDER')
        oid=acceptance_id+':'+str(i)
        orders[oid]=dict(row,order_id=oid,accepted_at=accepted.isoformat(),session_close=close.isoformat(),time_in_force='DAY',filled_quantity=0,closed=None)
    result=dict(schema=SCHEMA,genesis=deepcopy(old),retarget_acceptance=deepcopy(evidence),retarget_acceptance_id=acceptance_id,
        account_id=old['account_id'],acceptance=deepcopy(old['acceptance']),acceptance_id=old['acceptance_id'],cash=old['cash'],shares=deepcopy(old['shares']),fees=old['fees'],
        events=deepcopy(old['events']),retarget_events=[],orders=orders,target_quantities=deepcopy(proposal['target_quantities']),revision=_hash(dict(previous=old['revision'],acceptance=evidence)),
        research_only=True,execution_blocked=True,source_authenticated=False,subsequent_retarget_supported=False,same_month_continuation_supported=False)
    _reserves(result);return result


def accept_retarget_proposal(state,proposal,*,sizing_inputs,market_session,operation_id,now):
    if state.get('schema')==SCHEMA:
        verified=review_retarget_ledger(state);old=verified['retarget_acceptance']
        _require(old['operation_id']==operation_id and old['proposal']==proposal and old['sizing_inputs']==sizing_inputs and old['market_session']==market_session,'SECOND_RETARGET_NOT_SUPPORTED')
        return verified
    evidence=dict(proposal=deepcopy(proposal),sizing_inputs=deepcopy(sizing_inputs),market_session=deepcopy(market_session),operation_id=operation_id,accepted_at=_time(now).isoformat())
    return _initial(state,evidence)


def _apply(state,event):
    common={'event_id','kind','expected_revision','order_id','recorded_at'}
    kind=event.get('kind');extra={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
    _require(kind in extra and set(event)==common|extra[kind],'EVENT_SCHEMA')
    _require(isinstance(event['event_id'],str) and event['event_id'].strip(),'EVENT_ID_REQUIRED')
    _require(not any(e['event_id']==event['event_id'] for e in state['events']),'DUPLICATE_EVENT_ID')
    _require(event['expected_revision']==state['revision'],'STALE_REVISION')
    _require(event['order_id'] in state['orders'],'UNKNOWN_ORDER')
    result=deepcopy(state);order=result['orders'][event['order_id']]
    _require(not order['closed'],'ORDER_CLOSED')
    recorded=_time(event['recorded_at']);accepted=_time(order['accepted_at']);close=_time(order['session_close'])
    floor=max([accepted]+[_time(e['recorded_at']) for e in state['events']])
    _require(recorded>=floor,'RECORDING_TIME_REGRESSED')
    if kind=='FILL':
        executed=_time(event['executed_at']);q=event['quantity'];price=_cash(event['price']);fee=_cash(event['fees'])
        _require(type(q) is int and 0<q<=order['quantity']-order['filled_quantity'] and price>0 and fee>=0,'INVALID_FILL')
        _require(accepted<=executed<close and executed<=recorded,'INVALID_EXECUTION_TIME')
        prior=[_time(e['executed_at']) for e in state['retarget_events'] if e['kind']=='FILL']
        _require(not prior or executed>=max(prior),'EXECUTION_TIME_REGRESSED')
        limit=Fraction(order['limit_price']);sid=order['security_id'];cash=Fraction(state['cash'])
        if order['side']=='BUY':
            _require(price<=limit,'BUY_ABOVE_LIMIT');cash-=q*price+fee;result['shares'][sid]=result['shares'].get(sid,0)+q
        else:
            _require(price>=limit and q<=result['shares'].get(sid,0),'SELL_LIMIT_OR_SHARES_INVALID');cash+=q*price-fee;result['shares'][sid]-=q
        result['cash']=str(cash);result['fees']=str(Fraction(state['fees'])+fee);order['filled_quantity']+=q
        if order['filled_quantity']==order['quantity']:order['closed']='FILLED'
    elif kind=='CANCEL':
        cancelled=_time(event['cancelled_at'])
        prior=[_time(e['executed_at']) for e in state['retarget_events'] if e['kind']=='FILL' and e['order_id']==order['order_id']]
        _require(accepted<=cancelled<=recorded and (not prior or cancelled>=max(prior)),'INVALID_CANCEL_TIME');order['closed']='CANCELLED'
    else:
        _require(recorded>=close,'SESSION_NOT_CLOSED');order['closed']='EXPIRED'
    _reserves(result);result['events'].append(deepcopy(event));result['retarget_events'].append(deepcopy(event));result['revision']=_hash(dict(previous=state['revision'],event=event))
    return result


def review_retarget_ledger(state):
    _require(state.get('schema')==SCHEMA,'RETARGET_SCHEMA_REQUIRED')
    rebuilt=_initial(state['genesis'],state['retarget_acceptance'])
    for event in state['retarget_events']:rebuilt=_apply(rebuilt,event)
    _require(rebuilt==state,'RETARGET_STATE_REPLAY_MISMATCH');return deepcopy(state)


def apply_retarget_event(state,event,*,now):
    verified=review_retarget_ledger(state)
    for old in verified['events']:
        if old['event_id']==event.get('event_id'):
            _require(old==event,'CONFLICTING_EVENT_ID');return verified
    _require(_time(event['recorded_at'])<=_time(now),'FUTURE_RECORDING')
    return _apply(verified,event)
