import sys,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from test_capped_frontier_independent_review import inputs,raw_fixture
from reentry_repair import run_reentry,ReentryRepair
from independent_reference_review import review,ReferenceOrderVerifier
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter

class IndependentTests(unittest.TestCase):
 def setUp(self):
  self.d,self.b=inputs();self.d['source_hashes']={}
  self.context={'window':'2021_2023','document':{'assembled':self.d,'dividend_events':[]},'prices':{},'action_review':{}}
  self.book=run_reentry(assembled=self.d,ohlc=self.b,initial_cash='20000',fee_bps='1',slippage_bps='10',risk=MonthlyExitCoreResearchAdapter([]),max_new_searches=1,verify_interval=lambda *a:{'status':'NOT_CURRENT_BUY'},selector=lambda **a:raw_fixture(a))
 def check(self,b):
  return review(b,self.d,self.b,initial_cash='20000',dividend_events=[],expected_fee_bps='1',expected_slippage_bps='10',reference_context=self.context)
 def test_real_full_kernel_and_selection(self):
  self.assertTrue(self.check(self.book)['reference_order_rule_verified'])
 def test_false_lock(self):
  b=deepcopy(self.book);b['reentry_audit'][-1]['locks_after']={}
  with self.assertRaisesRegex(ValueError,'LOCK_AFTER'):self.check(b)
 def test_false_actual_shares(self):
  b=deepcopy(self.book);b['reentry_audit'][0]['actual_shares']={'A':1}
  with self.assertRaisesRegex(ValueError,'ACTUAL_SHARES'):self.check(b)
 def test_false_fill(self):
  b=deepcopy(self.book);next(x for x in b['order_log'] if x.get('event')=='ASSUMED_NEXT_OPEN_FILLED')['quantity']=1
  with self.assertRaises(ValueError):self.check(b)
 def test_original_sell_cannot_be_removed(self):
  b=deepcopy(self.book)
  for a in b['reentry_audit']:
   if any(o['side']=='SELL' for o in a['adjusted']['orders']):a['adjusted']['orders']=[];break
  with self.assertRaisesRegex(ValueError,'BUY_FILTER_OR_SELL_MUTATION'):self.check(b)
 def test_blocked_buy_does_not_remove_other_sell(self):
  d={'close_prices':{'A':{'2025-01-06':'100','2025-01-07':'90'}},'source_hashes':{},'actions':[],'session_dates':['2025-01-06','2025-01-07']}
  ctx={'window':'2021_2023','document':{'assembled':d,'dividend_events':[]},'prices':{},'action_review':{}}
  proof={'status':'VERIFIED','current_security_id':'A','completed_rows':[dict(date='2025-01-07',security_id='A',close='90',conversion=None)]}
  eng=ReentryRepair(close_prices=d['close_prices'],source_hashes={},verify_interval=lambda *a:proof);checker=ReferenceOrderVerifier(d,ctx)
  origin={'status':'READY','unreserved_cash':'0','risk_overlay':{'state':{'decision_date':'2024-12-31','exited':['A']}},'orders':[{'side':'SELL','security_id':'A','quantity':1}]}
  eng.adjust(origin,state={'cash':'0','shares':{'A':1}},decision_date='2025-01-06',active_date='2025-01-07');checker.verify(eng.audit[-1],origin,'2025-01-06','2025-01-07',{'A':1})
  origin=deepcopy(origin);origin['risk_overlay']['state']['exited']=[];origin['orders']=[{'side':'BUY','security_id':'A','quantity':1},{'side':'SELL','security_id':'B','quantity':1}]
  eng.adjust(origin,state={'cash':'0','shares':{'B':1}},decision_date='2025-01-07',active_date='2025-01-08')
  with patch('scripts.run_recent_continuous_probe.exposed_action_blockers',return_value={'missing_action_streams':[],'unmapped_events':[]}):
   result=checker.verify(eng.audit[-1],origin,'2025-01-07','2025-01-08',{'B':1})
  self.assertEqual(result,[origin['orders'][1]]);self.assertEqual(checker.blocked_buys,1)
 def test_reference_full_path_not_claimed_recovery(self):
  # Synthetic provider here isolates reference arithmetic; full kernel above
  # independently verifies actual risk/selection/account execution.
  d={'close_prices':{'A':{'2025-01-06':'100','2025-01-07':'90','2025-01-08':'101','2025-01-09':'85'}},'source_hashes':{},'actions':[],'session_dates':['2025-01-06','2025-01-07','2025-01-08','2025-01-09']}
  ctx={'window':'2021_2023','document':{'assembled':d,'dividend_events':[]},'prices':{},'action_review':{}}
  rows=[dict(date=day,security_id='A',close=d['close_prices']['A'][day],conversion=None) for day in d['session_dates'][1:]]
  proof={'status':'VERIFIED','current_security_id':'A','completed_rows':rows}
  eng=ReentryRepair(close_prices=d['close_prices'],source_hashes={},verify_interval=lambda *a:proof)
  checker=ReferenceOrderVerifier(d,ctx)
  def original(exited,orders):return {'status':'READY','unreserved_cash':'0','risk_overlay':{'state':{'decision_date':'2024-12-31','exited':exited}},'orders':orders}
  sell=original(['A'],[{'side':'SELL','security_id':'A','quantity':1}]);state={'cash':'0','shares':{'A':1}}
  eng.adjust(sell,state=state,decision_date='2025-01-06',active_date='2025-01-07');checker.verify(eng.audit[-1],sell,'2025-01-06','2025-01-07',state['shares'])
  buy=original([], [{'side':'BUY','security_id':'A','quantity':1}]);state={'cash':'0','shares':{}}
  eng.adjust(buy,state=state,decision_date='2025-01-09',active_date='2025-01-10')
  with patch('scripts.run_recent_continuous_probe.exposed_action_blockers',return_value={'missing_action_streams':[],'unmapped_events':[]}):
   checker.verify(eng.audit[-1],buy,'2025-01-09','2025-01-10',{})
   self.assertEqual(checker.locks,{})
   bad=deepcopy(eng.audit[-1]);bad['interval_reviews'][0]['recovered_at']='2025-01-07'
   checker.locks=deepcopy(bad['locks_before'])
   with self.assertRaisesRegex(ValueError,'REFERENCE_PATH'):checker.verify(bad,buy,'2025-01-09','2025-01-10',{})
if __name__=='__main__':unittest.main()
