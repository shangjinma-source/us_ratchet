import unittest
from scripts.run_fixed_monthly_weak5_exit_20261023 import persistent_weak_target

class Weak5Tests(unittest.TestCase):
 def test_five_held_weak_closes_then_exit_latch_prevents_immediate_rebuy(self):
  plans={}
  for n in range(1,6):
   result,_=persistent_weak_target({'A':7},{'A':7},plans,True,{'A':{'on':False}},{'A':15})
   self.assertEqual(result['A'],0 if n==5 else 7)
  self.assertEqual(persistent_weak_target({'A':7},{},plans,True,{'A':{'on':False}},{'A':15})[0]['A'],0)
  self.assertEqual(persistent_weak_target({'A':15},{},plans,True,{'A':{'on':True}},{'A':15})[0]['A'],15)
  self.assertEqual(plans,{})
 def test_unheld_does_not_accumulate_removal_resets_and_no_missing_fill(self):
  plans={}
  for _ in range(6):persistent_weak_target({'A':7},{},plans,True,{'A':{'on':False}},{'A':15})
  self.assertEqual(plans['A']['count'],0)
  persistent_weak_target({}, {},plans,True,{},{});self.assertEqual(plans,{})
  with self.assertRaises(KeyError):persistent_weak_target({'A':7},{'A':7},plans,True,{}, {'A':15})

if __name__=='__main__':unittest.main()
