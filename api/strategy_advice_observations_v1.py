"""Server-account-scoped read-only audit API. Not production mounted."""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
import sqlite3


def create_router(*, journal, account_id, validate_sources=None):
    router=APIRouter()
    def read_page(after,limit):
        if validate_sources is not None: validate_sources()
        result=journal.page(account_id=account_id,after=after,limit=limit)
        if validate_sources is not None: validate_sources()
        return result

    @router.get('/api/strategy-advice-v1/observations')
    async def observations(after: int=Query(0,ge=0),limit: int=Query(20,ge=1,le=100)):
        try:
            return await run_in_threadpool(read_page,after,limit)
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):
            return JSONResponse(status_code=409,content={'status':'AUDIT_UNAVAILABLE'})
    return router
