import unittest
from fractions import Fraction as F
from docs.candidates.profitability_smci_price_bridge_20261106 import OLD,NEW,old_share_series,load_bridge
class SmciBridge(unittest.TestCase):
 def test_constant_economic_value_no_false_split_loss(self):
  prices={OLD:{'2024-09-30':{'close':'100'}},NEW:{'2024-10-01':{'close':'10'}}}
  self.assertEqual(old_share_series(OLD,['2024-09-30','2024-10-01'],0,prices),[F(100),F(100)])
 def test_exact_scope_and_missing_reject(self):
  for sid,dates in [(NEW,['2024-09-30']), (OLD,['2024-09-29']), (OLD,['2024-09-30'])]:
   with self.subTest(sid=sid,dates=dates),self.assertRaises(ValueError):old_share_series(sid,dates,0,{})
 def test_real_pinned_transition_nominal_units(self):
  pins={};prices=load_bridge(pins);values=old_share_series(OLD,['2024-09-30','2024-10-01'],0,prices)
  self.assertEqual(values[0],F('1040999984741211/2500000000000'));self.assertEqual(values[1],10*F(prices[NEW]['2024-10-01']['close']));self.assertGreater(values[1]/values[0],F(1,2))
if __name__=='__main__':unittest.main()
