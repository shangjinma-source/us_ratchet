import unittest
from scripts import ndx_saved_network_diagnostic_independent_readback_20261003 as m

class SourceRoleReview(unittest.TestCase):
 def test_saved_qqq_response_cannot_be_assigned_to_spy(self):
  raw=b"/*<script>location.href='//sina.com';</script>*/\nvar _=QQQ_day([]);"
  with self.assertRaisesRegex(ValueError,'JSON array wrapper'):
   m.inspect('SPY',raw,b'',{})
 def test_false_does_not_equal_zero(self):
  with self.assertRaises(ValueError):m.exact({'fresh_observation':False},{'fresh_observation':0})

if __name__=='__main__':unittest.main()
