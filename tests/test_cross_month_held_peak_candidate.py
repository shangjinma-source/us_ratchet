import unittest
from copy import deepcopy
from docs.candidates.cross_month_held_peak_adapter import CrossMonthHeldPeakAdapter,ExecutedPositionEpochs
class Tests(unittest.TestCase):
 def apply(self,r,day,month,price,epoch='a',adjustments=()):
  return r.apply(day=day,month=month,target={'S':10},closes={'S':str(price)},position_epochs={'S':epoch} if epoch else {},adjustments=adjustments)
 def test_continuous_month_exit(self):
  r=CrossMonthHeldPeakAdapter();self.apply(r,'2026-01-30','2026-01-30',100)
  self.assertEqual(self.apply(r,'2026-02-27','2026-02-27',79)[0],{'S':0})
 def test_partial_and_add_do_not_reset(self):
  e=ExecutedPositionEpochs();state={'daily_ledger':[],'shares':{'S':10}};first=e.observe(state)
  for q in (5,20):state['shares']['S']=q;self.assertEqual(e.observe(state),first)
 def test_true_flat_new_epoch_month_latch_remains(self):
  r=CrossMonthHeldPeakAdapter();self.apply(r,'2026-01-30','2026-01-30',100)
  self.assertEqual(self.apply(r,'2026-02-02','2026-01-30',79)[0],{'S':0})
  self.assertEqual(self.apply(r,'2026-02-03','2026-01-30',85,epoch=None)[0],{'S':0})
  self.assertEqual(self.apply(r,'2026-02-27','2026-02-27',79,epoch='new')[0],{'S':10})
 def test_month_split_rebases_carried_peak(self):
  action={'date':'2026-02-27','security_id':'S','type':'split','old_shares':1,'new_shares':2,'source_references':['proof']}
  r=CrossMonthHeldPeakAdapter([action]);self.apply(r,'2026-01-30','2026-01-30',100)
  self.assertEqual(self.apply(r,'2026-02-27','2026-02-27',45,adjustments=[dict(date='2026-02-27',security_id='S',new_security_id='S')])[0],{'S':10})
  self.assertEqual(r.state['peaks']['S'],'50')
  self.assertEqual(self.apply(r,'2026-03-02','2026-02-27',39)[0],{'S':0})
 def test_hidden_zero_in_ledger_starts_new_epoch(self):
  e=ExecutedPositionEpochs();old=e.observe({'daily_ledger':[],'shares':{'S':10}})
  new=e.observe({'daily_ledger':[{'shares':{'S':0}},{'shares':{'S':3}}],'shares':{'S':3}})
  self.assertNotEqual(old,new)
 def test_failed_action_does_not_advance(self):
  r=CrossMonthHeldPeakAdapter();self.apply(r,'2026-01-30','2026-01-30',100);old=deepcopy(r.__dict__)
  with self.assertRaises(ValueError):self.apply(r,'2026-02-27','2026-02-27',45,adjustments=[dict(date='2026-02-27',security_id='S',new_security_id='S')])
  self.assertEqual(r.__dict__,old)
if __name__=='__main__':unittest.main()

class BookIntegration(unittest.TestCase):
 def test_real_next_open_book_carries_actual_positions(self):
  from unittest.mock import patch
  from docs.candidates import cross_month_held_peak_runner as runner
  days=['2026-01-29','2026-01-30','2026-02-02','2026-02-03','2026-02-04']
  closes=dict(zip(days,['100','100','79','82','83']))
  assembled=dict(session_dates=days,monthly_inputs=[dict(decision_date=d,search_arguments={'fee_bps':'0'},valuation_quotes=[dict(security_id='S',price=closes[d])],source_hashes={}) for d in (days[0],days[2])],close_prices={'S':closes},provider_actions=[],actions=[],cash_stock_merger_events=[],fractional_settlements=None,price_source_references={},distribution_events=[],distribution_fractional_cash_values=None)
  bars={'S':{d:dict(open=('80' if d==days[3] else closes[d]),high=max(int(closes[d]),80),low=min(int(closes[d]),80),close=closes[d]) for d in days}}
  risk=CrossMonthHeldPeakAdapter()
  from fractions import Fraction
  def select(**kw):return {'target_quantities':{'S':2},'investable_equity':str(Fraction(kw['account_state']['cash'])+kw['account_state']['shares'].get('S',0)*Fraction(closes[kw['decision_date']]))}
  with patch.object(runner,'decide_continuous_guided_for_account',side_effect=select),patch.object(runner,'rerank',side_effect=lambda x:x):
   book=runner.run_frontier_capped_next_open(assembled=assembled,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5',max_new_searches=2,risk=risk)
  self.assertEqual(book['status'],'COMPLETE',str(book))
  fills=[x for x in book['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
  self.assertEqual([(x['date'],x['side'],x['quantity']) for x in fills],[('2026-01-30','BUY',2),('2026-02-03','SELL',2)])
  self.assertEqual(risk.audit[0]['position_epochs'],{})
  self.assertTrue(risk.audit[1]['position_epochs'])
  self.assertEqual(risk.audit[2]['carried_peaks'],{'S':'100'})
  self.assertEqual(risk.audit[3]['position_epochs'],{})

