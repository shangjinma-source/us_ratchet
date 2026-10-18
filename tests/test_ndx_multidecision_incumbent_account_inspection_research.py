from copy import deepcopy
import unittest
from backtest import ndx_multidecision_incumbent_account_inspection_research as m
from backtest.ndx_incumbent_flow_split_control_research import simulate_incumbent_flow_split_control as run
from test_ndx_incumbent_flow_split_control_research import fixture

def prepared(args):
 k=deepcopy(args)
 for name in ('opens','closes'):
  frame=k[name];k[name]=dict(index=[str(d.date()) for d in frame.index],columns=list(frame.columns),data=frame.values.tolist())
 return dict(track=k['track'],status='CONTROL_INPUTS_PREPARED_NOT_EXECUTED',engine_binding=dict(keyword_arguments=k))
class Tests(unittest.TestCase):
 def test_original_literal_weights_and_observed_failed_risk_do_not_gate_orders(self):
  for kind in ('CONTINUOUS','WHOLE_LOT'):
   x=fixture(kind);r=run(**x);report=m.inspect_saved_control(prepared_track=prepared(x),result=r)
   self.assertFalse(r['daily'][-1]['risk']['all_passed']);self.assertTrue(r['trades']);self.assertEqual(report['original_targets_preserved'],x['schedule'][0]['targets']);self.assertFalse(report['weights_normalized'])
   bad=deepcopy(r);bad['original_targets']['A']['target_weight']=.125
   with self.assertRaises(ValueError):m.inspect_saved_control(prepared_track=prepared(x),result=bad)
 def test_exact_hand_expected_original8_quantities_no_fee_and_twr_zero(self):
  for kind in ('CONTINUOUS','WHOLE_LOT'):
   x=fixture(kind)
   for target in x['schedule'][0]['targets'].values():target['target_weight']=.125
   r=run(**x);out=m.inspect_saved_control(prepared_track=prepared(x),result=r)
   self.assertEqual(out['terminal_equity_exact'],'1000');self.assertEqual(out['chained_twr_exact'],'0')
   if kind=='WHOLE_LOT':self.assertEqual(r['daily'][-1]['shares'],dict.fromkeys('ABCDEFGH',11));self.assertEqual(out['terminal_cash_exact'],'120')
   else:self.assertEqual(r['daily'][-1]['holdings']['A']['shares'],11.25);self.assertEqual(out['terminal_cash_exact'],'100')
 def test_split_flow_fee_two_accounts_and_saved_mutations(self):
  for kind in ('CONTINUOUS','WHOLE_LOT'):
   x=fixture(kind);x['transaction_cost_bps']=10.;x['opens'].loc['2026-04-02':,'A']=5.;x['closes'].loc['2026-04-02':,'A']=5.;x['corporate_actions']=[dict(security_id='A',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/s',evidence_sha256='a'*64)];x['external_flows']=[dict(session='2026-04-02',amount_usd=200.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/flow',sha256='b'*64))]
   r=run(**x);out=m.inspect_saved_control(prepared_track=prepared(x),result=r);self.assertEqual(out['cash_injections_exact'],'200');self.assertEqual(out['split_trace_rows'],1)
   for mutate in (lambda z:z['daily'][2].update(cash_usd=z['daily'][2]['cash_usd']+1),lambda z:z.update(weights_normalized=True),lambda z:z['daily'][2].update(normalized_twr=2.)):
    bad=deepcopy(r);mutate(bad)
    with self.assertRaises(ValueError):m.inspect_saved_control(prepared_track=prepared(x),result=bad)
 def test_zero_slot_fee_floor_and_open_reject(self):
  for reject in (False,True):
   x=fixture('WHOLE_LOT');x['transaction_cost_bps']=10.;x['opens']['H']=100000.;x['closes']['H']=100000.
   if reject:x['opens'].iloc[1,:7]=100.
   r=run(**x);out=m.inspect_saved_control(prepared_track=prepared(x),result=r)
   self.assertEqual(r['decisions'][0]['desired_shares']['H'],0);self.assertEqual(len(r['trades']),0 if reject else 7)
   bad=deepcopy(r);bad['decisions'][0]['desired_shares']['H']=1
   with self.assertRaises(ValueError):m.inspect_saved_control(prepared_track=prepared(x),result=bad)
if __name__=='__main__':unittest.main()
