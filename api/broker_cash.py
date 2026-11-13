"""Confirm the broker split of already-confirmed cash; never place orders."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service):
    router = APIRouter()

    def failure(error, dispatched=False):
        text = str(error)
        reason = text if isinstance(error, ValueError) and re.fullmatch('[A-Z_]{1,100}', text) else 'BROKER_CASH_UNAVAILABLE'
        return JSONResponse(dict(status=reason, account_written=False,
            save_requires_readback=dispatched), status_code=409 if dispatched else 422,
            headers={'Cache-Control': 'no-store'})

    @router.get('/api/strategy-account/broker-cash')
    async def read(request: Request):
        try:
            if request.query_params:
                raise ValueError('UNSUPPORTED_PARAMETERS')
            return JSONResponse(await run_in_threadpool(service.read), headers={'Cache-Control': 'no-store'})
        except Exception as error:
            return failure(error)

    @router.post('/api/strategy-account/broker-cash')
    async def save(request: Request):
        dispatched = False
        try:
            if request.query_params:
                raise ValueError('UNSUPPORTED_PARAMETERS')
            raw = bytearray()
            async for part in request.stream():
                raw.extend(part)
                if len(raw) > 4096:
                    raise ValueError('BODY_TOO_LARGE')
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError('DUPLICATE_JSON_FIELD')
                    result[key] = value
                return result
            body = json.loads(raw, object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
            dispatched = True
            result = await run_in_threadpool(service.save, body)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except Exception as error:
            return failure(error, dispatched)

    return router
