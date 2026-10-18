from copy import deepcopy
import unittest
from backtest import ndx_incumbent_flow_split_control_research as c
from test_ndx_incumbent_flow_split_control_research import fixture

class Review(unittest.TestCase):
 def test_explicit_analytic_stock_gain_cash_injection_and_observed_risk(self):
  for track,stock_gain in [('CONTINUOUS',22.5),('WHOLE_LOT',22.)]:
   with self.subTest(track=track):
    args=fixture(track)
    for target in args['schedule'][0]['targets'].values():target['target_weight']=.125
    args['closes'].loc['2026-04-02':,'A']=6.;args['opens'].loc['2026-04-02':,'A']=6.
    args['corporate_actions']=[dict(security_id='A',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)]
    args['external_flows']=[dict(session='2026-04-02',amount_usd=200.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))]
    result=c.simulate_incumbent_flow_split_control(**args)
    self.assertAlmostEqual(result['summary']['chained_twr'],stock_gain/1000)
    self.assertAlmostEqual(result['daily'][-1]['close_equity_usd' if track=='CONTINUOUS' else 'total_value_usd'],1200+stock_gain)
    self.assertFalse(result['daily'][-1]['risk']['all_passed'])
    self.assertFalse(result['daily'][-1]['risk']['risk_is_order_gate'])
    self.assertFalse(result['weights_normalized'])
 def test_private_control_binding_never_mutates_candidate_helpers_even_on_failure(self):
  before=[c.fractional.identity._normalise_schedule,c.whole.identity._normalise_schedule,c.whole.repair._risk_snapshot,c.whole.projector.project_whole_lot_rebalance]
  for track in ('CONTINUOUS','WHOLE_LOT'):
   args=fixture(track);original=deepcopy(args['schedule'])
   c.simulate_incumbent_flow_split_control(**args)
   self.assertEqual(args['schedule'],original)
   args['external_flows']=[dict(session='2026-04-02',amount_usd=-1,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))]
   with self.assertRaises(ValueError):c.simulate_incumbent_flow_split_control(**args)
  after=[c.fractional.identity._normalise_schedule,c.whole.identity._normalise_schedule,c.whole.repair._risk_snapshot,c.whole.projector.project_whole_lot_rebalance]
  for left,right in zip(before,after):self.assertIs(left,right)

if __name__=='__main__':unittest.main()

