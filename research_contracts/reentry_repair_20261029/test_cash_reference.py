import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
from reference_coverage import ReferenceCoverage
class CashReferenceTests(unittest.TestCase):
 def test_exact_event_and_negative_variants(self):
  event=dict(kind='dividends',date='2024-03-18',source='synthetic',source_sha256='a'*64,provider_event={'amount':.04})
  row=dict(status='REVIEWED_REFERENCE_ONLY_ORDINARY_CASH_DIVIDEND',security_id='S',ex_date=event['date'],observed_provider_events=[deepcopy(event)],reference_price_adjustment='NONE_NOMINAL_CLOSE_RULE',cash_credit_authorized=False)
  doc={'assembled':dict(actions=[],session_dates=['2024-03-15','2024-03-18'],close_prices={'S':{'2024-03-18':'8'}},source_hashes={}), 'dividend_events':[]}
  def run(e,r):
   review={'rows':[r],'source_hashes':{}}
   c=ReferenceCoverage(window='2021_2023',document=doc,prices={},review={},source_validator=lambda:None,reference_cash_review=review,root=Path.cwd())
   with patch('scripts.run_recent_continuous_probe.exposed_action_blockers',return_value={'unmapped_events':[e],'missing_action_streams':[]}):return c({'security_id':'S','exit_date':'2024-03-15'},'2024-03-18',{'S'})
  self.assertEqual(run(event,row)['status'],'VERIFIED')
  for field,value in [('source_sha256','b'*64),('kind','splits'),('provider_event',{'amount':.4})]:
   changed=deepcopy(event);changed[field]=value
   with self.assertRaisesRegex(ValueError,'COVERAGE_BLOCKED'):run(changed,row)
  for field,value in [('cash_credit_authorized',True),('reference_price_adjustment','ADJUSTED')]:
   changed=deepcopy(row);changed[field]=value
   with self.assertRaisesRegex(ValueError,'COVERAGE_BLOCKED'):run(event,changed)
 def test_source_bytes_change_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source';p.write_bytes(b'original');h=sha256(p.read_bytes()).hexdigest();p.write_bytes(b'changed')
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):ReferenceCoverage(window='2021_2023',document={},prices={},review={},source_validator=lambda:None,reference_cash_review={'source_hashes':{'source':h},'rows':[]},root=d)
if __name__=='__main__':unittest.main()
