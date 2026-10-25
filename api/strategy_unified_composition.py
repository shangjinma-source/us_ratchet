"""Single-runtime account, charts, daily suggestions and new-capital routes.

Caller construction is server-owned. This does not adopt a release, select a
portfolio, enable a policy or mount a production application.
"""
from fastapi import APIRouter
from fastapi.routing import APIRoute

from core.strategy_account_ledger import require
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_profiled_server_preparation import SOURCES as PREPARATION_SOURCES
from api.strategy_profiled_capital_composition import (
    SOURCES as CAPITAL_SOURCES, create_profiled_capital_router,
)
from api.strategy_daily_server_mount_v3 import DAILY_SOURCES
from api.strategy_daily_preview_v3 import create_router as daily_router
from api.strategy_shared_runtime_composition import create_shared_runtime_router
from data.strategy_profiled_daily_packet_admission import create_profiled_packet_admission
from data.strategy_daily_continuity_normalizer import NORMALIZATION_CODE_PATHS


SOURCES = PREPARATION_SOURCES | CAPITAL_SOURCES | DAILY_SOURCES | NORMALIZATION_CODE_PATHS | {
    "api/strategy_unified_composition.py", "api/strategy_shared_runtime_composition.py",
    "api/strategy_rolling_composition.py", "data/strategy_account_rolling_router.py",
    "data/strategy_profiled_daily_packet_admission.py", "data/strategy_daily_packet_reader.py",
    "data/strategy_daily_profile_binding.py", "data/strategy_daily_session_capture.py",
    "data/strategy_daily_continuity_normalizer.py",
}


def create_unified_strategy_router(*, monthly, validate_code, source_pins, clock,
                                  daily_configuration, bootstrap_configuration=None,
                                  display_sources=None):
    require(isinstance(monthly, ProfiledRollingMonthlyRuntimeRouter),
            "UNIFIED_PROFILED_RUNTIME_REQUIRED")
    require(callable(validate_code) and type(source_pins) is dict
            and SOURCES <= set(source_pins), "UNIFIED_SOURCE_SCOPE_REQUIRED")
    source_gate = bind_dynamic_source_gate(root=monthly.root, source_pins=dict(source_pins))

    def gate():
        validate_code()
        source_gate()

    gate()
    daily = create_profiled_packet_admission(monthly=monthly, clock=clock,
        validate_code=gate, root=monthly.root, server_configuration=daily_configuration)
    sources = (
        create_shared_runtime_router(monthly=monthly, validate_code=gate,
            bootstrap_configuration=bootstrap_configuration, display_sources=display_sources),
        daily_router(service=daily),
        create_profiled_capital_router(monthly=monthly, validate_code=gate, source_pins=source_pins),
    )
    router = APIRouter()
    paths = set()
    for source in sources:
        for route in source.routes:
            require(isinstance(route, APIRoute), "UNIFIED_HTTP_ROUTE_REQUIRED")
            keys = {(route.path, method) for method in route.methods}
            require(not paths.intersection(keys), "UNIFIED_DUPLICATE_ROUTE")
            paths.update(keys)
        router.include_router(source)
    return router
