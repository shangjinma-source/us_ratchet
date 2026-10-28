import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from test_capped_frontier_independent_review import inputs,raw_fixture
from reentry_repair import run_reentry
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest import historical_dividend_frontier_research as f
class KernelTests(unittest.TestCase):
 def test_baseline_exact_and_real_exit_lock(self):
  d,b=inputs();d['source_hashes']={'synthetic':'0'*64}
  def args():return dict(assembled=d,ohlc=b,initial_cash='20000',fee_bps='1',slippage_bps='10',risk=MonthlyExitCoreResearchAdapter([]),max_new_searches=1)
  with patch.object(f,'decide_continuous_guided_for_account',side_effect=lambda **a:raw_fixture(a)):
   original=f.run_frontier_capped_next_open(**args())
  original.pop('research_only',None)
  seen=[]
  def coverage(*a):seen.append(a);return {'status':'NOT_CURRENT_BUY'}
  result=run_reentry(verify_interval=coverage,selector=lambda **a:raw_fixture(a),baseline=True,**args())
  for k,v in original.items():self.assertEqual(result[k],v,k)
  result=run_reentry(verify_interval=coverage,selector=lambda **a:raw_fixture(a),**args())
  self.assertEqual(result['status'],'COMPLETE');self.assertIn('A',result['reentry_locks'])
  lock=result['reentry_locks']['A'];self.assertEqual(lock['reference_price'],'120');self.assertEqual(lock['exit_date'],'2025-01-06')
  sells=[r for r in result['order_log'] if r.get('event')=='ASSUMED_NEXT_OPEN_FILLED' and r['side']=='SELL'];self.assertEqual(sells[0]['quantity'],99)
  self.assertTrue(all(o['side']!='BUY' for a in result['provider_audit'][2:] for o in a['orders']))
 def test_post_provider_deadline_blocks_execution(self):
  d,b=inputs();d['source_hashes']={};calls=[]
  def guard():
   calls.append(1)
   if len(calls)==2:raise ValueError('TIME_BUDGET_REACHED')
  result=run_reentry(assembled=d,ohlc=b,initial_cash='20000',fee_bps='1',slippage_bps='10',risk=MonthlyExitCoreResearchAdapter([]),max_new_searches=1,verify_interval=lambda *a:None,selector=lambda **a:raw_fixture(a),execution_guard=guard)
  self.assertNotEqual(result['status'],'COMPLETE')
  self.assertFalse(any(x.get('event')=='ASSUMED_NEXT_OPEN_FILLED' for x in result['order_log']))
  self.assertEqual(result['reentry_audit'][-1]['reason'],'TIME_BUDGET_REACHED')
if __name__=='__main__':unittest.main()


