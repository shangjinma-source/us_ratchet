"""Read-only planning for new advice price observations; never fills or returns.

Horizon 1 means the first complete exchange session AFTER the advice session.
Calendar bytes/hash are server-owned inputs. Missing future sessions remain WAIT.
A due date is not permission to collect: original execution proof still needs review.
Pagination is a scan cursor, never a completion watermark. WAIT_CLOSE and
WAIT_CALENDAR rows must be rescanned or retained in a durable due queue.
"""
from hashlib import sha256
from datetime import datetime
from zoneinfo import ZoneInfo
from fractions import Fraction
import json
from core.strategy_account_difference import require, timestamp
from data.strategy_daily_advice_journal_v1 import encoded

NY=ZoneInfo('America/New_York')


def plan_advice_followup(*, event, event_sha256, final_return, final_return_sha256,
                         calendar_bytes, calendar_sha256, now):
    require(sha256(encoded(event)).hexdigest()==event_sha256,'EVENT_HASH_MISMATCH')
    require(sha256(encoded(final_return)).hexdigest()==final_return_sha256,'RETURN_HASH_MISMATCH')
    require(final_return['event_id']==event['event_id'] and final_return['event_sha256']==event_sha256,
            'RETURN_EVENT_MISMATCH')
    generated=timestamp(event['generated_at']);checked=timestamp(final_return['checked_at'])
    require(generated<=checked<=now,'FOLLOWUP_FUTURE_EVENT')
    response=event['response']
    require(response['target_id']==event['target_id'] and response['account_revision']==event['account_revision'],
            'FOLLOWUP_EVENT_BINDING')
    require(sha256(encoded(response)).hexdigest()==event['response_sha256'],'RESPONSE_HASH_MISMATCH')
    if response['status']!='READY' or final_return['status']!='READY' or not response.get('new_orders'):
        return dict(status='NO_ACTIONABLE_ADVICE',observations=[])
    require(type(calendar_bytes)is bytes and len(calendar_bytes)<=4*1024*1024 and
            sha256(calendar_bytes).hexdigest()==calendar_sha256,'FOLLOWUP_CALENDAR_HASH')
    calendar=json.loads(calendar_bytes)
    require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','FOLLOWUP_CALENDAR_SCHEMA')
    sessions=calendar['sessions'];dates=[];last=None
    for session in sessions:
        opened=timestamp(session['open']);closed=timestamp(session['close'])
        require(opened<closed and (last is None or last<opened) and
                opened.astimezone(NY).date().isoformat()==session['date']==closed.astimezone(NY).date().isoformat(),
                'FOLLOWUP_CALENDAR_SESSION')
        require(session['date'] not in dates,'FOLLOWUP_CALENDAR_DUPLICATE')
        dates.append(session['date']);last=closed
    day=generated.astimezone(NY).date().isoformat()
    if day not in dates:return dict(status='WAIT_CALENDAR',observations=[])
    index=dates.index(day);session=sessions[index]
    require(timestamp(session['open'])<=generated<=checked<timestamp(session['close']), 'ADVICE_OUTSIDE_SESSION')
    policy=event.get('policy_references',{})
    evidence=policy.get('evidence_references') or {}
    # These are recorded actual server references, never guessed from a ticker.
    release=evidence.get('trusted_release_sha256')
    if not policy.get('policy_id') or not release:
        return dict(status='WAIT_POLICY_BINDING',observations=[])
    rows=[]
    for order_index,order in enumerate(response['new_orders']):
        sid=order['security_id'];quote=response.get('reference_quotes',{}).get(sid,{})
        require(quote.get('security_id')==sid and type(quote.get('ticker'))is str,'FOLLOWUP_SECURITY_BINDING')
        require(order['side'] in {'BUY','SELL'} and type(order['quantity'])is int and order['quantity']>0,
                'FOLLOWUP_ORDER_INVALID')
        require(Fraction(order['limit_price'])>0,'FOLLOWUP_LIMIT_INVALID')
        require(timestamp(quote['observed_at'])<=generated and checked<timestamp(quote['reference_valid_until']),
                'FOLLOWUP_INVALID_REFERENCE_TIME')
        for horizon in (1,5,20):
            identity=dict(schema='DAILY_ADVICE_PRICE_OBSERVATION_KEY_V1',account_id=event['account_id'],
                target_id=event['target_id'],account_revision=event['account_revision'],event_id=event['event_id'],
                event_sha256=event_sha256,
                policy_id=policy['policy_id'],policy_release_sha256=release,
                security_id=sid,side=order['side'],order_index=order_index,horizon_sessions=horizon)
            available=index+horizon<len(sessions)
            due=sessions[index+horizon] if available else None
            rows.append(dict(identity,observation_id=sha256(encoded(identity)).hexdigest(),
                final_return_sha256=final_return_sha256,calendar_sha256=calendar_sha256,ticker=quote['ticker'],
                reference_limit=order['limit_price'],reference_quantity=order['quantity'],reference_session=day,
                observation_session=due['date'] if due else None,observation_close=due['close'] if due else None,
                status='WAIT_CALENDAR' if due is None else ('DUE' if timestamp(due['close'])<=now else 'WAIT_CLOSE'),
                capture_admitted=False,admission_reason='EXECUTION_SOURCE_PROOF_NOT_REVIEWED',
                actual_fill_inferred=False,performance_computed=False,displayed=False))
    return dict(status='PLANNED_NOT_CAPTURE_ADMITTED',observations=rows)


def plan_journal_page(*,journal,account_id,calendar_bytes,calendar_sha256,now,after=0,limit=20):
    """Bounded consistent SQLite snapshot; private bodies never exposed by HTTP here."""
    require(type(after)is int and after>=0 and type(limit)is int and 1<=limit<=100,'PAGINATION_INVALID')
    if not journal.path.exists():return dict(items=[],next_cursor=after,
        cursor_semantics='SCAN_ONLY_NOT_COMPLETION',future_recheck_required=True)
    with journal._connection(readonly=True) as database:
        database.execute('BEGIN')
        rows=database.execute('SELECT sequence,event_id,account_id,body,digest FROM advice_events WHERE account_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                              (account_id,after,limit)).fetchall()
        items=[]
        for sequence,event_id,stored_account,raw,digest in rows:
            require(stored_account==account_id and sha256(raw).hexdigest()==digest,'FOLLOWUP_JOURNAL_HASH')
            event=json.loads(raw);journal._validate_event(event,event_id,account_id,now)
            returns,_,_,_=journal._returns(database,event,digest,now)
            if not returns:
                items.append(dict(event_id=event_id,status='WAIT_RETURN_AUDIT',observations=[]));continue
            _,return_raw,return_digest=returns[-1]
            plan=plan_advice_followup(event=event,event_sha256=digest,final_return=json.loads(return_raw),
                final_return_sha256=return_digest,calendar_bytes=calendar_bytes,calendar_sha256=calendar_sha256,now=now)
            items.append(dict(plan,event_id=event_id,event_sha256=digest))
    return dict(items=items,next_cursor=rows[-1][0] if rows else after,
                cursor_semantics='SCAN_ONLY_NOT_COMPLETION',future_recheck_required=True)


def reconcile_observation_plan(previous, current):
    """Before future capture, an existing observation cannot silently change date.

    Extending a calendar may fill a previously unresolved horizon. Any already
    resolved date/close changing under the same stable key is a recovery conflict.
    This pure check neither persists a queue nor treats a scan as completion.
    """
    require(previous['observation_id']==current['observation_id'],'OBSERVATION_KEY_MISMATCH')
    for key in ('observation_session','observation_close'):
        if previous.get(key) is not None:
            require(previous[key]==current.get(key),'OBSERVATION_CALENDAR_CONFLICT')
    return dict(current)
