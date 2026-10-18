"""Strict injected V2 paper router; never records broker executions."""
import json
import re
import sqlite3
from datetime import datetime
from fractions import Fraction
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

PREFIX='/api/current_portfolio_research/paper_v2'
CONFLICTS={'STALE_REVISION','OPERATION_ID_CONFLICT','EVENT_ID_CONFLICT','ACCOUNT_ALREADY_EXISTS',
           'RESEARCH_SOURCE_WITHDRAWN',
           'ORDER_CLOSED','PRIOR_ORDERS_OPEN','ACCOUNT_CHANGED','UNKNOWN_ORDER',
           'PROPOSAL_UNKNOWN_OR_EVICTED','PROPOSAL_ACCOUNT_MISMATCH','PROPOSAL_SOURCE_CHANGED',
           'REFERENCE_NOT_ACCEPTABLE','ACCEPTANCE_BEFORE_PROPOSAL'}
EVENT_REJECTIONS={'INVALID_FILL','BUY_ABOVE_LIMIT','SELL_LIMIT_OR_SHARES','EVENT_TIME_ORDER',
    'EVENT_BEFORE_ACCEPTANCE','FILL_OUTSIDE_DAY','CANCEL_OUTSIDE_DAY','SESSION_NOT_CLOSED',
    'FUTURE_RECORD_TIME','REMAINING_BUY_RESERVE_NOT_FUNDED','REMAINING_SELL_RESERVE_NOT_FUNDED'}


READ_REASONS={'PAPER_ACTION_SOURCE_UNAVAILABLE','PAPER_REVIEW_EVIDENCE_REQUIRED','PAPER_REVIEW_ACTION_CANDIDATE','PAPER_BASELINE_REQUIRED','PAPER_BASELINE_NOT_ANCESTOR','PAPER_REVIEW_IDENTITY_CHANGED','PAPER_REVIEW_UNSUPPORTED_OPERATION','PAPER_REVIEW_SOURCE_CHANGED','PAPER_REVIEW_REPLAY_MISMATCH',
    'MONTHLY_BOUNDED_REVIEW_UNAVAILABLE','MONTHLY_ORIGIN_ARCHIVE_REQUIRED','MONTHLY_ORIGIN_BYTES_MISSING','MONTHLY_ORIGIN_BYTES_CHANGED','BOUNDED_PUBLIC_REVIEW_UNAVAILABLE','BOUNDED_UNIT_CHANGE_CANDIDATE','MONTHLY_SOURCE_UNAVAILABLE','CONTINUATION_SOURCE_UNAVAILABLE','UNIT_REVIEW_SOURCE_UNAVAILABLE',
    'UNIT_REVIEW_SOURCE_CHANGED','RESELECT_REQUIRED','REFERENCE_EXPIRED',
    'CURRENT_CASH_REFERENCE_EXPIRED','OUTSIDE_REGULAR_SESSION','LAST_QUOTE_STALE',
    'COMPLETED_MINUTE_STALE','CAPTURE_SUPERSEDED','CONTINUATION_CAPTURE_REQUIRED'}


def create_router(*,service):
    router=APIRouter()
    def error(code,status,mutation=False):
        return JSONResponse(dict(status='UNAVAILABLE',error_code=code,orders=[],research_only=True,
            execution_blocked=True,real_account=False,
            mutation_outcome=('NOT_APPLIED' if status==400 or code in CONFLICTS|EVENT_REJECTIONS else
                              'UNKNOWN_RETRY_SAME_REQUEST' if mutation else 'READ_ONLY')),status_code=status)
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('DUPLICATE_FIELDS')
            result[key]=value
        return result
    def identifier(value):
        return type(value)is str and 0<len(value.strip())<=200
    async def body(request,keys):
        if request.query_params:raise ValueError('NO_QUERY')
        chunks=[];size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>4096:raise ValueError('BODY_TOO_LARGE')
            chunks.append(chunk)
        result=json.loads(b''.join(chunks),object_pairs_hook=unique)
        if type(result)is not dict or set(result)!=set(keys):raise ValueError('EXACT_FIELDS_REQUIRED')
        return result
    async def invoke(method,values,mutation=False,preview=False,monthly=False):
        try:
            result=await run_in_threadpool(method,**values)
            if (type(result)is not dict or result.get('account_id')!=values['account_id']
                    or result.get('real_account')is not False or result.get('research_only')is not True
                    or result.get('execution_blocked')is not True or result.get('status')!=('READY' if preview else 'PAPER_ACCOUNT')):
                return error('INVALID_SERVICE_RESULT',503,mutation)
            if preview and (result.get('scope')!=('MONTHLY_RETARGET' if monthly else 'FIXED_MONTH_CONTINUATION')
                    or result.get('prior_revision')!=values['expected_revision']
                    or result.get('source_bytes_verified')is not True or result.get('orders_created')is not False):
                return error('INVALID_SERVICE_RESULT',503)
            if monthly and (result.get('capital_decision_id')!=values['decision_id'] or result.get('target_scope')!='MONTHLY_CURRENT_QUOTE_ALLOCATION' or result.get('account_mutated')is not False or any(k in result for k in ('causal_inputs','binding','files','files_base64'))):
                return error('INVALID_SERVICE_RESULT',503)
            return JSONResponse(result)
        except (ValueError,KeyError,TypeError,IndexError,AttributeError,OSError,ArithmeticError,sqlite3.Error) as exc:
            code=str(exc)
            known=code in CONFLICTS|EVENT_REJECTIONS
            return error(code if known or (not mutation and code in READ_REASONS) else 'PAPER_SOURCE_OR_STATE_UNAVAILABLE',409 if known else 503,mutation)
    @router.get(PREFIX+'/account')
    async def account(request:Request):
        pairs=list(request.query_params.multi_items())
        if len(pairs)!=1 or pairs[0][0]!='account_id' or not identifier(pairs[0][1]):return error('INVALID_REQUEST',400)
        return await invoke(service.account,{'account_id':pairs[0][1]})
    async def accept(request,continuation):
        keys={'account_id','proposal_id','operation_id'}|({'expected_revision'} if continuation else set())
        try:
            values=await body(request,keys)
            if not all(identifier(v) for v in values.values()):raise ValueError('ID_REQUIRED')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400,True)
        return await invoke(service.accept_continuation if continuation else service.accept,values,True)
    @router.post(PREFIX+'/accept')
    async def initial(request:Request):return await accept(request,False)
    @router.post(PREFIX+'/continuation/accept')
    async def continuation(request:Request):return await accept(request,True)
    @router.post(PREFIX+'/continuation/preview')
    async def continuation_preview(request:Request):
        try:
            values=await body(request,{'account_id','expected_revision'})
            if not all(identifier(v) for v in values.values()):raise ValueError('ID_REQUIRED')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400)
        return await invoke(service.continuation_preview,values,preview=True)
    @router.post(PREFIX+'/monthly/preview')
    async def monthly_preview(request:Request):
        try:
            values=await body(request,{'account_id','decision_id','expected_revision'})
            if not all(identifier(v) for v in values.values()):raise ValueError('ID_REQUIRED')
            if not re.fullmatch('[0-9a-f]{64}',values['decision_id']):raise ValueError('DECISION_ID_REQUIRED')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400)
        return await invoke(service.monthly_preview,values,preview=True,monthly=True)
    @router.post(PREFIX+'/monthly/accept')
    async def monthly_accept(request:Request):
        try:
            values=await body(request,{'account_id','proposal_id','operation_id','expected_revision'})
            if not all(identifier(v) for v in values.values()):raise ValueError('ID_REQUIRED')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400,True)
        return await invoke(service.accept_monthly_retarget,values,mutation=True)
    @router.post(PREFIX+'/event')
    async def event(request:Request):
        try:
            values=await body(request,{'account_id','event'});e=values['event']
            if not identifier(values['account_id']) or type(e)is not dict:raise ValueError('INVALID_EVENT')
            common={'event_id','type','order_id','expected_revision'}
            extra={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
            if e.get('type') not in extra or set(e)!=common|extra[e['type']]:raise ValueError('EVENT_FIELDS')
            if not all(identifier(e[k]) for k in common):raise ValueError('EVENT_IDS')
            if e['type']=='FILL':
                if type(e['quantity'])is not int or e['quantity']<=0 or any(type(e[k])not in (str,int) for k in ('price','fees')):raise ValueError('EXACT_FILL_REQUIRED')
                if Fraction(e['price'])<=0 or Fraction(e['fees'])<0:raise ValueError('INVALID_FILL_AMOUNT')
            for k in ('executed_at','cancelled_at'):
                if k in e and (not identifier(e[k]) or datetime.fromisoformat(e[k]).tzinfo is None):raise ValueError('EVENT_TIME_REQUIRED')
        except (ValueError,TypeError,ArithmeticError):return error('INVALID_REQUEST',400,True)
        return await invoke(service.event,values,True)
    return router
