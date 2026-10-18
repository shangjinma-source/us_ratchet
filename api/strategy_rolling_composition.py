"""Rolling HTTP composition; importing never activates or adopts a release.

Callers provide reviewed pins. Replace the three old route registrations with
one include_router call; never register both sets of identical endpoint paths.
A post-operation gate failure cannot roll back an already committed event.
"""
import re
from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import require
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter, RollingArchivedHoldingCharts
from data.strategy_account_release_activation import MonthlyReleaseActivation
from data.strategy_account_runtime import build_runtime
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate, DYNAMIC_SOURCE_PATHS
from api.strategy_dynamic_monthly_target import create_dynamic_account_router


COMPOSITION_PATH = 'api/strategy_rolling_composition.py'
ROLLING_SOURCE_PATHS = DYNAMIC_SOURCE_PATHS | frozenset({
    COMPOSITION_PATH,
    'data/strategy_account_rolling_router.py',
    'data/strategy_account_release_activation.py',
    'data/strategy_account_active_release_store.py',
    'data/strategy_account_ready_release.py',
    'data/strategy_account_monthly_review.py',
    'scripts/prepare_real_monthly_release.py',
    'scripts/review_prepare_real_monthly_release.py',
    'scripts/activate_real_monthly_release.py',
})


def _holding_router(service, gate, bootstrap_configuration, display_sources):
    from data.strategy_account_runtime import ACCOUNT_ID
    from api.strategy_account_charts import create_router
    charts = RollingArchivedHoldingCharts(service=service, account_id=ACCOUNT_ID,
        bootstrap_configuration=bootstrap_configuration, display_sources=display_sources)
    return create_router(charts=charts, validate_runtime=gate)


def _target_router(service):
    from api.strategy_dynamic_monthly_target import MonthlyTargetHTTPAdapter
    from api.strategy_monthly_target import create_router
    from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts

    class ScopedCharts(StrategyMonthlyTargetCharts):
        def bars(self, **kwargs):
            # Runs inside the endpoint's worker thread, never across await.
            # Pin checks and every nested current() read share one snapshot.
            with service.snapshot_operation():
                service.validate_current_target_pins()
                result = super().bars(**kwargs)
                service.validate_current_target_pins()
                return result

    return create_router(service=MonthlyTargetHTTPAdapter(service),
        charts=ScopedCharts(root=service.root, target_service=service))


def create_rolling_strategy_router(*, root, registry_path, registry_sha256,
        archive_path, archive_sha256, source_pins, identity_configuration=None,
        migration_control=None, bootstrap_configuration=None, display_sources=None,
        clock=None, runtime_builder=build_runtime):
    """Create, but do not mount, all real-account routes using explicit approvals."""
    require(type(source_pins) is dict and ROLLING_SOURCE_PATHS <= set(source_pins),
            'ROLLING_COMPOSITION_SCOPE_REQUIRED')
    gate = bind_dynamic_source_gate(root=root,source_pins=source_pins)
    initial = dict(registry_path=registry_path, registry_sha256=registry_sha256,
        archive_path=archive_path, archive_sha256=archive_sha256)
    activation = MonthlyReleaseActivation(root=root, initial_snapshot=initial, validate_code=gate, clock=clock)
    service = RollingMonthlyRuntimeRouter(root=root, initial_snapshot=dict(initial, revision=0),
        snapshot_provider=activation.snapshot, clock=clock,
        runtime_builder=runtime_builder,identity_configuration=identity_configuration,
        migration_control=migration_control)

    class GatedRoute(APIRoute):
        # FastAPI include_router preserves the concrete route class, including
        # this closure, when it recreates a route on another router/application.
        def get_route_handler(self):
            original = super().get_route_handler()
            async def guarded(request):
                def failure(error, after):
                    reason = str(error)
                    if not isinstance(error,ValueError) or not re.fullmatch('[A-Z][A-Z0-9_]{0,99}',reason):
                        reason = 'DYNAMIC_SOURCE_UNAVAILABLE'
                    return JSONResponse(dict(status='BLOCKED',reason=reason,
                        gate_phase='AFTER_OPERATION' if after else 'BEFORE_OPERATION',
                        write_may_have_occurred=after and request.method not in {'GET','HEAD','OPTIONS'},
                        reconcile_before_retry=after and request.method not in {'GET','HEAD','OPTIONS'}),
                        status_code=503,headers={'Cache-Control':'no-store'})
                try:
                    await run_in_threadpool(gate)
                except Exception as error:
                    return failure(error,False)
                operation_error = None
                try:
                    response = await original(request)
                except Exception as error:
                    operation_error = error
                try:
                    await run_in_threadpool(gate)
                except Exception as error:
                    return failure(error,True)
                if operation_error is not None:
                    raise operation_error
                return response
            return guarded

    combined = APIRouter()
    sources = [create_dynamic_account_router(service=service),
               _target_router(service),
               _holding_router(service, gate, bootstrap_configuration, display_sources)]
    paths = set()
    for source in sources:
        for route in source.routes:
            require(isinstance(route,APIRoute),'UNSUPPORTED_DYNAMIC_ROUTE')
            keys = {(route.path,method) for method in route.methods}
            require(not paths.intersection(keys),'DUPLICATE_DYNAMIC_ROUTE')
            paths.update(keys)
            combined.add_api_route(route.path,route.endpoint,methods=route.methods,name=route.name,
                response_class=route.response_class,response_model=route.response_model,
                status_code=route.status_code,dependencies=route.dependencies,tags=route.tags,
                summary=route.summary,description=route.description,response_description=route.response_description,
                responses=route.responses,deprecated=route.deprecated,operation_id=route.operation_id,
                response_model_include=route.response_model_include,response_model_exclude=route.response_model_exclude,
                response_model_by_alias=route.response_model_by_alias,
                response_model_exclude_unset=route.response_model_exclude_unset,
                response_model_exclude_defaults=route.response_model_exclude_defaults,
                response_model_exclude_none=route.response_model_exclude_none,
                callbacks=route.callbacks,openapi_extra=route.openapi_extra,
                include_in_schema=route.include_in_schema,route_class_override=GatedRoute)
    return combined
