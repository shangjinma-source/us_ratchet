"""Daily RSS verified transport over unchanged V11; no policy or account change."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.routing import APIRoute
from core.strategy_account_ledger import require
from data.strategy_unified_server_preparation_v7 import _read
from data.strategy_unified_server_preparation_v12 import build_unified_server_preparation_v12
from data.strategy_bounded_source_gate_v1 import _read_digest
from data.strategy_daily_rolling_admission_v5 import RollingDailyAdmissionV5
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v3 import create_router
from data.strategy_daily_domain_policy_reader_v2 import ExplicitDomainPolicyReviewReaderV2
from data.strategy_profiled_daily_packet_admission import ProfiledCurrentSessionDailyReader
import json
from copy import deepcopy
from data.strategy_daily_dynamic_factory_v5 import resolve_saved_context
from data.strategy_daily_rolling_parent_v3 import pinned

V13_SOURCES={
 'data/strategy_unified_server_preparation_v13.py',
 'data/strategy_daily_rolling_admission_v5.py',
 'data/strategy_account_action_capture_v5.py',
 'data/strategy_rss_verified_transport_v2.py',
 'data/strategy_daily_domain_packet_reader_v2.py',
 'data/strategy_daily_domain_policy_reader_v2.py',
 'data/strategy_daily_dynamic_factory_v5.py',
 'data/strategy_daily_verified_rss_capture_v2.py',
}

class ProfiledMigrationDomainReader(ProfiledCurrentSessionDailyReader):
 def __init__(self,**options):
  self.packet_reader=ExplicitDomainPolicyReviewReaderV2(**options)


def attach_daily_rss_v13(*,prepared,root,daily_configuration,daily_reference,validate_v13_sources):
 def gate():
  prepared['validate_code']();validate_v13_sources()
 gate()
 old=prepared['observed_daily'];previous=old.service;monthly=prepared['monthly']
 require(old.monthly is monthly and previous.monthly is monthly,'V13_SHARED_MONTHLY_REQUIRED')
 config=daily_configuration
 require(set(config)=={'evidence','policy_execution_enabled','policy_id'} and
  config['policy_execution_enabled']==previous.enabled and config['policy_id']==previous.policy_id,
  'V13_POLICY_CHANGED')
 old_packet=previous.reader.packet_reader
 evidence=config['evidence']
 require(evidence.get('release_path')==old_packet.release_path and
  evidence.get('trusted_release_sha256')==old_packet.release_sha and
  evidence.get('archive_root')==old_packet.archive_root,'V13_RELEASE_CHANGED')
 source_ref=dict(path=evidence['configuration_path'],sha256=evidence['configuration_sha256'])
 source=json.loads(pinned(root,source_ref))
 require(source['prior_configuration']==old_packet.reference,'V13_PRIOR_SOURCE_CHANGED')
 resolve_saved_context(root=Path(root),config=source,configuration_sha256=source_ref['sha256'],day=source['migration_session'])
 app_ref=dict(path=evidence['review_configuration_path'],sha256=evidence['review_configuration_sha256'])
 old_app=json.loads(pinned(root,old_packet.review_reference));new_app=json.loads(pinned(root,app_ref))
 require(new_app['source_configuration']==source_ref,'V13_APPLICATION_SOURCE')
 before=deepcopy(old_app);after=deepcopy(new_app)
 for value in (before,after):
  value.pop('source_configuration');value.pop('code_pins')
 require(before==after,'V13_APPLICATION_SCOPE_CHANGED')
 old_pins={r['path']:r['sha256'] for r in old_app['code_pins']}
 new_pins={r['path']:r['sha256'] for r in new_app['code_pins']}
 require(len(old_pins)==len(old_app['code_pins']) and len(new_pins)==len(new_app['code_pins']) and
  all(new_pins.get(k)==v for k,v in old_pins.items()),'V13_APPLICATION_PINS_CHANGED')
 reader=ProfiledMigrationDomainReader(root=root,clock=previous.clock,**evidence)
 daily=RollingDailyAdmissionV5(monthly=monthly,reader=reader,
  clock=previous.clock,validate_code=gate,policy_execution_enabled=previous.enabled,
  policy_id=previous.policy_id)
 observed=ObservedDailyAdmission(service=daily,monthly=monthly,journal=old.journal,
  clock=old.clock,validate_sources=gate,policy_references=dict(daily_configuration=daily_reference,evidence_references=evidence,policy_id=config['policy_id'],policy_execution_enabled=config['policy_execution_enabled'],previous_policy_references=old.policy_references))
 matches=[r for r in prepared['router'].routes if isinstance(r,APIRoute)
  and r.path=='/api/strategy-daily-v3/preview' and r.methods=={'POST'}]
 require(len(matches)==1,'V13_DAILY_ROUTE_REQUIRED')
 router=APIRouter();router.routes.extend(r for r in prepared['router'].routes if r is not matches[0])
 router.include_router(create_router(service=observed))
 gate()
 return dict(prepared,router=router,observed_daily=observed,validate_code=gate)

def build_unified_server_preparation_v13(*,root,configuration_path,configuration_sha256,clock=None):
 root=Path(root).absolute();reference=dict(path=configuration_path,sha256=configuration_sha256)
 raw,config=_read(root,reference)
 require(set(config)=={'schema','base_v12','daily_configuration','source_pins'} and
  config['schema']=='DAILY_RSS_RECOVERY_UNIFIED_PREPARATION_V13','V13_CONFIGURATION_FIELDS')
 require(type(config['source_pins']) is dict and set(config['source_pins'])==V13_SOURCES,'V13_SOURCE_SCOPE')
 executing=Path(__file__).resolve().parents[1]
 def gate():
  require(_read(root,reference)[0]==raw,'V13_CONFIGURATION_CHANGED')
  _read(root,config['base_v12'])
  _read(root,config['daily_configuration'])
  for name,digest in config['source_pins'].items():
   require(_read_digest(root/name,32*1024*1024)==digest and
    _read_digest(executing/name,32*1024*1024)==digest,'V13_SOURCE_CHANGED')
 gate()
 prepared=build_unified_server_preparation_v12(root=root,
  configuration_path=config['base_v12']['path'],configuration_sha256=config['base_v12']['sha256'],clock=clock)
 return attach_daily_rss_v13(prepared=prepared,root=root,daily_reference=config['daily_configuration'],daily_configuration=json.loads(_read(root,config['daily_configuration'])[0]),validate_v13_sources=gate)
