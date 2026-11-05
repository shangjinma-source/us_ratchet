"""No economic search: exact action merge and parent-binding fixtures."""
import unittest
from copy import deepcopy
from scripts.research.run_downside_cap20_account_20261105 import append_pairs
class MergeTests(unittest.TestCase):
 def fixture(self):
  observations=[dict(ticker='TEST',kind='dividends',date='2024-01-04',source=s) for s in ['b','a']]
  event=dict(event_id='original',security_id='sid',ex_date='2024-01-04',payment_date='2024-01-19',currency='USD',amount_per_share='43/200',withholding_rate='0')
  row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',**{k:v for k,v in event.items() if k!='event_id'},observed_provider_events=list(reversed(observations)))
  document=dict(provider_event_inventory=observations,prepared_input_candidate=dict(metadata={'sid':dict(ticker='TEST')}),dividend_events=[event])
  artifact=dict(review_rows=[row],dividend_events=[dict(event,event_id='different-evidence-id')],source_hashes={})
  review=dict(rows=[deepcopy(row)],source_hashes={})
  return document,review,artifact
 def test_exact_same_terms_different_evidence_id_keeps_one_financial_event(self):
  d,r,a=self.fixture();result=append_pairs(d,r,a);self.assertEqual(len(d['dividend_events']),1);self.assertEqual(result['added'],[]);self.assertEqual(a['review_rows'][0]['observed_provider_events'][0]['source'],'a')
 def test_conflicting_payment_or_nominal_amount_rejected(self):
  for field,value in [('payment_date','2024-01-22'),('amount_per_share','1/5')]:
   d,r,a=self.fixture();a['dividend_events'][0][field]=value
   with self.assertRaises(ValueError):append_pairs(d,r,a)
 def test_duplicate_provider_observation_not_ignored(self):
  d,r,a=self.fixture();a['review_rows'][0]['observed_provider_events'].append(deepcopy(a['review_rows'][0]['observed_provider_events'][0]))
  with self.assertRaises(ValueError):append_pairs(d,r,a)
 def test_existing_cash_event_without_review_rejected(self):
  d,r,a=self.fixture();r['rows']=[]
  with self.assertRaises(ValueError):append_pairs(d,r,a)
if __name__=='__main__':unittest.main()
