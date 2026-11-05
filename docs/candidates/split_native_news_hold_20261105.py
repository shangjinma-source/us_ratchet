"""Actual news HOLD risk-plan integration with protected native execution.
No ledger writes, production install, or change to strategy risk targets.
"""
from copy import deepcopy
from hashlib import sha256
from core.strategy_account_ledger import canonical,require
from data import news_risk_execution_bridge_v1 as original
from data.news_risk_plan_v1 import build_risk_plan
from docs.candidates.strategy_account_split_scoped_preview import preview_scoped_account
from docs.candidates.split_native_daily_execution_bridge_20261105 import DailyExecutionBridge
from docs.candidates.split_production_admission_20261105 import bind

class NativeNewsHoldBridge(DailyExecutionBridge):
 def __init__(self,*,base_target,execution_provider,validate_sources,signal,proposal):
  super().__init__(base_target=base_target,execution_provider=execution_provider,validate_sources=validate_sources,signal=signal)
  self.review=deepcopy(proposal)

 def __call__(self,state,targets,now):
  effective=deepcopy(self.signal['effective_target_quantities'])
  require(set(targets)==set(effective),'NEWS_PROJECTION_DOMAIN')
  require(all(type(q)is int and 0<=q<=effective[s] and q<=state['shares'].get(s,0) for s,q in targets.items()),'NEWS_SELL_ONLY_REQUIRED')
  extra=dict(schema='NATIVE_NEWS_HOLD_EXECUTION_PROJECTION_V1',review_id=self.review['review_id'],review_sha256=original.digest(self.review),projected_target_quantities=deepcopy(targets),original_signal_mutated=False)
  result=self._execute(state,effective,now,projection=targets,extra=extra)
  self.binding=dict(self.last_binding,lineage=extra)
  return result


def install_native_hold_risk_plan(*,service,configured,validate):
 """Install before lifecycle start on a freshly composed actual news service.

 No generic attribute facade: each call opens one target-bound protected
 composition holding the real monthly snapshot and full factory provider gates.
 """
 from data.news_investment_service_v1 import NewsInvestmentService
 require(isinstance(service,NewsInvestmentService),'NATIVE_NEWS_SERVICE_REQUIRED')
 make=bind(original.make_hold_risk_plan_adapter,NewsHoldExecutionBridge=NativeNewsHoldBridge,preview_scoped_account=preview_scoped_account)
 def project(*,original,proposal,account,target,now):
  if original.get('status')!='HOLD':
   return build_risk_plan(proposal=proposal,original_preview=original,account=account,now=now)
  generation=service.news_generation()
  def guard():
   validate()
   require(service.news_generation()==generation,'NEWS_UPDATED_DURING_EXECUTION_PREVIEW')
  with configured.protected_composition(expected_revision=account['revision'],target_id=target['target_id'],expected_proposal_id=target['proposal_id']) as composition:
   adapter=make(composition=composition,validate=validate,review_guard=guard)
   return adapter(original=original,proposal=proposal,account=account,target=target,now=now)
 service.risk_plan_provider=project
 return service
