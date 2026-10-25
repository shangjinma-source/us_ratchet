"""Daily RSS verified transport over unchanged V11; no policy or account change."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v11 import build_unified_server_preparation_v11
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_rolling_admission_v4 import RollingDailyAdmissionV4
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v3 import create_router

V12_SOURCES={
 'data/strategy_unified_server_preparation_v12.py',
 'data/strategy_daily_rolling_admission_v4.py',
 'data/strategy_account_action_capture_v4.py',
 'data/strategy_account_action_capture_v3.py',
 'data/strategy_rss_verified_transport_v1.py',
}

def attach_daily_rss_v12(*,prepared,validate_v12_sources):
 def gate():
  prepared['validate_code']();validate_v12_sources()
 gate()
 old=prepared['observed_daily'];previous=old.service;monthly=prepared['monthly']
 require(old.monthly is monthly and previous.monthly is monthly,'V12_SHARED_MONTHLY_REQUIRED')
 daily=RollingDailyAdmissionV4(monthly=monthly,reader=previous.reader,
  clock=previous.clock,validate_code=gate,policy_execution_enabled=previous.enabled,
  policy_id=previous.policy_id)
 observed=ObservedDailyAdmission(service=daily,monthly=monthly,journal=old.journal,
  clock=old.clock,validate_sources=gate,policy_references=old.policy_references)
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute)
  and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V12_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0])
 router.include_router(create_router(service=observed))
 gate()
 return dict(prepared,router=router,observed_daily=observed,validate_code=gate)

def build_unified_server_preparation_v12(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v11','source_pins'} and
  config['schema']=='DAILY_RSS_UNIFIED_PREPARATION_V12','V12_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==V12_SOURCES,'V12_SOURCE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V12_CONFIGURATION_CHANGED')
  _read(root,config['base_v11'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and
    _read_digest(executing/name,32*1024*1024)==digest,'V12_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v11(root=root,
  configuration_path=config['base_v11']['path'],configuration_sha256=config['base_v11']['sha256'],clock=clock)
 return attach_daily_rss_v12(prepared=prepared,validate_v12_sources=gate)
