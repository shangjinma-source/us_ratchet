from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import Mock
import unittest
import test_ndx_standard_cash_controls_research_20261002 as owner
from scripts import ndx_standard_cash_controls_research_20261002 as subject
from backtest.ndx_target_cash_neighbors_research import generate_target_neighbors
from backtest.ndx_explicit_cash_plan_evaluation_research import evaluate_explicit_plans

class IndependentControlsReview(unittest.TestCase):
 def test_cash_same_issuer_two_classes_remain_distinct_and_failed(self):
  row=owner.fixture(True)
  row['securities']['B']['issuer_id']='A'
  before=deepcopy(row); generator=Mock(side_effect=AssertionError('unexpected generator'))
  result=subject.research_row(row,generator,evaluate_explicit_plans)
  plan=result['evaluation']['branches'][0]['evaluated_plans'][0]
  self.assertEqual(plan['proposed_holdings'],before['holdings'])
  self.assertEqual(plan['issuer_conflicts'],{'A':['A','B']})
  self.assertFalse(plan['feasible']); self.assertEqual(plan['buy_shares'],{})
  self.assertEqual(plan['cash_after_usd'],'2000'); self.assertEqual(plan['fees_usd'],'0')
  self.assertIsNone(result['selected_supplied_plan_index']); self.assertEqual(result['feasible_scores'],[])
  self.assertEqual(result['input_row'],before); self.assertEqual(row,before); generator.assert_not_called()
  row['holdings']={'A':4}; row['execution_prices']={'A':'10'}; row['securities']={'A':{'issuer_id':'A','risk_chain':'A'}}
  result=subject.research_row(row,generator,evaluate_explicit_plans)
  gates=result['evaluation']['branches'][0]['evaluated_plans'][0]['risk']['checks']
  self.assertFalse(gates['MAX_SINGLE_WEIGHT']); self.assertFalse(gates['SECURITY_TOP3_WEIGHT'])

 def test_missing_target_old_position_full_l1_and_fee_index_tiebreak(self):
  row=owner.fixture(); row['holdings']['E']=1; row['execution_prices']['E']='10'
  row['securities']['E']={'issuer_id':'E','risk_chain':'E'}
  result=subject.research_row(row,generate_target_neighbors,evaluate_explicit_plans)
  candidates=[]
  for plan in result['evaluation']['branches'][0]['evaluated_plans']:
   self.assertEqual(plan['proposed_holdings']['E'],1)
   self.assertNotIn('E',plan['buy_shares'])
   if plan['feasible']:
    value={s:q*F(row['execution_prices'][s]) for s,q in plan['proposed_holdings'].items()}
    total=sum(value.values()); distance=sum(abs(v/total-(F(1,4) if s in 'ABCD' else 0)) for s,v in value.items())
    candidates.append((distance,F(plan['fees_usd']),plan['supplied_plan_index']))
  self.assertTrue(candidates)
  reported=[(F(int(s['target_l1_distance']['numerator']),int(s['target_l1_distance']['denominator'])),F(int(s['fee_usd']['numerator']),int(s['fee_usd']['denominator'])),s['supplied_plan_index']) for s in result['feasible_scores']]
  self.assertEqual(reported,candidates)
  self.assertEqual(result['selected_supplied_plan_index'],min(candidates)[2])
  self.assertFalse(result['global_optimality_claimed']); self.assertFalse(result['time_series_return_evaluated'])

 def test_coordinate_and_budget_closure(self):
  doc=owner.document()
  for mutate in (lambda d:d.update(scenario_count=True),lambda d:d.update(orders_executed=True),lambda d:d['rows'][0]['cash_event'].update(amount_usd='1001'),lambda d:d['rows'][-1].update(branch_role='MIGRATION_CONTROL')):
   bad=deepcopy(doc);mutate(bad)
   with self.assertRaises(ValueError): subject.control_rows(bad)
  row=owner.fixture()
  evaluator=Mock(side_effect=AssertionError('must reject before evaluation'))
  for count,plans in ((False,[{}]),(1,[{}]),(0,[{}]*258)):
   with self.assertRaises(ValueError): subject.research_row(row,Mock(return_value={'ungenerated_count':count,'plans':plans}),evaluator)
  evaluator.assert_not_called()

if __name__=='__main__':unittest.main()
