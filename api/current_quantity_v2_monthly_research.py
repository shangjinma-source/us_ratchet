"""Injected monthly research routes; no production instance or source discovery."""
import json
import re
import sqlite3
import subprocess
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

PREFIX='/api/current_portfolio_research/paper_v2/monthly/research'
CONFLICTS={'MONTHLY_RESEARCH_EXPIRED','MONTHLY_RESEARCH_SUPERSEDED','MONTHLY_RESEARCH_ACCOUNT_CHANGED','STALE_REVISION','ACCOUNT_CHANGED','MONTHLY_REGISTERED_ACCOUNT_CHANGED',
           'MONTHLY_ATTEMPT_IN_PROGRESS_OR_RETRY_REQUIRED'}
SOURCE_ERRORS={'INVALID_MONTHLY_CONFIGURATION','MONTHLY_CONFIGURATION_REQUIRED','MONTHLY_RESEARCH_UNAVAILABLE','MONTHLY_RESEARCH_SELECTION_UNAVAILABLE','MONTHLY_SOURCE_UNAVAILABLE','MONTHLY_REGISTRY_MISSING',
               'MONTHLY_REGISTRATION_UNKNOWN','MONTHLY_RESULT_NOT_READY',
               'REGISTRY_SOURCE_CHANGED','MONTHLY_RESULT_CHANGED'}


def create_router(*, service):
    router=APIRouter()
    def error(code,status):
        return JSONResponse(dict(status='UNAVAILABLE',error_code=code,
            account_mutated=False,orders_created=False,research_only=True,
            execution_blocked=True,real_account=False,automatic_retry=False),status_code=status)
    def identifier(value):
        return type(value)is str and 0<len(value.strip())<=200
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('DUPLICATE_FIELDS')
            result[key]=value
        return result
    async def invoke(method,values,current=False):
        try:
            result=await run_in_threadpool(method,**values)
            if (type(result)is not dict or result.get('account_id')!=values['account_id']
                or result.get('status')not in ({'READY','INCOMPLETE','ATTEMPT_STARTED','FAILED','PENDING','UNAVAILABLE'} if current else {'READY','INCOMPLETE','ATTEMPT_STARTED','FAILED'})
                or result.get('account_mutated')is not False or result.get('orders_created')is not False
                or result.get('research_only')is not True or result.get('execution_blocked')is not True
                or result.get('real_account')is not False
                or any(k in result for k in ('capital_decision','binding','causal_inputs','files','files_base64','source_hashes'))):
                return error('INVALID_SERVICE_RESULT',503)
            if 'expected_revision' in values and result.get('state_revision')!=values['expected_revision']:
                return error('INVALID_SERVICE_RESULT',503)
            if 'registration_id' in values and result.get('registration_id')!=values['registration_id']:
                return error('INVALID_SERVICE_RESULT',503)
            registration=result.get('registration_id')
            missing_registration=current and result['status'] in {'PENDING','FAILED','UNAVAILABLE'} and registration is None
            if (type(result.get('selected_for_current_account'))is not bool
                or (not missing_registration and (not isinstance(registration,str) or not re.fullmatch('[a-f0-9]{64}',registration)))):
                return error('INVALID_SERVICE_RESULT',503)
            if result.get('automatic_retry')is not False or (result['status'] in {'PENDING','ATTEMPT_STARTED'} and result.get('worker_liveness')!='UNKNOWN'):
                return error('INVALID_SERVICE_RESULT',503)
            if result['status']=='READY':
                if (not isinstance(result.get('decision_id'),str) or not re.fullmatch('[a-f0-9]{64}',result['decision_id'])
                    or result.get('research_id')!=result['decision_id'][:24]):return error('INVALID_SERVICE_RESULT',503)
            elif result.get('decision_id')is not None or result.get('research_id')is not None or result['selected_for_current_account']is not False:
                return error('INVALID_SERVICE_RESULT',503)
            return JSONResponse(result)
        except (ValueError,KeyError,TypeError,IndexError,AttributeError,OSError,ArithmeticError,sqlite3.Error,subprocess.SubprocessError) as exc:
            code=str(exc)
            return error(code if code in CONFLICTS|SOURCE_ERRORS else 'MONTHLY_RESEARCH_UNAVAILABLE',409 if code in CONFLICTS else 503)
    @router.post(PREFIX+'/generate')
    async def generate(request:Request):
        try:
            if request.query_params:raise ValueError('NO_QUERY')
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>4096:raise ValueError('BODY_TOO_LARGE')
                chunks.append(chunk)
            values=json.loads(b''.join(chunks),object_pairs_hook=unique)
            if type(values)is not dict or set(values)!={'account_id','expected_revision','retry_failed'}:raise ValueError('EXACT_FIELDS')
            if not identifier(values['account_id']) or not identifier(values['expected_revision']) or type(values['retry_failed'])is not bool:raise ValueError('INVALID_FIELDS')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400)
        return await invoke(service.generate,values)
    @router.get(PREFIX)
    async def read(request:Request):
        try:
            values=unique(request.query_params.multi_items())
            if set(values) not in ({'account_id'},{'account_id','registration_id'}) or not identifier(values['account_id']):raise ValueError('INVALID_FIELDS')
            if 'registration_id' in values and not re.fullmatch('[a-f0-9]{64}',values['registration_id']):raise ValueError('INVALID_FIELDS')
            async for chunk in request.stream():
                if chunk:raise ValueError('NO_BODY')
        except (ValueError,TypeError):return error('INVALID_REQUEST',400)
        return await invoke(service.current if set(values)=={'account_id'} else service.read,values,current=set(values)=={'account_id'})
    return router
