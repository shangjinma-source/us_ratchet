import json
import unittest
from copy import deepcopy
from pathlib import Path
from docs.candidates.momentum_split_admission_20261105 import FixedSplitAdmission,ROOT

class FixedSplitTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.adapter=FixedSplitAdmission()
  cls.docs={w:json.loads((ROOT/'tmp'/n/'execution_inputs.json').read_bytes()) for w,n in [('2021_2023','recent_continuous_baseline_20261026_v7'),('2024_2026','old_continuous_baseline_20261026_v9')]}
  cls.review=json.loads((ROOT/'tmp/momentum_inventory_recheck_20261105/review.json').read_bytes())
 def test_real_pairs_and_no_double_split_or_quote_mutation(self):
  for w,d in self.docs.items():
   before=deepcopy(d);new=self.adapter.install(d,w);self.assertEqual(d,before);self.assertEqual(new['ohlc'],d['ohlc'])
   self.assertEqual(new,self.adapter.install(new,w));self.assertEqual(len(new['assembled']['actions']),2 if w=='2021_2023' else 4)
   self.assertEqual(new['assembled']['actions'],new['assembled']['provider_actions'])
 def test_real_gates_only_fixed_events_removed(self):
  installed={w:self.adapter.install(d,w) for w,d in self.docs.items()};seen=set()
  for row in self.review['rows']:
   gate=self.adapter.admit(row['gate'],installed[row['window']],row['window'])
   for mapped in gate['mapped_fixed_splits']:seen.add((mapped['execution_event']['security_id'],mapped['execution_event']['date']))
   self.assertFalse(any(e['kind'] in ('splits','IDENTITY_CONVERSION') for e in gate['unmapped_events']))
   if any(e.get('kind')=='CASH_MERGER' for e in row['gate']['unmapped_events']):self.assertFalse(gate['admitted'])
  self.assertEqual(len(seen),6)
 def test_tampered_ratio_unknown_and_unpaired_rejected(self):
  w='2024_2026';d=self.adapter.install(self.docs[w],w)
  source=next(r['gate'] for r in self.review['rows'] if r['window']==w and any(e.get('kind')=='splits' for e in r['gate']['unmapped_events']))
  g=deepcopy(source);event=next(e for e in g['unmapped_events'] if e['kind']=='splits');event['provider_payload']['numerator']='999'
  result=self.adapter.admit(g,d,w);self.assertIn(event,result['unmapped_events']);self.assertFalse(result['admitted'])
  broken=deepcopy(d);broken['assembled']['provider_actions']=[]
  with self.assertRaisesRegex(ValueError,'PAIR_REQUIRED'):self.adapter.admit(source,broken,w)
  broken=deepcopy(d);broken['assembled']['actions'].append(deepcopy(broken['assembled']['actions'][0]))
  with self.assertRaises(ValueError):self.adapter.install(broken,w)
  broken=deepcopy(d);broken['ohlc']['security:0001045810:67066G104']['2024-06-10']['close']='1'
  with self.assertRaisesRegex(ValueError,'NOMINAL_QUOTE_CHANGED'):self.adapter.install(broken,w)

if __name__=='__main__':unittest.main()
