"""Read-only recorded holding charts, explicitly distinct from monthly targets."""
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import require


def create_router(*, charts, validate_runtime=None):
    router = APIRouter()
    @router.get('/api/strategy-account/holding-bars')
    async def holding_bars(request: Request):
        try:
            if validate_runtime is not None:await run_in_threadpool(validate_runtime)
            items=list(request.query_params.multi_items()); values=dict(items)
            require(len(items)==len(values) and set(values)<= {'account_revision','security_id','interval','bars'}
                    and {'account_revision','security_id'}<=set(values),'CHART_QUERY_FIELDS')
            count=values.get('bars','90')
            require(re.fullmatch('[1-9][0-9]{0,2}',count),'CHART_ARGUMENTS_INVALID')
            result=await run_in_threadpool(charts.bars,account_revision=values['account_revision'],
                security_id=values['security_id'],interval=values.get('interval','day'),bars=int(count))
            if validate_runtime is not None:await run_in_threadpool(validate_runtime)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except Exception as error:
            reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{0,99}',str(error)) else 'HOLDING_CHART_UNAVAILABLE'
            return JSONResponse(dict(status='BLOCKED',reason=reason,orders_created=False),
                status_code=409 if reason=='STALE_REVISION' else 422,headers={'Cache-Control':'no-store'})
    return router
