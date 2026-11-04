"""Opt-in display batching over the unchanged V27 trading policy."""
from inspect import getclosurevars
from pathlib import Path
from fastapi.routing import APIRoute
from fastapi.responses import Response

from api.strategy_frontier_display_batch_v1 import create_router
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_frontier_display_batch_v1 import FrontierDisplayBatchV1
from data.strategy_frontier_latest_display_charts_v1 import FrontierLatestDisplayChartsV1
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v30 import build_unified_server_preparation_v30

SOURCES = {'data/strategy_unified_server_preparation_v31.py',
           'data/strategy_frontier_display_batch_v1.py',
           'api/strategy_frontier_display_batch_v1.py',
           'web/strategy_display_batch_fetch.js',
           'web/strategy_monthly_target_charts.js', 'web/index.html',
           'api/strategy_server_mount_v8.py'}


def attach_display_batch(*, prepared, validate_sources):
    router = prepared['router']
    routes = [route for route in router.routes if isinstance(route, APIRoute)
              and route.path == '/api/strategy-display/latest-bars' and route.methods == {'GET'}]
    require(len(routes) == 1, 'V31_DISPLAY_ROUTE_REQUIRED')
    require(not any(getattr(route, 'path', None) == '/api/strategy-display/latest-batch'
                    for route in router.routes), 'V31_DUPLICATE_BATCH_ROUTE')
    existing = getclosurevars(routes[0].endpoint).nonlocals.get('service')
    require(type(existing) is FrontierLatestDisplayChartsV1, 'V31_DISPLAY_SERVICE_REQUIRED')
    options = dict(existing.display_options, validate_sources=validate_sources)
    batch = FrontierDisplayBatchV1(view=existing.view, **options)
    # Extend this exact router, preserving its lifecycle without copying hooks.
    router.include_router(create_router(service=batch))
    # Pin the exact startup-validated asset in memory, not an unmounted file.
    script = (Path(__file__).resolve().parents[1] / 'web/strategy_display_batch_fetch.js').read_bytes()
    @router.get('/static/strategy_display_batch_fetch.js')
    async def display_batch_script():
        return Response(script, media_type='application/javascript',
                        headers={'Cache-Control': 'no-store'})
    return dict(prepared, validate_code=validate_sources, display_batch=batch,
                display_batch_enabled=True)


def build_unified_server_preparation_v31(*, root, configuration_path,
                                       configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {'schema', 'base_v30', 'source_pins'} and
            configuration['schema'] == 'BATCH_DISPLAY_UNIFIED_PREPARATION_V31',
            'V31_CONFIGURATION')
    pins = configuration['source_pins']
    require(type(pins) is dict and set(pins) == SOURCES, 'V31_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root, reference)[0] == raw, 'V31_CONFIGURATION_CHANGED')
        for name, digest in pins.items():
            for base in {root, executing}:
                require(_read_digest(base/name, 32*1024*1024) == digest, 'V31_SOURCE_CHANGED')
    validate()
    base = configuration['base_v30']
    prepared = build_unified_server_preparation_v30(root=root,
        configuration_path=base['path'], configuration_sha256=base['sha256'], clock=clock)
    previous = prepared['validate_code']
    def gate():
        previous()
        validate()
    result = attach_display_batch(prepared=prepared, validate_sources=gate)
    gate()
    return result
