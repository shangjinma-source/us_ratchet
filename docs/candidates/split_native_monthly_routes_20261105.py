"""Attach the existing proposal-aware monthly API to a fresh isolated runtime.

The caller must supply an authenticated monthly factory/router and source gate.
This does not authorize a production release or change an active configuration.
"""
from api.strategy_frontier_monthly_target_v1 import create_router
from core.strategy_account_ledger import require


def attach_monthly_routes(*, prepared, validate_sources, charts=None):
    validate_sources()
    require(prepared.get('monthly_generation_enabled') is False,
            'NATIVE_MONTHLY_ROUTES_ALREADY_ENABLED')
    view = prepared['monthly']
    require(prepared['current_advice'].monthly is view,
            'NATIVE_MONTHLY_CURRENT_VIEW_MISMATCH')
    for name in ('generate', 'current', 'require_proposal', 'snapshot_operation', 'validate_sources'):
        require(callable(getattr(view, name, None)), 'NATIVE_MONTHLY_VIEW_REQUIRED')
    routes = create_router(service=view, charts=charts)
    existing = {(route.path, method) for route in prepared['router'].routes
                for method in getattr(route, 'methods', ())}
    added = {(route.path, method) for route in routes.routes
             for method in getattr(route, 'methods', ())}
    require(not existing.intersection(added), 'NATIVE_MONTHLY_ROUTE_COLLISION')
    validate_sources()
    prepared['router'].include_router(routes)
    return dict(prepared, monthly_generation_enabled=True, production_activated=False)
