"""Single-plan manual paper fills. Pure functions; no IO or broker integration."""
from copy import deepcopy
from datetime import date
from fractions import Fraction
import hashlib
import json

from data.current_research_limit_plan import build_current_research_limit_plan

MODE = 'PAPER_MANUAL_FILL'
FLAGS = dict(research_only=True, execution_blocked=True, adopted=False, real_account=False)
EVENT_KEYS = {'event_id','mode','plan_id','order_id','qty','price','fees','session','expected_revision'}


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


def _amount(value, positive=False):
    _require(not isinstance(value,bool) and isinstance(value,(str,int,float,Fraction)), 'INVALID_AMOUNT_TYPE')
    parsed=Fraction(str(value))
    _require(parsed>0 if positive else parsed>=0, 'INVALID_AMOUNT')
    return parsed


def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _verified_plan(plan):
    """Reconstruct the public builder's input, never trust supplied order rows."""
    causal=plan['causal_inputs']
    rebuilt=build_current_research_limit_plan(
        research_snapshot=deepcopy(causal['research_snapshot']),
        quotes=[dict(deepcopy(q),security_id=sid) for sid,q in causal['quotes'].items()],
        available_cash=causal['available_cash'],shares=deepcopy(causal['shares']),
        account_revision=causal['account_revision'],decision_date=causal['decision_date'],
        active_date=causal['active_date'],calendar=list(causal['calendar']),
        strategy_version=causal['strategy_version'],target_quantities=deepcopy(causal['target_quantities']))
    _require(rebuilt.get('status')=='READY' and rebuilt==plan, 'PLAN_TAMPERED_OR_NOT_READY')
    return rebuilt


def _initial(plan,account_id):
    _require(isinstance(account_id,str) and bool(account_id.strip()),'ACCOUNT_ID_REQUIRED')
    return dict(FLAGS,mode=MODE,account_id=account_id,active_plan_id=plan['plan_id'],plan=deepcopy(plan),
        schema='PAPER_LEDGER_V2',plans=[deepcopy(plan)],closed_orders={},
        revision=_hash(dict(account_id=account_id,plan_id=plan['plan_id'],plan_account_revision=plan['account_revision'])),
        cash=plan['available_cash'],shares=deepcopy(plan['causal_inputs']['shares']),
        reserved_cash=plan['reserved_cash'],
        total_recorded_fees='0',events=[],filled_quantities={o['order_id']:0 for o in plan['orders']})


def initialize_paper_ledger(plan, account_id, *, mode=MODE):
    """Explicitly create one isolated paper state with one active plan."""
    try:
        _require(mode==MODE,'PAPER_MODE_REQUIRED')
        return _initial(_verified_plan(plan),account_id)
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_PAPER_PLAN_INPUT') from error


def _apply(state,event):
    _require(isinstance(event,dict),'EXPLICIT_EVENT_SCHEMA_REQUIRED')
    kind=event.get('event_type','FILL')
    common={'event_id','mode','plan_id','expected_revision','event_type'}
    expected=EVENT_KEYS if kind=='FILL' else common|({'new_plan'} if kind=='ACTIVATE_PLAN' else {'order_id','completed_session'} if kind=='EXPIRE' else {'order_id'})
    _require(kind in ('FILL','CANCEL','EXPIRE','ACTIVATE_PLAN') and set(event)==expected,'EXPLICIT_EVENT_SCHEMA_REQUIRED')
    _require(event['mode']==MODE,'PAPER_MODE_REQUIRED')
    _require(isinstance(event['event_id'],str) and bool(event['event_id'].strip()),'EVENT_ID_REQUIRED')
    for old in state['events']:
        if old['event_id']==event['event_id']:
            _require(old==event,'CONFLICTING_EVENT_ID')
            return deepcopy(state)
    _require(event['expected_revision']==state['revision'],'STALE_ACCOUNT_REVISION')
    if kind=='ACTIVATE_PLAN':
        old_orders=state['plan']['orders']
        _require(all(state['filled_quantities'][o['order_id']]==o['quantity'] or o['order_id'] in state['closed_orders'] for o in old_orders),'OLD_PLAN_HAS_OPEN_ORDERS')
        plan=_verified_plan(event['new_plan'])
        _require(event['plan_id']==plan['plan_id'] and all(p['plan_id']!=plan['plan_id'] for p in state['plans']),'PLAN_ID_REUSED_OR_MISMATCH')
        _require(plan['account_revision']==state['revision'],'NEW_PLAN_REVISION_MISMATCH')
        _require(Fraction(plan['available_cash'])==Fraction(state['cash']),'NEW_PLAN_CASH_MISMATCH')
        _require({s:q for s,q in plan['causal_inputs']['shares'].items() if q}=={s:q for s,q in state['shares'].items() if q},'NEW_PLAN_SHARES_MISMATCH')
        _require(plan['signal_asof']>=state['plan']['active_date'],'NEW_PLAN_BEFORE_OLD_ACTIVE_SESSION')
        result=deepcopy(state)
        result.update(plan=deepcopy(plan),active_plan_id=plan['plan_id'],reserved_cash=plan['reserved_cash'])
        result['plans'].append(deepcopy(plan))
        result['filled_quantities'].update({o['order_id']:0 for o in plan['orders']})
        return _commit(result,event)
    _require(event['plan_id']==state['active_plan_id'],'OTHER_PLAN_NOT_ACTIVE')
    order=next((o for o in state['plan']['orders'] if o['order_id']==event['order_id']),None)
    _require(order is not None,'UNKNOWN_ORDER_ID')
    _require(order['order_id'] not in state['closed_orders'],'ORDER_CLOSED')
    if kind in ('CANCEL','EXPIRE'):
        remaining=order['quantity']-state['filled_quantities'][order['order_id']]
        _require(remaining>0,'ORDER_ALREADY_FILLED')
        if kind=='EXPIRE':
            completed=event['completed_session']
            _require(type(completed) is str and date.fromisoformat(completed).isoformat()==completed and completed>=order['active_date'],'EXPIRY_SESSION_NOT_COMPLETED')
        result=deepcopy(state)
        result['closed_orders'][order['order_id']]=dict(event_type=kind,event_id=event['event_id'],unfilled_quantity=remaining)
        if order['side']=='BUY':
            result['reserved_cash']=str(Fraction(state['reserved_cash'])-remaining*Fraction(order['limit']))
        return _commit(result,event)
    _require(event['session']==order['active_date'],'FILL_SESSION_OUTSIDE_DAY_ORDER')
    q=event['qty']
    _require(type(q) is int and q>0,'POSITIVE_WHOLE_FILL_REQUIRED')
    _require(state['filled_quantities'][order['order_id']]+q<=order['quantity'],'ORDER_OVERFILL')
    price,fees=_amount(event['price'],True),_amount(event['fees'])
    buy=order['side']=='BUY';limit=Fraction(order['limit'])
    _require(price<=limit if buy else price>=limit,'FILL_VIOLATES_LIMIT')
    cash=Fraction(state['cash'])+(-1 if buy else 1)*q*price-fees
    sid=order['security_id'];held=state['shares'].get(sid,0)+(q if buy else -q)
    _require(cash>=0,'INSUFFICIENT_CASH_WITH_RECORDED_FEES')
    _require(held>=0,'SELL_EXCEEDS_PAPER_HOLDINGS')
    reserved=sum(((o['quantity']-state['filled_quantities'][o['order_id']]-(q if o['order_id']==order['order_id'] else 0))*Fraction(o['limit'])
                  for o in state['plan']['orders'] if o['side']=='BUY' and o['order_id'] not in state['closed_orders']),Fraction(0))
    _require(cash>=reserved,'FEES_OR_FILL_INVADE_REMAINING_BUY_RESERVATIONS')
    result=deepcopy(state)
    result['cash']=str(cash);result['shares'][sid]=held
    result['reserved_cash']=str(reserved)
    result['total_recorded_fees']=str(Fraction(state['total_recorded_fees'])+fees)
    result['filled_quantities'][order['order_id']]+=q
    return _commit(result,event)


def _commit(state,event):
    state['events'].append(deepcopy(event))
    state['revision']=_hash(dict(previous=state['revision'],event=event))
    return state


def _verified_state(state):
    _require(isinstance(state,dict),'PAPER_STATE_DICT_REQUIRED')
    _require(state.get('schema')=='PAPER_LEDGER_V2','EXPLICIT_V1_MIGRATION_REQUIRED')
    _require(state.get('mode')==MODE,'PAPER_MODE_REQUIRED')
    rebuilt=_initial(_verified_plan(state['plans'][0]),state['account_id'])
    for event in state['events']:
        rebuilt=_apply(rebuilt,event)
    _require(rebuilt==state,'PAPER_STATE_TAMPERED')
    return rebuilt


def apply_paper_fill(state,event):
    """Late entry is allowed: validate event session, never today's wall clock.

    Recorded fees are actual explicit paper-event costs, not assumed zero.
    Same event payload is idempotent even after its original revision advanced.
    """
    try:
        _require(isinstance(event,dict) and set(event)==EVENT_KEYS,'EXPLICIT_FILL_EVENT_SCHEMA_REQUIRED')
        return _apply(_verified_state(state),event)
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_PAPER_FILL_INPUT') from error


def apply_paper_order_event(state,event):
    """EXPIRE accepts a manual completed-session declaration, including active day.

    No wall-clock inference proves that the session has closed. A future API
    must independently authenticate the exchange session's completion.
    """
    try:
        _require(isinstance(event,dict) and event.get('event_type') in ('CANCEL','EXPIRE'),'CANCEL_OR_EXPIRE_REQUIRED')
        return _apply(_verified_state(state),event)
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_PAPER_ORDER_EVENT') from error


def activate_paper_plan(state,new_plan,event):
    """Replace only a settled/closed plan without modifying actual paper capital."""
    try:
        _require(isinstance(event,dict) and set(event)=={'event_id','mode','event_type','plan_id','expected_revision'} and event['event_type']=='ACTIVATE_PLAN','ACTIVATION_EVENT_REQUIRED')
        return _apply(_verified_state(state),dict(deepcopy(event),new_plan=deepcopy(new_plan)))
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_PAPER_ACTIVATION') from error


def migrate_paper_ledger(state):
    """Explicit V1 migration: verify every old event and full legacy state first.

    V1 fill revision hashes remain unchanged; new lifecycle fields are added only.
    No events, cash, quantities or account identity are silently discarded.
    """
    try:
        _require(isinstance(state,dict) and 'schema' not in state,'EXPLICIT_LEGACY_STATE_REQUIRED')
        rebuilt=_initial(_verified_plan(state['plan']),state['account_id'])
        for event in state['events']:
            _require(set(event)==EVENT_KEYS,'LEGACY_FILL_EVENTS_ONLY')
            rebuilt=_apply(rebuilt,event)
        legacy={k:v for k,v in rebuilt.items() if k not in ('schema','plans','closed_orders')}
        _require(legacy==state,'LEGACY_STATE_TAMPERED')
        return rebuilt
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_LEGACY_MIGRATION') from error


def review_paper_ledger(state):
    try:
        verified=_verified_state(state)
    except (KeyError,TypeError,IndexError,ZeroDivisionError,OverflowError) as error:
        raise ValueError('INVALID_PAPER_REVIEW_INPUT') from error
    plan=verified['plan']
    return dict(FLAGS,mode=MODE,account_id=verified['account_id'],plan_id=plan['plan_id'],research_id=plan['research_id'],
        revision=verified['revision'],cash=verified['cash'],shares=deepcopy(verified['shares']),
        reserved_cash=verified['reserved_cash'],unreserved_cash=str(Fraction(verified['cash'])-Fraction(verified['reserved_cash'])),
        target_quantities=deepcopy(plan['target_quantities']),total_recorded_fees=verified['total_recorded_fees'],
        price_touch_status='UNKNOWN_NOT_EVALUATED',fill_authority='EXPLICIT_PAPER_MANUAL_EVENTS_ONLY',
        expiry_authority='MANUAL_COMPLETED_SESSION_DECLARATION_NOT_CLOCK_VERIFIED',
        orders=[dict(order_id=o['order_id'],security_id=o['security_id'],side=o['side'],
            planned_quantity=o['quantity'],filled_quantity=verified['filled_quantities'][o['order_id']],
            unfilled_quantity=o['quantity']-verified['filled_quantities'][o['order_id']],
            order_status=verified['closed_orders'].get(o['order_id'],{}).get('event_type','FILLED' if verified['filled_quantities'][o['order_id']]==o['quantity'] else 'OPEN'),
            recorded_fees=str(sum((Fraction(e['fees']) for e in verified['events'] if e.get('order_id')==o['order_id'] and 'fees' in e),Fraction(0))),
            event_ids=[e['event_id'] for e in verified['events'] if e.get('order_id')==o['order_id']]) for o in plan['orders']],
        plan_history_ids=[p['plan_id'] for p in verified['plans']])
