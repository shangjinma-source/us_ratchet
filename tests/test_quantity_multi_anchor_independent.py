from copy import deepcopy
from fractions import Fraction as F
from random import Random
import unittest
from backtest import quantity_multi_anchor_bound_prototype as multi
from test_quantity_integer_box_certificate_independent import oracle

class MultiAnchorIndependent(unittest.TestCase):
    def test_random_boxes_against_independent_integer_enumeration(self):
        rng=Random(117)
        for index in range(70):
            ids=['A','B','C'];args=dict(prices={s:str(rng.randint(1,5)) for s in ids},metadata={s:dict(ticker=s,issuer_id='shared' if index%2==0 and s!='C' else s) for s in ids},entered_cash=str(rng.randint(5,15)),fee_bps=str(rng.choice([0,50,1000])),minimum_cash_buffer=str(rng.randint(0,4)),training_scenarios=[{s:str(F(rng.randint(1,8),4)) for s in ids} for _ in range(3)])
            p=multi.core.prepare(**args);incumbent=rng.choice(oracle(args))[0];box={}
            for s in ids:
                hi=int(p['spendable']//p['cost'][s]);lo=rng.randint(0,hi);box[s]=[lo,rng.randint(lo,hi)]
            evidence=multi.bound(inputs=args,box=box,incumbent=incumbent);values=oracle(args,box)
            multi.verify(evidence,expected_binding_sha256=evidence['binding_sha256'])
            if evidence['empty']:self.assertEqual(values,[])
            else:
                self.assertEqual(len(evidence['anchors']),4)
                self.assertLessEqual(F(evidence['upper_product']),F(evidence['old_bound']['upper']))
                if values:self.assertGreaterEqual(F(evidence['upper_product']),max(v for _,v in values))
                for a in evidence['anchors']:
                    if values:self.assertGreaterEqual(F(a['upper_product']),max(v for _,v in values))
                    self.assertFalse(a['executable_portfolio'])

    def test_fractional_shared_issuer_outside_box_zero_cash_and_negative_gradients(self):
        args=dict(prices={'A':'2','B':'2'},metadata={s:dict(ticker=s,issuer_id='same') for s in 'AB'},entered_cash='5',fee_bps='2500',minimum_cash_buffer='0',training_scenarios=[{'A':'1/2','B':'1/3'},{'A':'1/4','B':'1/2'}])
        p=multi.core.prepare(**args);box={'A':[0,0],'B':[0,1]}
        # Reference violates integer/issuer/box rules but has zero residual cash
        # and strictly positive scenario wealth. It is only an upper anchor.
        a=multi.anchor_bound(p,box,{'A':'1/2','B':'3/2'})
        self.assertTrue(all(F(v)<0 for v in a['linear_coefficients'].values()))
        self.assertEqual(a['linear_extreme'],{'A':'0','B':'0'})
        self.assertGreaterEqual(F(a['upper_product']),max(v for _,v in oracle(args,box)))
        for quantities in ({'A':True,'B':0},{'A':'-1','B':'0'},{'A':'3','B':'0'}):
            with self.assertRaises(ValueError):multi.anchor_bound(p,box,quantities)

    def test_evidence_tampering_and_external_digest(self):
        args=dict(prices={'A':'2'},metadata={'A':dict(ticker='A',issuer_id='A')},entered_cash='5',fee_bps='0',minimum_cash_buffer='0',training_scenarios=[{'A':'2'},{'A':'1/2'}])
        evidence=multi.bound(inputs=args,box={'A':[0,2]},incumbent={});h=evidence['binding_sha256']
        for mutation in (lambda x:x.update(upper_product='0'),lambda x:x.update(executable_portfolio=True),lambda x:x['anchors'][1]['wealth'].__setitem__(0,'0'),lambda x:x['anchors'][0]['linear_extreme'].update(A='0'),lambda x:x['binding']['box'].update(A=[0,1])):
            x=deepcopy(evidence);mutation(x)
            with self.assertRaises(ValueError):multi.verify(x,expected_binding_sha256=h)
        with self.assertRaises(ValueError):multi.verify(evidence,expected_binding_sha256='0'*64)
