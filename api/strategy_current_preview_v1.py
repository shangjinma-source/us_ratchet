"""Read-only current advice endpoint, never mounted automatically."""
import re
from xml.etree.ElementTree import ParseError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import require


def create_router(*, service):
    router = APIRouter()

    @router.get('/api/strategy-daily-v3/current')
    async def current(request: Request):
        try:
            items = list(request.query_params.multi_items())
            values = dict(items)
            require(len(items) == len(values) and set(values) <= {'expected_revision'},
                    'CURRENT_ADVICE_QUERY_FIELDS')
            revision = values.get('expected_revision')
            require(revision is None or re.fullmatch('[0-9a-f]{64}', revision),
                    'CURRENT_ADVICE_REVISION')
            result = await run_in_threadpool(service.read, expected_revision=revision)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ParseError:
            reason = 'OFFICIAL_ACTION_SOURCE_UNAVAILABLE'
        except (ValueError, KeyError, TypeError, OSError) as error:
            message = str(error)
            reason = ('WAIT_KNOWN_ACTION_REVIEW' if message ==
                'SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW' else message
                if re.fullmatch('[A-Z][A-Z0-9_]{0,99}', message)
                else 'CURRENT_ADVICE_UNAVAILABLE')
        return JSONResponse(dict(status='WAIT', detail_status='UNAVAILABLE', reason=reason,
            new_orders=[], reference_quotes={}, orders_created=False),
            status_code=409, headers={'Cache-Control': 'no-store'})

    return router
