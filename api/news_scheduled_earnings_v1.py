"""No client source URLs or financial context accepted by the calendar endpoint."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service, validate=lambda: None):
    router = APIRouter()
    headers = {'Cache-Control': 'no-store'}

    @router.get('/api/news/scheduled-earnings')
    async def read(request: Request):
        validate()
        if request.query_params:
            return JSONResponse({'status': 'INVALID_REQUEST'}, status_code=400, headers=headers)
        result = await run_in_threadpool(service.read)
        result['refresh'] = await run_in_threadpool(service.progress)
        return JSONResponse(result, headers=headers)

    @router.post('/api/news/scheduled-earnings/refresh')
    async def refresh(request: Request):
        validate()
        if request.headers.get('origin') not in (None, str(request.base_url).rstrip('/')):
            return JSONResponse({'status': 'INVALID_ORIGIN'}, status_code=403, headers=headers)
        if request.query_params or request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'status': 'INVALID_REQUEST'}, status_code=400, headers=headers)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 64:
                return JSONResponse({'status': 'INVALID_REQUEST'}, status_code=400, headers=headers)
        if bytes(raw).strip() != b'{}':
            return JSONResponse({'status': 'INVALID_REQUEST'}, status_code=400, headers=headers)
        code, result = await run_in_threadpool(service.start)
        return JSONResponse(result, status_code=code, headers=headers)

    return router
