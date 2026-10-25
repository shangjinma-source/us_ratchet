"""Optional latest display endpoint; never mounted implicitly."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import require


def create_router(*, service):
    router = APIRouter()

    @router.get("/api/strategy-display/latest-bars")
    async def latest(request: Request):
        try:
            items = list(request.query_params.multi_items())
            values = dict(items)
            require(len(items) == len(values) and set(values) <= {"security_id", "interval", "bars", "expected_proposal_id"}
                    and {"security_id", "expected_proposal_id"} <= set(values), "DISPLAY_QUERY_FIELDS")
            result = await run_in_threadpool(service.bars, security_id=values["security_id"],
                expected_proposal_id=values["expected_proposal_id"], interval=values.get("interval", "day"), bars=int(values.get("bars", "90")))
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except (ValueError, KeyError, TypeError, OSError):
            return JSONResponse(dict(status="DISPLAY_UNAVAILABLE", executable=False),
                                status_code=409, headers={"Cache-Control": "no-store"})
    return router
