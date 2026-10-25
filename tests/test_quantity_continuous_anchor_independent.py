from copy import deepcopy
from fractions import Fraction as F
from random import Random
from unittest.mock import patch
import unittest
from backtest import quantity_continuous_anchor_bound as m
from backtest import quantity_multi_anchor_bound_prototype as multi
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_independent import oracle

class IndependentContinuousAnchorTests(unittest.TestCase):
 def test_twenty_full_domain_repairs_against_cartesian_oracle(self):
  rng=Random(991)
  for index in range(20):
   args=dict(prices={s:str(rng.randint(1,4)) for s in 'ABC'},metadata={s:dict(ticker=s,issuer_id='same' if index%2 and s in 'AB' else s) for s in 'ABC'},entered_cash='9',fee_bps=str(rng.choice([0,500,9999])),minimum_cash_buffer=str(rng.randint(0,3)),training_scenarios=[{s:str(rng.choice([0.5,1,1.5,2])) for s in 'ABC'} for _ in range(3)])
   p=core.prepare(**args);outer={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']};box={s:[0,rng.randint(0,outer[s][1])] for s in p['ids']};ev=multi.bound(inputs=args,box=outer,incumbent={});diag=dict(success=False,status=9,iterations=0,message='untrusted')
   candidate={s:rng.random()*30 for s in p['ids']};c=m.from_candidate(inputs=args,box=box,inherited_evidence=ev,candidate=candidate,diagnostics=diag)
   vals=oracle(args,box);self.assertGreaterEqual(F(c['upper_product']),max(v for _,v in vals));self.assertLessEqual(F(c['upper_product']),F(ev['upper_product']))
   q={s:F(v) for s,v in c['repaired_quantities'].items()};self.assertEqual(set(q),set(p['ids']));self.assertLessEqual(sum(p['cost'][s]*q[s] for s in q),p['spendable'])
   with patch.object(m,'optimize',side_effect=AssertionError('no optimizer')),patch('scipy.optimize.minimize',side_effect=AssertionError('no solver')):m.verify(c,expected_binding_sha256=c['binding_sha256'])

 def test_containment_source_and_canonical_attacks(self):
  from test_quantity_continuous_anchor_bound import setup,diag
  src=setup();good={s:0.0 for s in src['box']};c=m.from_candidate(**src,candidate=good,diagnostics=diag())
  for kind in ('outside','foreign_inputs','forged_inherited'):
   x=deepcopy(src)
   if kind=='outside':x['box']['A'][1]+=1
   elif kind=='foreign_inputs':x['inputs']['entered_cash']='99'
   else:x['inherited_evidence']['upper_product']='0'
   with self.subTest(kind=kind),self.assertRaises(ValueError):m.from_candidate(**x,candidate=good,diagnostics=diag())
  for field,value in [('lower_bound_updated',0),('data_authenticated',0),('executable_portfolio',True),('upper_product','0')]:
   bad=deepcopy(c);bad[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):m.verify(bad,expected_binding_sha256=c['binding_sha256'])
  with self.assertRaises(ValueError):m.verify(c,expected_binding_sha256='0'*64)

 def test_actual_tiny_solver_and_verifier_never_calls_solver(self):
  from test_quantity_continuous_anchor_bound import setup
  src=setup();c=m.optimize(**src)
  self.assertGreaterEqual(F(c['upper_product']),max(v for _,v in oracle(src['inputs'])))
  with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):m.verify(c,expected_binding_sha256=c['binding_sha256'])
  self.assertFalse(c['solver_optimality_trusted']);self.assertFalse(c['lower_bound_updated'])

if __name__=='__main__':unittest.main()
