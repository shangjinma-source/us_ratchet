import unittest
from copy import deepcopy
from fractions import Fraction as F
from test_ndx_single_replacement_domain_research import fixture,ref
from backtest import ndx_single_replacement_domain_research as m

class Review(unittest.TestCase):
 def test_fractional_prices_bilateral_cash_oracle_and_frozen_state(self):
  a=fixture();r=a['original_rows'][0]['input_row'];r['starting_cash_usd']='99.99';r['cash_event']['amount_usd']='1.25'
  r['execution_prices'].update(A='7.13',B='9.87',C='0.37',D='1.11')
  p=m.prepare_single_replacement_domain(**a);oracle=[]
  for out in ['A','B']:
   for inc in ['C','D']:
    for q in range(1,200):
     sale=r['holdings'][out]*F(r['execution_prices'][out]);buy=q*F(r['execution_prices'][inc])
     if F('101.24')+sale-buy-(sale+buy)*F(1,1000)>=100:oracle.append((out,inc,q))
  self.assertEqual(len(oracle),p['document']['integer_count'])
  for i,(out,inc,q) in enumerate(oracle):
   t=m.unrank(p,i)
   self.assertEqual([(s,n) for s,n in t['signed_trade_quantities'].items() if n<0],[(out,-r['holdings'][out])])
   self.assertEqual([(s,n) for s,n in t['signed_trade_quantities'].items() if n>0],[(inc,q)])
   for s,n in r['holdings'].items():self.assertEqual(t['proposed_holdings'][s],0 if s==out else n)

 def test_existing_issuer_collision_exclusion_and_complete_shards(self):
  a=fixture();r=a['original_rows'][0]['input_row'];r['holdings']['E']=1
  r['execution_prices']['E']='3';r['securities']['E']=dict(ticker='E',issuer_id=r['securities']['B']['issuer_id'],risk_chain='e')
  other=deepcopy(a['original_rows'][0]);other['input_row']['scenario_id']='second';other['input_reference']=ref(1)
  a['original_rows'].append(other);a['action_contract']['expected_scenario_ids'].append('second')
  p=m.prepare_single_replacement_domain(**a);d=p['document']
  self.assertTrue(all(x['enumerable_quantity_count']==0 for c in d['cases'] for x in c['pairs'] if x['outgoing_security_id']=='A'))
  self.assertEqual(d['integer_count']+d['structurally_excluded_integer_count'],d['financial_integer_count_before_issuer'])
  n=d['integer_count']; count=(n+6)//7;page=m.shard_page(p,shard_size=7,shard_start=0,shard_stop=count)
  self.assertEqual([i for s in page['shards'] for i in range(s['identity']['start'],s['identity']['stop'])],list(range(n)))
  for i in range(n):
   t=m.unrank(p,i);z=t['identity'];self.assertEqual(m.rank(p,scenario_index=t['scenario_index'],outgoing_security_id=z['outgoing_security_id'],incoming_security_id=z['incoming_security_id'],buy_quantity=z['buy_quantity']),i)
  self.assertNotEqual(m.unrank(p,0)['task_id'],m.unrank(p,d['cases'][1]['first_global_ordinal'])['task_id'])

 def test_ref_identity_and_explicit_conditional_scope(self):
  a=fixture();p=m.prepare_single_replacement_domain(**a)
  self.assertTrue(all(p['document'][k] is False for k in m.FLAGS))
  for value in (True,0,-1):
   with self.assertRaises(ValueError):m.rank(p,scenario_index=0,outgoing_security_id='A',incoming_security_id='C',buy_quantity=value)
  a=fixture();a['original_rows'][0]['input_reference']['json_pointer']='/rows/00'
  with self.assertRaises(ValueError):m.prepare_single_replacement_domain(**a)
  a=fixture();a['action_contract']['domain_core_reference']['path']=a['original_rows'][0]['input_reference']['path']
  with self.assertRaises(ValueError):m.prepare_single_replacement_domain(**a)

if __name__=='__main__':unittest.main()
