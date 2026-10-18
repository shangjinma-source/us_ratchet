"""Unmounted V2 research routes; caller supplies an admitted snapshot service."""
import json
import re
import subprocess

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from data.current_cash_portfolio_research import normalize_cash, ResearchExpiredError

BASE = '/api/current_portfolio_research'
FLAGS = dict(research_only=True, execution_blocked=True)


def create_router(*, service):
    if not all(callable(getattr(service, method, None)) for method in ('calculate', 'snapshot', 'bars')):
        raise ValueError('EXPLICIT_V2_SERVICE_REQUIRED')
    router = APIRouter(prefix=BASE)

    def error(status, code):
        return JSONResponse(dict(FLAGS, status=status, error_code=code),
                            status_code=400 if status == 'INVALID' else 410 if status == 'EXPIRED' else 503)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_FIELD')
            result[key] = value
        return result

    async def invoke(method, *args):
        try:
            result = await run_in_threadpool(method, *args)
            if not isinstance(result, dict) or result.get('research_only') is not True or result.get('execution_blocked') is not True:
                return error('UNAVAILABLE', 'RESEARCH_BOUNDARY_INVALID')
            if result.get('status') in ('INCOMPLETE', 'UNAVAILABLE'):
                return JSONResponse(result, status_code=503)
            return result
        except ResearchExpiredError:
            return error('EXPIRED', 'SNAPSHOT_UNKNOWN_OR_EXPIRED')
        except ValueError as exc:
            return error('UNAVAILABLE', 'RESEARCH_SOURCE_WITHDRAWN' if str(exc) == 'RESEARCH_SOURCE_WITHDRAWN' else 'SOURCE_OR_RESULT_NOT_AVAILABLE')
        except (KeyError, TypeError, OSError, ArithmeticError, subprocess.SubprocessError):
            return error('UNAVAILABLE', 'SOURCE_OR_RESULT_NOT_AVAILABLE')

    async def bounded_body(request, limit):
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise ValueError('BODY_TOO_LARGE')
            chunks.append(chunk)
        return b''.join(chunks)

    @router.post('')
    async def calculate(request: Request):
        try:
            if request.query_params:
                raise ValueError('NO_QUERY')
            raw = await bounded_body(request, 4096)
            body = json.loads(raw, object_pairs_hook=unique)
            if not isinstance(body, dict) or set(body) != {'entered_cash'}:
                raise ValueError('EXACT_CASH_BODY_REQUIRED')
            cash = normalize_cash(body['entered_cash'])
        except (ValueError, TypeError, ArithmeticError):
            return error('INVALID', 'EXACT_VALID_CASH_REQUIRED')
        return await invoke(service.calculate, cash)

    async def query(request, fields):
        if await bounded_body(request, 0) or set(request.query_params) != fields or len(request.query_params.multi_items()) != len(fields):
            raise ValueError('EXACT_QUERY_REQUIRED')
        values = dict(request.query_params)
        if not re.fullmatch('[0-9a-f]{24}', values['research_id']):
            raise ValueError('INVALID_RESEARCH_ID')
        return values

    @router.get('/snapshot')
    async def snapshot(request: Request):
        try:
            values = await query(request, {'research_id'})
        except ValueError:
            return error('INVALID', 'INVALID_SNAPSHOT_QUERY')
        return await invoke(service.snapshot, values['research_id'])

    @router.get('/bars')
    async def bars(request: Request):
        try:
            values = await query(request, {'research_id', 'ticker', 'interval', 'bars'})
            if (not re.fullmatch('[A-Za-z0-9.^=-]{1,24}', values['ticker'])
                    or values['interval'] not in ('day', 'week', 'month')
                    or not re.fullmatch('[0-9]{1,3}', values['bars']) or not 1 <= int(values['bars']) <= 260):
                raise ValueError('INVALID_BAR_ARGUMENTS')
        except ValueError:
            return error('INVALID', 'INVALID_BAR_QUERY')
        return await invoke(service.bars, values['research_id'], values['ticker'], values['interval'], int(values['bars']))

    return router
