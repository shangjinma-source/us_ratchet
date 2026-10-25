"""Saved-snapshot valuation overlay; frozen V8 routes remain intact."""
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_difference import require
from data.strategy_unified_server_preparation_v8 import build_unified_server_preparation_v8
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_saved_target_valuation_v1 import SnapshotValuationServiceV1

VALUATION_SOURCES = {
    'data/strategy_unified_server_preparation_v9.py',
    'data/strategy_saved_target_valuation_v1.py',
}


def attach_snapshot_valuation(*, prepared, root, validate_valuation_sources):
    def gate():
        prepared['validate_code']()
        validate_valuation_sources()
    gate()
    monthly = prepared['monthly']
    service = SnapshotValuationServiceV1(monthly=monthly, root=root,
        calendar_reference=prepared['publication_calendar'], validate_sources=gate,
        clock=monthly.clock)
    old = [r for r in prepared['router'].routes if isinstance(r, APIRoute)
           and r.path == '/api/strategy-account/valuation' and r.methods == {'GET'}]
    require(len(old) == 1, 'SNAPSHOT_VALUATION_ROUTE_REQUIRED')
    router = APIRouter()
    router.routes.extend(r for r in prepared['router'].routes if r is not old[0])

    @router.get('/api/strategy-account/valuation')
    async def valuation(request: Request):
        def read():
            gate()
            require(not request.query_params, 'QUERY_FIELDS')
            result = service.valuation()
            gate()
            return result
        try:
            result = await run_in_threadpool(read)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ValueError as error:
            return JSONResponse({'status': 'BLOCKED', 'reason': str(error)},
                                status_code=409, headers={'Cache-Control': 'no-store'})
    gate()
    return dict(prepared, router=router, snapshot_valuation=service)


def build_unified_server_preparation_v9(*, root, configuration_path,
                                      configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, config = _read(root, reference)
    require(set(config) == {'schema', 'base_v8', 'source_pins'} and
            config['schema'] == 'SNAPSHOT_VALUATION_UNIFIED_PREPARATION_V9',
            'SNAPSHOT_VALUATION_CONFIGURATION_FIELDS')
    require(type(config['source_pins']) is dict and set(config['source_pins']) == VALUATION_SOURCES,
            'SNAPSHOT_VALUATION_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]
    def extra_gate():
        require(_read(root, reference)[0] == raw, 'SNAPSHOT_VALUATION_CONFIGURATION_CHANGED')
        _read(root, config['base_v8'])
        for name, digest in config['source_pins'].items():
            require(_read_digest(root/name, 32*1024*1024) == digest and
                    _read_digest(executing/name, 32*1024*1024) == digest,
                    'SNAPSHOT_VALUATION_SOURCE_CHANGED')
    extra_gate()
    prepared = build_unified_server_preparation_v8(root=root,
        configuration_path=config['base_v8']['path'],
        configuration_sha256=config['base_v8']['sha256'], clock=clock)
    return attach_snapshot_valuation(prepared=prepared, root=root,
                                     validate_valuation_sources=extra_gate)
