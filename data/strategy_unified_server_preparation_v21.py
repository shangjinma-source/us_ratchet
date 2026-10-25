"""Add source-bound display explanations without changing the V20 strategy."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v20 import build_unified_server_preparation_v20
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_explanations_v1 import explain_preview
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v4 import create_router

SOURCES={'data/strategy_unified_server_preparation_v21.py','data/strategy_daily_explanations_v1.py'}

class ExplainedDailyService:
 def __init__(self,service,archive_root,validate):
  self.service,self.monthly,self.archive_root,self.validate=service,service.monthly,archive_root,validate
 def preview(self,*,expected_revision,target_id):
  with self.monthly.snapshot_operation():
   self.validate()
   response=self.service.preview(expected_revision=expected_revision,target_id=target_id)
   result=explain_preview(response,archive_root=self.archive_root,policy_id=self.service.policy_id)
   self.validate()
   return result

def attach_explanations(*,prepared,archive_root,validate_sources):
 def gate():
  prepared['validate_code']();validate_sources()
 gate()
 old=prepared['observed_daily'];monthly=prepared['monthly']
 require(old.monthly is monthly and old.service.monthly is monthly,'V21_SHARED_MONTHLY_REQUIRED')
 service=ExplainedDailyService(old.service,archive_root,gate)
 observed=ObservedDailyAdmission(service=service,monthly=monthly,journal=old.journal,
  clock=old.clock,validate_sources=gate,policy_references=old.policy_references)
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute)
  and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V21_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0])
 router.include_router(create_router(service=observed));gate()
 return dict(prepared,router=router,observed_daily=observed,validate_code=gate)

def build_unified_server_preparation_v21(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v20','source_pins','archive_root'} and
  config['schema']=='DAILY_EXPLANATIONS_UNIFIED_PREPARATION_V21','V21_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==SOURCES,'V21_SOURCE_SCOPE')
 archive=Path(config['archive_root'])
 require(not archive.is_absolute() and '..' not in archive.parts and bool(archive.parts),'V21_ARCHIVE_SCOPE')
 archive=root/archive
 require(archive.resolve().is_relative_to(root.resolve()) and archive.resolve()!=root.resolve(),'V21_ARCHIVE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V21_CONFIGURATION_CHANGED');_read(root,config['base_v20'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and _read_digest(executing/name,32*1024*1024)==digest,'V21_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v20(root=root,configuration_path=config['base_v20']['path'],configuration_sha256=config['base_v20']['sha256'],clock=clock)
 return attach_explanations(prepared=prepared,archive_root=archive,validate_sources=gate)
