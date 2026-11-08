"""Explicitly mounted ROA HTTP orchestration with cash durability semantics."""
import json
import re
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_difference import require


def create_router(*, coordinator):
    router=APIRouter()

    @router.get('/static/strategy_roa_controller.js')
    async def controller_asset():
        return FileResponse(Path(__file__).resolve().parents[1]/'web/strategy_roa_controller.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})

    @router.get('/static/strategy_roa_mount.js')
    async def mount_asset():
        return FileResponse(Path(__file__).resolve().parents[1]/'web/strategy_roa_mount.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})

    async def invoke(request, retry, status=False):
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
            operation=coordinator.cash_status if status else coordinator.retry_advice if retry else coordinator.save_cash
            result=await run_in_threadpool(operation, *([] if retry else [body]))
            return JSONResponse(result,status_code=503 if not retry and result['cash_saved'] is None else 200,headers={'Cache-Control':'no-store'})
        except Exception as error:
            # Once dispatched, this router cannot infer durability from the
            # exception class. Conservatively request reconciliation.
            uncertain=dispatched and not retry and not status
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'REQUEST_REJECTED'
            return JSONResponse(dict(cash_saved=None if uncertain or retry or status else False,advice_ready=False,
                reason='CASH_WRITE_REQUIRES_RECONCILIATION' if uncertain else reason,orders_created=False),
                status_code=503 if uncertain else 409 if reason=='STALE_REVISION' else 422,headers={'Cache-Control':'no-store'})

    @router.post('/api/strategy-roa/cash-save-and-preview')
    async def save(request:Request):return await invoke(request,False)

    @router.post('/api/strategy-roa/advice-retry')
    async def retry(request:Request):return await invoke(request,True)

    @router.post('/api/strategy-roa/cash-status')
    async def status(request:Request):return await invoke(request,False,True)

    @router.get('/api/strategy-roa/config')
    async def configuration():
        return JSONResponse(dict(active=True,strategy_kind='ROA_DEFENSIVE_V1',strategy_epoch=coordinator.lifecycle.epoch,account_id=coordinator.account_service.account_id),headers={'Cache-Control':'no-store'})

    @router.get('/api/strategy-roa/snapshot')
    async def snapshot():
        try:
            result=await run_in_threadpool(coordinator.snapshot)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as error:
            result=coordinator.unavailable_snapshot(error)
            return JSONResponse(result,status_code=503,headers={'Cache-Control':'no-store'})

    return router
