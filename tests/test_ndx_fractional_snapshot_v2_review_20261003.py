from copy import deepcopy
from pathlib import Path
import hashlib,unittest
import pandas as pd
from backtest import ndx_dynamic_fractional_flow_split_research_v2 as v2

class Review(unittest.TestCase):
 def test_two_opposite_splits_do_not_rewrite_either_historical_rebalance(self):
  days=['2026-03-31','2026-04-01','2026-04-02','2026-04-03'];prices=pd.DataFrame({'AAA':[10.,10.,5.,10.]},index=pd.to_datetime(days))
  target={'S':dict(ticker='AAA',issuer_id='I',target_weight=1.)}
  args=dict(closes=prices,opens=prices.copy(),schedule=[dict(decision_date=days[0],execution_date=days[1],targets=deepcopy(target)),dict(decision_date=days[1],execution_date=days[2],targets=deepcopy(target))],corporate_actions=[dict(security_id='S',session=days[2],new_shares=2,old_shares=1,source_url='https://example.com/a',evidence_sha256='a'*64),dict(security_id='S',session=days[3],new_shares=1,old_shares=2,source_url='https://example.com/b',evidence_sha256='b'*64)],external_flows=[dict(session=days[2],amount_usd=100.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='/synthetic/receipt',sha256='c'*64))],initial_cash_usd=100.,minimum_cash_buffer_usd=0.,transaction_cost_bps=0.,valuation_end_date=days[-1])
  out=v2.simulate_dynamic_fractional_flow_split_research(**args)
  self.assertAlmostEqual(out['rebalances'][0]['projection']['holdings']['S']['shares'],10.)
  self.assertAlmostEqual(out['rebalances'][1]['projection']['holdings']['S']['shares'],40.)
  self.assertAlmostEqual(out['daily'][-1]['holdings']['S']['shares'],20.)
  self.assertAlmostEqual(out['summary']['chained_twr'],0.)
  snapshots=deepcopy(out['rebalances']);out['daily'][-1]['holdings']['S']['shares']=999
  self.assertEqual(out['rebalances'],snapshots)
 def test_reverse_bytes_only_snapshot_and_schema(self):
  root=Path(v2.__file__).parent;original=(root/'ndx_dynamic_fractional_flow_split_research.py').read_bytes();new=Path(v2.__file__).read_bytes()
  self.assertEqual(hashlib.sha256(original).hexdigest(),'d33937157b7b3e4aa0d031962d1a0b0669eb7aa0ded7c1f8818b5d4348291687')
  self.assertEqual(new.count(b'projection=deepcopy(projection)))'),1)
  self.assertEqual(new.replace(b'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V2',b'DYNAMIC_FRACTIONAL_USD_FLOW_SPLIT_ACCOUNT_V1').replace(b'projection=deepcopy(projection)))',b'projection=projection))'),original)

if __name__=='__main__':unittest.main()
