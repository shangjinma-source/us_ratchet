from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json,unittest
from unittest.mock import patch
from backtest import quantity_saved_anchor_tail_tightening as m
from backtest import quantity_saved_anchor_coordinate_fixing as fixing
from test_quantity_saved_anchor_coordinate_fixing import sources,inside
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def setup(args=None,box=None):
 s,src=sources(args,box);parent=fixing.build(**s);raw=json.dumps(parent).encode()
 return dict(fixing_raw=raw,expected_fixing_sha256=sha256(raw).hexdigest(),fixing_sources=s),src

class TailTests(unittest.TestCase):
 def test_exhaustive_cover_improvers_and_monotone(self):
  for fee in ('0','25','9999'):
   args=fixture();args['fee_bps']=fee;s,src=setup(args)
   with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):c=m.build(**s);m.verify(c,**s)
   for value,q in oracle(args,c['original_box']):
    self.assertEqual(sum(inside(q,r['box']) for r in c['closed_regions'])+inside(q,c['remaining_box']),1)
    if any(inside(q,r['box']) for r in c['closed_regions']):self.assertLessEqual(value,F(c['lower_product']))
    if value>F(c['lower_product']):self.assertTrue(inside(q,c['remaining_box']))
   for row in c['rows']:
    previous=None
    for t in sorted(row['tests'],key=lambda t:t['threshold']):
     if t['bound']['empty']:continue
     upper=F(t['bound']['upper_product'])
     if previous is not None:self.assertLessEqual(upper,previous)
     previous=upper
   self.assertLessEqual(c['conditional_bound_calls'],c['conditional_bound_calls_max'])
   self.assertEqual(set(c['remaining_box']),set(args['prices']))
 def test_closed_parent_and_positive_lower(self):
  args=fixture();args['training_scenarios']=[dict(A='1',B='.8',C='1')];args['fee_bps']='0'
  s,src=setup(args,dict(A=[1,2],B=[0,1],C=[0,2]));c=m.build(**s)
  self.assertTrue(c['objective_value_covered']);self.assertEqual(c['conditional_bound_calls'],0);self.assertEqual(c['remaining_box']['A'],[1,1])
 def test_attacks(self):
  s,_=setup();c=m.build(**s)
  for key,val in [('conditional_bound_calls',False),('solver_calls',False),('upper_product','0'),('remaining_box',{}),('rows',[])]:
   bad=deepcopy(c);bad[key]=val
   with self.assertRaises(ValueError):m.verify(bad,**s)
  bad=dict(s,expected_fixing_sha256='0'*64)
  with self.assertRaises(ValueError):m.build(**bad)
if __name__=='__main__':unittest.main()
