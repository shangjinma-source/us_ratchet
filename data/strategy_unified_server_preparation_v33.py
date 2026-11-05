"""Opt-in restart performance; unchanged trading policy and account ledger."""
from pathlib import Path
from api.strategy_restart_performance import build_router
from core.strategy_account_ledger import require
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v32 import build_unified_server_preparation_v32

SOURCES = {'data/strategy_unified_server_preparation_v33.py',
           'data/strategy_restart_performance.py','api/strategy_restart_performance.py',
           'web/strategy_account.js','api/strategy_server_mount_v8.py'}


def build_unified_server_preparation_v33(*, root, configuration_path, configuration_sha256, clock=None):
    root = Path(root).absolute()
    reference = dict(path=configuration_path,sha256=configuration_sha256)
    raw, config = _read(root,reference)
    require(set(config)=={'schema','base_v32','source_pins','performance'} and
            config['schema']=='RESTART_PERFORMANCE_UNIFIED_PREPARATION_V33','V33_CONFIGURATION')
    require(type(config['source_pins']) is dict and set(config['source_pins'])==SOURCES,'V33_SOURCE_SCOPE')
    executing=Path(__file__).resolve().parents[1]
    def validate():
        require(_read(root,reference)[0]==raw,'V33_CONFIGURATION_CHANGED')
        for name,digest in config['source_pins'].items():
            for base in {root,executing}:
                require(_read_digest(base/name,32*1024*1024)==digest,'V33_SOURCE_CHANGED')
    validate()
    base=config['base_v32']
    prepared=build_unified_server_preparation_v32(root=root,configuration_path=base['path'],configuration_sha256=base['sha256'],clock=clock)
    previous=prepared['validate_code']
    def gate():
        previous();validate()
    def read_account():
        gate()
        return prepared['monthly'].accounts.read()
    def valuation():
        gate()
        value=prepared['snapshot_valuation'].valuation()
        gate()
        return value
    require(not any(getattr(r,'path',None)=='/api/strategy-account/restart-performance' for r in prepared['router'].routes),'V33_DUPLICATE_ROUTE')
    prepared['router'].include_router(build_router(root=root,configuration=config['performance'],read_account=read_account,valuation=valuation,clock=clock))
    gate()
    return dict(prepared,validate_code=gate,restart_performance_enabled=True)
