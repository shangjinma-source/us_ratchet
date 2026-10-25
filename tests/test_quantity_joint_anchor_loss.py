from copy import deepcopy
from fractions import Fraction as F
import unittest
from backtest import quantity_joint_anchor_loss as m
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def setup(lam='0'):
 a=fixture();p=core.prepare(**a);box={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
 return dict(inputs=a,box=box,anchor_quantities={s:'0' for s in p['ids']},incumbent={},dual_lambda=lam)
class LossTests(unittest.TestCase):
 def test_arbitrary_dual_and_exhaustive_identity(self):
  for lam in ('0','1/100','1','100'):
   args=setup(lam);c=m.build(**args);m.verify(c,expected_binding_sha256=c['binding_sha256'])
   for value,q in oracle(args['inputs'],args['box']):
    point=m.inspect_point(c,q)
    if value>F(c['lower_product']):self.assertFalse(point['excluded_for_strict_improvement'])
    if point['excluded_for_strict_improvement']:self.assertLessEqual(value,F(c['lower_product']))
 def test_root_exact_brackets(self):
  for n in (1,2,3,12):
   for value in (F(1),F(2),F(1,10**30),F(1234567,31)):
    t=m.floor_root_ratio(value,n,1000);self.assertLessEqual(t**n,value);self.assertGreater((t+F(1,1000))**n,value)
 def test_negative_zero_coefficients_and_attacks(self):
  args=setup();args['inputs']['fee_bps']='0';args['inputs']['training_scenarios']=[dict(A='1',B='.5',C='1')]
  c=m.build(**args);self.assertEqual(c['reduced_coefficients']['A'],'0');self.assertLess(F(c['reduced_coefficients']['B']),0)
  for key,value in [('threshold_floor','999'),('solver_calls',False),('executable_portfolio',0),('strict_loss_budget','999')]:
   bad=deepcopy(c);bad[key]=value
   with self.assertRaises(ValueError):m.verify(bad,expected_binding_sha256=c['binding_sha256'])
  for lam in (-1,False,0.1):
   with self.assertRaises(ValueError):m.build(**dict(args,dual_lambda=lam))
if __name__=='__main__':unittest.main()

