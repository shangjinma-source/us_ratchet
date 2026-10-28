"""Explicit opt-in and read-only progress; browser never supplies source or actions."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_event_router(*, pipeline, validate=lambda: None):
    router = APIRouter()
    headers = {'Cache-Control': 'no-store'}

    @router.get('/api/news/events/status')
    async def status():
        validate()
        return JSONResponse(await run_in_threadpool(pipeline.status), headers=headers)

    async def body(request):
        validate()
        if request.headers.get('origin') not in (None, str(request.base_url).rstrip('/')):
            raise ValueError('SAME_ORIGIN_REQUIRED')
        if request.query_params or request.headers.get('content-type', '').split(';')[0] != 'application/json':
            raise ValueError('JSON_REQUIRED')
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 64:
                raise ValueError('BODY_TOO_LARGE')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('DUPLICATE_FIELD')
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=unique)

    @router.post('/api/news/events/control')
    async def control(request: Request):
        try:
            value = await body(request)
            if type(value) is not dict or set(value) != {'enabled'} or type(value['enabled']) is not bool:
                raise ValueError('EXPLICIT_BOOLEAN_REQUIRED')
            return JSONResponse(await run_in_threadpool(pipeline.set_enabled, value['enabled']), headers=headers)
        except (ValueError, TypeError):
            return JSONResponse(dict(status='FAILED', error='EVENT_CONTROL_REJECTED'), status_code=409, headers=headers)

    @router.post('/api/news/events/tick')
    async def tick(request: Request):
        try:
            if await body(request) != {}:
                raise ValueError('NO_CLIENT_CONTEXT_ALLOWED')
            return JSONResponse(await run_in_threadpool(pipeline.tick), headers=headers)
        except (ValueError, TypeError):
            return JSONResponse(dict(status='FAILED', error='EVENT_TICK_REJECTED'), status_code=409, headers=headers)
    return router
