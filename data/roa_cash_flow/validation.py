"""Isolated cash classification validation; no persistence or return calculation."""
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
import json
from core.strategy_account_ledger import apply_event
from .audit import audit_cash_changes


def validate_classification(*, baseline, current, document, now, existing=None):
    def require(ok, message):
        if not ok:raise ValueError(message)
    def instant(value):
        require(type(value)is str,'TIME_STRING_REQUIRED')
        result=datetime.fromisoformat(value)
        require(result.utcoffset() is not None,'AWARE_TIME_REQUIRED')
        require(result<=now,'FUTURE_EFFECTIVE_TIME')
        return result
    require(now.utcoffset() is not None,'AWARE_CLOCK_REQUIRED')
    required={'schema','account_id','cash_event_id','before_revision','after_revision','net_change','items'}
    require(type(document)is dict and set(document)==required,'CLASSIFICATION_FIELDS')
    require(document['schema']=='CASH_CHANGE_CLASSIFICATION_V1','CLASSIFICATION_SCHEMA')
    audit=audit_cash_changes(baseline=baseline,current=current)
    require(document['account_id']==current['account_id'],'ACCOUNT_MISMATCH')
    rows=[r for r in audit['confirmations'] if r['event_id']==document['cash_event_id']]
    require(len(rows)==1,'CASH_EVENT_NOT_IN_AUDIT')
    state=baseline;bound=None
    for row in current['events'][len(baseline['events']):]:
        before=state['revision'];state,_=apply_event(state,row['payload'],expected_revision=before)
        if row['payload']['event_id']==document['cash_event_id']:bound=(before,state['revision'])
    require(bound==(document['before_revision'],document['after_revision']),'CONFIRMATION_REVISION_MISMATCH')
    def exact(value):
        require(type(value)in(str,int),'EXACT_AMOUNT_REQUIRED')
        return F(value)
    difference=exact(document['net_change'])
    require(difference==F(rows[0]['unexplained_net_change']),'NET_CHANGE_MISMATCH')
    items=document['items'];require(type(items)is list and bool(items),'ITEMS_REQUIRED')
    total=F(0);external=F(0);blocked=False;ids=set()
    for item in items:
        require(type(item)is dict and set(item)=={'item_id','kind','amount','effective_at'},'ITEM_FIELDS')
        require(type(item['item_id'])is str and bool(item['item_id']) and item['item_id']not in ids,'DUPLICATE_ITEM_ID');ids.add(item['item_id'])
        kind=item['kind'];require(kind in {'DEPOSIT','WITHDRAWAL','INCOME','FEE','CORRECTION','UNRECORDED_TRADE'},'UNKNOWN_CLASSIFICATION')
        amount=exact(item['amount']);require(amount!=0,'ZERO_ITEM')
        require(kind not in {'DEPOSIT','INCOME'} or amount>0,'POSITIVE_AMOUNT_REQUIRED')
        require(kind not in {'WITHDRAWAL','FEE'} or amount<0,'NEGATIVE_AMOUNT_REQUIRED')
        instant(item['effective_at']);total+=amount
        if kind in {'DEPOSIT','WITHDRAWAL'}:external+=amount
        if kind in {'CORRECTION','UNRECORDED_TRADE'}:blocked=True
    require(total==difference,'ITEM_TOTAL_MISMATCH')
    raw=json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if existing is not None:
        require(existing==document,'CASH_EVENT_CLASSIFICATION_CONFLICT')
    return dict(status='ALREADY_CLASSIFIED' if existing is not None else 'VALID_CLASSIFICATION',
        document_sha256=sha256(raw).hexdigest(),net_external_flow=str(external),
        performance_blocked=blocked,performance_reason='ACCOUNT_FACT_REPAIR_REQUIRED' if blocked else 'FLOW_TIMED_VALUATIONS_STILL_REQUIRED',
        performance_ready=False,account_mutated=False,persisted=False,
        limitation='User supplied classification is not independent proof of broker facts; effective_at is explicit, never inferred from receipt time.')
