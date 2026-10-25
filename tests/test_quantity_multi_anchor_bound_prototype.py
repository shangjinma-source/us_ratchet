from copy import deepcopy
from fractions import Fraction as F
from itertools import product
import json
import unittest
from backtest.quantity_multi_anchor_bound_prototype import bound,verify,anchor_bound
from backtest.quantity_integer_box_certificate_prototype import prepare
from test_quantity_integer_box_certificate_prototype import fixture,oracle


class MultiAnchorTests(unittest.TestCase):
    def test_tiny_boxes_independent_oracle_and_never_looser(self):
        for fee in ('0','25','9999'):
            args=fixture();args['fee_bps']=fee
            for pairs in product(((0,0),(0,1),(1,2)),repeat=3):
                box={s:list(pair) for s,pair in zip('ABC',pairs)}
                ev=bound(inputs=args,box=box,incumbent={})
                values=oracle(args,box)
                if ev['empty']:self.assertFalse(values);continue
                self.assertEqual(len(ev['anchors']),4)
                for previous,current in zip(ev['anchors'],ev['anchors'][1:]):
                    self.assertEqual({s:F(v) for s,v in current['quantities'].items()},{s:(F(previous['quantities'][s])+F(previous['linear_extreme'][s]))/2 for s in 'ABC'})
                self.assertLessEqual(F(ev['upper_product']),F(ev['old_bound']['upper']))
                if values:self.assertGreaterEqual(F(ev['upper_product']),max(v for v,_ in values))
                verify(json.loads(json.dumps(ev)),expected_binding_sha256=ev['binding_sha256'])

    def test_cash_only_and_negative_coefficients_and_fractional_issuer_relaxation(self):
        args=fixture();args['minimum_cash_buffer']='99';p=prepare(**args)
        ev=bound(inputs=args,box={s:[0,0] for s in 'ABC'},incumbent={});self.assertEqual(ev['upper_product'],'1')
        args=fixture();args['training_scenarios']=[{'A':'.8','B':'1','C':'.9'}];args['fee_bps']='0';p=prepare(**args)
        ev=bound(inputs=args,box={s:[0,1] for s in 'ABC'},incumbent={});self.assertEqual(ev['upper_product'],'1')
        # A and B share issuer: fractional reference is a bound anchor only.
        item=anchor_bound(p,{s:[0,1] for s in 'ABC'},{'A':'1/2','B':'1/2','C':'0'})
        self.assertFalse(item['executable_portfolio']);self.assertTrue(all(F(w)>0 for w in item['wealth']))

    def test_invalid_anchor_and_evidence_tamper(self):
        args=fixture();p=prepare(**args);box={s:[0,1] for s in 'ABC'}
        for q in ({'A':'-1','B':'0','C':'0'},{'A':'100','B':'0','C':'0'},{'A':True,'B':'0','C':'0'}):
            with self.assertRaises(ValueError):anchor_bound(p,box,q)
        ev=bound(inputs=args,box=box,incumbent={})
        # Direct helper also rejects nonpositive wealth if an invalid prepared
        # problem is supplied, rather than relying only on prepare's guarantee.
        bad=deepcopy(p);bad['fee']=F(0);bad['cost']=bad['prices'];bad['scenarios']=[{s:F(0) for s in 'ABC'}]
        with self.assertRaisesRegex(ValueError,'ANCHOR_WEALTH_NOT_POSITIVE'):anchor_bound(bad,box,{'A':'7/2','B':'0','C':'0'})
        for kind in ('wealth','lp','upper','rule','authority','input'):
            changed=deepcopy(ev)
            if kind=='wealth':changed['anchors'][0]['wealth'][0]='0'
            elif kind=='lp':changed['anchors'][0]['linear_extreme']['A']='100'
            elif kind=='upper':changed['upper_product']='0'
            elif kind=='rule':changed['rule']='TUNED'
            elif kind=='authority':changed['executable_portfolio']=True
            else:changed['binding']['inputs']['entered_cash']='9'
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify(changed,expected_binding_sha256=ev['binding_sha256'])

if __name__=='__main__':unittest.main()
