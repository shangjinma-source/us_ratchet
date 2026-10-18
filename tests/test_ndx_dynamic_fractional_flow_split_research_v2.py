"""V2 snapshot repair only; frozen V1 ledger/trade numerics remain unchanged."""
import hashlib,unittest
from pathlib import Path
from copy import deepcopy
from backtest import ndx_dynamic_fractional_flow_split_research as old
from backtest import ndx_dynamic_fractional_flow_split_research_v2 as new
from test_ndx_dynamic_fractional_flow_split_research import fixture,flow,split

class Tests(unittest.TestCase):
 def test_saved_projection_does_not_follow_future_split(self):
  a=fixture();a['transaction_cost_bps']=10.;a['opens'].iloc[2:,0]=5.;a['closes'].iloc[2:,0]=5.;a['external_flows']=[flow()];a['corporate_actions']=[split()];before=deepcopy(a)
  prior=old.simulate_dynamic_fractional_flow_split_research(**a);fixed=new.simulate_dynamic_fractional_flow_split_research(**a)
  p=prior['rebalances'][0];f=fixed['rebalances'][0]
  self.assertAlmostEqual(p['projection']['holdings']['SID']['shares'],2*p['holdings_after']['SID']['shares'])
  self.assertEqual(f['projection']['holdings'],f['holdings_after']);self.assertIsNot(f['projection']['holdings'],f['holdings_after'])
  for key in ('daily','trades','summary','corporate_actions','external_flows'):self.assertEqual(fixed[key],prior[key])
  for key in f:
   if key!='projection':self.assertEqual(f[key],p[key])
  self.assertEqual(fixed['schema'],'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2');self.assertEqual(a['schedule'],before['schedule'])
 def test_later_state_mutation_cannot_change_historical_projection(self):
  a=fixture();a['corporate_actions']=[split()];a['opens'].iloc[2:,0]=5.;a['closes'].iloc[2:,0]=5.;r=new.simulate_dynamic_fractional_flow_split_research(**a);snap=deepcopy(r['rebalances'][0]['projection']);r['daily'][-1]['holdings']['SID']['shares']=1000.;r['rebalances'][0]['holdings_after']['SID']['shares']=2000.
  self.assertEqual(r['rebalances'][0]['projection'],snap)
 def test_only_declared_two_source_changes_and_frozen_original(self):
  src=Path(old.__file__).read_bytes();self.assertEqual(hashlib.sha256(src).hexdigest(),'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687')
  restored=Path(new.__file__).read_bytes().replace(b'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2',b'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V1').replace(b'projection=deepcopy(projection)))',b'projection=projection))');self.assertEqual(restored,src)

if __name__=='__main__':unittest.main()
