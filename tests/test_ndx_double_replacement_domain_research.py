from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations
from decimal import localcontext,Inexact
import unittest
from backtest import ndx_double_replacement_domain_research as m
from test_ndx_single_replacement_domain_research import fixture as single_fixture

def fixture():
 a=single_fixture();r=a['original_rows'][0]['input_row'];r.update(starting_cash_usd='95.05');r['cash_event']['amount_usd']='5';r['execution_prices'].update(B='30',C='10',D='15')
 a['action_contract']=dict(m.SEMANTICS,expected_scenario_ids=['case0'],domain_core_reference=dict(path='E:/synthetic/double_core.py',sha256='d'*64),action_contract_reference=dict(path='E:/synthetic/double_policy.json',sha256='e'*64),budget_math_reference=dict(path='E:/synthetic/budget_math.py',sha256=m.BUDGET_MATH_SHA256))
 return a

def oracle(a):
 result=[]
 for ci,envelope in enumerate(a['original_rows']):
  r=envelope['input_row'];old=sorted(s for s,q in r['holdings'].items()if q>0);new=sorted(set(r['target_weights'])-set(old));p={s:F(v)for s,v in r['execution_prices'].items()};fee=F(r['transaction_cost_bps'])/10000
  for outgoing in combinations(old,2):
   for incoming in combinations(new,2):
    kept=(set(old)-set(outgoing))|set(incoming);issuers=[r['securities'][s]['issuer_id']for s in kept]
    if len(set(issuers))!=len(issuers):continue
    budget=F(r['starting_cash_usd'])+F(r['cash_event']['amount_usd'])+sum((r['holdings'][s]*p[s]*(1-fee)for s in outgoing),F(0))-F(r['minimum_cash_buffer_usd'])
    for q1 in range(1,51):
     for q2 in range(1,51):
      if p[incoming[0]]*(1+fee)*q1+p[incoming[1]]*(1+fee)*q2<=budget:result.append((ci,list(outgoing),list(incoming),[q1,q2]))
 return result

class Tests(unittest.TestCase):
 def test_exact_nonrectangular_four_points_full_roundtrip(self):
  a=fixture();before=deepcopy(a);p=m.prepare_double_replacement_domain(**a);d=p['document'];self.assertEqual(d['integer_count'],4);self.assertEqual(d['pair_count'],1)
  pairs=[]
  for i in range(4):
   t=m.unrank(p,i);v=t['identity'];pairs.append(tuple(v['buy_quantities']));self.assertEqual(m.rank(p,scenario_index=0,outgoing_security_ids=v['outgoing_security_ids'],incoming_security_ids=v['incoming_security_ids'],buy_quantities=v['buy_quantities']),i)
   self.assertEqual(t['signed_trade_quantities']['A'],-2);self.assertEqual(t['signed_trade_quantities']['B'],-1);self.assertEqual(t['signed_trade_quantities']['ZERO'],0);self.assertEqual(t['proposed_holdings']['ZERO'],0)
  self.assertEqual(pairs,[(1,1),(1,2),(2,1),(3,1)]);self.assertEqual(a,before)
  with self.assertRaises(ValueError):m.rank(p,scenario_index=0,outgoing_security_ids=['A','B'],incoming_security_ids=['C','D'],buy_quantities=[2,2])
  self.assertEqual(d['cases'][0]['pairs'][0]['financial_bound']['joint_budget_usd'],'50')
 def test_complete_small_bruteforce_multiple_pairs_cases_issuer_partitions(self):
  for conflict in ('none','incoming','retained'):
   a=fixture();r=a['original_rows'][0]['input_row'];r['holdings']['E']=1;r['execution_prices']['E']='5';r['securities']['E']=dict(ticker='E',issuer_id='issuer:E',risk_chain='chain:E')
   if conflict=='incoming':r['securities']['D']['issuer_id']=r['securities']['C']['issuer_id']
   elif conflict=='retained':r['securities']['E']['issuer_id']=r['securities']['C']['issuer_id']
   row2=deepcopy(a['original_rows'][0]);row2['input_row']['scenario_id']='case1';row2['input_reference']['json_pointer']='/rows/1';a['original_rows'].append(row2);a['action_contract']['expected_scenario_ids'].append('case1')
   expected=oracle(a);p=m.prepare_double_replacement_domain(**a);d=p['document'];self.assertEqual(d['integer_count'],len(expected));self.assertEqual(d['pair_count'],6);self.assertEqual(d['integer_count']+d['structurally_excluded_integer_count'],d['financial_integer_count_before_issuer'])
   for i,item in enumerate(expected):
    t=m.unrank(p,i);v=t['identity'];self.assertEqual((t['scenario_index'],v['outgoing_security_ids'],v['incoming_security_ids'],v['buy_quantities']),item)
   page=m.task_page(p,start=0,limit=100);self.assertEqual(len(page['tasks']),len(expected));self.assertFalse(page['domain_truncated'])
   if conflict=='incoming':self.assertGreater(d['structurally_excluded_integer_count'],0);self.assertEqual(page['tasks'],[])
 def test_large_exact_domain_and_shards_no_quantity_cap(self):
  a=fixture();a['original_rows'][0]['input_row']['cash_event']['amount_usd']='1000000000000000000000000000000'
  with localcontext()as c:
   c.prec=2;c.traps[Inexact]=True;p=m.prepare_double_replacement_domain(**a)
  total=p['document']['integer_count'];self.assertGreater(total,10**50);last=m.unrank(p,total-1);v=last['identity'];self.assertEqual(m.rank(p,scenario_index=0,outgoing_security_ids=v['outgoing_security_ids'],incoming_security_ids=v['incoming_security_ids'],buy_quantities=v['buy_quantities']),total-1)
  page=m.shard_page(p,shard_size=32,shard_start=0,shard_stop=2);self.assertEqual(page['full_integer_count'],total);self.assertEqual(page['shards'][1]['identity']['start'],32)
  self.assertEqual(m.task_page(p,start=total-1,limit=2)['stop'],total)
 def test_input_types_refs_identity_and_unsorted_quantity_not_reordered(self):
  p=m.prepare_double_replacement_domain(**fixture());self.assertNotEqual(m.unrank(p,1)['task_id'],m.unrank(p,2)['task_id'])
  for incoming,q in [(['D','C'],[1,2]),(['C','D'],[True,1]),(['C','D'],[0,1])]:
   with self.assertRaises(ValueError):m.rank(p,scenario_index=0,outgoing_security_ids=['A','B'],incoming_security_ids=incoming,buy_quantities=q)
  for kind in ('math','source','fee','schema','bool'):
   a=fixture()
   if kind=='math':a['action_contract']['budget_math_reference']['sha256']='a'*64
   elif kind=='source':a['action_contract']['budget_math_reference']['path']=a['action_contract']['domain_core_reference']['path']
   elif kind=='fee':a['action_contract']['transaction_cost_bps']='20'
   elif kind=='schema':a['action_contract']['schema']='SINGLE_REPLACEMENT_ACTION_CONTRACT_V1'
   else:a['original_rows'][0]['input_row']['holdings']['A']=True
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare_double_replacement_domain(**a)
 def test_empty_financial_domain_and_not_enough_outgoing_preserved(self):
  a=fixture();a['original_rows'][0]['input_row']['starting_cash_usd']='0';p=m.prepare_double_replacement_domain(**a);self.assertEqual(p['document']['pair_count'],1);self.assertEqual(p['document']['integer_count'],0);self.assertEqual(p['document']['cases'][0]['pairs'][0]['status'],'EMPTY_FINANCIAL_DOMAIN')
  a=fixture();a['original_rows'][0]['input_row']['holdings']['B']=0;del a['original_rows'][0]['input_row']['execution_prices']['B'];del a['original_rows'][0]['input_row']['securities']['B'];p=m.prepare_double_replacement_domain(**a);self.assertEqual(p['document']['scenario_count'],1);self.assertEqual(p['document']['pair_count'],0);self.assertEqual(p['document']['integer_count'],0)
if __name__=='__main__':unittest.main()
