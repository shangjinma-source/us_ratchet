from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import unittest
from backtest import quantity_continuous_anchor_bound as m
from backtest import quantity_multi_anchor_bound_prototype as multi
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_prototype import fixture,oracle

def setup(args=None):
    args=args or fixture();p=core.prepare(**args)
    box={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
    return dict(inputs=args,box=box,inherited_evidence=multi.bound(inputs=args,box=box,incumbent={}))
def diag():return dict(success=False,status=9,iterations=1,message='deliberately unsuccessful')

class ContinuousTests(unittest.TestCase):
    def test_synthetic_solver_oracle_and_no_verify_solver(self):
        for fee in ('0','25','9999'):
            args=fixture();args['fee_bps']=fee;src=setup(args)
            c=m.optimize(**src)
            self.assertEqual(set(c['repaired_quantities']),set(args['prices']))
            self.assertGreaterEqual(F(c['upper_product']),max(v for v,_ in oracle(args)))
            self.assertLessEqual(F(c['upper_product']),F(src['inherited_evidence']['upper_product']))
            with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER IN VERIFY')):m.verify(c,expected_binding_sha256=c['binding_sha256'])
    def test_exact_repair_failed_solver_and_containing_box(self):
        src=setup();src['box']=dict(src['box'],C=[1,4])
        c=m.from_candidate(**src,candidate={s:999.0 for s in 'ABC'},diagnostics=diag());p=core.prepare(**src['inputs'])
        q={s:F(v) for s,v in c['repaired_quantities'].items()}
        self.assertLessEqual(sum(p['cost'][s]*q[s] for s in q),p['spendable'])
        self.assertGreaterEqual(q['C'],1);self.assertFalse(c['solver_diagnostics']['success'])
        self.assertGreaterEqual(F(c['upper_product']),max(v for v,_ in oracle(src['inputs'],src['box'])))
        m.verify(c,expected_binding_sha256=c['binding_sha256'])
    def test_bad_vectors_and_attacks(self):
        src=setup();good={s:0.0 for s in 'ABC'}
        for candidate in ({'A':0.0},dict(good,A=float('nan')),dict(good,A=float('inf')),dict(good,A=-1.0),dict(good,A=False)):
            with self.assertRaises(ValueError):m.from_candidate(**src,candidate=candidate,diagnostics=diag())
        c=m.from_candidate(**src,candidate=good,diagnostics=diag())
        for key,val in [('solver_optimality_trusted',0),('executable_portfolio',0),('upper_product','0'),('settings',{})]:
            bad=deepcopy(c);bad[key]=val
            with self.assertRaises(ValueError):m.verify(bad,expected_binding_sha256=c['binding_sha256'])
        bad=deepcopy(c);bad['anchor']['wealth'][0]='0'
        with self.assertRaises(ValueError):m.verify(bad,expected_binding_sha256=c['binding_sha256'])
        bad=deepcopy(src);bad['inherited_evidence']['upper_product']='0'
        with self.assertRaises(ValueError):m.from_candidate(**bad,candidate=good,diagnostics=diag())
    def test_cash_only_negative_coefficients_and_empty(self):
        args=fixture();args['minimum_cash_buffer']='20';src=setup(args)
        c=m.optimize(**src);self.assertEqual(c['upper_product'],'1')
        args=fixture();args['training_scenarios']=[dict(A='1',B='.5',C='.9')];c=m.optimize(**setup(args));self.assertGreaterEqual(F(c['upper_product']),1)
        src=setup();src['box']=dict(src['box'],A=[1,1],B=[1,1])
        with patch('scipy.optimize.minimize',side_effect=AssertionError('EMPTY NO SOLVER')):c=m.optimize(**src)
        self.assertTrue(c['empty']);m.verify(c,expected_binding_sha256=c['binding_sha256'])

if __name__=='__main__':unittest.main()
