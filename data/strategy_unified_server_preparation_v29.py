"""Add bounded scheduled earnings context without changing the V27 trade policy."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v28 import build_unified_server_preparation_v28
from data.news_scheduled_service_v1 import ScheduledEarningsService
from api.news_scheduled_earnings_v1 import create_router

SOURCES = {'data/news_issuer_calendar_source.py', 'data/news_sandisk_wire_v1.py', 'data/news_sandisk_wire_capture_v1.py', 'data/news_schedule_binding_v1.py', 'data/strategy_unified_server_preparation_v29.py',
           'data/news_scheduled_earnings_v1.py', 'data/news_scheduled_service_v1.py',
           'api/news_scheduled_earnings_v1.py', 'web/news_scheduled_earnings.js',
           'api/strategy_server_mount_v8.py'}


def build_unified_server_preparation_v29(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path, sha256=configuration_sha256)
    raw, configuration = _read(root, reference)
    require(set(configuration) == {'schema', 'base_v28', 'source_pins'} and
            configuration['schema'] == 'SCHEDULED_EARNINGS_UNIFIED_PREPARATION_V29', 'V29_CONFIGURATION')
    pins = configuration['source_pins']
    require(set(pins) == SOURCES, 'V29_SOURCE_SCOPE')
    executing = Path(__file__).resolve().parents[1]

    def validate():
        require(_read(root, reference)[0] == raw, 'V29_CONFIGURATION_CHANGED')
        for name, digest in pins.items():
            for base in (root, executing):
                require(_read_digest(base/name, 32*1024*1024) == digest, 'V29_SOURCE_CHANGED')

    validate()
    base = configuration['base_v28']
    prepared = build_unified_server_preparation_v28(root=root,
        configuration_path=base['path'], configuration_sha256=base['sha256'], clock=clock)
    previous_gate = prepared['validate_code']

    def gate():
        previous_gate()
        validate()

    service = ScheduledEarningsService(root/'data/cache/news/scheduled_earnings_v1', clock=clock)
    router = APIRouter()
    router.include_router(prepared['router'])
    router.include_router(create_router(service=service, validate=gate))

    @router.get('/static/news_scheduled_earnings.js')
    def script():
        gate()
        return FileResponse(root/'web/news_scheduled_earnings.js', media_type='application/javascript',
                            headers={'Cache-Control': 'no-store'})

    gate()
    return dict(prepared, router=router, validate_code=gate, scheduled_earnings=service)
