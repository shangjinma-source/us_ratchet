"""Explicit first-retarget routes; caller owns mounting and account authorization."""
import re
import sqlite3
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from api.current_research_intraday_multiorder import (
    FLAGS, _body, _keys, _identifier, _digest, _require)
from data.current_research_intraday_initial_retarget_service import IntradayInitialRetargetService, InitialRetargetNotApplied

BASE = '/api/research_paper/intraday_initial_retarget'


def create_router(*, service):
    _require(isinstance(service, IntradayInitialRetargetService), 'EXPLICIT_INITIAL_RETARGET_SERVICE_REQUIRED')
    router = APIRouter(prefix=BASE)

    @router.get('/context')
    async def context(request: Request):
        try:
            _require(not await request.body(), 'GET_BODY_NOT_ALLOWED')
            _require(set(request.query_params) == {'account_id'} and len(request.query_params.multi_items()) == 1,
                     'EXACT_ACCOUNT_QUERY_REQUIRED')
            account_id = request.query_params['account_id']
            _identifier(account_id)
            return await run_in_threadpool(service.context, account_id)
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError, sqlite3.Error) as error:
            code = str(error).split(':', 1)[0]
            if not re.fullmatch('[A-Z][A-Z0-9_]{0,100}', code):
                code = 'REQUEST_FAILED'
            return JSONResponse(status_code=400, content=dict(FLAGS, status='UNAVAILABLE', error_code=code,
                mutation_outcome='NOT_A_MUTATION', retry_same_request=False,
                message='首次月度调仓账户暂不可用：' + code))

    async def invoke(request, *, mutation):
        service_called = False
        try:
            body = await _body(request)
            fields = {'account_id', 'expected_revision'}
            if mutation:
                fields |= {'proposal_id', 'operation_id'}
            _keys(body, fields)
            _identifier(body['account_id'])
            _digest(body['expected_revision'])
            if not mutation:
                return await run_in_threadpool(service.preview, body['account_id'], body['expected_revision'])
            _digest(body['proposal_id'])
            _identifier(body['operation_id'])
            service_called = True
            result = await run_in_threadpool(service.accept, body['account_id'], body['proposal_id'],
                                            body['operation_id'], body['expected_revision'])
            return dict(result, mutation_outcome='APPLIED_OR_IDEMPOTENT')
        except (ValueError, KeyError, TypeError, OSError, ArithmeticError, sqlite3.Error) as error:
            code = str(error).split(':', 1)[0]
            if not re.fullmatch('[A-Z][A-Z0-9_]{0,100}', code):
                code = 'REQUEST_FAILED'
            # Only typed factory rejection proves this acceptance did not write.
            # Never infer rollback from an arbitrary error string after invocation.
            outcome = ('NOT_A_MUTATION' if not mutation else
                       'UNKNOWN_RETRY_SAME_REQUEST' if service_called and not isinstance(error, InitialRetargetNotApplied) else 'NOT_APPLIED')
            return JSONResponse(status_code=400, content=dict(
                FLAGS, status='UNAVAILABLE', error_code=code, mutation_outcome=outcome,
                retry_same_request=outcome == 'UNKNOWN_RETRY_SAME_REQUEST',
                message='首次月度纸面调仓请求未完成：' + code))

    @router.post('/preview')
    async def preview(request: Request):
        return await invoke(request, mutation=False)

    @router.post('/accept')
    async def accept(request: Request):
        return await invoke(request, mutation=True)

    return router
