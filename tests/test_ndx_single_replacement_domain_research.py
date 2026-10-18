from copy import deepcopy
from decimal import getcontext, Inexact
from fractions import Fraction
import unittest
from backtest import ndx_single_replacement_domain_research as m

def ref(index=0):return dict(path='E:/synthetic/inputs.json',sha256='a'*64,json_pointer='/rows/'+str(index))

def fixture():
 row=dict(scenario_id='case0',lane='LANE',branch_role='MAIN_LANE',zero_buy_only=False,target_l1_applicable=True,
  point_in_time_verified=False,promotion_allowed=False,fork_executable=False,orders_executed=False,target_weights_normalized=False,
  scenario_reference=ref(10),inventory_row_reference=ref(20),cash_event=dict(decision_date='2023-04-28',execution_date='2023-05-01',amount_usd='10'),
  starting_cash_usd='100',holdings={'A':2,'B':1,'ZERO':0},target_weights={'C':'0.4','D':'0.6'},allowed_buy_security_ids=['C','D'],
  execution_prices={'A':'10','B':'20','C':'5','D':'10'},securities={s:dict(ticker=s,issuer_id='issuer:'+s,risk_chain='chain:'+s) for s in 'ABCD'},
  risk_parameters=dict(max_single_weight='0.30',min_single_weight='0.08',top_weight_cap='0.65',minimum_effective_n_ratio='0.8',risk_chain_top1_cap='0.5'),
  transaction_cost_bps='10',minimum_cash_buffer_usd='100',gaps=[{'security_id':'C','reason':'DATED_IDENTITY_NOT_IN_BOUND_LANE_EVIDENCE'}],original_inventory_row={'preserve':'full original'},original_scenario={'no_future_returns':True})
 contract=dict(m.SEMANTICS,expected_scenario_ids=['case0'],domain_core_reference=dict(path='E:/synthetic/core.py',sha256='b'*64),action_contract_reference=dict(path='E:/synthetic/action.json',sha256='c'*64))
 return dict(original_rows=[dict(input_row=row,input_reference=ref())],action_contract=contract)

class Tests(unittest.TestCase):
 def test_full_small_oracle_bilateral_fees_rank_and_frozen_old(self):
  a=fixture(); before=deepcopy(a); p=m.prepare_single_replacement_domain(**a); d=p['document']; row=a['original_rows'][0]['input_row']; oracle=[]
  for out in ['A','B']:
   for inc in ['C','D']:
    # Independent enumeration checks actual bilateral cash, not the cap formula.
    for q in range(1,100):
     sale=row['holdings'][out]*Fraction(row['execution_prices'][out]); buy=q*Fraction(row['execution_prices'][inc])
     cash=Fraction(110)+sale-buy-(sale+buy)/1000
     if cash>=100:oracle.append((out,inc,q))
  self.assertEqual(d['integer_count'],len(oracle)); self.assertEqual(a,before)
  for i,(out,inc,q) in enumerate(oracle):
   task=m.unrank(p,i); self.assertEqual(m.rank(p,scenario_index=0,outgoing_security_id=out,incoming_security_id=inc,buy_quantity=q),i)
   self.assertEqual(task['signed_trade_quantities'][out],-row['holdings'][out]);self.assertEqual(task['signed_trade_quantities'][inc],q)
   self.assertEqual(task['proposed_holdings']['ZERO'],0)
   self.assertEqual(set(task['signed_trade_quantities']),set(row['holdings'])|set(row['execution_prices']))
   for s in {'C','D'}-{inc}:self.assertEqual(task['proposed_holdings'][s],0)
   for s in set(row['holdings'])-{out}:self.assertEqual(task['proposed_holdings'][s],row['holdings'][s])
  self.assertEqual(d['cases'][0]['identity']['original_input_row'],row)
  self.assertTrue(all(d[k] is False for k in m.FLAGS))

 def test_fee_boundary_one_cent_and_one_share(self):
  a=fixture(); row=a['original_rows'][0]['input_row']; row['cash_event']['amount_usd']='0.04'
  # Sell 20, sellfee .02, buy one 20 plus buyfee .02 => exactly100.
  row['execution_prices']['C']='20'; p=m.prepare_single_replacement_domain(**a)
  self.assertEqual(p['document']['cases'][0]['pairs'][0]['quantity_max'],1)
  row['cash_event']['amount_usd']='0.03'; p=m.prepare_single_replacement_domain(**a)
  self.assertEqual(p['document']['cases'][0]['pairs'][0]['quantity_max'],0)
  row['starting_cash_usd']='0'; row['cash_event']['amount_usd']='0'
  p=m.prepare_single_replacement_domain(**a);self.assertEqual(p['document']['integer_count'],0)
  self.assertLess(p['document']['cases'][0]['pairs'][0]['financial_cap_floor'],0)

 def test_issuer_certificate_includes_retained_old_and_removed_old(self):
  a=fixture(); row=a['original_rows'][0]['input_row']; row['securities']['C']['issuer_id']=row['securities']['B']['issuer_id']
  p=m.prepare_single_replacement_domain(**a); d=p['document']; pairs=d['cases'][0]['pairs']
  self.assertEqual(pairs[0]['status'],'STRUCTURALLY_EXCLUDED')
  self.assertEqual(pairs[0]['issuer_exclusion_certificate']['conflicts'],{'issuer:B':['B','C']})
  self.assertEqual(pairs[2]['status'],'INTEGER_DOMAIN_NOT_EVALUATED')
  self.assertEqual(d['integer_count']+d['structurally_excluded_integer_count'],d['financial_integer_count_before_issuer'])
  with self.assertRaises(ValueError):m.rank(p,scenario_index=0,outgoing_security_id='A',incoming_security_id='C',buy_quantity=1)

 def test_huge_integer_domain_paging_and_no_float_context(self):
  a=fixture(); a['original_rows'][0]['input_row']['cash_event']['amount_usd']='1000000000000000000000000'
  context=getcontext().copy()
  try:
   getcontext().prec=2;getcontext().traps[Inexact]=True
   p=m.prepare_single_replacement_domain(**a)
  finally:
   from decimal import setcontext
   setcontext(context)
  n=p['document']['integer_count'];self.assertGreater(n,2**53)
  task=m.unrank(p,n-1);self.assertEqual(m.rank(p,scenario_index=task['scenario_index'],outgoing_security_id=task['identity']['outgoing_security_id'],incoming_security_id=task['identity']['incoming_security_id'],buy_quantity=task['identity']['buy_quantity']),n-1)
  page=m.shard_page(p,shard_size=1000,shard_start=0,shard_stop=2);self.assertEqual(page['full_shard_count'],(n+999)//1000)
  last=m.shard_page(p,shard_size=1000,shard_start=page['full_shard_count']-1,shard_stop=page['full_shard_count']);self.assertEqual(last['shards'][0]['identity']['stop'],n)

 def test_same_target_different_scenarios_do_not_alias_or_drop(self):
  a=fixture(); other=deepcopy(a['original_rows'][0]);other['input_row']['scenario_id']='case1';other['input_reference']=ref(1)
  a['original_rows'].append(other);a['action_contract']['expected_scenario_ids'].append('case1')
  p=m.prepare_single_replacement_domain(**a); c=p['document']['cases'];self.assertEqual(c[0]['integer_count'],c[1]['integer_count'])
  self.assertNotEqual(m.unrank(p,0)['task_id'],m.unrank(p,c[1]['first_global_ordinal'])['task_id'])
  a['original_rows'].reverse()
  with self.assertRaises(ValueError):m.prepare_single_replacement_domain(**a)

 def test_contract_missing_bool_bad_price_and_no_risk_pruning(self):
  for mode in ('contract','quantity','price','fee','target','source'):
   a=fixture(); r=a['original_rows'][0]['input_row']
   if mode=='contract':del a['action_contract']['fee_policy']
   elif mode=='quantity':r['holdings']['A']=True
   elif mode=='price':r['execution_prices']['A']='NaN'
   elif mode=='fee':r['transaction_cost_bps']='0'
   elif mode=='target':r['target_weights_normalized']=0
   else:r['scenario_reference']['sha256']='d'*64
   with self.subTest(mode=mode),self.assertRaises((ValueError,KeyError)):m.prepare_single_replacement_domain(**a)
  a=fixture(); a['original_rows'][0]['input_row']['risk_parameters']['min_single_weight']='0.99'
  p=m.prepare_single_replacement_domain(**a)
  self.assertGreater(p['document']['integer_count'],0);self.assertFalse(p['document']['risk_evaluated'])
  with self.assertRaises(ValueError):m.unrank(p,False)
  with self.assertRaises(ValueError):m.rank(p,scenario_index=False,outgoing_security_id='A',incoming_security_id='C',buy_quantity=1)

if __name__=='__main__':unittest.main()
