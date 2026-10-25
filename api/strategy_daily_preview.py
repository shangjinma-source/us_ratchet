"""Optional separate daily route; never replaces the monthly endpoint by import."""
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service):
    router = APIRouter()

    @router.post("/api/strategy-daily/preview")
    async def preview(request: Request):
        try:
            body = await request.json()
            if type(body) is not dict or set(body) != {"expected_revision", "target_id"}:
                raise ValueError("BODY_FIELDS")
            if not all(type(value) is str and re.fullmatch("[a-f0-9]{64}", value)
                       for value in body.values()):
                raise ValueError("REVISION_OR_TARGET_ID_REQUIRED")
            result = await run_in_threadpool(service.preview, **body)
            if "difference" in result:
                allowed = {"status", "strategy_equity", "spendable_cash", "strategy_market_value",
                           "new_orders", "waiting_cash", "cancel_before_recalculate",
                           "new_buy_cash_required"}
                result["difference"] = {k: v for k, v in result["difference"].items() if k in allowed}
            return result
        except (ValueError, KeyError, TypeError) as error:
            message = str(error)
            reason = message if re.fullmatch("[A-Z][A-Z0-9_]{0,99}", message) else "DAILY_PREVIEW_UNAVAILABLE"
            return JSONResponse(status_code=409, content=dict(status="UNAVAILABLE",
                                reason=reason, new_orders=[], orders_created=False))
    return router
