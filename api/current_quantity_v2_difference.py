"""Strict injected route for server-owned current-cash previews."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from data.current_cash_portfolio_research import ResearchExpiredError

PUBLIC_SOURCE_REASONS = frozenset({
    'RESEARCH_SOURCE_WITHDRAWN',
    'EXPLICIT_PINNED_CLASS_UNAVAILABLE', 'CLASS_ADMISSION_SOURCE_MISMATCH',
    'RESEARCH_SNAPSHOT_EXPIRED',
    'OUTSIDE_REGULAR_SESSION', 'SESSION_DATE_MISMATCH', 'LAST_QUOTE_STALE',
    'COMPLETED_MINUTE_STALE', 'NO_COMPLETED_VALID_MINUTE', 'LAST_QUOTE_FUTURE',
    'QUOTE_AFTER_CAPTURE', 'REFERENCE_EXPIRED', 'CURRENT_CASH_REFERENCE_EXPIRED',
    'CAPTURE_SUPERSEDED', 'KNOWN_POST_DECISION_UNIT_ACTION', 'KNOWN_QUOTE_ACTION_UNSUPPORTED',
    'MONTH_MANDATE_REQUIRED', 'RESELECT_REQUIRED', 'EXECUTION_MONTH_NOT_ACTIVE',
})

def public_source_reason(reason):
    return reason if type(reason) is str and reason in PUBLIC_SOURCE_REASONS else 'SOURCE_UNAVAILABLE'


def create_router(*, service):
    router=APIRouter()
    if callable(getattr(service, 'history', None)):
        @router.get('/api/current_portfolio_research/observations')
        async def observations(request: Request):
            query = request.query_params
            if (set(query) != {'decision_id', 'research_version', 'available_cash_exact'}
                    or len(query.multi_items()) != 3
                    or re.fullmatch('[a-f0-9]{64}', query['decision_id']) is None
                    or query['research_version'] != 'CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH'
                    or re.fullmatch(r'[0-9]{1,20}(?:\.[0-9]{1,10})?(?:/[1-9][0-9]{0,20})?', query['available_cash_exact']) is None):
                return failure('INVALID_REQUEST', 400)
            return await run_in_threadpool(service.history, 50, decision_id=query['decision_id'],
                research_version=query['research_version'], available_cash_exact=query['available_cash_exact'])
    def failure(reason,code):
        return JSONResponse(dict(status='UNAVAILABLE',reason=reason,orders=[],proposal_id=None,
            research_only=True,execution_blocked=True,orders_created=False),status_code=code)
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result: raise ValueError('DUPLICATE_FIELD')
            result[k]=v
        return result
    @router.post('/api/current_portfolio_research/difference')
    async def preview(request:Request):
        try:
            if request.query_params: raise ValueError('NO_QUERY')
            chunks=[];size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>1024: raise ValueError('BODY_TOO_LARGE')
                chunks.append(chunk)
            body=json.loads(b''.join(chunks),object_pairs_hook=unique)
            if (type(body)is not dict or set(body)!={'decision_id'} or type(body['decision_id'])is not str
                    or re.fullmatch('[a-f0-9]{64}',body['decision_id'])is None):raise ValueError('EXACT_DECISION_ID_REQUIRED')
        except (ValueError,TypeError):return failure('INVALID_REQUEST',400)
        try:
            result=await run_in_threadpool(service.preview,body['decision_id'])
            if (type(result)is not dict or result.get('decision_id')!=body['decision_id']
                    or result.get('research_only')is not True or result.get('execution_blocked')is not True
                    or result.get('orders_created')is not False):return failure('INVALID_SERVICE_RESULT',503)
            if result.get('status')!='READY':
                reason=public_source_reason(result.get('reason'))
                return failure(reason,410 if reason=='RESEARCH_SNAPSHOT_EXPIRED' else 503)
            return JSONResponse(result,status_code=200)
        except ResearchExpiredError:
            return failure('RESEARCH_SNAPSHOT_EXPIRED',410)
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,ArithmeticError) as error:
            return failure(public_source_reason(str(error)),503)
    return router
