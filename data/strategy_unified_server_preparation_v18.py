"""Daily market verified transport over unchanged V17; no policy or account change."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v17 import build_unified_server_preparation_v17
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_rolling_admission_v9 import RollingDailyAdmissionV9
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v4 import create_router

V18_SOURCES={'data/strategy_daily_rolling_admission_v9.py', 'data/strategy_halt_aware_pullback_sources_v1.py', 'data/strategy_execution_halt_evidence_v1.py', 'data/strategy_halt_market_capture_v1.py', 'data/strategy_halt_aware_pullback_entry_v1.py', 'data/strategy_unified_server_preparation_v18.py', 'data/strategy_halt_aware_pullback_cap_store_v1.py', 'data/strategy_halt_gap_diagnostic_v1.py', 'data/strategy_halt_observation_v1.py', 'data/strategy_daily_composition_v5.py', 'data/strategy_halt_aware_execution_limits_v1.py'}

def attach_daily_rss_v18(*,prepared,validate_v18_sources):
 def gate():
  prepared['validate_code']();validate_v18_sources()
 gate()
 old=prepared['observed_daily'];previous=old.service;monthly=prepared['monthly']
 require(old.monthly is monthly and previous.monthly is monthly,'V18_SHARED_MONTHLY_REQUIRED')
 daily=RollingDailyAdmissionV9(monthly=monthly,reader=previous.reader,
  clock=previous.clock,validate_code=gate,policy_execution_enabled=previous.enabled,
  policy_id=previous.policy_id)
 observed=ObservedDailyAdmission(service=daily,monthly=monthly,journal=old.journal,
  clock=old.clock,validate_sources=gate,policy_references=old.policy_references)
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute)
  and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V18_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0])
 router.include_router(create_router(service=observed))
 gate()
 return dict(prepared,router=router,observed_daily=observed,validate_code=gate)

def build_unified_server_preparation_v18(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v17','source_pins'} and
  config['schema']=='HALT_AWARE_UNIFIED_PREPARATION_V18','V18_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==V18_SOURCES,'V18_SOURCE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V18_CONFIGURATION_CHANGED')
  _read(root,config['base_v17'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and
    _read_digest(executing/name,32*1024*1024)==digest,'V18_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v17(root=root,
  configuration_path=config['base_v17']['path'],configuration_sha256=config['base_v17']['sha256'],clock=clock)
 return attach_daily_rss_v18(prepared=prepared,validate_v18_sources=gate)
