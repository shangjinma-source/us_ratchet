"""Independent synthetic first-period input metadata review."""
from copy import deepcopy
from decimal import localcontext, Inexact, Rounded
import unittest
import test_ndx_first_period_standard_cash_inputs_20261002 as f
m=f.m
class Review(unittest.TestCase):
 def test_eight_exact_raw_targets_baseline_and_no_input_mutation(self):
  docs,refs=f.fixture();docs['inventory']['rows'][0]['lane_target']['targets']['s0']['target_weight']=0.25000000000000006
  before=deepcopy(docs);r=m.assemble(docs,refs)
  self.assertEqual(docs,before)
  self.assertEqual({(x['lane'],x['cash_event']['amount_usd']) for x in r['rows']},{(l,a) for l in m.LANES for a in ('1000','10000')})
  self.assertEqual(r['rows'][0]['target_weights']['s0'],'0.25000000000000006')
  self.assertEqual(r['rows'][0]['original_target_weight_sum'],'1.00000000000000006')
  for row in r['rows']:
   self.assertEqual(row['holdings'],{});self.assertEqual(row['starting_cash_usd'],'25000.0')
   for flag in m.FLAGS:self.assertIs(row[flag],False)
  with localcontext() as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True;ctx.traps[Rounded]=True
   self.assertEqual(m.assemble(docs,refs),r)
 def test_date_pointer_capital_and_cash_amount_attacks(self):
  for attack in ('date','pointer','capital','holding','amount'):
   docs,refs=f.fixture()
   if attack=='date':docs['inventory']['rows'][0]['execution_date']='2023-04-04'
   elif attack=='pointer':docs['scenarios']['rows'][0]['parent_row_reference']['json_pointer']='/rows/00'
   elif attack=='capital':docs['inventory']['rows'][0]['baseline']['cash_usd']=26000.0
   elif attack=='holding':docs['inventory']['rows'][0]['baseline']['shares']={'old':1}
   else:docs['scenarios']['rows'][0]['standardized_cash_injection_usd']='5000'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,refs)
 def test_issuer_risk_missing_marks_and_float_target_bool(self):
  for attack in ('risk','missingprice','booltarget','duplicate'):
   docs,refs=f.fixture();row=docs['inventory']['rows'][0];sec=row['securities'][0]
   if attack=='risk':sec['risk_observations'].append({'observation_date':'2023-03-31','risk_chain':'wrong'})
   elif attack=='missingprice':sec['execution_open_observations']=[]
   elif attack=='booltarget':row['lane_target']['targets']['s0']['target_weight']=True
   else:row['securities'][1]=deepcopy(sec)
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs,refs)
if __name__=='__main__':unittest.main()
