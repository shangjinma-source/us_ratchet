"""Unmounted server composition. Construction does not adopt or select anything."""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
from core.strategy_account_ledger import require
from data.strategy_account_runtime_archive import _document
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate,DYNAMIC_SOURCE_PATHS
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
from data.strategy_profiled_release_activation import ProfiledMonthlyReleaseActivation
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from scripts.register_quantity_v2_paper_protocol import safe_path

SOURCES=DYNAMIC_SOURCE_PATHS|RUNTIME_PATHS|PROFILE_ADMISSION_SOURCES|{
 'data/strategy_profiled_server_preparation.py','data/strategy_account_active_release_store.py',
 'data/strategy_account_ready_release.py','data/strategy_account_release_activation.py','scripts/prepare_real_monthly_release.py',
 'scripts/register_quantity_v2_paper_protocol.py'}

def build_preparation(*,root,configuration_path,configuration_sha256,clock=None):
    root=Path(root).resolve();path=safe_path(root,configuration_path);raw=path.read_bytes()
    require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==configuration_sha256,'PROFILE_SERVER_CONFIG_CHANGED')
    config=_document(raw)
    require(set(config)=={'schema','initial_snapshot','source_pins','legacy_anchor'} and config['schema']=='PROFILED_SERVER_PREPARATION_V2','PROFILE_SERVER_FIELDS')
    require(SOURCES<=set(config['source_pins']),'PROFILE_SERVER_SOURCE_SCOPE')
    code=bind_dynamic_source_gate(root=root,source_pins=config['source_pins'])
    def gate():
        require(path.read_bytes()==raw,'PROFILE_SERVER_CONFIG_CHANGED');code()
    clock=clock or (lambda:datetime.now(timezone.utc));gate()
    activation=ProfiledMonthlyReleaseActivation(root=root,initial_snapshot=config['initial_snapshot'],validate_code=gate,legacy_anchor=config['legacy_anchor'],clock=clock)
    router=ProfiledRollingMonthlyRuntimeRouter(root=root,initial_snapshot=dict(config['initial_snapshot'],revision=0),snapshot_provider=activation.snapshot,clock=clock)
    return dict(activation=activation,router=router,validate_code=gate)
