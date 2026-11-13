"""Explicit reconciliation endpoints. Mounted only by an opted-in composition."""
import json
import re
import sqlite3
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*,service):
    router=APIRouter()
    def response(value,code=200):return JSONResponse(value,status_code=code,headers={'Cache-Control':'no-store'})
    async def invoke(call, dispatched=False):
        try:return response(await run_in_threadpool(call))
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z_]+',str(error)) else 'RECONCILIATION_UNAVAILABLE'
            return response(dict(status=reason,account_mutated=False,save_requires_readback=dispatched),409)
    @router.get('/api/strategy-account/transfer-reconciliation')
    async def read(request:Request):
        if request.query_params:return response({'status':'UNSUPPORTED_PARAMETERS'},422)
        return await invoke(service.read)
    @router.get('/api/strategy-account/transfer-reconciliation/profit')
    async def profit(request:Request):
        if request.query_params:return response({'status':'UNSUPPORTED_PARAMETERS'},422)
        return await invoke(service.profit)
    @router.post('/api/strategy-account/transfer-reconciliation')
    async def save(request:Request):
        if request.query_params:return response({'status':'UNSUPPORTED_PARAMETERS'},422)
        raw=bytearray()
        async for part in request.stream():
            raw.extend(part)
            if len(raw)>65536:return response({'status':'BODY_TOO_LARGE'},422)
        def pairs(items):
            output={}
            for key,value in items:
                if key in output:raise ValueError('DUPLICATE_FIELD')
                output[key]=value
            return output
        def constant(value):raise ValueError('INVALID_CONSTANT')
        try:body=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
        except (ValueError,UnicodeError,RecursionError):return response({'status':'INVALID_JSON'},422)
        return await invoke(lambda:service.save(body),dispatched=True)
    return router
