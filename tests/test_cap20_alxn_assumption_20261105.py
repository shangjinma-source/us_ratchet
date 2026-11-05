import unittest
from docs.candidates.cap20_alxn_may_assumption_20261105 import apply_gate,SID,START,END
class Tests(unittest.TestCase):
 def gate(self):return dict(decision_date=START,through=END,missing_action_streams=[SID],unmapped_events=[],admitted=False,exposure_end_by_security={SID:END})
 def test_only_missing_stream_conditional_and_original_kept(self):
  g=self.gate();r=apply_gate(g,window='2021_2023',arguments={'decision_date':START},until=END);self.assertTrue(r['admitted']);self.assertFalse(r['conditional_assumptions'][0]['absence_proven']);self.assertEqual(r['original_gate_rejection_preserved'],g);self.assertFalse(g['admitted'])
 def test_unmapped_or_other_missing_remains_rejected(self):
  for field,value in [('unmapped_events',[{'security_id':SID,'kind':'dividends'}]),('missing_action_streams',[SID,'OTHER'])]:
   g=self.gate();g[field]=value;r=apply_gate(g,window='2021_2023',arguments={'decision_date':START},until=END);self.assertFalse(r['admitted']);self.assertEqual(r['unmapped_events'],g['unmapped_events'])
 def test_no_extension_or_wrong_sid(self):
  g=self.gate();self.assertEqual(apply_gate(g,window='2021_2023',arguments={'decision_date':START},until='2021-06-30'),g)
  g['missing_action_streams']=['OTHER'];self.assertEqual(apply_gate(g,window='2021_2023',arguments={'decision_date':START},until=END),g)
if __name__=='__main__':unittest.main()
