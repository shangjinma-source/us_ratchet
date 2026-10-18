from copy import deepcopy
from decimal import localcontext, Inexact
from fractions import Fraction as F
import unittest
from backtest import ndx_double_replacement_domain_research as m
from test_ndx_double_replacement_domain_research import fixture

class Tests(unittest.TestCase):
 def test_hand_joint_budget_quantity_identity_and_boundary(self):
  a=fixture();before=deepcopy(a)
  with localcontext()as ctx:
   ctx.prec=1;ctx.traps[Inexact]=True;p=m.prepare_double_replacement_domain(**a)
  d=p['document'];pair=d['cases'][0]['pairs'][0]
  self.assertEqual(F(pair['financial_bound']['gross_sale_usd']),50)
  self.assertEqual(F(pair['financial_bound']['sell_fee_usd']),F(1,20))
  self.assertEqual(F(pair['financial_bound']['joint_budget_usd']),50)
  self.assertEqual(list(map(F,pair['financial_bound']['incoming_unit_costs_with_buy_fee_usd'])),[F(1001,100),F(3003,200)])
  tasks=m.task_page(p,start=0,limit=9)['tasks'];self.assertEqual([t['identity']['buy_quantities']for t in tasks],[[1,1],[1,2],[2,1],[3,1]])
  self.assertEqual(d['pair_count'],1);self.assertEqual(d['integer_count'],4)
  for i,(qc,qd)in enumerate(((1,1),(1,2),(2,1),(3,1))):
   task=tasks[i];self.assertEqual(task['signed_trade_quantities'],dict(A=-2,B=-1,C=qc,D=qd,ZERO=0))
   cash=F('95.05')+5+50-F(1,20)-10*qc-15*qd-F(10*qc+15*qd,1000)
   self.assertGreaterEqual(cash,100);self.assertFalse(task['financial_feasibility_evaluated'])
   self.assertEqual(m.rank(p,scenario_index=0,outgoing_security_ids=['A','B'],incoming_security_ids=['C','D'],buy_quantities=[qc,qd]),i)
  self.assertEqual(a,before)
  for cash,expected in [('95.099999999999999999999999999999',4),('95.1',5)]:
   a=fixture();a['original_rows'][0]['input_row']['starting_cash_usd']=cash;p=m.prepare_double_replacement_domain(**a)
   self.assertEqual(p['document']['integer_count'],expected)
   if expected==5:self.assertEqual(m.unrank(p,3)['identity']['buy_quantities'],[2,2])
 def test_issuer_exclusion_complete_pre_exclusion_domain_and_cash_pool(self):
  a=fixture();r=a['original_rows'][0]['input_row'];r['securities']['B']['issuer_id']=r['securities']['A']['issuer_id']
  # Both old classes disappear; incoming matching a SOLD issuer is not a conflict.
  r['securities']['C']['issuer_id']=r['securities']['A']['issuer_id']
  p=m.prepare_double_replacement_domain(**a);self.assertEqual(p['document']['integer_count'],4)
  r['securities']['D']['issuer_id']=r['securities']['C']['issuer_id'];p=m.prepare_double_replacement_domain(**a);d=p['document']
  self.assertEqual((d['financial_integer_count_before_issuer'],d['structurally_excluded_integer_count'],d['integer_count']),(4,4,0));self.assertEqual(d['pair_count'],1)
  self.assertEqual(d['cases'][0]['pairs'][0]['issuer_exclusion_certificate']['conflicts'],{r['securities']['C']['issuer_id']:['C','D']})
  self.assertEqual(m.task_page(p,start=0,limit=1)['tasks'],[])
  with self.assertRaises(ValueError):m.unrank(p,0)
  a=fixture();r=a['original_rows'][0]['input_row'];r['holdings']['E']=1;r['execution_prices']['E']='5';r['securities']['E']=dict(ticker='E',issuer_id=r['securities']['C']['issuer_id'],risk_chain='x')
  p=m.prepare_double_replacement_domain(**a);first=p['document']['cases'][0]['pairs'][0]
  self.assertEqual(first['outgoing_security_ids'],['A','B']);self.assertEqual(first['financial_integer_count'],4);self.assertEqual(first['enumerable_integer_count'],0)
  self.assertEqual(first['issuer_exclusion_certificate']['conflicts'],{r['securities']['C']['issuer_id']:['C','E']})
  self.assertEqual(p['document']['integer_count']+p['document']['structurally_excluded_integer_count'],p['document']['financial_integer_count_before_issuer'])
 def test_empty_case_contiguous_shards_full_metadata_and_source_conflict(self):
  a=fixture();second=deepcopy(a['original_rows'][0]);a['original_rows'][0]['input_row']['starting_cash_usd']='0'
  second['input_row']['scenario_id']='second';second['input_reference']['json_pointer']='/rows/1';a['original_rows'].append(second);a['action_contract']['expected_scenario_ids'].append('second')
  p=m.prepare_double_replacement_domain(**a);self.assertEqual(p['document']['scenario_count'],2);self.assertEqual(p['document']['pair_count'],2)
  self.assertEqual([m.unrank(p,i)['scenario_index']for i in range(4)],[1]*4)
  shards=m.shard_page(p,shard_size=3,shard_start=0,shard_stop=2);self.assertEqual([(s['identity']['start'],s['identity']['stop'])for s in shards['shards']],[(0,3),(3,4)])
  self.assertEqual(m.task_page(p,start=4,limit=2)['tasks'],[])
  for key in m.FLAGS:self.assertIs(p['document'][key],False)
  for kw in (dict(scenario_index=False,outgoing_security_ids=['A','B'],incoming_security_ids=['C','D'],buy_quantities=[1,1]),dict(scenario_index=1,outgoing_security_ids=['B','A'],incoming_security_ids=['C','D'],buy_quantities=[1,1])):
   with self.assertRaises(ValueError):m.rank(p,**kw)
  a['action_contract']['budget_math_reference']['path']=a['original_rows'][0]['input_reference']['path']
  with self.assertRaises(ValueError):m.prepare_double_replacement_domain(**a)

if __name__=='__main__':unittest.main()
