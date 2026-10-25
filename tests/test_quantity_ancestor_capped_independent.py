from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from random import Random
from unittest.mock import patch
import unittest
from backtest import quantity_ancestor_capped_resume as m
from backtest.quantity_box_supplemental_certificate import supplement
from backtest.quantity_ancestor_bound_supplement import build
from backtest.quantity_supplement_frontier_resume import resume as oldresume
from test_quantity_box_supplemental_certificate import sources,raw
from test_quantity_integer_box_certificate_independent import oracle
from test_quantity_ancestor_capped_resume import setup

def chain(args):
 bs=sources(args);sr=raw(supplement(**bs));ctx=dict(supplement_raw=sr,expected_supplement_sha256=sha256(sr).hexdigest(),bound_sources=bs)
 c=raw(oldresume(**ctx,additional_node_budget=1));cs=dict(continuation_raw=c,expected_continuation_sha256=sha256(c).hexdigest(),continuation_sources=ctx)
 a=raw(build(**cs));return dict(ancestor_raw=a,expected_ancestor_sha256=sha256(a).hexdigest(),ancestor_sources=cs)

class IndependentCappedTests(unittest.TestCase):
 def test_eight_domains_oracle_monotonic_segment_identity(self):
  rng=Random(923)
  for index in range(8):
   args=dict(prices={s:str(rng.randint(1,3)) for s in 'AB'},metadata={s:dict(ticker=s,issuer_id='same' if index%2 else s) for s in 'AB'},entered_cash='7',fee_bps=str(index*100),minimum_cash_buffer=str(index%3),training_scenarios=[{s:str(rng.choice([0.5,1,1.5,2])) for s in 'AB'} for _ in range(2)])
   src=chain(args);c=m.resume(**src,additional_node_budget=0)
   for budget in (1,2,100):
    old=deepcopy(c);pr=raw(old);c=m.resume(**src,additional_node_budget=budget,previous_raw=pr,expected_previous_sha256=sha256(pr).hexdigest())
    m.verify_transition(c,**src,previous_raw=pr,expected_previous_sha256=sha256(pr).hexdigest())
    self.assertLessEqual(F(c['upper_product']),F(old['upper_product']));self.assertGreaterEqual(F(c['lower_product']),F(old['lower_product']))
    self.assertEqual(c['binding']['closed_ids_sha256'],old['binding']['closed_ids_sha256'])
   self.assertTrue(c['objective_value_optimal']);self.assertEqual(F(c['lower_product']),max(v for _,v in oracle(args)))
   whole=m.resume(**src,additional_node_budget=103)
   self.assertEqual({k:v for k,v in whole.items() if k!='parent_continuation_raw_sha256'},{k:v for k,v in c.items() if k!='parent_continuation_raw_sha256'})

 def test_true_oracle_cap_beats_loose_child_and_is_inherited(self):
  src=setup();ctx=m.context(**src);p=deepcopy(ctx['roots'][0]);args=ctx['inputs'];values=oracle(args,p['box']);self.assertTrue(values)
  cap=max(v for _,v in values);p['effective_upper_product']=str(cap)
  child=m.child_node(ctx,p,p['id']+'0',deepcopy(p['box']),ctx['c']['selected'])
  self.assertGreater(F(child['bound']['upper_product']),cap)
  self.assertEqual(F(child['effective_upper_product']),cap)
  self.assertEqual(child['inherited_proof_ref'],m.proof(p))

 def test_public_boundary_no_trusted_context_and_strict_fifo(self):
  src=setup();c=m.resume(**src,additional_node_budget=1)
  for key in ('verified_context','ctx','skip_verification'):
   with self.subTest(key=key),self.assertRaises(TypeError):m.verify(c,**src,**{key:True})
  with patch.object(m.ancestor,'verify',side_effect=ValueError('SOURCE_REJECTED')) as gate:
   with self.assertRaisesRegex(ValueError,'SOURCE_REJECTED'):m.verify(c,**src)
   self.assertEqual(gate.call_count,1)
  for kind in ('fifo','bool','closed','cap','completion'):
   bad=deepcopy(c)
   if kind=='fifo':bad['unsearched_frontier'].reverse()
   elif kind=='bool':bad['node_budget']=True
   elif kind=='closed':bad['binding']['closed_ids_sha256']='0'*64
   elif kind=='cap':bad['unsearched_frontier'][0]['effective_upper_product']='0'
   else:bad['objective_value_optimal']=True
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.verify(bad,**src)

if __name__=='__main__':unittest.main()
