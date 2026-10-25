from copy import deepcopy
from fractions import Fraction as F
import unittest
from unittest.mock import patch
from backtest import quantity_coupled_joint_loss_iterator as m
from backtest import quantity_joint_anchor_loss as loss
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_prototype import oracle
from test_quantity_small_joint_loss_enumerator import fixture as source_fixture


def synthetic():
 inputs=dict(prices={'A':'1','B':'1','C':'1'},metadata={s:dict(ticker=s,issuer_id=s) for s in 'ABC'},entered_cash='5/2',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[dict(A='2',B='3/2',C='1/2')])
 box={s:[0,2] for s in 'ABC'};inc={'A':2}
 evidence=loss.build(inputs=inputs,box=box,anchor_quantities={s:'0' for s in 'ABC'},incumbent=inc,dual_lambda='2/5')
 report=dict(inherited_closed_rows=[{'prior':'closed'}],inherited_fixing_rows=[{'slabs':'retained'}],new_rows=[dict(id='other',upper_product='99')])
 parent=dict(remaining_box=box,lower_product=evidence['lower_product'])
 context=(report,parent,evidence,m.pattern_bound(evidence),core.prepare(**inputs),inc)
 sources=dict(expected_parent_report_sha256='a'*64,target_id='target',expected_tail_sha256='b'*64,expected_loss_sha256='c'*64,expected_loss_binding_sha256=evidence['binding_sha256'])
 return inputs,context,sources

class CoupledTests(unittest.TestCase):
 def test_real_loss_tiny_exhaustive_and_no_solver(self):
  inputs,ctx,s=synthetic();loss.verify(ctx[2],expected_binding_sha256=s['expected_loss_binding_sha256'])
  with patch.object(m,'_context',return_value=ctx),patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
   c=m.build(**s);m.verify(c,**s)
  self.assertTrue(c['domain_complete']);self.assertEqual(c['zero_axis'],'A');self.assertEqual(F(c['strict_interval_width']),F(1,2))
  expected=max([F(ctx[1]['lower_product'])]+[v for v,q in oracle(inputs,ctx[1]['remaining_box'])]);self.assertEqual(F(c['candidate_product']),expected)
  checked={tuple(sorted(p['quantities'].items())) for p in c['points']}
  for v,q in oracle(inputs,ctx[1]['remaining_box']):
   if v>F(ctx[1]['lower_product']):self.assertIn(tuple(sorted(q.items())),checked)
  self.assertEqual(c['other_domains'],ctx[0]['new_rows']);self.assertEqual(set(c['original_box']),set(inputs['prices']))
 def test_strict_integer_endpoints(self):
  args=dict(spendable=F(5,2),other_spend=F(0),loss_budget=F(1,2),other_loss=F(0),dual_lambda=F(1),unit_cost=F(1),lo=0,hi=3)
  r=m.strict_interval(**args);self.assertEqual((r['first'],r['last']),(3,2))
  r=m.strict_interval(**dict(args,loss_budget=F(3,4)));self.assertEqual((r['first'],r['last']),(2,2))
 def test_budget_frontier_types_and_certificate_attacks(self):
  _,ctx,s=synthetic()
  with patch.object(m,'_context',return_value=ctx):
   for budget in (0,1,3):
    c=m.build(**s,node_budget=budget);m.verify(c,**s)
    self.assertLessEqual(c['visited_nodes'],budget)
   c=m.build(**s,objective_budget=0);self.assertEqual(c['unsearched_frontier'],[[]])
   for k,v in [('visited_nodes',False),('other_domains',[]),('global_objective_value_optimal',0),('unsearched_frontier',[])]:
    bad=deepcopy(c);bad[k]=v
    with self.assertRaises(ValueError):m.verify(bad,**s)
   for key,value in [('node_budget',True),('node_budget',100001),('objective_budget',10001)]:
    with self.assertRaises(ValueError):m.build(**s,**{key:value})
 def test_degeneracies_and_actual_source_hash_rejection(self):
  _,ctx,s=synthetic()
  for change in ('lambda','multiple','width'):
   modified=deepcopy(ctx)
   if change=='lambda':modified[2]['binding']['dual_lambda']='0'
   elif change=='multiple':modified[2]['reduced_coefficients']['B']='0'
   else:modified[2]['strict_loss_budget']='99'
   with patch.object(m,'_context',return_value=modified),self.assertRaises(ValueError):m.build(**s)
  sources,_,_=source_fixture()
  with self.assertRaisesRegex(ValueError,'RAW_HASH_CHANGED'):m.build(**dict(sources,expected_loss_sha256='0'*64))

 def test_full_real_source_chain(self):
  import json
  from hashlib import sha256
  from test_quantity_saved_anchor_coordinate_fixing import sources as anchor_sources
  from backtest import quantity_saved_anchor_coordinate_fixing as fixing
  from backtest import quantity_saved_anchor_tail_tightening as tail
  inputs,ctx,_=synthetic();fs,_=anchor_sources(inputs,ctx[1]['remaining_box']);fs['incumbent']={'A':2}
  fr=json.dumps(fixing.build(**fs)).encode();ts=dict(fixing_raw=fr,expected_fixing_sha256=sha256(fr).hexdigest(),fixing_sources=fs)
  t=tail.build(**ts);tr=json.dumps(t).encode();anchor=json.loads(fs['anchor_raw'])
  l=loss.build(inputs=inputs,box=t['remaining_box'],anchor_quantities=anchor['repaired_quantities'],incumbent=fs['incumbent'],dual_lambda='2/5');lr=json.dumps(l).encode()
  report=dict(lower_product=t['lower_product'],integer_selected_unchanged=fs['incumbent'],new_rows=[dict(id='target',certificate_sha256=sha256(tr).hexdigest()),dict(id='other',certificate_sha256='f'*64)],inherited_closed_rows=[{'closed':'prior'}],inherited_fixing_rows=[{'slabs':'prior'}]);rr=json.dumps(report).encode()
  s=dict(parent_report_raw=rr,expected_parent_report_sha256=sha256(rr).hexdigest(),target_id='target',tail_raw=tr,expected_tail_sha256=sha256(tr).hexdigest(),tail_sources=ts,loss_raw=lr,expected_loss_sha256=sha256(lr).hexdigest(),expected_loss_binding_sha256=l['binding_sha256'])
  c=m.build(**s);m.verify(c,**s);self.assertTrue(c['domain_complete'])
  with self.assertRaises(ValueError):m.build(**dict(s,expected_loss_binding_sha256='0'*64))

 def test_prefix_bound_safe_for_all_tiny_suffixes(self):
  from itertools import product
  _,ctx,_=synthetic();p=ctx[4];box=ctx[1]['remaining_box'];ev=ctx[2];all_axes=ctx[3]['axes'];axes=[a for a in all_axes if a['sid']!='A' and a['max_deviation']>0]
  # Also exercise broad axes with both signs, beyond the necessary filter.
  axes=[dict(a,max_deviation=box[a['sid']][1]-box[a['sid']][0]) for a in all_axes if a['sid']!='A']
  broad=[next((a for a in axes if a['sid']==old['sid']),old) for old in all_axes]
  lam=F(ev['binding']['dual_lambda'])
  for depth in range(len(axes)+1):
   for prefix in product(*(range(a['max_deviation']+1) for a in axes[:depth])):
    b=m.prefix_bound(problem=p,all_axes=broad,branch_axes=axes,prefix=prefix,zero_axis='A',box=box,dual_lambda=lam)
    for suffix in product(*(range(a['max_deviation']+1) for a in axes[depth:])):
     q={a['sid']:a['preferred'] for a in broad}
     for a,d in zip(axes,prefix+suffix):q[a['sid']]+=a['direction']*d
     for z in range(3):
      q['A']=z;spent=sum((p['cost'][sid]*n for sid,n in q.items()),F(0))
      if spent>p['spendable']:continue
      exact=lam*(p['spendable']-spent)+sum((F(ev['reduced_coefficients'][sid])*(ev['preferred_endpoints'][sid]-n) for sid,n in q.items()),F(0))
      self.assertLessEqual(F(b['total_loss_lower']),exact)
  _,ctx,sources=synthetic()
  with patch.object(m,'_context',return_value=ctx):
   c=m.build(**sources)
   self.assertEqual(c['ledger'][0]['terminal'],'CLOSED_BY_PREFIX_BUDGET_AND_COORDINATE_LOSS')
   bad=deepcopy(c);bad['ledger'][0]['prefix_loss_bound']['maximum_possible_spend']='999'
   with self.assertRaises(ValueError):m.verify(bad,**sources)

if __name__=='__main__':unittest.main()
