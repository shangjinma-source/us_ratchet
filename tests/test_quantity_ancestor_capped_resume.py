from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from unittest.mock import patch
import unittest
from backtest import quantity_ancestor_capped_resume as m
from backtest.quantity_ancestor_bound_supplement import build
from test_quantity_ancestor_bound_supplement import fixture_sources
from test_quantity_box_supplemental_certificate import raw
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def setup():
    sources,_=fixture_sources(1);a=raw(build(**sources))
    return dict(ancestor_raw=a,expected_ancestor_sha256=sha256(a).hexdigest(),ancestor_sources=sources)

class CappedTests(unittest.TestCase):
    def test_oracle_and_single_boundary(self):
        src=setup()
        for count in (0,1,3,100):
            with patch.object(m.ancestor,'verify',wraps=m.ancestor.verify) as gate:
                c=m.resume(**src,additional_node_budget=count)
                self.assertEqual(gate.call_count,1)
            m.verify(c,**src)
            self.assertGreaterEqual(F(c['upper_product']),max(v for v,_ in oracle(fixture())))
            for n in c['unsearched_frontier']:
                vals=oracle(fixture(),n['box'])
                if vals:self.assertGreaterEqual(F(n['effective_upper_product']),max(v for v,_ in vals))
        self.assertTrue(c['objective_value_optimal'])
    def test_segments_and_monotonic(self):
        src=setup();c=m.resume(**src,additional_node_budget=0)
        for budget in (1,2,3,50):
            prior=raw(c);old=deepcopy(c)
            c=m.resume(**src,additional_node_budget=budget,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest())
            m.verify_transition(c,**src,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest())
            self.assertLessEqual(F(c['upper_product']),F(old['upper_product']))
            self.assertLessEqual(F(c['upper_product'])/F(c['lower_product']),F(old['upper_product'])/F(old['lower_product']))
        full=m.resume(**src,additional_node_budget=56)
        self.assertEqual({k:v for k,v in c.items() if k!='parent_continuation_raw_sha256'},{k:v for k,v in full.items() if k!='parent_continuation_raw_sha256'})
    def test_attacks(self):
        src=setup();c=m.resume(**src,additional_node_budget=1)
        for field,value in [('processed_nodes',True),('objective_value_optimal',1),('data_authenticated',0),('upper_product','0'),('scope','ALL')]:
            bad=deepcopy(c);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.verify(bad,**src)
        for field,value in [('parent_id','fake'),('effective_upper_product','0'),('effective_empty',0),('inherited_proof_ref',{})]:
            bad=deepcopy(c);bad['unsearched_frontier'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.verify(bad,**src)
        bad=deepcopy(c);bad['unsearched_frontier'].pop()
        with self.assertRaises(ValueError):m.verify(bad,**src)
        with self.assertRaises(ValueError):m.resume(**src,additional_node_budget=False)
        bad=dict(src,expected_ancestor_sha256='0'*64)
        with self.assertRaises(ValueError):m.verify(c,**bad)
    def test_transition_retains_pending_evidence(self):
        src=setup();previous=m.resume(**src,additional_node_budget=0)
        prior=raw(previous)
        current=m.resume(**src,additional_node_budget=1,previous_raw=prior,expected_previous_sha256=sha256(prior).hexdigest())
        ctx=m.context(**src)
        identifier=previous['unsearched_frontier'][0]['id']
        for field in ('box','bound','parent_id','inherited_proof_ref','effective_empty','effective_upper_product'):
            changed=deepcopy(current)
            node=next(n for n in changed['coverage_ledger']+changed['unsearched_frontier'] if n['id']==identifier)
            node[field]='tampered'
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'INHERITED_PENDING_CHANGED'):
                m._transition(changed,previous,ctx)
        self.assertEqual(previous['unsearched_frontier'][0]['bound'],current['coverage_ledger'][0]['bound'])

    def test_loose_local_child_cap(self):
        src=setup();ctx=m.context(**src);parent=deepcopy(ctx['roots'][0]);parent['effective_upper_product']='1'
        child=m.child_node(ctx,parent,parent['id']+'0',deepcopy(parent['box']),ctx['c']['selected'])
        self.assertGreater(F(child['bound']['upper_product']),1)
        self.assertEqual(child['effective_upper_product'],'1')
        self.assertEqual(child['inherited_proof_ref'],m.proof(parent))

if __name__=='__main__':unittest.main()
