import json
from copy import deepcopy
from hashlib import sha256
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import quantity_saved_anchor_coordinate_fixing as m
from backtest import quantity_continuous_anchor_bound as continuous
from test_quantity_continuous_anchor_bound import setup,diag
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def sources(args=None,box=None):
    src=setup(args)
    if box is not None:src['box']=box
    ev=continuous.from_candidate(**src,candidate={s:0.0 for s in src['inputs']['prices']},diagnostics=diag())
    raw=json.dumps(ev).encode()
    return dict(anchor_raw=raw,expected_anchor_sha256=sha256(raw).hexdigest(),expected_anchor_binding_sha256=ev['binding_sha256'],incumbent={}),src

def inside(q,box):return all(lo<=q.get(s,0)<=hi for s,(lo,hi) in box.items())

class FixingTests(unittest.TestCase):
    def test_exhaustive_coverage_and_no_solver(self):
        for fee in ('0','25','9999'):
            args=fixture();args['fee_bps']=fee;s,src=sources(args)
            with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
                c=m.build(**s);m.verify(c,**s)
            for value,q in oracle(args,src['box']):
                hits=sum(inside(q,r['box']) for r in c['closed_regions'])+inside(q,c['remaining_box'])
                self.assertEqual(hits,1)
                if any(inside(q,r['box']) for r in c['closed_regions']):self.assertLessEqual(value,F(c['lower_product']))
                if value>F(c['lower_product']):self.assertTrue(inside(q,c['remaining_box']))
            self.assertEqual(set(c['remaining_box']),set(args['prices']))
    def test_nonzero_lower_equality_negative_coefficients(self):
        args=fixture();args['fee_bps']='0';args['training_scenarios']=[dict(A='1',B='.8',C='1')]
        s,src=sources(args,dict(A=[1,2],B=[0,1],C=[0,2]));s['incumbent']={'A':1}
        c=m.build(**s);self.assertEqual(c['remaining_box']['A'],[1,1]);self.assertTrue(c['objective_value_covered']);self.assertFalse(c['tie_break_optimality_established'])
    def test_attacks(self):
        s,_=sources();c=m.build(**s)
        for key,value in [('solver_calls',False),('tie_break_optimality_established',0),('upper_product','0'),('remaining_box',{}),('rows',[])]:
            bad=deepcopy(c);bad[key]=value
            with self.assertRaises(ValueError):m.verify(bad,**s)
        bad=dict(s,expected_anchor_sha256='0'*64)
        with self.assertRaises(ValueError):m.build(**bad)
        bad=dict(s,expected_anchor_binding_sha256='0'*64)
        with self.assertRaises(ValueError):m.build(**bad)

if __name__=='__main__':unittest.main()
