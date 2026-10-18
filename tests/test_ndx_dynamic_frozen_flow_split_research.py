import unittest
from copy import deepcopy
import pandas as pd
from backtest.ndx_dynamic_frozen_flow_split_research import simulate_dynamic_frozen_flow_split_research as simulate
from backtest.ndx_dynamic_frozen_execution_research import simulate_dynamic_frozen_execution_research as old


def fixture():
 dates=pd.bdate_range('2026-03-31',periods=6);prices=pd.DataFrame(10.,index=dates,columns=['A'])
 return dict(closes=prices,opens=prices.copy(),schedule=[dict(decision_date=str(dates[0].date()),execution_date=str(dates[1].date()),targets={'A':dict(ticker='A',issuer_id='ISS',target_weight=1.)})],risk_chains_by_decision={str(dates[0].date()):{'A':'chain'}},corporate_actions=[],external_flows=[],initial_cash_usd=1000.,minimum_cash_buffer_usd=100.,valuation_end_date=str(dates[-1].date()),transaction_cost_bps=0.,max_single_weight=1.,min_single_weight=0.,top_weight_cap=1.,minimum_effective_n_ratio=0.,risk_chain_top1_cap=1.)

def flow(day,amount=1000.):return dict(session=day,amount_usd=amount,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))
def split(day):return dict(security_id='A',session=day,new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)

class Tests(unittest.TestCase):
 def test_no_flow_keeps_frozen_engine_results(self):
  x=fixture();x['transaction_cost_bps']=10.;r=simulate(**x);x.pop('external_flows');prior=old(**x)
  for key in ('decisions','executions','trades'):self.assertEqual(r[key],prior[key])
  self.assertEqual(r['summary']['path_return_net'],prior['summary']['path_return_net'])
 def test_future_receipt_does_not_change_close_basket(self):
  x=fixture();baseline=simulate(**x);x['external_flows']=[flow(x['schedule'][0]['execution_date'])];r=simulate(**x)
  self.assertEqual(r['decisions'],baseline['decisions']);self.assertEqual(r['daily'][-1]['shares'],{'A':90})
  self.assertEqual(r['daily'][-1]['cash_usd'],1100.);self.assertAlmostEqual(r['summary']['chained_twr'],0.)
 def test_rejection_preserves_credited_cash_and_no_retry(self):
  x=fixture();x['opens'].iloc[1,0]=100.;x['external_flows']=[flow(x['schedule'][0]['execution_date'],100.)];r=simulate(**x)
  self.assertEqual(r['executions'][0]['status'],'REJECTED');self.assertEqual(r['daily'][-1]['cash_usd'],1100.)
  self.assertEqual(r['trades'],[]);self.assertEqual(r['summary']['chained_twr'],0.)
 def test_split_old_holdings_and_cancel_pending_no_replan(self):
  x=fixture();day=str(x['closes'].index[3].date());dec=str(x['closes'].index[2].date());x['schedule'].append(dict(x['schedule'][0],decision_date=dec,execution_date=day));x['risk_chains_by_decision'][dec]={'A':'chain'}
  x['corporate_actions']=[split(day)];x['closes'].iloc[3:,0]=5.;x['opens'].iloc[3:,0]=5.;x['external_flows']=[flow(day)]
  r=simulate(**x);self.assertEqual(r['executions'][-1]['status'],'CANCELLED_SPLIT');self.assertEqual(r['daily'][-1]['shares'],{'A':180})
  self.assertEqual(len(r['trades']),1);self.assertEqual(r['daily'][-1]['cash_usd'],1100.);self.assertAlmostEqual(r['summary']['chained_twr'],0.)
 def test_nonrebalance_receipt_and_accounts_independent(self):
  x=fixture();x['external_flows']=[flow(str(x['closes'].index[2].date()),0.),flow(str(x['closes'].index[3].date()),20.)];before=deepcopy(x);r=simulate(**x)
  self.assertEqual(r['daily'][-1]['cash_usd'],120.);self.assertEqual(len(r['trades']),1);self.assertEqual(r['summary']['chained_twr'],0.)
  pd.testing.assert_frame_equal(x['closes'],before['closes']);self.assertEqual(x['schedule'],before['schedule']);self.assertEqual(simulate(**fixture())['daily'][-1]['cash_usd'],100.)
 def test_strict_flow_identity_and_dates(self):
  for change in ('currency','negative','initial','duplicate'):
   x=fixture();f=flow(x['schedule'][0]['execution_date']);x['external_flows']=[f]
   if change=='currency':f['currency']='CNY'
   elif change=='negative':f['amount_usd']=-1.
   elif change=='initial':f['session']=x['schedule'][0]['decision_date']
   else:x['external_flows'].append(deepcopy(f))
   with self.assertRaises(ValueError):simulate(**x)

if __name__=='__main__':unittest.main()
