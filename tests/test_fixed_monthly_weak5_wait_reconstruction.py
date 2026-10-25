from copy import deepcopy
from unittest.mock import patch
import unittest
from scripts.run_fixed_monthly_weak5_exit_20261023_v2 import advance_wait_only

class WaitReconstructionTests(unittest.TestCase):
 def test_fifth_weak_observation_still_cannot_trade_in_action_wait(self):
  row=dict(status='READY',action='WAIT_POST_ACTION_MARK',orders=[],target_shares={'A':14})
  plans={'A':dict(count=4,exited=False)}
  risk=dict(target_quantities={'A':7},diagnostics={'A':{'on':False}})
  resolver=lambda **kw:dict(histories={'A':dict(closes=[dict(close='100')])})
  events=[dict(date='2026-01-02',parent_sid='OTHER',post_parent_sid='OTHER',child_sid='CHILD')]
  with patch('scripts.run_fixed_monthly_weak5_exit_20261023_v2.partial_sma20_target',return_value=risk):
   result,_=advance_wait_only(row,{'A':7},plans,'2026-01-02',resolver,'2025-12-31',events,{'A':{'2026-01-02':'100'}})
  self.assertEqual(result,row);self.assertIsNot(result,row);self.assertEqual(result['orders'],[])
  self.assertTrue(plans['A']['exited'])
  events[0]['parent_sid']='A'
  with self.assertRaisesRegex(ValueError,'AFFECTED'):
   advance_wait_only(row,{'A':7},plans,'2026-01-02',resolver,'2025-12-31',events,{'A':{'2026-01-02':'100'}})
 def test_wait_with_order_and_missing_evidence_rejected(self):
  row=dict(status='READY',action='WAIT_POST_ACTION_MARK',orders=[{}],target_shares={'A':14})
  with self.assertRaisesRegex(ValueError,'EMPTY_ACTION_WAIT'):
   advance_wait_only(row,{}, {},'2026-01-02',None,None,[],{})
  row['orders']=[]
  with self.assertRaisesRegex(ValueError,'EVIDENCE_REQUIRED'):
   advance_wait_only(row,{}, {},'2026-01-02',None,None,[],{})

if __name__=='__main__':unittest.main()
