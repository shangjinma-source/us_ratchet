"""Opt-in single current-advice read; account writes and V27 policy unchanged."""
from inspect import getclosurevars
from pathlib import Path
from fastapi.routing import APIRoute

from api.strategy_current_preview_v1 import create_router
from core.strategy_account_ledger import require
from data.strategy_bound_preview_snapshot_v1 import BoundPreviewSnapshotV1
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_current_preview_v1 import CurrentPreviewV1
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v31 import build_unified_server_preparation_v31

SOURCES = {'data/strategy_unified_server_preparation_v32.py',
           'data/strategy_current_preview_v1.py', 'api/strategy_current_preview_v1.py',
           'web/strategy_daily_controller.js', 'web/index.html',
           'api/strategy_server_mount_v8.py'}


def attach_current_preview(*, prepared, validate_sources):
    existing = prepared.get('bound_snapshot_daily')
    require(type(existing) is BoundPreviewSnapshotV1, 'V32_BOUND_PREVIEW_REQUIRED')
    router = prepared['router']
    routes = [route for route in router.routes if isinstance(route, APIRoute)
              and route.path == '/api/strategy-daily-v3/preview' and route.methods == {'POST'}]
    require(len(routes) == 1 and getclosurevars(routes[0].endpoint).nonlocals.get('service') is existing,
            'V32_BOUND_PREVIEW_ROUTE_MISMATCH')
    require(not any(getattr(route, 'path', None) == '/api/strategy-daily-v3/current'
                    for route in router.routes), 'V32_DUPLICATE_CURRENT_ROUTE')
    # Request-local service wiring; never mutate the existing observer or its gate.
    bound = BoundPreviewSnapshotV1(observed=existing.observed,
        project_account=existing.project_account, validate_sources=validate_sources)
    current = CurrentPreviewV1(bound_preview=bound)
    router.include_router(create_router(service=current))
    return dict(prepared, validate_code=validate_sources,
                current_advice=current, current_advice_enabled=True)


def build_unified_server_preparation_v32(*, root, configuration_path,
                                       configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {'schema', 'base_v31', 'source_pins'} and
            configuration['schema'] == 'CURRENT_ADVICE_UNIFIED_PREPARATION_V32',
            'V32_CONFIGURATION')
    pins = configuration['source_pins']
    require(type(pins) is dict and set(pins) == SOURCES, 'V32_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw, 'V32_CONFIGURATION_CHANGED')
        for name, digest in pins.items():
            for base in {root, executing}:
                require(_read_digest(base/name, 32*1024*1024) == digest, 'V32_SOURCE_CHANGED')
    validate()
    base = configuration['base_v31']
    prepared = build_unified_server_preparation_v31(root=root,
        configuration_path=base['path'], configuration_sha256=base['sha256'], clock=clock)
    previous = prepared['validate_code']
    def gate():
        previous()
        validate()
    result = attach_current_preview(prepared=prepared, validate_sources=gate)
    gate()
    return result
