from fractions import Fraction as F
from itertools import product
from copy import deepcopy
import json
from math import prod
import unittest
from backtest.quantity_integer_box_certificate_prototype import prepare,objective,box_bound,solve,verify


def fixture():
    return dict(prices={'A':'2','B':'3','C':'1'},metadata={s:dict(ticker=s,issuer_id=('one' if s in 'AB' else 'two')) for s in 'ABC'},entered_cash='7',fee_bps='25',minimum_cash_buffer='1',training_scenarios=[{'A':'1.3','B':'.9','C':'1.1'},{'A':'.8','B':'1.4','C':'1.05'}])


def oracle(args,box=None):
    p=prepare(**args);ids=p['ids'];box=box or {s:[0,int(p['spendable']//p['cost'][s])] for s in ids};rows=[]
    for point in product(*(range(box[s][0],box[s][1]+1) for s in ids)):
        q={s:n for s,n in zip(ids,point) if n}
        if len({args['metadata'][s]['issuer_id'] for s in q})!=len(q):continue
        cash=F(args['entered_cash']);fee=F(args['fee_bps'])/10000
        residual=cash-sum((F(args['prices'][s])*n*(1+fee) for s,n in q.items()),F(0))
        if residual<0 or (q and residual<F(args['minimum_cash_buffer'])):continue
        v=prod((residual+sum((F(args['prices'][s])*n*F(r[s]) for s,n in q.items()),F(0)))/cash for r in args['training_scenarios'])
        rows.append((v,q))
    return rows


class BoxCertificateTests(unittest.TestCase):
    def test_falsey_invalid_incumbent_and_authority_tamper_rejected(self):
        for initial in ([],0,False,''):
            with self.subTest(initial=initial),self.assertRaises(ValueError):solve(**fixture(),node_budget=0,initial_quantities=initial)
        result=solve(**fixture(),node_budget=1)
        for key,value in [('schema','OTHER'),('objective','RETURN'),('scope','ALL_MARKETS'),('data_authenticated',True),('future_performance_guaranteed',True),('node_budget',True),('processed_nodes',True),('objective_value_optimal',0)]:
            changed=deepcopy(result);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):verify(changed,expected_input_sha256=result['input_sha256'])

    def test_full_domain_matches_independent_integer_enumeration(self):
        for fee in ('0','25','9999'):
            args=fixture();args['fee_bps']=fee
            with self.subTest(fee=fee):
                result=solve(**args,node_budget=1000)
                self.assertEqual(F(result['lower_product']),max(v for v,_ in oracle(args)))
                self.assertTrue(result['objective_value_optimal'])
                self.assertFalse(result['tie_break_optimality_established'])
                self.assertTrue(verify(json.loads(json.dumps(result)),expected_input_sha256=result['input_sha256'])['complete'])

    def test_every_tiny_box_bound_covers_oracle_for_different_anchors(self):
        args=fixture();p=prepare(**args);ranges={s:list(product(range(3),repeat=2)) for s in p['ids']}
        for pairs in product(*(ranges[s] for s in p['ids'])):
            if any(lo>hi for lo,hi in pairs):continue
            box={s:list(pair) for s,pair in zip(p['ids'],pairs)};rows=oracle(args,box)
            for anchor in ({},{'A':1},{'C':2}):
                bound=box_bound(p,box,anchor)
                if bound['empty']:self.assertFalse(rows)
                elif rows:self.assertGreaterEqual(F(bound['upper']),max(v for v,_ in rows))

    def test_budget_zero_one_return_explicit_unsearched_domain(self):
        for budget in (0,1):
            result=solve(**fixture(),node_budget=budget)
            self.assertFalse(result['objective_value_optimal']);self.assertTrue(result['unsearched_frontier'])
            self.assertLessEqual(F(result['lower_product']),max(v for v,_ in oracle(fixture())))
            self.assertGreaterEqual(F(result['upper_product']),max(v for v,_ in oracle(fixture())))
            self.assertFalse(verify(result,expected_input_sha256=result['input_sha256'])['complete'])

    def test_cash_only_buffer_and_zero_negative_coefficients(self):
        for buffer in ('20','0'):
            args=fixture();args['minimum_cash_buffer']=buffer;args['training_scenarios']=[{'A':'1','B':'.8','C':'.9'}];args['fee_bps']='0'
            result=solve(**args,node_budget=1000)
            self.assertEqual(result['selected'],{});self.assertEqual(result['lower_product'],'1')
            self.assertTrue(verify(result,expected_input_sha256=result['input_sha256'])['complete'])

    def test_tampered_frontier_bound_and_inputs_rejected(self):
        result=solve(**fixture(),node_budget=1)
        for kind in ('omit','bound','input','claim'):
            changed=deepcopy(result)
            if kind=='omit':changed['unsearched_frontier'].pop()
            elif kind=='bound':changed['unsearched_frontier'][0]['bound']['upper']='0'
            elif kind=='input':changed['inputs']['entered_cash']='9'
            else:changed['objective_value_optimal']=True
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify(changed,expected_input_sha256=result['input_sha256'])


if __name__=='__main__':unittest.main()
