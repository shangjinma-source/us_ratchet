import random
import unittest
from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
from backtest import quantity_joint_anchor_loss as module
from backtest import quantity_integer_box_certificate_prototype as core
from test_quantity_integer_box_certificate_prototype import fixture,oracle


class IndependentJointLoss(unittest.TestCase):
    def test_seeded_oracle_identity_and_no_strict_improver_excluded(self):
        rng=random.Random(6119)
        for _ in range(20):
            args=fixture();args['fee_bps']=rng.choice(['0','25','3000']);args['minimum_cash_buffer']=rng.choice(['0','1','2'])
            args['training_scenarios']=[{s:str(F(rng.randint(2,19),10)) for s in 'ABC'} for _ in range(rng.randint(1,4))]
            p=core.prepare(**args);box={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
            points=oracle(args,box);incumbent=rng.choice(points)[1]
            anchor={s:str(F(incumbent.get(s,0),2)) for s in p['ids']}
            with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
                c=module.build(inputs=args,box=box,anchor_quantities=anchor,incumbent=incumbent,dual_lambda=rng.choice(['0','1/100','1/3','10']))
                module.verify(c,expected_binding_sha256=c['binding_sha256'])
                for value,q in points:
                    result=module.inspect_point(c,q)
                    if value>F(c['lower_product']):self.assertFalse(result['excluded_for_strict_improvement'])
                    if result['excluded_for_strict_improvement']:self.assertLessEqual(value,F(c['lower_product']))
                    self.assertEqual(F(result['loss']),F(c['linear_dual_upper'])-F(result['linear_sum']))

    def test_exact_threshold_boundaries_and_floor_direction(self):
        for degree in (1,2,3,7,20):
            for integer in (0,1,2,17):
                for offset in (F(0),F(1,11),F(10,11)):
                    value=(F(integer,10)+offset/10)**degree
                    if value==0:continue
                    t=module.floor_root_ratio(value,degree,10)
                    self.assertLessEqual(t**degree,value)
                    self.assertGreater((t+F(1,10))**degree,value)
        args=fixture();args['fee_bps']='0';args['training_scenarios']=[dict(A='1',B='1',C='1')]
        p=core.prepare(**args);box={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
        c=module.build(inputs=args,box=box,anchor_quantities={s:'0' for s in p['ids']},incumbent={},dual_lambda='0')
        self.assertEqual(F(c['strict_loss_budget']),0)
        self.assertTrue(module.inspect_point(c,{})['excluded_for_strict_improvement'])
        self.assertFalse(c['tie_break_optimality_established'])

    def test_external_binding_and_canonical_attack(self):
        args=fixture();p=core.prepare(**args);box={s:[0,int(p['spendable']//p['cost'][s])] for s in p['ids']}
        c=module.build(inputs=args,box=box,anchor_quantities={s:'0' for s in p['ids']},incumbent={},dual_lambda='0')
        for key,value in [('solver_calls',False),('scenario_count',True),('threshold_floor','1000'),('strict_loss_budget','-1000'),('preferred_endpoints',{})]:
            bad=deepcopy(c);bad[key]=value
            with self.assertRaises(ValueError):module.verify(bad,expected_binding_sha256=c['binding_sha256'])
        bad=deepcopy(c);bad['binding']['dual_lambda']='1';bad['binding_sha256']=module.digest(bad['binding'])
        with self.assertRaises(ValueError):module.verify(bad,expected_binding_sha256=c['binding_sha256'])

if __name__=='__main__':unittest.main()
