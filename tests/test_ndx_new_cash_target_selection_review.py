"""Independent small synthetic target-plan selection tests."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_ndx_new_cash_target_selection_research as f
m=f.module
class Review(unittest.TestCase):
 def test_long_saved_decimal_targets_and_prices_hostile_context(self):
  inputs,targets=f.fixture();targets['lane']['A']='0.25000000000000002';inputs['execution_prices']['A']='10.123456789123456789'
  expected=m.select_target_plans(evaluation_inputs=inputs,target_weights_by_branch=targets)
  with localcontext() as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
   self.assertEqual(m.select_target_plans(evaluation_inputs=inputs,target_weights_by_branch=targets),expected)
 def test_independent_exact_scores_and_single_evaluator_call(self):
  inputs,targets=f.fixture();targets={'lane':{'A':'1'}};before=deepcopy((inputs,targets))
  with patch.object(m.kernel,'evaluate_branches',wraps=m.kernel.evaluate_branches) as evaluator:
   result=m.select_target_plans(evaluation_inputs=inputs,target_weights_by_branch=targets)
   self.assertEqual(evaluator.call_count,1)
  self.assertEqual((inputs,targets),before)
  scores=result['selections'][0]['feasible_candidate_scores']
  self.assertEqual([f.fraction(s['target_l1_distance']) for s in scores],[Fraction(3,2),Fraction(60,41),Fraction(10,7)])
  self.assertFalse(result['economic_winner_selected']);self.assertFalse(result['target_provenance_verified'])
 def test_global_budget_retains_unevaluated_second_branch(self):
  inputs,targets=f.fixture();inputs['branches'].append({'branch_id':'second','buy_limits':{'B':2}});targets['second']=dict(targets['lane']);inputs['max_evaluations']=1
  result=m.select_target_plans(evaluation_inputs=inputs,target_weights_by_branch=targets)
  self.assertEqual(result['evaluation']['candidate_count'],6)
  self.assertEqual(result['selections'][0]['unevaluated_count'],2)
  self.assertEqual(result['selections'][1]['unevaluated_count'],3)
  self.assertIsNone(result['selections'][1]['selected'])
  self.assertFalse(result['full_integer_space_infeasibility_claimed'])
 def test_gate_and_coverage_tampering_rejected(self):
  inputs,targets=f.fixture();base=m.kernel.evaluate_branches(**inputs)
  for attack in ('boolrank','boolgate','remaining','issuer'):
   value=deepcopy(base);branch=value['branches'][0];row=branch['candidates'][0]
   if attack=='boolrank':row['rank']=False
   elif attack=='boolgate':row['financial_checks']['CASH_BUFFER']=1
   elif attack=='remaining':branch['unevaluated_count']=1
   else:row['issuer_conflicts']=[['A','B']]
   with self.subTest(attack=attack),patch.object(m.kernel,'evaluate_branches',return_value=value),self.assertRaises(ValueError):m.select_target_plans(evaluation_inputs=inputs,target_weights_by_branch=targets)
if __name__=='__main__':unittest.main()
