"""Opt-in versioned API; no production mount and no client decision/profile."""
import re,json,sqlite3
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*,service):
    router=APIRouter()
    async def invoke(request,method,fields):
        try:
            raw=bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>4096:raise ValueError("CAPITAL_BODY_TOO_LARGE")
            def unique(pairs):
                result={}
                for key,value in pairs:
                    if key in result:raise ValueError("CAPITAL_DUPLICATE_FIELD")
                    result[key]=value
                return result
            body=json.loads(raw,object_pairs_hook=unique)
            if type(body) is not dict or set(body)!=set(fields):raise ValueError("CAPITAL_BODY_FIELDS")
            if type(body.get("event_id")) is not str or not 0<len(body["event_id"])<=128:
                raise ValueError("CAPITAL_EVENT_ID")
            for key in ("expected_revision","previous_target_id"):
                if key in body and (type(body[key]) is not str or not re.fullmatch("[a-f0-9]{64}",body[key])):
                    raise ValueError("CAPITAL_SNAPSHOT_FIELDS")
            result=await run_in_threadpool(method,**body)
            return dict(result,event_id=body["event_id"])
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as error:
            code=str(error)
            if not re.fullmatch("[A-Z][A-Z0-9_]{0,99}",code):code="CAPITAL_OPERATION_UNAVAILABLE"
            return JSONResponse(status_code=409,content=dict(status="BLOCKED",reason=code,orders_created=False,orders=[]))
    @router.post("/api/strategy-capital-v1/intents")
    async def record(request:Request):
        return await invoke(request,service.record,{"event_id","contribution_amount","expected_revision","previous_target_id"})
    @router.post("/api/strategy-capital-v1/configure")
    async def configure(request:Request):return await invoke(request,service.configure,{"event_id"})
    @router.post("/api/strategy-capital-v1/recover-publication")
    async def recover(request:Request):return await invoke(request,service.recover_publication,{"event_id"})
    @router.post("/api/strategy-capital-v1/status")
    async def status(request:Request):return await invoke(request,service.status,{"event_id"})
    return router
