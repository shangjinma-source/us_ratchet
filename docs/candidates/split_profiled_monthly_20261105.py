"""Independent ready envelope and operation-scoped split monthly router.

No active configuration publication or production registration. Legacy ready
receipts are replayed unchanged at their authenticated historical revision.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
from core.strategy_account_ledger import canonical,require
from core.strategy_account_split_v1 import replay,apply_event
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data import strategy_account_monthly_router as base_router
from data import strategy_account_rolling_router as rolling
from data import strategy_profiled_rolling_router as profiled
from data import strategy_account_monthly_release as base_release
from data import strategy_profiled_monthly_release as profile_release
from docs.candidates import split_monthly_ready_verifier_20261105 as base_ready
from data import strategy_profiled_ready_release as profile_ready
from data import strategy_account_release_activation as base_activation
from data import strategy_profiled_release_activation as profile_activation
from data.strategy_profiled_runtime import build_runtime as legacy_builder
from data.strategy_account_runtime_archive import _document
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from docs.candidates import split_monthly_factory_20261105 as factory
from docs.candidates.split_monthly_unit_review_20261105 import review_interval
from docs.candidates.split_three_clock_action_review_20261105 import review_recorded_splits
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider

PATH='docs/candidates/split_profiled_monthly_20261105.py'
SCHEMA='SPLIT_PROFILED_READY_CONTENT_V1'
ADMISSION_PATHS={PATH,'docs/candidates/split_monthly_ready_verifier_20261105.py',
 'data/strategy_account_monthly_router.py','data/strategy_account_rolling_router.py',
 'data/strategy_profiled_rolling_router.py','data/strategy_account_monthly_release.py',
 'data/strategy_profiled_monthly_release.py','data/strategy_profiled_ready_release.py',
 'data/strategy_account_release_activation.py','data/strategy_profiled_release_activation.py',
 'data/strategy_profiled_runtime_archive.py','data/strategy_account_runtime_archive.py',
 'data/strategy_account_active_release_store.py'}
bind=factory.bind
identity_coverage=bind(base_release.validate_account_identity_coverage,replay=replay)
resolve_original=bind(base_release.resolve_monthly_runtime,validate_account_identity_coverage=identity_coverage)
resolve_profiled=bind(profile_release.resolve_monthly_runtime,resolve_original=resolve_original)


def read_reference(root,ref):
 require(type(ref)is dict and set(ref)=={'path','sha256'},'SPLIT_READY_REFERENCE')
 reader=MonthlyFileConfiguration(root=Path(root).resolve(),path=ref['path'],sha256_value=ref['sha256'],clock=None)
 return reader._read(ref['path'],ref['sha256'],8*1024*1024)


def checked_approval(root,configuration,approval):
 require(set(approval)=={'schema','configuration_sha256','source_pins','training_review','timing_bundles'} and approval['schema']=='SPLIT_MONTHLY_EXECUTION_APPROVAL_V1','SPLIT_MONTHLY_APPROVAL_SCHEMA')
 require(approval['configuration_sha256']==sha256(canonical(configuration)).hexdigest(),'SPLIT_MONTHLY_APPROVAL_CONFIGURATION')
 required=factory.RUNTIME_PATHS|ADMISSION_PATHS
 require(required<=set(approval['source_pins']),'SPLIT_READY_APPROVAL_CLOSURE')
 for name in required:
  expected=approval['source_pins'][name]
  require(configuration['runtime_pins'].get(name)==expected,'SPLIT_READY_CONFIGURATION_SOURCE')
  read_reference(root,dict(path=name,sha256=expected))
  require(sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest()==expected,'SPLIT_READY_EXECUTING_SOURCE')
 raw=read_reference(root,approval['training_review'])
 return raw


def validate_ready_release(*,root,receipt_path,receipt_sha256,account_state,clock=None):
 root=Path(root).resolve();ref=dict(path=receipt_path,sha256=receipt_sha256)
 document=_document(read_reference(root,ref))
 if document.get('schema')!=SCHEMA:
  # The original validator still rejects a legacy receipt at a split-era revision.
  return profile_ready.validate_ready_release(root=root,receipt_path=receipt_path,receipt_sha256=receipt_sha256,account_state=account_state,clock=clock)
 require(set(document)=={'schema','status','base_ready','approval'} and document['status']=='READY_FOR_REVIEW_NOT_ACTIVATED','SPLIT_READY_FIELDS')
 base_ref=document['base_ready'];base=_document(read_reference(root,base_ref))
 configuration=_document(read_reference(root,base['runtime']))
 approval=_document(read_reference(root,document['approval']));rawreview=checked_approval(root,configuration,approval)
 timing=approval['timing_bundles']
 provider=StrategyAccountEvidenceProvider(root=root,manifest_path=configuration['training_manifest'],manifest_sha256=configuration['training_sha256'],training_closed_at=configuration['training_closed_at'],market_capture=None,action_capture=None,limits_builder=None,output_root=root,runtime_pins=configuration['runtime_pins'])
 package,historical=provider.training()
 def units(**arguments):
  proof=factory.history_admission(package=package,manifest_path=provider.manifest_path,state=account_state,review_bytes=rawreview,review_sha256=approval['training_review']['sha256'],timing_bundles=timing,now=arguments['now'])
  recorded=[r['payload'] for r in account_state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
  require(len(recorded)<=1,'MONTHLY_MULTI_SPLIT_REVIEW_NOT_IMPLEMENTED')
  for action in recorded:
   checked=review_timing(action=action,timing=timing[action['action_id']],now=arguments['now'])
   mark=arguments['marks'].get(action['security_id'])
   if mark is not None:
    from data.strategy_account_target_inputs import stamp
    require(stamp(mark['observed_at'])>=stamp(checked['quote_unit_effective_at']) and mark.get('unit_id')==action['new_unit_id'],'MONTHLY_MARK_BEFORE_QUOTE_UNIT')
  def splits(**kw):return review_recorded_splits(**kw,timing=timing[recorded[0]['action_id']])
  return bind(review_interval,review_recorded_splits=splits)(**arguments,training_admission=proof)
 _original=bind(base_ready.validate_ready_release,replay=replay,resolve_monthly_runtime=resolve_original,review_interval=units)
 def original(**kwargs):return _original(**kwargs,generated_training_review_path=approval['training_review']['path'])
 wrapped=bind(profile_ready.validate_ready_release,validate_original=original,resolve_monthly_runtime=resolve_profiled)
 result=wrapped(root=root,receipt_path=base_ref['path'],receipt_sha256=base_ref['sha256'],account_state=account_state,clock=clock)
 require(result['configuration']==configuration,'SPLIT_READY_CONFIGURATION_CHANGED')
 checked_approval(root,configuration,approval)
 # Preserve original schema result consumed by unchanged CAS; outer receipt is stored.
 return result


class LegacyPrefixActivation(base_activation.MonthlyReleaseActivation):
 __init__=bind(base_activation.MonthlyReleaseActivation.__init__,ScopedAccountStore=SplitStrategyAccountStore)
 _validate_saved=bind(base_activation.MonthlyReleaseActivation._validate_saved,apply_event=apply_event)
 # Legacy adoption is deliberately not enabled for split-era accounts.


class SplitProfiledActivation(profile_activation.ProfiledMonthlyReleaseActivation):
 __init__=bind(profile_activation.ProfiledMonthlyReleaseActivation.__init__,ScopedAccountStore=SplitStrategyAccountStore,LegacyActivation=LegacyPrefixActivation)
 _validate_saved=bind(profile_activation.ProfiledMonthlyReleaseActivation._validate_saved,apply_event=apply_event,validate_ready_release=validate_ready_release)
 adopt=bind(profile_activation.ProfiledMonthlyReleaseActivation.adopt,validate_ready_release=validate_ready_release)


class SplitProfiledRouter(profiled.ProfiledRollingMonthlyRuntimeRouter):
 def __init__(self,*,root,snapshot_provider,initial_snapshot,approvals,clock=None,market_factory=None,action_factory=None,**kwargs):
  # Reuse the real base initialization with split storage, then original rolling scope.
  require(not kwargs.get('migration_control'),'PROFILE_MIGRATION_NOT_IMPLEMENTED')
  require(callable(snapshot_provider),'ROLLING_SNAPSHOT_PROVIDER_REQUIRED')
  initial=rolling._snapshot(initial_snapshot);self.approvals=deepcopy(approvals)
  def builder(*,root,configuration,clock):
   key=sha256(canonical(configuration)).hexdigest();approval=self.approvals.get(key)
   if approval is None:
    # Old target archive validation/execution construction preserves exact old pins;
    # generate below requires a separately approved new configuration.
    return legacy_builder(root=root,configuration=configuration,clock=clock)
   raw=checked_approval(root,configuration,approval)
   return factory.build_runtime(root=root,configuration=configuration,approval_pins=approval['source_pins'],timing_bundles=approval['timing_bundles'],training_review_bytes=raw,training_review_sha256=approval['training_review']['sha256'],clock=clock,market_factory=market_factory,action_factory=action_factory)
  bind(base_router.MonthlyRuntimeRouter.__init__,ScopedAccountStore=SplitStrategyAccountStore)(self,root=root,clock=clock,runtime_builder=builder,**{k:initial[k] for k in rolling._BINDINGS},**kwargs)
  self._snapshot_provider=snapshot_provider;self._active_snapshot=None;self._loading_snapshot=False
 @rolling._scoped
 def _selection_configuration(self,state,reason):
  config=resolve_profiled(root=self.root,registry_path=self.registry_path,registry_sha256=self.registry_sha256,clock=self.clock,account_state=state)
  require(sha256(canonical(config)).hexdigest() in self.approvals,'SPLIT_NEW_MONTH_APPROVAL_REQUIRED')
  return config
 generate=rolling._scoped(bind(profiled.ProfiledRollingMonthlyRuntimeRouter.generate.__wrapped__,validate_account_identity_coverage=identity_coverage))
 preview=rolling._scoped(bind(base_router.MonthlyRuntimeRouter.preview,validate_account_identity_coverage=identity_coverage))
 valuation=rolling._scoped(bind(base_router.MonthlyRuntimeRouter.valuation,validate_account_identity_coverage=identity_coverage))
 resolve_identity=rolling._scoped(bind(base_router.MonthlyRuntimeRouter.resolve_identity,validate_account_identity_coverage=identity_coverage,resolve_monthly_runtime=resolve_profiled))
