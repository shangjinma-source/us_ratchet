"""Daily market verified transport over unchanged V14; no policy or account change."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v14 import build_unified_server_preparation_v14
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_rolling_admission_v7 import RollingDailyAdmissionV7
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v3 import create_router

V15_SOURCES={
 'data/strategy_unified_server_preparation_v15.py',
 'data/strategy_daily_rolling_admission_v7.py',
 'data/strategy_account_action_capture_v6.py',
 'data/strategy_rss_verified_transport_v3.py',
}

def attach_daily_rss_v15(*,prepared,validate_v15_sources):
 def gate():
  prepared['validate_code']();validate_v15_sources()
 gate()
 old=prepared['observed_daily'];previous=old.service;monthly=prepared['monthly']
 require(old.monthly is monthly and previous.monthly is monthly,'V15_SHARED_MONTHLY_REQUIRED')
 daily=RollingDailyAdmissionV7(monthly=monthly,reader=previous.reader,
  clock=previous.clock,validate_code=gate,policy_execution_enabled=previous.enabled,
  policy_id=previous.policy_id)
 observed=ObservedDailyAdmission(service=daily,monthly=monthly,journal=old.journal,
  clock=old.clock,validate_sources=gate,policy_references=old.policy_references)
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute)
  and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V15_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0])
 router.include_router(create_router(service=observed))
 gate()
 return dict(prepared,router=router,observed_daily=observed,validate_code=gate)

def build_unified_server_preparation_v15(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v14','source_pins'} and
  config['schema']=='DAILY_RSS_ITEM_SCOPE_UNIFIED_PREPARATION_V15','V15_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==V15_SOURCES,'V15_SOURCE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V15_CONFIGURATION_CHANGED')
  _read(root,config['base_v14'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and
    _read_digest(executing/name,32*1024*1024)==digest,'V15_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v14(root=root,
  configuration_path=config['base_v14']['path'],configuration_sha256=config['base_v14']['sha256'],clock=clock)
 return attach_daily_rss_v15(prepared=prepared,validate_v15_sources=gate)
