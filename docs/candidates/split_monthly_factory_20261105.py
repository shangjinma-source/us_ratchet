"""Isolated V27 monthly composition; old source receipts remain unchanged.

Separate server approval pins this derivative. History review never changes raw
bytes or the original twelve-scenario compiler/search. Not production activation.
"""
from copy import deepcopy, copy
from hashlib import sha256
from types import FunctionType
from pathlib import Path
from functools import partial
import json
from fractions import Fraction
from core.strategy_account_ledger import canonical, require
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data import strategy_continuous32_runtime as original_runtime
from data.current_quantity_v2_monthly_training import compile_saved_training
from docs.candidates.split_continuous32_integration_20261105 import (
 SplitContinuous32TargetService,SplitContinuous32MonthlyService,RUNTIME_PATHS as CONTINUOUS_PATHS)
from docs.candidates.strategy_account_split_evidence_provider import StrategyAccountEvidenceProvider as SplitProvider
from docs.candidates.strategy_account_split_market_capture import StrategyAccountMarketCapture
from docs.candidates.strategy_account_split_execution_limits import build_execution_limits
from docs.candidates.split_monthly_unit_review_20261105 import review_interval
from docs.candidates.split_monthly_raw_history_20261105 import normalize_monthly_raw
from docs.candidates.split_three_clock_action_review_20261105 import review_recorded_splits
from docs.candidates.split_three_clock_coordinates_20261105 import review_timing

PATH='docs/candidates/split_monthly_factory_20261105.py'
RUNTIME_PATHS=original_runtime.RUNTIME_PATHS|CONTINUOUS_PATHS|{PATH,
 'docs/candidates/split_monthly_unit_review_20261105.py',
 'docs/candidates/split_monthly_raw_history_20261105.py',
 'docs/candidates/split_three_clock_action_review_20261105.py',
 'docs/candidates/split_three_clock_coordinates_20261105.py',
 'docs/candidates/strategy_account_split_evidence_provider.py',
 'docs/candidates/strategy_account_split_market_capture.py',
 'docs/candidates/strategy_account_split_execution_limits.py',
 'docs/candidates/strategy_account_split_unit_review.py',
 'core/strategy_account_split_store_v1.py','core/strategy_account_split_v1.py'}


def bind(function,**dependencies):
 result=FunctionType(function.__code__,dict(function.__globals__,**dependencies),function.__name__,function.__defaults__,function.__closure__)
 result.__kwdefaults__=function.__kwdefaults__;return result


def history_admission(*,package,manifest_path,state,review_bytes,review_sha256,timing_bundles,now):
 """Compare real raw-normalized 253 closes to original compiled training values."""
 require(sha256(review_bytes).hexdigest()==review_sha256,'MONTHLY_HISTORY_REVIEW_CHANGED')
 proof=json.loads(review_bytes);files=package['files'];pins=package['source_hashes']
 require(proof['schema']=='SPLIT_MONTHLY_TRAINING_UNITS_CONTENT_V1' and proof['manifest_sha256']==pins[manifest_path], 'MONTHLY_HISTORY_MANIFEST_BINDING')
 manifest=json.loads(files[manifest_path]);days=manifest['training_dates']
 require(len(days)==253 and days==sorted(set(days)) and days[-1]==manifest['decision_date'],'MONTHLY_TRAINING_DATES')
 compiled=compile_saved_training(package,manifest_path)
 rows={r['security_id']:r for r in compiled['compiled']['window']['candidates'] if r['status']=='READY_CONDITIONAL'}
 recorded=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
 require(set(proof['actions'])=={a['action_id'] for a in recorded},'MONTHLY_HISTORY_ACTION_DOMAIN')
 result={}
 for action in recorded:
  sid=action['security_id'];item=proof['actions'][action['action_id']]
  require(item['recorded_action_sha256']==sha256(canonical(action)).hexdigest(),'MONTHLY_HISTORY_ACTION_CHANGED')
  timing=timing_bundles[action['action_id']];clockproof=review_timing(action=action,timing=timing,now=now)
  require(item['timing_sha256']==clockproof['timing_sha256'],'MONTHLY_HISTORY_TIMING_CHANGED')
  # A carried noncandidate still needs current-unit marks, not invented history.
  if sid not in rows:
   require(item['scope']=='CARRIED_NONCANDIDATE' and sid not in compiled['input']['search_arguments']['prices'],'MONTHLY_HISTORY_NONCANDIDATE')
   result[action['action_id']]=item['recorded_action_sha256'];continue
  require(item['scope']=='COMPLETE_253_CURRENT_UNITS','MONTHLY_HISTORY_SCOPE')
  row=rows[sid];path=row['training_source'];inputs=item['inputs'];review=item['normalization']
  require(inputs['session_dates']==days and inputs['base_target']['monthly_decision_date']==days[0] and inputs['signal_date']==days[-1]
   and set(inputs['histories'])=={sid} and set(inputs['base_target']['quantities'])=={sid},'MONTHLY_HISTORY_WINDOW')
  require(review['current_unit_id']==action['new_unit_id'] and review['raw_sha256']==pins[path],'MONTHLY_HISTORY_CURRENT_UNIT')
  schedule=review['split_schedule']
  boundary=clockproof['quote_bar_boundary_at']
  from data.strategy_account_target_inputs import stamp
  from zoneinfo import ZoneInfo
  boundary_day=stamp(boundary).astimezone(ZoneInfo('America/New_York')).date().isoformat()
  if boundary_day>=days[0]:
   require(schedule==[dict(action_id=action['action_id'],security_id=sid,ratio=action['ratio'],old_unit_id=action['old_unit_id'],new_unit_id=action['new_unit_id'],quote_unit_effective_at=boundary)],'MONTHLY_HISTORY_SPLIT_SCHEDULE')
  else:
   require(schedule==[],'MONTHLY_HISTORY_PREWINDOW_SCHEDULE')
  normalized=normalize_monthly_raw(inputs=inputs,sources={sid:files[path]},expected_hashes={sid:pins[path]},identities={sid:item['identity']},reviews={sid:review})
  values=[Fraction(normalized['projections'][sid]['normalized_closes'][d]) for d in days]
  require(values==list(map(Fraction,row['training_close'])),'MONTHLY_HISTORY_COMPILER_DOUBLE_OR_MISSING_ADJUSTMENT')
  require(values[-1]==Fraction(compiled['input']['search_arguments']['prices'][sid]),'MONTHLY_HISTORY_DECISION_PRICE')
  result[action['action_id']]=item['recorded_action_sha256']
 return dict(training_manifest_sha256=pins[manifest_path],historical_search_arguments_sha256=sha256(canonical(compiled['input']['search_arguments'])).hexdigest(),recorded_action_sha256=result,review_sha256=review_sha256)


def build_runtime(*,root,configuration,approval_pins,timing_bundles,training_review_bytes,training_review_sha256,clock=None,market_factory=None,action_factory=None):
 root=Path(root).resolve();configuration=deepcopy(configuration);timing_bundles=deepcopy(timing_bundles)
 require(RUNTIME_PATHS<=set(approval_pins) and RUNTIME_PATHS<=set(configuration['runtime_pins']),'SPLIT_MONTHLY_APPROVAL_REQUIRED')
 def gate():
  for name in RUNTIME_PATHS:
   expected=approval_pins[name]
   require(expected==configuration['runtime_pins'][name] and sha256((root/name).read_bytes()).hexdigest()==expected and sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest()==expected,'SPLIT_MONTHLY_SOURCE_CHANGED')
 gate()
 class Provider(SplitProvider):
  def _assemble(self,state,package,historical,**kwargs):
   gate()
   proof=history_admission(package=package,manifest_path=self.manifest_path,state=state,review_bytes=training_review_bytes,review_sha256=training_review_sha256,timing_bundles=timing_bundles,now=self.clock().isoformat())
   package=deepcopy(package);name='split-monthly-training-review.json'
   require(name not in package['files'],'MONTHLY_REVIEW_SOURCE_COLLISION')
   package['files'][name]=training_review_bytes;package['source_hashes'][name]=training_review_sha256
   def units(**arguments):
    recorded=[r['payload'] for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
    require(len(recorded)<=1,'MONTHLY_MULTI_SPLIT_REVIEW_NOT_IMPLEMENTED')
    for action in recorded:
     from data.strategy_account_target_inputs import stamp
     timing=timing_bundles[action['action_id']]
     checked=review_timing(action=action,timing=timing,now=arguments['now'])
     mark=arguments['marks'].get(action['security_id'])
     if mark is not None:
      require(stamp(mark['observed_at'])>=stamp(checked['quote_unit_effective_at']) and mark.get('unit_id')==action['new_unit_id'],'MONTHLY_MARK_BEFORE_QUOTE_UNIT')
    def split_review(**values):return review_recorded_splits(**values,timing=timing_bundles[recorded[0]['action_id']])
    return bind(review_interval,review_recorded_splits=split_review)(**arguments,training_admission=proof)
   delegate=self.actions
   class ActionCapture:
    def capture(self,request,output_directory):
     request=deepcopy(request)
     from data.strategy_account_target_inputs import stamp
     starts=[stamp(request['window_start'])]+[stamp(timing_bundles[r['payload']['action_id']]['review']['quote_unit_effective_at']) for r in state['events'] if r['payload']['kind']=='SPLIT_CONFIRMED']
     request['window_start']=min(starts).isoformat()
     return delegate.capture(request,output_directory=output_directory)
   local=copy(self);local.actions=ActionCapture()
   result=bind(SplitProvider._assemble,review_interval=units)(local,state,package,historical,**kwargs)
   gate();return result
 factory=bind(original_runtime.build_runtime,ScopedAccountStore=SplitStrategyAccountStore,
  StrategyAccountTargetService=SplitContinuous32TargetService,StrategyMonthlyTargetService=SplitContinuous32MonthlyService,
  StrategyAccountEvidenceProvider=Provider,StrategyAccountMarketCapture=market_factory or StrategyAccountMarketCapture,
  StrategyAccountActionCapture=action_factory or original_runtime.StrategyAccountActionCapture,
  build_execution_limits=build_execution_limits,RUNTIME_PATHS=RUNTIME_PATHS)
 monthly=factory(root=root,configuration=configuration,clock=clock)
 state=monthly.accounts.read();require(state is None or state['account_id']==original_runtime.ACCOUNT_ID,'ACCOUNT_SCOPE_MISMATCH')
 monthly.validate_current_target_pins=monthly.selection._pins
 return monthly
