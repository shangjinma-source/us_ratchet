"""Versioned single-input arrived-capital HTTP interface."""
import json,re,sqlite3
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

def create_router(*,service):
    router=APIRouter()
    async def invoke(request,method,fields):
        body=None
        try:
            raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>4096:raise ValueError('CAPITAL_BODY_TOO_LARGE')
            def unique(pairs):
                result={}
                for k,v in pairs:
                    if k in result:raise ValueError('CAPITAL_DUPLICATE_FIELD')
                    result[k]=v
                return result
            body=json.loads(raw,object_pairs_hook=unique)
            if type(body) is not dict or set(body)!=fields:raise ValueError('CAPITAL_BODY_FIELDS')
            if type(body['event_id']) is not str or not 0<len(body['event_id'])<=128:raise ValueError('CAPITAL_EVENT_ID')
            for key in ('expected_revision','previous_target_id'):
                if key in body and (type(body[key]) is not str or not re.fullmatch('[a-f0-9]{64}',body[key])):raise ValueError('CAPITAL_SNAPSHOT_FIELDS')
            return await run_in_threadpool(method,**body)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:
            reason=str(error)
            if not re.fullmatch('[A-Z][A-Z0-9_]{0,99}',reason):reason='CAPITAL_OPERATION_UNAVAILABLE'
            result=dict(status='BLOCKED',reason=reason,credited=None)
            if type(body) is dict and type(body.get('event_id')) is str:
                result['event_id']=body['event_id']
                try:
                    state=await run_in_threadpool(service.status,event_id=body['event_id'])
                    result.update(credited=state['credited'],recovery_status=state['status'])
                except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):pass
            return JSONResponse(status_code=409,content=result)
    @router.post('/api/strategy-capital-v2/arrive')
    async def arrive(request:Request):return await invoke(request,service.arrive,{'event_id','contribution_amount','expected_revision','previous_target_id'})
    @router.post('/api/strategy-capital-v2/withdraw')
    async def withdraw(request:Request):return await invoke(request,service.withdraw,{'event_id'})
    @router.post('/api/strategy-capital-v2/status')
    async def status(request:Request):return await invoke(request,service.status,{'event_id'})
    @router.post('/api/strategy-capital-v2/configure')
    async def configure(request:Request):return await invoke(request,service.configure,{'event_id'})
    @router.post('/api/strategy-capital-v2/recover-publication')
    async def recover(request:Request):return await invoke(request,service.recover_publication,{'event_id'})
    return router
