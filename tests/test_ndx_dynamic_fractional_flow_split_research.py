import unittest
from copy import deepcopy
import pandas as pd
from backtest.ndx_dynamic_fractional_flow_split_research import simulate_dynamic_fractional_flow_split_research as run


def fixture():
 days=['2026-03-31','2026-04-01','2026-04-02','2026-04-03']
 prices=pd.DataFrame({'A':[10.]*4},index=pd.to_datetime(days))
 return dict(opens=prices,closes=prices.copy(),schedule=[dict(decision_date=days[0],execution_date=days[1],targets={'SID':dict(ticker='A',issuer_id='ISS',target_weight=1.)})],corporate_actions=[],external_flows=[],initial_cash_usd=100.,minimum_cash_buffer_usd=0.,transaction_cost_bps=0.,valuation_end_date=days[-1])

def flow(amount=100.,session='2026-04-02'):
 return dict(session=session,amount_usd=amount,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))

def split():
 return dict(security_id='SID',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)

class Tests(unittest.TestCase):
 def test_flat_flow_is_cash_not_return_or_unscheduled_trade(self):
  for amount in (0.,100.):
   x=fixture();x['external_flows']=[flow(amount)];r=run(**x)
   self.assertAlmostEqual(r['summary']['chained_twr'],0.);self.assertAlmostEqual(r['daily'][-1]['cash_usd'],amount)
   self.assertEqual(len(r['trades']),1);self.assertAlmostEqual(r['daily'][-1]['holdings']['SID']['shares'],10.)
 def test_split_zero_return_and_original_inputs_unchanged(self):
  x=fixture();x['opens'].iloc[2:,0]=5.;x['closes'].iloc[2:,0]=5.;x['corporate_actions']=[split()];x['external_flows']=[flow()]
  before=deepcopy(x);r=run(**x)
  self.assertAlmostEqual(r['summary']['chained_twr'],0.);self.assertAlmostEqual(r['daily'][-1]['holdings']['SID']['shares'],20.)
  self.assertEqual(r['corporate_actions'][0]['split_fee_usd'],0.);pd.testing.assert_frame_equal(x['opens'],before['opens']);self.assertEqual(x['schedule'],before['schedule'])
  other=run(**fixture());self.assertAlmostEqual(other['daily'][-1]['holdings']['SID']['shares'],10.)
 def test_rejected_low_capital_keeps_injection(self):
  x=fixture();x.update(initial_cash_usd=50.,minimum_cash_buffer_usd=100.);x['external_flows']=[flow(20.,'2026-04-01')];r=run(**x)
  self.assertEqual(r['summary']['rejected_rebalance_count'],1);self.assertEqual(r['daily'][-1]['cash_usd'],70.)
  self.assertEqual(r['daily'][-1]['holdings'],{});self.assertEqual(r['summary']['chained_twr'],0.);self.assertEqual(r['summary']['total_fees_usd'],0.)
 def test_fee_is_performance_loss(self):
  x=fixture();x['transaction_cost_bps']=10.;r=run(**x)
  expected=100./1.001
  self.assertAlmostEqual(r['summary']['terminal_equity_usd'],expected);self.assertAlmostEqual(r['summary']['chained_twr'],expected/100.-1.)
  self.assertAlmostEqual(r['summary']['total_fees_usd'],100.-expected)
 def test_bad_flow_split_and_price_rejected(self):
  for mutate in (lambda x:x.update(external_flows=[flow(-1.)]),lambda x:x.update(external_flows=[dict(flow(),currency='CNY')]),lambda x:x.update(external_flows=[flow(session='2026-03-31')]),lambda x:x.update(corporate_actions=[split(),split()]),lambda x:x.update(corporate_actions=[dict(split(),new_shares=True)]),lambda x:x.update(initial_cash_usd=True)):
   x=fixture();mutate(x)
   with self.assertRaises(ValueError):run(**x)
 def test_missing_decision_and_unbridged_alias_rejected(self):
  x=fixture();x['opens']=x['opens'].drop(pd.Timestamp('2026-04-02'));x['closes']=x['closes'].drop(pd.Timestamp('2026-04-02'));x['schedule'].append(dict(x['schedule'][0],decision_date='2026-04-02',execution_date='2026-04-03'))
  with self.assertRaises(ValueError):run(**x)
  x=fixture();x['opens']['B']=10.;x['closes']['B']=10.;x['schedule'].append(dict(decision_date='2026-04-01',execution_date='2026-04-02',targets={'SID':dict(ticker='B',issuer_id='ISS',target_weight=1.)}))
  with self.assertRaises(ValueError):run(**x)

if __name__=='__main__':unittest.main()
