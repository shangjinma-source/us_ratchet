"""Unactivated native monthly rolling admission retaining the factory subclass."""
from copy import copy,deepcopy
from functools import partial
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import require
from core.strategy_account_split_v1 import replay
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider
from docs.candidates.split_production_admission_20261105 import (
 bind,SplitDailyMarketCapture,HaltMarketCaptureV1,PullbackCapStore,
 StrategyAccountActionCaptureV6,build_timed_limits)
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data import strategy_halt_aware_execution_limits_v1 as halt_limits
from data import strategy_recent_minute_retry_v1 as retry
from docs.candidates.split_native_daily_composition_20261105 import build_composition
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyMixedExecutionBridge,DailyBuyDataWaitExecutionBridge


class NativeSplitRollingAdmission:
 def __init__(self,*,monthly,monthly_view,reader,clock,validate_code,timing_bundles,
              policy_execution_enabled=False,policy_id=None):
  require(type(policy_execution_enabled) is bool,'DAILY_ENABLED_FLAG_REQUIRED')
  self.monthly,self.monthly_view,self.reader=monthly,monthly_view,reader
  self.clock,self.validate_code=clock,validate_code
  self.timing_bundles=deepcopy(timing_bundles)
  self.enabled,self.policy_id=policy_execution_enabled,policy_id

 def preview(self,*,expected_revision,target_id,expected_proposal_id):
  with self.monthly.snapshot_operation():
   self.validate_code()
   proposal=self.monthly_view.require_proposal(target_id=target_id,expected_proposal_id=expected_proposal_id)
   target=self.monthly.current();state=self.monthly.accounts.read()
   require(target is not None and target['target_id']==target_id,'STALE_TARGET')
   require(state is not None and state['revision']==expected_revision,'STALE_REVISION')
   runtime,configuration=self.monthly._for_target(target)
   bind(validate_account_identity_coverage,replay=replay)(self.monthly.root,configuration,state)
   original=runtime.execution_provider
   require(getattr(original,'__func__',None) is StrategyAccountEvidenceProvider.execution,'NATIVE_DAILY_PROVIDER_REQUIRED')
   require(getattr(original.__self__._assemble,'__func__',None) is not StrategyAccountEvidenceProvider._assemble,
    'NATIVE_FACTORY_ASSEMBLY_REQUIRED')
   # A shallow copy preserves the concrete factory class and its lexical gates.
   provider=copy(original.__self__)
   require(type(provider) is type(original.__self__) and
    getattr(provider._assemble,'__func__',None) is getattr(original.__self__._assemble,'__func__',None),
    'NATIVE_DAILY_SUBCLASS_LOST')
   market=provider.market
   provider.market=SplitDailyMarketCapture(identity_resolver=market.identity,fetch=market.fetch,
    clock=market.clock,max_workers=market.workers,max_mark_age=market.max_mark_age)
   provider.market=HaltMarketCaptureV1(provider.market,clock=self.clock)
   require(isinstance(provider.limits,partial) and 'cap_store' in provider.limits.keywords,'HALT_ORIGINAL_CAP_STORE_REQUIRED')
   legacy=provider.limits.keywords['cap_store']
   require(legacy.path.is_file(),'HALT_LEGACY_CAP_STORE_MISSING')
   session=self.clock().astimezone(ZoneInfo('America/New_York')).date().isoformat()
   caps=PullbackCapStore(legacy.path.with_name('halt_pullback_caps_v2_'+session+'.sqlite3'),legacy_path=legacy.path,
    clock=legacy.clock,max_history_rows=legacy.max_history_rows,max_history_bytes=legacy.max_history_bytes)
   actions=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
   require(len(actions)<=1,'NATIVE_DAILY_MULTI_SPLIT_NOT_IMPLEMENTED')
   if actions:
    action=actions[0];require(action['action_id'] in self.timing_bundles,'NATIVE_DAILY_TIMING_REQUIRED')
    provider.limits=partial(build_timed_limits,cap_store=caps,timing_slot={'timing':deepcopy(self.timing_bundles[action['action_id']])})
   else:
    original_limits=bind(halt_limits.build_execution_limits,replay=replay)
    provider.limits=partial(bind(retry.build_execution_limits,original_limits=original_limits),cap_store=caps)
   prior_actions=provider.actions
   provider.actions=StrategyAccountActionCaptureV6(fetch=prior_actions.fetch,rss_fetch=prior_actions.rss_fetch,
    clock=prior_actions.clock,max_workers=prior_actions.workers)
   service=build_composition(mixed_execution_bridge=DailyMixedExecutionBridge,buy_wait_execution_bridge=DailyBuyDataWaitExecutionBridge,
    monthly_service=self.monthly,monthly_view=self.monthly_view,evidence_reader=self.reader,
    execution_provider=provider.execution,clock=self.clock,policy_execution_enabled=self.enabled,
    policy_id=self.policy_id,fee_bps=runtime.selection.fees)
   result=service.preview(expected_revision=expected_revision,target_id=target_id,expected_proposal_id=expected_proposal_id)
   require(self.monthly_view.require_proposal(target_id=target_id,expected_proposal_id=expected_proposal_id)==proposal,'FRONTIER_PROPOSAL_CHANGED')
   self.validate_code()
   return result
