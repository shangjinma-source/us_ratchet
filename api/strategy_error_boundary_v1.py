"""Last-resort JSON errors for account/advice HTTP transport only.

Does not retry, admit data, alter strategy results, or infer write rollback.
"""
import logging
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

LOGGER = logging.getLogger(__name__)


class StrategyErrorBoundary(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        covered = path == '/api/strategy-daily-v3/preview' or path == '/api/strategy-account' or path.startswith('/api/strategy-account/')
        if not covered:
            return await call_next(request)
        try:
            return await call_next(request)
        except Exception as error:
            incident = uuid4().hex
            # Do not print exception messages, request bodies, or account data.
            LOGGER.error('strategy_http_failure incident=%s type=%s', incident, type(error).__name__)
            uncertain_write = request.method not in ('GET', 'HEAD', 'OPTIONS') and path != '/api/strategy-daily-v3/preview'
            result = dict(status='BLOCKED', reason='RECONCILE_REQUIRED' if uncertain_write else 'DAILY_RESPONSE_UNAVAILABLE',
                          incident_id=incident, new_orders=[], reference_quotes={})
            if uncertain_write:
                result.update(write_may_have_occurred=True, reconcile_before_retry=True)
            return JSONResponse(status_code=500, content=result, headers={'Cache-Control': 'no-store'})
