from contextlib import nullcontext
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from fastapi import APIRouter
from data.strategy_unified_server_preparation_v21 import attach_explanations, ExplainedDailyService

class ExplanationMountTests(TestCase):
 def test_only_preview_route_replaced_and_audit_kept(self):
  monthly=SimpleNamespace(snapshot_operation=nullcontext)
  service=SimpleNamespace(monthly=monthly,policy_id='SMA20_HALF_OFF_RESEARCH')
  old=SimpleNamespace(monthly=monthly,service=service,journal=object(),clock=object(),policy_references={'original':'policy'})
  router=APIRouter()
  async def endpoint():return {}
  router.add_api_route('/api/strategy-account',endpoint,methods=['GET'])
  router.add_api_route('/api/strategy-daily-v3/preview',endpoint,methods=['POST'])
  account_route=router.routes[0];calls=[]
  prepared=dict(monthly=monthly,observed_daily=old,router=router,validate_code=lambda:calls.append('base'))
  result=attach_explanations(prepared=prepared,archive_root='archive',validate_sources=lambda:calls.append('new'))
  self.assertIs(result['router'].routes[0],account_route)
  self.assertEqual(len(result['router'].routes),2)
  self.assertIs(result['observed_daily'].journal,old.journal)
  self.assertIs(result['observed_daily'].service.service,service)
  self.assertEqual(result['observed_daily'].policy_references,old.policy_references)
  self.assertEqual(calls,['base','new']*2)
 def test_wait_unchanged_and_exact_single_underlying_call(self):
  calls=[];response=dict(status='WAIT',reason='WAIT_NEXT_SESSION',new_orders=[],reference_quotes={})
  service=SimpleNamespace(monthly=SimpleNamespace(snapshot_operation=nullcontext),policy_id='SMA20_HALF_OFF_RESEARCH',preview=lambda **kw:(calls.append(kw) or response))
  wrapper=ExplainedDailyService(service,'missing',lambda:None)
  self.assertEqual(wrapper.preview(expected_revision='r',target_id='t'),response)
  self.assertEqual(calls,[dict(expected_revision='r',target_id='t')])
 def test_source_gate_failure_prevents_request(self):
  calls=[]
  service=SimpleNamespace(monthly=SimpleNamespace(snapshot_operation=nullcontext),preview=lambda **kw:calls.append(kw))
  def fail():raise ValueError('SOURCE_CHANGED')
  with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
   ExplainedDailyService(service,'missing',fail).preview(expected_revision='r',target_id='t')
  self.assertEqual(calls,[])
