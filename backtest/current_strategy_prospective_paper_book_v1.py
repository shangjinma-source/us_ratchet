"""Pure prospective paper ledger. No persistence, registration or broker IO.

Production adapters must load trusted registration/decision hashes themselves
and recheck a real clock after acquiring their write lock. This module does not
turn a temporary preview into authority and does not perform source admission.
"""
from copy import deepcopy
from hashlib import sha256
from datetime import datetime, timezone, time
from fractions import Fraction
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v1 import (
    validate_descriptor, document, require, stamp, sessions, SCOPE, LEDGER_SCHEMA)
from backtest.current_strategy_paper_slice_v1 import _resources, _settle, _projection
from zoneinfo import ZoneInfo
import re
from data.strategy_continuous32_target_decision import REQUIRED_PINS

DECISION_SCHEMA='PROSPECTIVE_PAPER_ORDER_DECISION_V1'
SETTLEMENT_SCHEMA='PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE_V1'
CODE_PATHS=set(REQUIRED_PINS)|{'backtest/current_strategy_prospective_paper_book_v1.py',
            'backtest/current_strategy_paper_slice_v1.py',
            'backtest/current_quantity_v2_minute_day_fill.py',
            'data/strategy_paper_application_descriptor_v1.py',
            'core/strategy_account_ledger.py','core/strategy_account_difference.py',
            'backtest/partial_trend_exposure.py','data/strategy_continuous32_target_decision.py'}


def digest(value): return sha256(canonical(value)).hexdigest()


def _context(authority, now):
    admitted=validate_descriptor(**authority['descriptor_arguments'],now=now)
    app=admitted['application']
    require(CODE_PATHS <= set(app['code_sha256']), 'PROSPECTIVE_BOOK_CODE_SCOPE')
    registration=document(authority['registration_bytes'],authority['trusted_registration_sha256'])
    require(set(registration)=={'schema','scope','descriptor_sha256','account_id','simulation_id',
        'registered_at','first_session','terminal_session','integration_review_sha256'} and
        registration['schema']=='PROSPECTIVE_PAPER_REGISTRATION_V1' and registration['scope']==SCOPE and
        registration['descriptor_sha256']==admitted['descriptor_sha256'] and
        registration['account_id']==app['account_id'] and registration['simulation_id']==app['simulation_id'] and
        registration['first_session']==app['plan']['first_session'] and
        registration['terminal_session']==app['plan']['terminal_session'], 'PROSPECTIVE_REGISTRATION_BINDING')
    require(registration['integration_review_sha256']==authority['trusted_integration_review_sha256'] and
        type(registration['integration_review_sha256']) is str and
        re.fullmatch('[a-f0-9]{64}',registration['integration_review_sha256']), 'PROSPECTIVE_INTEGRATION_REVIEW_REQUIRED')
    approval=document(authority['descriptor_arguments']['approval_bytes'],
                      authority['descriptor_arguments']['trusted_approval_sha256'])
    require(stamp(app['plan']['planned_at']) <= stamp(approval['reviewed_at']) <= stamp(registration['registered_at']) <
        stamp(app['plan']['first_session']['decision_at']) and stamp(registration['registered_at'])<=stamp(now),
        'PROSPECTIVE_REGISTRATION_TIME')
    return app


def _initial(authority, initialized_at):
    app=_context(authority,initialized_at)
    first=app['plan']['first_session']
    require(stamp(first['decision_at'])<=stamp(initialized_at)<stamp(first['decision_until']),
            'PROSPECTIVE_INITIALIZATION_MISSED')
    return dict(schema=LEDGER_SCHEMA,account_id=app['account_id'],
        descriptor_sha256=authority['descriptor_arguments']['trusted_descriptor_sha256'],
        registration_sha256=authority['trusted_registration_sha256'],initialized_at=initialized_at,
        application=dict(account_id=app['account_id'],fee_bps=app['policy']['fee_bps']),
        cash='20000',shares={},orders={},operations=[],last_observed_at=None,
        last_available_at=initialized_at,revision=digest(dict(registration=authority['trusted_registration_sha256'],
            initialized_at=initialized_at)),real_account=False)


def create_book(*,authority,clock=None):
    current=(clock or (lambda:datetime.now(timezone.utc)))()
    return _initial(authority,stamp(current).isoformat())


def _accept(book, request, authority, admitted_decisions):
    app=_context(authority,request['accepted_at']);current=stamp(request['accepted_at'])
    raw=request['decision_bytes'].encode('utf8')
    decision_hash=sha256(raw).hexdigest()
    require(decision_hash in admitted_decisions and admitted_decisions[decision_hash]==raw,
            'PROSPECTIVE_DECISION_NOT_SERVER_ADMITTED')
    decision=document(raw,decision_hash)
    require(decision.get('schema')==DECISION_SCHEMA and decision.get('scope')==SCOPE and
        decision.get('status')=='VERIFIED_PROSPECTIVE_PAPER_EXECUTION_DECISION' and
        decision.get('descriptor_sha256')==book['descriptor_sha256'] and
        decision.get('registration_sha256')==book['registration_sha256'] and
        decision.get('account_id')==book['account_id'] and decision.get('account_revision')==book['revision'],
        'PROSPECTIVE_DECISION_BINDING')
    calendar=authority['descriptor_arguments']['calendar_bytes']
    rows=sessions(calendar,app['calendar_sha256'])
    row=next((r for r in rows if r['date']==decision['session_date']),None)
    require(row is not None and app['plan']['first_session']['date']<=row['date']<=app['plan']['terminal_session']['date'] and
            stamp(row['decision_at'])<=current<stamp(row['decision_until']), 'PROSPECTIVE_ACCEPT_WINDOW')
    require(stamp(decision['available_at'])<=current<stamp(decision['valid_until'])<=stamp(row['close']) and
        current>=stamp(book['last_available_at']) and
        (book['last_observed_at'] is None or current>=stamp(book['last_observed_at'])), 'PROSPECTIVE_DECISION_EXPIRED_OR_REVERSED')
    require(type(decision['target_id']) is str and bool(decision['target_id']) and
            decision['fee_bps']==app['policy']['fee_bps'] and decision.get('cancel_before_recalculate')==[],
            'PROSPECTIVE_TARGET_OR_CONFLICT')
    orders=decision['new_orders'];effective=decision['effective_target_quantities']
    require(type(orders) is list and orders and type(effective) is dict and
        all(type(q) is int and q>=0 for q in effective.values()), 'PROSPECTIVE_ORDER_DOMAIN')
    used=set()
    for index, order in enumerate(orders):
        sid=order['security_id'];side=order['side'];q=order['quantity'];price=Fraction(order['limit_price'])
        require(type(sid) is str and sid and sid not in used and side in ('BUY','SELL') and
                type(q) is int and q>0 and price>0, 'PROSPECTIVE_ORDER_INVALID')
        require(not any(o['security_id']==sid and o['closed'] is None for o in book['orders'].values()),
                'PROSPECTIVE_PENDING_CONFLICT')
        delta=effective.get(sid,0)-book['shares'].get(sid,0)
        require((side=='BUY' and 0<q<=delta) or (side=='SELL' and 0<q<=-delta), 'PROSPECTIVE_TARGET_DIFFERENCE')
        used.add(sid);oid=request['operation_id']+':'+str(index)
        require(oid not in book['orders'],'PROSPECTIVE_ORDER_ID_REUSE')
        fee=q*price*Fraction(app['policy']['fee_bps'])/10000
        book['orders'][oid]=dict(order,order_id=oid,filled_quantity=0,closed=None,fees=str(fee),
            accepted_at=request['accepted_at'],session_close=row['close'],decision_sha256=decision_hash,
            target_id=decision['target_id'])
        _resources(book)


def _settlement(book,request,admitted_settlements):
    raw=request['settlement_bytes'].encode('utf8');digest_value=sha256(raw).hexdigest()
    require(digest_value in admitted_settlements and admitted_settlements[digest_value]==raw,
            'PROSPECTIVE_SETTLEMENT_NOT_SERVER_ADMITTED')
    evidence=document(raw,digest_value)
    require(evidence.get('schema')==SETTLEMENT_SCHEMA and evidence.get('scope')==SCOPE and
        evidence.get('status')=='VERIFIED_PROSPECTIVE_PAPER_SETTLEMENT_EVIDENCE' and
        evidence.get('descriptor_sha256')==book['descriptor_sha256'] and
        evidence.get('registration_sha256')==book['registration_sha256'] and
        evidence.get('account_id')==book['account_id'] and evidence.get('account_revision')==book['revision'],
        'PROSPECTIVE_SETTLEMENT_BINDING')
    pending={oid:order for oid,order in book['orders'].items() if order['closed'] is None}
    require(evidence['pending_orders_sha256']==digest(pending) and
        evidence['observed_through']==request['observed_through'] and evidence['minutes']==request['minutes'],
        'PROSPECTIVE_SETTLEMENT_INPUT_CHANGED')
    require(stamp(evidence['observed_through'])<=stamp(evidence['available_at'])<=stamp(request['evaluated_at']),
        'PROSPECTIVE_SETTLEMENT_NOT_AVAILABLE')
    review=evidence['source_review']
    require(type(review) is dict and review.get('scope')=='PROSPECTIVE_PAPER_MINUTE_SOURCE_REVIEW_V1' and
        type(review.get('receipt_sha256')) is str and re.fullmatch('[a-f0-9]{64}',review['receipt_sha256']) and
        type(review.get('source_sha256')) is dict and review['source_sha256'] and
        all(type(p) is str and p and type(h) is str and re.fullmatch('[a-f0-9]{64}',h)
            for p,h in review['source_sha256'].items()), 'PROSPECTIVE_SETTLEMENT_SOURCE_REVIEW')
    trial=deepcopy(book)
    outcomes=_settle(trial,request)
    if any(value['status']=='UNKNOWN' for value in outcomes.values()):
        # Incomplete chronological evidence cannot advance a global watermark
        # or partially book other orders ahead of the unresolved interval.
        return {oid:(value if value['status']=='UNKNOWN' else
                     dict(status='UNKNOWN',reason='SETTLEMENT_BATCH_INCOMPLETE'))
                for oid,value in outcomes.items()}
    book.clear();book.update(trial)
    return outcomes


def _apply(book,request,authority,admitted_decisions,admitted_settlements):
    require(request['expected_revision']==book['revision'],'PROSPECTIVE_STALE_REVISION')
    require(type(request['operation_id']) is str and request['operation_id'],'PROSPECTIVE_OPERATION_ID')
    require(not any(item['request']['operation_id']==request['operation_id'] for item in book['operations']),
            'PROSPECTIVE_OPERATION_ID_REUSE')
    require(request['kind'] in ('ACCEPT','SETTLE'),'PROSPECTIVE_OPERATION_KIND')
    available=request['accepted_at'] if request['kind']=='ACCEPT' else request['evaluated_at']
    _context(authority,available)
    require(stamp(available)>=stamp(book['last_available_at']),'PROSPECTIVE_AVAILABILITY_REVERSED')
    before=book['revision']
    if request['kind']=='ACCEPT':
        _accept(book,request,authority,admitted_decisions);outcome=dict(status='PAPER_ORDERS_ACCEPTED')
    else:outcome=_settlement(book,request,admitted_settlements)
    book['last_available_at']=available
    book['revision']=digest(dict(previous=before,request=request,outcome=outcome))
    book['operations'].append(dict(request=deepcopy(request),outcome=outcome,revision=book['revision']))
    return book


def replay(book,*,authority,admitted_decisions,admitted_settlements=None):
    admitted_settlements={} if admitted_settlements is None else admitted_settlements
    result=_initial(authority,book['initialized_at'])
    for operation in book['operations']:
        _apply(result,deepcopy(operation['request']),authority,admitted_decisions,admitted_settlements)
        require(result['operations'][-1]==operation,'PROSPECTIVE_OPERATION_REPLAY')
    require(result==book,'PROSPECTIVE_BOOK_REPLAY')
    return result


def project(book,*,authority,admitted_decisions,admitted_settlements=None):
    value=_projection(replay(book,authority=authority,admitted_decisions=admitted_decisions,
                             admitted_settlements=admitted_settlements))
    value['schema']='PROSPECTIVE_PAPER_DECISION_PROJECTION_V1'
    return value


def transact(book,request,*,authority,admitted_decisions,admitted_settlements=None,current_target_id=None,clock=None):
    admitted_settlements={} if admitted_settlements is None else admitted_settlements
    rebuilt=replay(book,authority=authority,admitted_decisions=admitted_decisions,
                   admitted_settlements=admitted_settlements)
    field='accepted_at' if request['kind']=='ACCEPT' else 'evaluated_at'
    for previous in rebuilt['operations']:
        if previous['request']['operation_id']==request['operation_id']:
            comparable=deepcopy(previous['request'])
            if field not in request: comparable.pop(field)
            require(comparable==request,'PROSPECTIVE_OPERATION_ID_CONFLICT')
            return rebuilt
    current=stamp((clock or (lambda:datetime.now(timezone.utc)))())
    request=deepcopy(request)
    if field in request:
        require(stamp(request[field])==current,'PROSPECTIVE_FRESH_OPERATION_CLOCK_REQUIRED')
    request[field]=current.isoformat()
    if request['kind']=='ACCEPT':
        raw=request['decision_bytes'].encode('utf8');decision=document(raw,sha256(raw).hexdigest())
        require(type(current_target_id) is str and current_target_id and
                current_target_id==decision['target_id'],'PROSPECTIVE_CURRENT_TARGET_CHANGED')
    # Replay can be expensive: sample again immediately before applying. A live
    # service additionally samples after locking its durable store.
    before=deepcopy(rebuilt)
    changed=_apply(rebuilt,deepcopy(request),authority,admitted_decisions,admitted_settlements)
    checked=stamp((clock or (lambda:datetime.now(timezone.utc)))())
    require(checked>=current,'PROSPECTIVE_CLOCK_ROLLBACK')
    if request['kind']=='ACCEPT':
        probe=deepcopy(request);probe['accepted_at']=checked.isoformat()
        _accept(before,probe,authority,admitted_decisions)
        # Last check has no replay/source IO after its clock sample. Durable
        # publishers must repeat this same time boundary inside their lock.
        finished=stamp((clock or (lambda:datetime.now(timezone.utc)))())
        require(finished>=checked,'PROSPECTIVE_CLOCK_ROLLBACK')
        raw=request['decision_bytes'].encode('utf8');decision=document(raw,sha256(raw).hexdigest())
        local=finished.astimezone(ZoneInfo('America/New_York'))
        require(local.date().isoformat()==decision['session_date'] and
                time(10)<=local.time()<time(10,1) and finished<stamp(decision['valid_until']),
                'PROSPECTIVE_FINAL_ACCEPT_DEADLINE')
    return changed
