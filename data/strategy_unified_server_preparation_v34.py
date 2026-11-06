"""Explicit ROA strategy attachment over the preserved V33 account infrastructure."""
from pathlib import Path
from data.strategy_unified_server_preparation_v33 import build_unified_server_preparation_v33
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_bounded_source_gate_v1 import _read_digest
from core.strategy_account_ledger import require
from data.roa_account_composition import attach_roa
SOURCES={
 'data/strategy_unified_server_preparation_v34.py','api/strategy_server_mount_v9.py',
 'data/roa_account_composition.py','data/roa_execution_lifecycle.py','data/roa_strategy_service.py',
 'data/roa_cash_advice_coordinator.py','data/roa_target_account_bridge.py','data/roa_session_reader.py',
 'core/strategy_account_ledger.py','core/strategy_account_store.py','core/strategy_account_difference.py',
 'data/roa_limit_policy.py',
 'data/roa_close_recovery.py','data/roa_monthly_loader.py',
 'data/roa_current_signal.py','data/roa_daily_signal.py','data/roa_quote_provider.py','api/roa_strategy.py',
 'web/strategy_roa_controller.js','web/strategy_roa_mount.js','web/index.html'}
def build_unified_server_preparation_v34(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v33','source_pins','roa'} and config['schema']=='ROA_UNIFIED_PREPARATION_V34','V34_CONFIGURATION')
 require(set(config['source_pins'])==SOURCES,'V34_SOURCE_SCOPE')
 def validate():
  require(_read(root,reference)[0]==raw,'V34_CONFIGURATION_CHANGED')
  for name,digest in config['source_pins'].items():
   for base in {root,Path(__file__).resolve().parents[1]}:
    require(_read_digest(base/name,32*1024*1024)==digest,'V34_SOURCE_CHANGED')
 validate();base=config['base_v33']
 prepared=build_unified_server_preparation_v33(root=root,configuration_path=base['path'],configuration_sha256=base['sha256'],clock=clock)
 previous=prepared['validate_code']
 def gate():previous();validate()
 result=attach_roa(prepared=prepared,root=root,configuration=config['roa'],validate_sources=gate,clock=clock)
 gate();return dict(result,validate_code=gate)
