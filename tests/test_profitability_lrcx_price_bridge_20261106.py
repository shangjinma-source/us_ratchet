import unittest,copy
from docs.candidates.profitability_lrcx_price_bridge_20261106 import series,OLD,NEW,SOURCE
class BridgeTests(unittest.TestCase):
 def fixture(self):return {'dated_identity_transitions':[dict(old_sid=OLD,new_sid=NEW,date='2024-10-03',share_ratio='10',identity_quote_binding_only=True,source_references=[SOURCE])],'ohlc':{OLD:{'2024-10-02':{'close':'100'}},NEW:{'2024-10-03':{'close':'10'}}}}
 def test_constant_value_coordinate(self):self.assertEqual(series(self.fixture(),OLD,['2024-10-02','2024-10-03'],0,{}),[100,100])
 def test_wrong_ratio(self):
  d=self.fixture();d['dated_identity_transitions'][0]['share_ratio']='9'
  with self.assertRaises(ValueError):series(d,OLD,['2024-10-02'],0,{})
 def test_missing_or_wrong_sid(self):
  with self.assertRaises(ValueError):series(self.fixture(),NEW,['2024-10-02'],0,{})
  with self.assertRaises(ValueError):series(self.fixture(),OLD,['2024-10-04'],0,{})
if __name__=='__main__':unittest.main()
