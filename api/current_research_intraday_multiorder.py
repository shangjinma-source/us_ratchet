"""Strict dependency-injected multi-order paper routes; no production singleton."""
import json
from fractions import Fraction
import re
import sqlite3
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from data.current_research_intraday_buy_plan import _time
from data.current_research_intraday_multiorder_service import IntradayMultiorderService

BASE='/api/research_paper/intraday_multiorder'
FLAGS=dict(research_only=True,execution_blocked=True,real_account=False)
MAX_BODY_BYTES=32768
# Exact service reasons reached before any commit in the current service contract.
DEFINITE_REJECTIONS=frozenset({
    'PREVIEW_NOT_FOUND','PREVIEW_ACCOUNT_BINDING_MISMATCH','STALE_ACCOUNT_REVISION',
    'EXECUTION_EVIDENCE_CHANGED_REPREVIEW_REQUIRED',
    'CURRENT_CONTINUATION_NOT_ACCEPTABLE:STALE_EXECUTION_REFERENCE',
})


def _require(value,message):
    if not value:raise ValueError(message)


def _keys(value,keys):
    _require(isinstance(value,dict) and set(value)==set(keys),'EXACT_REQUEST_FIELDS_REQUIRED')


def _identifier(value):
    _require(isinstance(value,str) and re.fullmatch('[A-Za-z0-9:_-]{1,160}',value),'INVALID_ID')


def _digest(value):
    _require(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value),'INVALID_DIGEST_OR_REVISION')


def _pairs(pairs):
    result={}
    for key,value in pairs:
        _require(key not in result,'DUPLICATE_JSON_FIELD');result[key]=value
    return result


async def _body(request):
    _require(not request.query_params,'POST_QUERY_NOT_ALLOWED')
    _require(request.headers.get('content-type','').split(';')[0].strip().lower()=='application/json','JSON_CONTENT_TYPE_REQUIRED')
    raw=await request.body();_require(len(raw)<=MAX_BODY_BYTES,'REQUEST_TOO_LARGE')
    return json.loads(raw,object_pairs_hook=_pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON_NUMBER')))


def _event(event):
    extras={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
    _require(isinstance(event,dict) and isinstance(event.get('kind'),str) and event['kind'] in extras,'EVENT_KIND_UNSUPPORTED')
    _keys(event,{'event_id','kind','expected_revision','order_id'}|extras[event['kind']])
    _identifier(event['event_id']);_identifier(event['order_id']);_digest(event['expected_revision'])
    if event['kind']=='FILL':
        _require(type(event['quantity']) is int and 0<event['quantity']<=9007199254740991,'INTEGER_QUANTITY_REQUIRED')
        for field in ('price','fees'):
            value=event[field]
            _require(isinstance(value,str) and 0<len(value)<=128,'EXACT_MONEY_STRING_REQUIRED')
            amount=Fraction(value)
            _require(amount>0 if field=='price' else amount>=0,'INVALID_FILL_MONEY')
    for field in ('executed_at','cancelled_at'):
        if field in event:
            _require(isinstance(event[field],str) and len(event[field])<=64,'TIMESTAMP_STRING_REQUIRED');_time(event[field])


def create_router(*,service):
    """Caller owns service, account authorization and mounting. No implicit paths."""
    _require(isinstance(service,IntradayMultiorderService),'EXPLICIT_MULTIORDER_SERVICE_REQUIRED')
    router=APIRouter(prefix=BASE)

    async def invoke(request,kind):
        mutation=kind in ('accept','event');service_called=False
        try:
            if kind=='account':
                _require(not await request.body(),'GET_BODY_NOT_ALLOWED')
                _require(set(request.query_params)=={'account_id'} and len(request.query_params.multi_items())==1,'EXACT_ACCOUNT_QUERY_REQUIRED')
                account_id=request.query_params['account_id'];_identifier(account_id)
                return await run_in_threadpool(service.account,account_id)
            body=await _body(request)
            keys={'preview':{'account_id','expected_revision'},'accept':{'account_id','proposal_id','operation_id','expected_revision'},'event':{'account_id','event'}}
            _keys(body,keys[kind]);_identifier(body['account_id'])
            if kind=='event':
                _event(body['event']);service_called=True
                result=await run_in_threadpool(service.event,body['account_id'],body['event'])
                return dict(result,mutation_outcome='APPLIED_OR_IDEMPOTENT')
            _digest(body['expected_revision'])
            if kind=='preview':return await run_in_threadpool(service.preview,body['account_id'],body['expected_revision'])
            _digest(body['proposal_id']);_identifier(body['operation_id'])
            service_called=True
            result=await run_in_threadpool(service.accept,body['account_id'],body['proposal_id'],body['operation_id'],body['expected_revision'])
            return dict(result,mutation_outcome='APPLIED_OR_IDEMPOTENT')
        except (ValueError,KeyError,TypeError,OSError,ArithmeticError,sqlite3.Error) as error:
            reason=str(error);code=reason.split(':',1)[0]
            if not re.fullmatch('[A-Z][A-Z0-9_]{0,100}',code):code='REQUEST_FAILED'
            outcome='NOT_A_MUTATION' if not mutation else 'NOT_APPLIED' if not service_called or reason in DEFINITE_REJECTIONS else 'UNKNOWN_RETRY_SAME_REQUEST'
            return JSONResponse(status_code=400,content=dict(FLAGS,status='UNAVAILABLE',error_code=code,mutation_outcome=outcome,
                retry_same_request=outcome=='UNKNOWN_RETRY_SAME_REQUEST',message='多订单纸面请求未完成：'+reason))

    @router.get('/account')
    async def account(request:Request):return await invoke(request,'account')

    @router.post('/preview')
    async def preview(request:Request):return await invoke(request,'preview')

    @router.post('/accept')
    async def accept(request:Request):return await invoke(request,'accept')

    @router.post('/event')
    async def event(request:Request):return await invoke(request,'event')

    return router
