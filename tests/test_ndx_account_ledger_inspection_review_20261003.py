from copy import deepcopy
import unittest
import pandas as pd
from backtest import ndx_multidecision_account_inspection_research as r
from backtest.ndx_dynamic_fractional_flow_split_research_v2 import simulate_dynamic_fractional_flow_split_research as fractional
from backtest.ndx_dynamic_frozen_flow_split_research import simulate_dynamic_frozen_flow_split_research as whole
from test_ndx_multidecision_account_inspection_research import prepared

def case(kind):
 days=['2026-03-31','2026-04-01','2026-04-02','2026-04-03','2026-04-06','2026-04-07'];frame=pd.DataFrame(10.,index=pd.to_datetime(days),columns=list('ABCD'));frame.loc[days[2]:,'A']=5.;frame.loc[days[5]:,'C']=5.
 def target(s):return dict(ticker=s,issuer_id='ISS'+s,target_weight=.5)
 args=dict(opens=frame.copy(),closes=frame,schedule=[dict(decision_date=days[0],execution_date=days[1],targets={s:target(s) for s in 'AB'}),dict(decision_date=days[2],execution_date=days[3],targets={s:target(s) for s in 'CD'})],corporate_actions=[dict(security_id=s,session=d,new_shares=2,old_shares=1,source_url='https://example.com/'+s,evidence_sha256=h*64) for s,d,h in [('A',days[2],'a'),('C',days[5],'b')]],external_flows=[dict(session=days[2],amount_usd=100.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/flow',sha256='c'*64))],initial_cash_usd=10000.,minimum_cash_buffer_usd=100.,transaction_cost_bps=10.,valuation_end_date=days[-1])
 if kind=='WHOLE_LOT':args.update(risk_chains_by_decision={days[0]:{s:s for s in 'AB'},days[2]:{s:s for s in 'CD'}},max_single_weight=1.,min_single_weight=0.,top_weight_cap=1.,minimum_effective_n_ratio=0.,risk_chain_top1_cap=1.)
 return prepared(args,kind),(whole if kind=='WHOLE_LOT' else fractional)(**args)

class Review(unittest.TestCase):
 def test_multisecurity_exit_entry_two_splits_and_cash_conservation(self):
  for kind in ('CONTINUOUS','WHOLE_LOT'):
   track,result=case(kind);report=r.inspect_saved_account(prepared_track=track,result=result)
   self.assertEqual(report['daily_rows'],6);self.assertEqual(report['split_trace_rows'],2);self.assertEqual(report['trades'],6)
   self.assertEqual(report['cash_injections_exact'],'100');self.assertFalse(report['integer_repair_search_independently_recomputed'])
   for attack in ('fee','exit','split'):
    bad=deepcopy(result)
    if attack=='fee':bad['trades'][2]['transaction_cost_usd' if kind=='WHOLE_LOT' else 'fee_usd']+=.01
    elif attack=='exit':bad['trades'][2]['share_delta']=abs(bad['trades'][2]['share_delta'])
    elif kind=='WHOLE_LOT':bad['corporate_actions'][-1]['applied_events'][0]['post_shares']+=1
    else:bad['corporate_actions'][-1]['shares_after']+=1
    with self.subTest(kind=kind,attack=attack),self.assertRaises(ValueError):r.inspect_saved_account(prepared_track=track,result=bad)
 def test_arithmetic_pass_cannot_upgrade_authority_or_execution_state(self):
  for kind in ('CONTINUOUS','WHOLE_LOT'):
   track,result=case(kind)
   for value in (True,0):
    bad=deepcopy(result);bad['point_in_time_verified']=value
    with self.subTest(kind=kind,value=value),self.assertRaises(ValueError):r.inspect_saved_account(prepared_track=track,result=bad)
  track,result=case('CONTINUOUS');result['daily'][1]['execution_status']='NO_REBALANCE'
  with self.assertRaises(ValueError):r.inspect_saved_account(prepared_track=track,result=result)

if __name__=='__main__':unittest.main()
