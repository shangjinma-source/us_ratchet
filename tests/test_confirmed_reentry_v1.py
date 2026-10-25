import unittest
from backtest.confirmed_reentry_v1 import confirmed_reentry_target as apply
class ReentryTests(unittest.TestCase):
 def test_exit_and_three_confirmations_with_reset(self):
  plans={}
  def step(on,held=5):return apply({'S':10 if on else 5},{'S':held},plans,True,{'S':{'on':on}},{'S':10})[0]['S']
  self.assertEqual([step(False) for _ in range(5)],[5,5,5,5,0])
  self.assertEqual(step(True,0),0);self.assertEqual(step(True,0),0)
  self.assertEqual(step(False,0),0)
  self.assertEqual([step(True,0) for _ in range(3)],[0,0,10]);self.assertEqual(plans,{})
 def test_no_exit_no_delay_and_removed_selection(self):
  plans={};self.assertEqual(apply({'S':10},{},plans,True,{'S':{'on':True}},{'S':10})[0],{'S':10})
  plans['OLD']={'count':5,'exited':True,'confirmations':1}
  apply({}, {},plans,True,{},{});self.assertEqual(plans,{})
 def test_off_without_holdings_does_not_trigger_exit(self):
  plans={}
  for _ in range(10):self.assertEqual(apply({'S':5},{},plans,True,{'S':{'on':False}},{'S':10})[0]['S'],5)
  self.assertFalse(plans['S']['exited'])
if __name__=='__main__':unittest.main()
