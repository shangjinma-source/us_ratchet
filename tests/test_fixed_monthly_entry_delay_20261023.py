import unittest
from scripts.run_fixed_monthly_entry_delay_20261023 import delayed_target

class EntryDelayTests(unittest.TestCase):
 def test_only_incremental_buys_blocked_and_sell_target_unchanged(self):
  target,blocked=delayed_target({'A':20,'B':6},{'A':14,'B':14},{'A':{'close':'120','sma20':'100'},'B':{'close':'120','sma20':'100'}},'11/10')
  self.assertEqual(target,{'A':14,'B':6});self.assertEqual(blocked,['A'])
 def test_equality_is_admitted_and_wait_releases_when_price_cools(self):
  self.assertEqual(delayed_target({'A':20},{'A':14},{'A':{'close':'110','sma20':'100'}},'11/10'),({'A':20},[]))
  self.assertEqual(delayed_target({'A':20},{},{'A':{'close':'120','sma20':'100'}},None),({'A':20},[]))

if __name__=='__main__':unittest.main()
