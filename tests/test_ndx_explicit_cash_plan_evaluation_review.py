"""Independent bounded synthetic explicit-plan review."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_ndx_explicit_cash_plan_evaluation_research as f
m=f.module
class Review(unittest.TestCase):
 def test_fee_cash_buffer_and_old_holdings_independently(self):
  inputs=f.fixture();inputs['starting_cash_usd']='0';inputs['cash_event']['amount_usd']='20';inputs['minimum_cash_buffer_usd']='0'
  result=m.evaluate_explicit_plans(evaluation_inputs=inputs,plans_by_branch={'first':[{'A':2}],'second':[{'B':0}]})
  row=result['branches'][0]['evaluated_plans'][0]
  self.assertEqual(Fraction(row['fees_usd']),Fraction(1,50))
  self.assertEqual(Fraction(row['cash_after_usd']),Fraction(-1,50))
  self.assertEqual(Fraction(row['equity_after_usd']),Fraction(20999,50))
  self.assertEqual(Fraction(row['cash_flow_adjusted_pnl_usd']),Fraction(-1,50))
  self.assertFalse(row['feasible']);self.assertFalse(row['financial_checks']['NONNEGATIVE_CASH'])
  self.assertEqual(row['proposed_holdings'],dict(A=12,B=10,C=10,D=10))
 def test_issuer_conflict_and_no_search_global_suffix(self):
  inputs=f.fixture();inputs['securities']['B']['issuer_id']='A';inputs['max_evaluations']=1
  plans={'first':[{'A':1},{'A':2}],'second':[{'B':1}]};before=deepcopy((inputs,plans))
  with patch.object(m.kernel,'evaluate_branches',wraps=m.kernel.evaluate_branches) as called:
   r=m.evaluate_explicit_plans(evaluation_inputs=inputs,plans_by_branch=plans)
   self.assertEqual(called.call_count,1);self.assertEqual(called.call_args.kwargs['max_evaluations'],0)
  self.assertEqual((inputs,plans),before);self.assertEqual(r['unevaluated_supplied_plan_count'],2)
  self.assertFalse(r['branches'][0]['evaluated_plans'][0]['issuer_unique'])
  self.assertEqual(r['branches'][1]['evaluated_plans'],[])
  self.assertFalse(r['full_integer_space_infeasibility_claimed'])
 def test_suffix_duplicate_float_bool_rejected_with_zero_budget(self):
  for invalid in ([{'B':1},{'B':1}],[{'B':True}],[{'B':1.0}],[{'B':2}],[{}]):
   inputs=f.fixture();inputs['max_evaluations']=0
   with self.subTest(invalid=invalid),self.assertRaises(ValueError):m.evaluate_explicit_plans(evaluation_inputs=inputs,plans_by_branch={'first':[],'second':invalid})
 def test_long_money_hostile_context_same_full_result(self):
  inputs=f.fixture();inputs['execution_prices']['A']='10.123456789012345678901234567890123456';plans={'first':[{'A':1}],'second':[]}
  expected=m.evaluate_explicit_plans(evaluation_inputs=inputs,plans_by_branch=plans)
  with localcontext() as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
   self.assertEqual(m.evaluate_explicit_plans(evaluation_inputs=inputs,plans_by_branch=plans),expected)
if __name__=='__main__':unittest.main()
