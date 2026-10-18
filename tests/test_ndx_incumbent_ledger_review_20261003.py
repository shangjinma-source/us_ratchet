from copy import deepcopy
from fractions import Fraction
import unittest
from test_ndx_multidecision_incumbent_account_inspection_research import m, prepared, fixture, run


class Review(unittest.TestCase):
 def test_independent_stock_gain_and_injection_boundary_not_capital_return(self):
  for kind,gain in [('CONTINUOUS',Fraction(45,2)),('WHOLE_LOT',Fraction(22))]:
   args=fixture(kind)
   for t in args['schedule'][0]['targets'].values():t['target_weight']=.125
   for key in ('opens','closes'):args[key].loc['2026-04-02':,'A']=6.
   args['corporate_actions']=[dict(security_id='A',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)]
   args['external_flows']=[dict(session='2026-04-02',amount_usd=200.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))]
   saved=run(**args);out=m.inspect_saved_control(prepared_track=prepared(args),result=saved)
   self.assertEqual(Fraction(out['terminal_equity_exact']),1200+gain)
   self.assertEqual(Fraction(out['chained_twr_exact']),gain/1000)
   self.assertEqual(Fraction(out['cash_injections_exact']),200)
   self.assertFalse(saved['daily'][-1]['risk']['all_passed'])
   for change in (lambda r:r['daily'][-1]['risk'].update(risk_is_order_gate=0),lambda r:r.update(weights_normalized=0),lambda r:r['daily'][-1]['risk'].update(all_passed=True),lambda r:r['summary'].update(chained_twr=float((200+gain)/1000))):
    bad=deepcopy(saved);change(bad)
    with self.assertRaises(ValueError):m.inspect_saved_control(prepared_track=prepared(args),result=bad)

 def test_split_cancels_frozen_order_without_consuming_flow_as_fill(self):
  args=fixture('WHOLE_LOT')
  args['corporate_actions']=[dict(security_id='A',session='2026-04-01',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)]
  for key in ('opens','closes'):args[key].loc['2026-04-01':,'A']=5.
  args['external_flows']=[dict(session='2026-04-01',amount_usd=200.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))]
  saved=run(**args);out=m.inspect_saved_control(prepared_track=prepared(args),result=saved)
  self.assertEqual(out['terminal_cash_exact'],'1200');self.assertEqual(out['chained_twr_exact'],'0');self.assertEqual(saved['trades'],[])
  self.assertEqual(saved['executions'][0]['status'],'CANCELLED_SPLIT')
  for change in (lambda r:r['corporate_actions'][0].update(cancelled_plan=None),lambda r:r['executions'][0].update(status='FILLED'),lambda r:r['corporate_actions'][0]['applied_events'][0].update(post_shares=1)):
   bad=deepcopy(saved);change(bad)
   with self.assertRaises(ValueError):m.inspect_saved_control(prepared_track=prepared(args),result=bad)


if __name__=='__main__':unittest.main()
