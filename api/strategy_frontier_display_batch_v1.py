"""Explicit read-only batch route; composition must opt in."""
from threading import BrokenBarrierError

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from core.strategy_account_ledger import require


def create_router(*, service):
    router = APIRouter()

    @router.get("/api/strategy-display/latest-batch")
    async def latest_batch(request: Request):
        try:
            identifiers = request.query_params.getlist("security_id")
            items = [(key, value) for key, value in request.query_params.multi_items()
                     if key != "security_id"]
            values = dict(items)
            require(len(items) == len(values)
                    and set(values) <= {"expected_proposal_id", "interval", "bars"}
                    and "expected_proposal_id" in values, "DISPLAY_QUERY_FIELDS")
            result = await run_in_threadpool(service.bars, security_ids=identifiers,
                expected_proposal_id=values["expected_proposal_id"],
                interval=values.get("interval", "day"), bars=int(values.get("bars", "90")))
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, KeyError, TypeError, OSError, BrokenBarrierError):
            return JSONResponse(dict(status="DISPLAY_UNAVAILABLE", executable=False),
                                status_code=409, headers={"Cache-Control": "no-store"})

    return router
