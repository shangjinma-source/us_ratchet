from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import unittest
from backtest.quantity_ancestor_bound_supplement import build,verify
from backtest.quantity_supplement_frontier_resume import resume
from backtest.quantity_box_supplemental_certificate import supplement
from test_quantity_box_supplemental_certificate import sources,raw
from test_quantity_integer_box_certificate_independent import oracle

class IndependentAncestorTests(unittest.TestCase):
    def test_shared_issuer_fee_buffer_oracle_and_parent_cap(self):
        for fee in ('0','500'):
            for buffer in ('0','1'):
                args=dict(prices={'A':'1','B':'2','C':'2'},metadata={s:dict(ticker=s,issuer_id='shared' if s in 'AB' else s) for s in 'ABC'},entered_cash='7',fee_bps=fee,minimum_cash_buffer=buffer,training_scenarios=[dict(A='2',B='1/2',C='3/2'),dict(A='1/2',B='3',C='2')])
                bs=sources(args);sr=raw(supplement(**bs));ctx=dict(supplement_raw=sr,expected_supplement_sha256=sha256(sr).hexdigest(),bound_sources=bs)
                for budget in (0,1,4,100):
                    c=resume(**ctx,additional_node_budget=budget);cr=raw(c);a=dict(continuation_raw=cr,expected_continuation_sha256=sha256(cr).hexdigest(),continuation_sources=ctx);result=build(**a);verify(result,**a)
                    self.assertGreaterEqual(F(result['upper_product']),max(v for _,v in oracle(args)))
                    self.assertLessEqual(F(result['upper_product']),F(c['upper_product']))
                    for row in result['rows']:
                        values=oracle(args,row['box'])
                        if row['empty']:self.assertEqual(values,[])
                        elif values:self.assertGreaterEqual(F(row['effective_upper_product']),max(v for _,v in values))
                        if not row['empty']:self.assertEqual(F(row['effective_upper_product']),min(F(x['upper_product']) for x in row['original_bounds']))
                    self.assertFalse(result['tie_break_optimality_established'])

    def test_external_sources_and_false_authority(self):
        from test_quantity_ancestor_bound_supplement import fixture_sources
        a,c=fixture_sources();result=build(**a)
        for field,value in [('objective_value_optimal',1),('parent_modified',0),('remaining_node_ids',[]),('future_performance_guaranteed',True)]:
            bad=deepcopy(result);bad[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):verify(bad,**a)
        bad=deepcopy(a);bad['continuation_sources']['expected_supplement_sha256']='0'*64
        with self.assertRaises(ValueError):build(**bad)

if __name__=='__main__':unittest.main()
