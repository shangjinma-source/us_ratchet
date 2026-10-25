"""Independent exact enumeration of synthetic domains; no economic data."""
from copy import deepcopy
from fractions import Fraction as F
from itertools import product
from math import prod
from random import Random
import unittest
from backtest import quantity_integer_box_certificate_prototype as cert


def oracle(args,box=None):
    ids=sorted(args['prices']);cash=F(args['entered_cash']);fee=F(args['fee_bps'])/10000;buffer=F(args['minimum_cash_buffer'])
    prices={s:F(args['prices'][s]) for s in ids};spendable=max(F(0),cash-buffer);rows=[]
    for qs in product(*(range(*( [box[s][0],box[s][1]+1] if box else [0,int(spendable//(prices[s]*(1+fee)))+1])) for s in ids)):
        q={s:n for s,n in zip(ids,qs) if n};issuers=[args['metadata'][s]['issuer_id'] for s in q]
        if len(set(issuers))!=len(issuers):continue
        residual=cash-sum((prices[s]*n*(1+fee) for s,n in q.items()),F(0))
        if residual<0 or (q and residual<buffer):continue
        value=prod((residual+sum((prices[s]*n*F(row[s]) for s,n in q.items()),F(0)))/cash for row in args['training_scenarios'])
        rows.append((q,value))
    return rows


class IndependentIntegerCertificateTests(unittest.TestCase):
    def test_random_tiny_exhaustive_bounds_and_budget(self):
        rng=Random(20261019)
        for index in range(35):
            ids=['A','B','C'];args=dict(prices={s:str(rng.randint(2,6)) for s in ids},metadata={s:dict(ticker=s,issuer_id=('shared' if index%3==0 and s!='C' else s)) for s in ids},entered_cash=str(rng.randint(5,15)),fee_bps=str(rng.choice([0,25,1000])),minimum_cash_buffer=str(rng.randint(0,6)),training_scenarios=[{s:str(F(rng.randint(1,8),4)) for s in ids} for _ in range(3)])
            feasible=oracle(args);best=max(v for _,v in feasible)
            result=cert.solve(**args,node_budget=10000)
            self.assertEqual(F(result['lower_product']),best)
            self.assertTrue(cert.verify(result,expected_input_sha256=result['input_sha256'])['complete'])
            p=cert.prepare(**args)
            for node in result['coverage_ledger']:
                values=oracle(args,node['box']);bound=node['bound']
                if bound['empty']:self.assertEqual(values,[])
                elif values:self.assertGreaterEqual(F(bound['upper']),max(v for _,v in values))
            cut=cert.solve(**args,node_budget=0)
            self.assertFalse(cert.verify(cut,expected_input_sha256=cut['input_sha256'])['complete'])
            self.assertGreaterEqual(F(cut['upper_product']),best)
            self.assertFalse(cut['objective_value_optimal'])

    def test_forged_tree_and_metadata_rejected(self):
        args=dict(prices={'A':'2','B':'3'},metadata={s:dict(ticker=s,issuer_id=s) for s in ['A','B']},entered_cash='10',fee_bps='10',minimum_cash_buffer='1',training_scenarios=[{'A':'2','B':'1/2'},{'A':'1/2','B':'2'}])
        result=cert.solve(**args,node_budget=10000);expected=result['input_sha256']
        mutations=[lambda c:c['coverage_ledger'].pop(),lambda c:c.update(lower_product='999'),lambda c:c.update(data_authenticated=True),lambda c:c.update(node_budget=True),lambda c:c['inputs'].update(fee_bps='0'),lambda c:c['coverage_ledger'][0].update(children=['r0','r0'])]
        for mutate in mutations:
            c=deepcopy(result);mutate(c)
            with self.assertRaises((ValueError,KeyError)):cert.verify(c,expected_input_sha256=expected)
        for q in ([],False,{'A':True},{'A':-1},{'C':1}):
            with self.assertRaises(ValueError):cert.solve(**args,node_budget=5,initial_quantities=q)
