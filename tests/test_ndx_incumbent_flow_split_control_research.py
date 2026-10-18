import unittest
from copy import deepcopy
import pandas as pd
from backtest.ndx_incumbent_flow_split_control_research import simulate_incumbent_flow_split_control as run


def fixture(track):
 days=['2026-03-31','2026-04-01','2026-04-02','2026-04-03'];p=pd.DataFrame(10.,index=pd.to_datetime(days),columns=list('ABCDEFGH'))
 targets={s:dict(ticker=s,issuer_id='I'+s,target_weight=.125+(5e-14 if s=='A' else 0)) for s in p.columns}
 return dict(track=track,closes=p,opens=p.copy(),schedule=[dict(decision_date=days[0],execution_date=days[1],targets=targets)],risk_chains_by_decision={days[0]:{s:'SAME_CHAIN' for s in p.columns}},corporate_actions=[],external_flows=[],initial_cash_usd=1000.,minimum_cash_buffer_usd=100.,valuation_end_date=days[-1],transaction_cost_bps=0.,max_single_weight=.1,min_single_weight=.05,top_weight_cap=.2,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.1)

class Tests(unittest.TestCase):
 def test_original_weights_not_normalized_and_risk_not_gate(self):
  for track in ('CONTINUOUS','WHOLE_LOT'):
   x=fixture(track);r=run(**x);self.assertEqual(r['original_targets'],x['schedule'][0]['targets']);self.assertFalse(r['weights_normalized']);self.assertFalse(r['daily'][-1]['risk']['all_passed']);self.assertTrue(r['trades'])
   target=(r['rebalances'][0]['effective_normalized_targets'] if track=='CONTINUOUS' else r['decisions'][0]['targets'])
   self.assertEqual(target,x['schedule'][0]['targets'])
 def test_both_tracks_split_flow_and_independent_state(self):
  for track in ('CONTINUOUS','WHOLE_LOT'):
   x=fixture(track);x['closes'].loc['2026-04-02':,'A']=5.;x['opens'].loc['2026-04-02':,'A']=5.;x['corporate_actions']=[dict(security_id='A',session='2026-04-02',new_shares=2,old_shares=1,source_url='https://example.com/split',evidence_sha256='b'*64)];x['external_flows']=[dict(session='2026-04-02',amount_usd=200.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='a'*64))];before=deepcopy(x);r=run(**x)
   self.assertAlmostEqual(r['summary']['chained_twr'],0.);self.assertEqual(r['summary']['total_cash_injection_usd'],200.);self.assertEqual(x['schedule'],before['schedule']);pd.testing.assert_frame_equal(x['opens'],before['opens'])
   clean=run(**fixture(track));self.assertEqual(clean['summary']['total_cash_injection_usd'],0.)
 def test_zero_slots_retained_without_risk_repair(self):
  x=fixture('WHOLE_LOT');x['opens']['H']=100000.;x['closes']['H']=100000.;r=run(**x)
  self.assertEqual(r['decisions'][0]['desired_shares']['H'],0);self.assertIn('H',r['daily'][-1]['risk']['zero_share_security_ids']);self.assertTrue(r['trades'])
 def test_string_index_matches_datetime_without_mutation(self):
  x=fixture('CONTINUOUS');expected=run(**x)
  x['closes'].index=x['closes'].index.strftime('%Y-%m-%d');x['opens'].index=x['opens'].index.strftime('%Y-%m-%d');before=x['closes'].copy();actual=run(**x)
  self.assertEqual(actual['daily'],expected['daily']);pd.testing.assert_frame_equal(x['closes'],before)
 def test_fixed_definition_and_missing_risk_rejected(self):
  x=fixture('CONTINUOUS');x['schedule'].append(deepcopy(x['schedule'][0]));x['schedule'][1].update(decision_date='2026-04-02',execution_date='2026-04-03');x['schedule'][1]['targets']['A']['target_weight']=.2
  with self.assertRaises(ValueError):run(**x)
  x=fixture('CONTINUOUS');x['risk_chains_by_decision'].clear()
  with self.assertRaises(ValueError):run(**x)

if __name__=='__main__':unittest.main()
