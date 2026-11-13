"""Local recordkeeping only: these endpoints never initiate bank transfers."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.broker_internal_transfers import project_transfers


def create_router(*, store):
    router = APIRouter()

    def response(state):
        return dict(state=state, summary=project_transfers(state),
            bank_transfer_initiated=False, strategy_account_written=False,
            buying_power_updated=False)

    def error_response(error):
        message = str(error)
        reason = message if isinstance(error, ValueError) and re.fullmatch('[A-Z_]{1,80}', message) else 'TRANSFER_RECORD_UNAVAILABLE'
        return JSONResponse(dict(status=reason, bank_transfer_initiated=False,
            strategy_account_written=False, buying_power_updated=False),
            status_code=409 if reason in ('STALE_REVISION','EVENT_ID_CONFLICT') else 422,
            headers={'Cache-Control':'no-store'})

    @router.get('/api/strategy-account/internal-transfers')
    async def read():
        try:
            return JSONResponse(response(await run_in_threadpool(store.read)),headers={'Cache-Control':'no-store'})
        except Exception as error:
            return error_response(error)

    @router.post('/api/strategy-account/internal-transfers')
    async def append(request: Request):
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
                for key,value in items:
                    if key in result:raise ValueError('DUPLICATE_JSON_FIELD')
                    result[key]=value
                return result
            body=json.loads(raw,object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('INVALID_JSON')))
            if type(body) is not dict or set(body) != {'expected_revision','event'}:
                raise ValueError('BODY_FIELDS')
            if type(body['expected_revision']) is not str or len(body['expected_revision']) != 64:
                raise ValueError('REVISION_REQUIRED')
            state=await run_in_threadpool(store.append,body['event'],expected_revision=body['expected_revision'])
            return JSONResponse(response(state),headers={'Cache-Control':'no-store'})
        except Exception as error:
            return error_response(error)

    return router
