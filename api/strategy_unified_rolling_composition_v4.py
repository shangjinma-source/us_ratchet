"""One admitted runtime for account, target, rolling daily advice and capital.

Construction does not publish a target, approve a policy, or install a task.
"""
from fastapi import APIRouter
from fastapi.routing import APIRoute

from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_daily_rolling_runner_v3 import V3_SOURCES
from data.strategy_profiled_rolling_packet_admission_v3 import (
    create_profiled_rolling_packet_admission_v3,
)
from api.strategy_unified_composition import SOURCES as PREVIOUS_SOURCES
from api.strategy_shared_runtime_composition import create_shared_runtime_router
from api.strategy_capital_transition_composition import (
    SOURCES as CAPITAL_TRANSITION_SOURCES, create_transition_capital_router,
)
from api.strategy_daily_preview_v3 import create_router as daily_router


SOURCES = PREVIOUS_SOURCES | V3_SOURCES | CAPITAL_TRANSITION_SOURCES | {
    "api/strategy_unified_rolling_composition_v3.py",
    "api/strategy_unified_rolling_composition_v4.py",
    "data/strategy_bounded_source_gate_v1.py",
    "data/strategy_daily_rolling_packet_reader_v3.py",
    "data/strategy_profiled_rolling_packet_admission_v3.py",
    "data/strategy_continuous32_upgrade_handoff.py",
}


def create_unified_rolling_strategy_router_v4(
        *, monthly, validate_code, source_pins, clock, daily_configuration,
        bootstrap_configuration=None, display_sources=None):
    require(isinstance(monthly, ProfiledRollingMonthlyRuntimeRouter),
            "UNIFIED_PROFILED_RUNTIME_REQUIRED")
    require(callable(validate_code) and type(source_pins) is dict
            and SOURCES <= set(source_pins), "UNIFIED_ROLLING_SOURCE_SCOPE_REQUIRED")
    require(type(validate_code) is BoundedSourceGateV1, "UNIFIED_BOUNDED_GATE_REQUIRED")
    validate_code.require_scope(source_pins)
    gate = validate_code

    gate()
    daily = create_profiled_rolling_packet_admission_v3(
        monthly=monthly, clock=clock, validate_code=gate, root=monthly.root,
        server_configuration=daily_configuration,
    )
    routes = (
        create_shared_runtime_router(
            monthly=monthly, validate_code=gate,
            bootstrap_configuration=bootstrap_configuration, display_sources=display_sources),
        daily_router(service=daily),
        create_transition_capital_router(
            monthly=monthly, validate_code=gate, source_pins=source_pins),
    )
    router, paths = APIRouter(), set()
    for source in routes:
        for route in source.routes:
            require(isinstance(route, APIRoute), "UNIFIED_HTTP_ROUTE_REQUIRED")
            keys = {(route.path, method) for method in route.methods}
            require(not paths.intersection(keys), "UNIFIED_DUPLICATE_ROUTE")
            paths.update(keys)
        router.include_router(source)
    return router
