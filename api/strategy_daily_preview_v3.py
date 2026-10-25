"""Isolated v3 route; not mounted by production imports."""
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service):
    router = APIRouter()

    @router.post("/api/strategy-daily-v3/preview")
    async def preview(request: Request):
        try:
            body = await request.json()
            if type(body) is not dict or set(body) != {"expected_revision", "target_id"}:
                raise ValueError("BODY_FIELDS")
            if not all(type(v) is str and re.fullmatch("[a-f0-9]{64}", v) for v in body.values()):
                raise ValueError("REVISION_OR_TARGET_ID_REQUIRED")
            return await run_in_threadpool(service.preview, **body)
        except (ValueError, KeyError, TypeError, OSError) as error:
            message = str(error)
            reason = message if re.fullmatch("[A-Z][A-Z0-9_]{0,99}", message) else "DAILY_PREVIEW_UNAVAILABLE"
            return JSONResponse(status_code=409, content=dict(status="WAIT", detail_status="UNAVAILABLE",
                reason=reason,new_orders=[],reference_quotes={},orders_created=False))
    return router
