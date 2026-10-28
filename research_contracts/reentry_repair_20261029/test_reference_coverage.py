import unittest
from copy import deepcopy
from reference_coverage import ReferenceCoverage
class CoverageTests(unittest.TestCase):
 def setup(self,ticker='XYZ'):
  domain=dict(actions=[],session_dates=['2024-03-15','2024-03-18','2024-03-19'],close_prices={'S':{'2024-03-18':'8','2024-03-19':'9'}},source_hashes={'synthetic':'0'*64})
  doc=dict(assembled=domain,prepared_input_candidate={'metadata':{'S':{'ticker':ticker}},'source_provenance':{'S':{'segments':[{'source_path':'synthetic','start':'2024-03-15','end':'2024-03-19'}]}}},provider_event_inventory=[],action_stream_missing=[],dated_identity_transitions=[],prior_distribution_events=[],dividend_events=[])
  return doc
 def invoke(self,doc):return ReferenceCoverage(window='2024_2026',document=doc,prices={},review={'rows':[]},source_validator=lambda:None)({'security_id':'S','exit_date':'2024-03-15','reference_price':'10'},'2024-03-19',{'S'})
 def test_actual_gate_absence_then_missing_stream(self):
  d=self.setup();self.assertEqual(self.invoke(d)['status'],'VERIFIED')
  d['action_stream_missing']=[{'ticker':'XYZ','source':'synthetic'}]
  with self.assertRaisesRegex(ValueError,'COVERAGE_BLOCKED'):self.invoke(d)
 def test_known_merger_and_distribution(self):
  with self.assertRaisesRegex(ValueError,'COVERAGE_BLOCKED'):self.invoke(self.setup('SPLK'))
  d=self.setup();d['prior_distribution_events']=[{'parent_sid':'S','effective_date':'2024-03-18','timing':'AFTER_CLOSE'}]
  with self.assertRaisesRegex(ValueError,'COVERAGE_BLOCKED'):self.invoke(d)
 def test_missing_middle_close(self):
  d=self.setup();del d['assembled']['close_prices']['S']['2024-03-18']
  with self.assertRaisesRegex(ValueError,'PRICE_MISSING'):self.invoke(d)
 def test_unreviewed_successor(self):
  d=self.setup();d['dated_identity_transitions']=[{'old_sid':'S','new_sid':'N','date':'2024-03-18'}]
  c=ReferenceCoverage(window='2024_2026',document=d,prices={},review={'rows':[]},source_validator=lambda:None)
  with self.assertRaisesRegex(ValueError,'UNREVIEWED_SUCCESSOR'):c({'security_id':'S','exit_date':'2024-03-15','reference_price':'10'},'2024-03-19',{'N'})
if __name__=='__main__':unittest.main()
