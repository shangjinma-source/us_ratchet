"""Read-only V2 reference route; no order or paper-account endpoints."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from data.current_cash_portfolio_research import ResearchExpiredError


def create_router(*, service):
    router = APIRouter()

    def unavailable(code, status=503):
        return JSONResponse(dict(status='UNAVAILABLE', error_code=code, stocks=[],
                                 research_only=True, execution_blocked=True, orders_created=False),
                            status_code=status)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_FIELD')
            result[key] = value
        return result

    @router.post('/api/current_portfolio_research/intraday')
    async def preview(request: Request):
        try:
            if request.query_params:
                raise ValueError('NO_QUERY')
            chunks = []; size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 1024:
                    raise ValueError('BODY_TOO_LARGE')
                chunks.append(chunk)
            body = json.loads(b''.join(chunks), object_pairs_hook=unique)
            if (not isinstance(body, dict) or set(body) != {'research_id'}
                    or not isinstance(body['research_id'], str)
                    or re.fullmatch('[a-f0-9]{24}', body['research_id']) is None):
                raise ValueError('EXACT_RESEARCH_ID_REQUIRED')
        except (ValueError, TypeError):
            return unavailable('INVALID_REFERENCE_REQUEST', 400)
        try:
            result = await run_in_threadpool(service.preview, body['research_id'])
            if (not isinstance(result, dict) or result.get('research_id') != body['research_id']
                    or result.get('research_only') is not True or result.get('execution_blocked') is not True
                    or result.get('orders_created') is not False):
                return unavailable('INVALID_REFERENCE_RESULT')
            return JSONResponse(result, status_code=503 if result.get('status') == 'UNAVAILABLE' else 200)
        except ResearchExpiredError:
            return unavailable('SNAPSHOT_EXPIRED', 410)
        except (ValueError, TypeError, KeyError, OSError, ArithmeticError):
            return unavailable('REFERENCE_NOT_AVAILABLE')

    return router
