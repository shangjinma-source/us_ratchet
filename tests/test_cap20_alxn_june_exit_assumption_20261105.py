import unittest
from docs.candidates.cap20_alxn_june_exit_assumption_20261105 import *
class Tests(unittest.TestCase):
 def fixture(self):return dict(decision_date=START,through=MONTH_END,missing_action_streams=[SID],unmapped_events=[],admitted=False,exposure_end_by_security={SID:END})
 def apply(self,g,**changes):
  kwargs=dict(window='2021_2023',arguments={'decision_date':START,'account_state':{'shares':{SID:24}}},selected={'target_quantities':{}},active=END,until=MONTH_END);kwargs.update(changes);return apply_gate(g,**kwargs)
 def test_exact_exit_only(self):
  g=self.fixture();r=self.apply(g);self.assertTrue(r['admitted']);self.assertEqual(r['original_gate_rejection_preserved'],g);self.assertFalse(g['admitted'])
 def test_positive_target_wrong_active_or_holding_refused(self):
  for k,v in [('selected',{'target_quantities':{SID:1}}),('active','2021-06-02'),('arguments',{'decision_date':START,'account_state':{'shares':{SID:23}}})]:
   g=self.fixture();self.assertEqual(self.apply(g,**{k:v}),g)
 def test_unmapped_and_other_missing_not_removed(self):
  g=self.fixture();g['unmapped_events']=[{'security_id':SID}];self.assertFalse(self.apply(g)['admitted']);self.assertEqual(self.apply(g)['unmapped_events'],g['unmapped_events'])
  g=self.fixture();g['missing_action_streams'].append('other');self.assertFalse(self.apply(g)['admitted'])
 def test_exit_is_checked_before_further_june_but_not_july(self):
  assert_exit([{'date':END,'shares':{SID:0}},{'date':'2021-07-01','shares':{SID:10}}])
  for date in [END,MONTH_END]:
   with self.assertRaises(ValueError):assert_exit([{'date':date,'shares':{SID:1}}])
if __name__=='__main__':unittest.main()
