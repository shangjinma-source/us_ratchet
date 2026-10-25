import unittest
from scripts.run_fixed_monthly_staged_entry_20261023 import staged_target

class StagedEntryTests(unittest.TestCase):
 def test_three_tranches_preserve_integer_total_and_immediate_reduction(self):
  plans={};held=0;parts=[]
  for _ in range(3):
   target,_=staged_target({'A':14},{'A':held},plans,3,'month');parts.append(target['A']-held);held=target['A']
  self.assertEqual(parts,[5,5,4]);self.assertEqual(held,14)
  self.assertEqual(staged_target({'A':6},{'A':14},plans,3,'month'),({'A':6},[]))
 def test_no_cash_does_not_invent_fill_and_new_goal_resets(self):
  plans={}
  self.assertEqual(staged_target({'A':15},{},plans,3,'month')[0],{'A':5})
  self.assertEqual(staged_target({'A':15},{},plans,3,'month')[0],{'A':8})
  self.assertEqual(staged_target({'A':15},{},plans,3,'month')[0],{'A':15})
  self.assertEqual(staged_target({'A':30},{'A':15},plans,3,'month')[0],{'A':20})
 def test_removed_target_clears_plan_and_no_delay_matches_target(self):
  plans={'A':{'key':('month',10),'remaining':2}}
  self.assertEqual(staged_target({}, {'A':10},plans,5,'month'),({},[]));self.assertEqual(plans,{})
  self.assertEqual(staged_target({'A':20},{'A':14},plans,1,'month'),({'A':20},[]))

if __name__=='__main__':unittest.main()
