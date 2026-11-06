"""Unregistered research-only HTTP orchestration; never mounts production."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_difference import require


def create_router(*, coordinator):
    router=APIRouter()

    async def invoke(request, retry):
        dispatched=False
        try:
            require(not request.query_params,'UNSUPPORTED_PARAMETERS')
            raw=bytearray()
            async for part in request.stream():
                raw.extend(part);require(len(raw)<=8192,'BODY_TOO_LARGE')
            def pairs(items):
                result={}
                for key,value in items:
                    require(key not in result,'DUPLICATE_JSON_FIELD');result[key]=value
                return result
            body=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
            require(type(body) is dict,'BODY_FIELDS')
            if retry:require(not body,'BODY_FIELDS')
            else:
                require(set(body)=={'expected_revision','event'},'BODY_FIELDS')
                require(type(body['event']) is dict and set(body['event'])=={'event_id','kind','amount','cash_basis'},'CASH_EVENT_FIELDS')
                require(body['event']['kind']=='CASH_CONFIRM','CASH_CONFIRM_REQUIRED')
            dispatched=True
            result=await run_in_threadpool(coordinator.retry_advice if retry else coordinator.save_cash, *([] if retry else [body]))
            return JSONResponse(result,status_code=503 if result['cash_saved'] is None else 200,headers={'Cache-Control':'no-store'})
        except Exception as error:
            # Once dispatched, this router cannot infer durability from the
            # exception class. Conservatively request reconciliation.
            uncertain=dispatched and not retry
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'REQUEST_REJECTED'
            return JSONResponse(dict(cash_saved=None if uncertain or retry else False,advice_ready=False,
                reason='CASH_WRITE_REQUIRES_RECONCILIATION' if uncertain else reason,orders_created=False),
                status_code=503 if uncertain else 409 if reason=='STALE_REVISION' else 422,headers={'Cache-Control':'no-store'})

    @router.post('/api/research-candidate/cash-save-and-preview')
    async def save(request:Request):return await invoke(request,False)

    @router.post('/api/research-candidate/advice-retry')
    async def retry(request:Request):return await invoke(request,True)

    return router
