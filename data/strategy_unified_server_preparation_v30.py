"""Explicit UI snapshot transport over the unchanged V27 trading policy."""
from inspect import getclosurevars
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from api.strategy_account import StrategyAccountService
from api.strategy_frontier_daily_preview_v1 import create_router
from core.strategy_account_ledger import require
from data.strategy_bound_preview_snapshot_v1 import BoundPreviewSnapshotV1
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v29 import build_unified_server_preparation_v29

SOURCES = {'data/strategy_unified_server_preparation_v30.py',
           'data/strategy_bound_preview_snapshot_v1.py',
           'api/strategy_server_mount_v8.py', 'web/strategy_daily_controller.js',
           'web/index.html'}


def attach_bound_snapshot(*, prepared, validate_sources):
    routes = prepared['router'].routes
    def unique(path, method):
        found = [route for route in routes if isinstance(route, APIRoute)
                 and route.path == path and route.methods == {method}]
        require(len(found) == 1, 'V30_ROUTE_BINDING_REQUIRED')
        return found[0]
    account_route = unique('/api/strategy-account', 'GET')
    daily_route = unique('/api/strategy-daily-v3/preview', 'POST')
    # Bind the already-mounted account API projection, not a second account store.
    account = getclosurevars(account_route.endpoint).nonlocals.get('service')
    observed = prepared['observed_daily']
    require(type(account) is StrategyAccountService and
            getclosurevars(daily_route.endpoint).nonlocals.get('service') is observed,
            'V30_SERVICE_BINDING_REQUIRED')
    require(account.store.path.resolve() == observed.monthly.accounts.path.resolve(),
            'V30_ACCOUNT_DATABASE_MISMATCH')
    service = BoundPreviewSnapshotV1(observed=observed,
        project_account=account.project, validate_sources=validate_sources)
    # Keep the original lifespan (including its startup/shutdown hooks).
    # Copying hooks as well would invoke them again under FastAPI's merged lifespan.
    router = APIRouter(lifespan=prepared['router'].lifespan_context)
    router.routes.extend(route for route in routes if route is not daily_route)
    router.include_router(create_router(service=service))
    # News keeps its original observer; only the UI transport gains a snapshot.
    return dict(prepared, router=router, validate_code=validate_sources,
                bound_snapshot_daily=service, bound_snapshot_enabled=True)


def build_unified_server_preparation_v30(*, root, configuration_path,
                                       configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {'schema', 'base_v29', 'source_pins'} and
            configuration['schema'] == 'BOUND_UI_SNAPSHOT_UNIFIED_PREPARATION_V30',
            'V30_CONFIGURATION')
    pins = configuration['source_pins']
    require(type(pins) is dict and set(pins) == SOURCES, 'V30_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw, 'V30_CONFIGURATION_CHANGED')
        for name, digest in pins.items():
            for base in {root, executing}:
                require(_read_digest(base/name, 32*1024*1024) == digest, 'V30_SOURCE_CHANGED')
    validate()
    base = configuration['base_v29']
    prepared = build_unified_server_preparation_v29(root=root,
        configuration_path=base['path'], configuration_sha256=base['sha256'], clock=clock)
    previous = prepared['validate_code']
    def gate():
        previous()
        validate()
    result = attach_bound_snapshot(prepared=prepared, validate_sources=gate)
    gate()
    return result
