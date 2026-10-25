"""Compose account and target HTTP routes around one admitted runtime.

The caller supplies the server-owned runtime and source gate. This factory
creates no runtime, adopts no release and mounts nothing by itself.
"""
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from core.strategy_account_ledger import require
from api.strategy_dynamic_monthly_target import create_dynamic_account_router
from api.strategy_rolling_composition import _target_router, _holding_router


def create_shared_runtime_router(*, monthly, validate_code,
                                 bootstrap_configuration=None, display_sources=None):
    require(callable(validate_code), "SHARED_RUNTIME_GATE_REQUIRED")
    validate_code()

    class GatedRoute(APIRoute):
        def get_route_handler(self):
            original = super().get_route_handler()

            async def guarded(request):
                def failure(error, after):
                    reason = str(error)
                    if not isinstance(error, ValueError) or not re.fullmatch(
                            "[A-Z][A-Z0-9_]{0,99}", reason):
                        reason = "DYNAMIC_SOURCE_UNAVAILABLE"
                    uncertain = after and request.method not in {"GET", "HEAD", "OPTIONS"}
                    return JSONResponse(dict(status="BLOCKED", reason=reason,
                        gate_phase="AFTER_OPERATION" if after else "BEFORE_OPERATION",
                        write_may_have_occurred=uncertain, reconcile_before_retry=uncertain),
                        status_code=503, headers={"Cache-Control": "no-store"})
                try:
                    await run_in_threadpool(validate_code)
                except Exception as error:
                    return failure(error, False)
                operation_error = None
                try:
                    response = await original(request)
                except Exception as error:
                    operation_error = error
                try:
                    await run_in_threadpool(validate_code)
                except Exception as error:
                    return failure(error, True)
                if operation_error is not None:
                    raise operation_error
                return response
            return guarded

    combined = APIRouter()
    paths = set()
    sources = (create_dynamic_account_router(service=monthly), _target_router(monthly),
               _holding_router(monthly, validate_code, bootstrap_configuration, display_sources))
    for source in sources:
        # include_router preserves this concrete route class across nested mounts.
        # Rebuild handlers so the new class actually wraps the original endpoints.
        gated = APIRouter(route_class=GatedRoute)
        for route in source.routes:
            require(isinstance(route, APIRoute), "UNSUPPORTED_DYNAMIC_ROUTE")
            keys = {(route.path, method) for method in route.methods}
            require(not paths.intersection(keys), "DUPLICATE_DYNAMIC_ROUTE")
            paths.update(keys)
            gated.add_api_route(route.path, route.endpoint, methods=route.methods,
                name=route.name, response_class=route.response_class,
                response_model=route.response_model, status_code=route.status_code,
                dependencies=route.dependencies, responses=route.responses,
                include_in_schema=route.include_in_schema)
        combined.include_router(gated)
    return combined
