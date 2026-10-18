import importlib,os
from fractions import Fraction
import unittest
module=importlib.import_module(os.environ.get('CASH_RATIO_MODULE','backtest.ndx_cash_neighbor_combined_stream_selection_v2_research'))

class Tests(unittest.TestCase):
    def test_real_saved_old_and_new_scores(self):
        # OLD results.json SHA1192aa5876b8ea9e36c84ad33d88f5504df849e8612312f1886fad6b579351fb,
        # /rows/0/feasible_scores/0; row SHA4fec51c475663a931eee6363ed58be5cda8ce9920c844ca3fa0339112ca7ee19.
        # NEW shard-00000.json SHAc5519d290e6d20852c4de8e909a14414ec9119ca2146274a207be8864d08a8ec,
        # /task_results/1/original_target_stock_weight_l1. Complete census retained in tmp sidecar.
        examples=[
            {'distance':{'numerator':'3945764054870605398','denominator':'2391482033538818299'},
             'fees_usd':{'numerator':'38068000793457031','denominator':'100000000000000000'}},
            {'distance':{'numerator':3979406056213378838,'denominator':2408303034210205019},
             'fees_usd':{'numerator':54889001464843751,'denominator':100000000000000000}},
        ]
        for example in examples:
            for value in example.values():
                self.assertEqual(module.ratio(value),Fraction(int(value['numerator']),int(value['denominator'])))

    def test_exact_canonical_nonnegative_components_only(self):
        for bad in (True,False,0.0,1.0,-1,'-1','-0','+1','01','',' 1','1 ','1.0','1e2','١','１',None):
            for field in ('numerator','denominator'):
                value={'numerator':1,'denominator':2};value[field]=bad
                with self.subTest(field=field,bad=bad),self.assertRaises(ValueError):module.ratio(value)
        for zero in (0,'0'):
            with self.assertRaises(ValueError):module.ratio({'numerator':1,'denominator':zero})
        self.assertEqual(module.ratio({'numerator':'9007199254740993','denominator':7}),Fraction(9007199254740993,7))
        self.assertEqual(module.ratio({'numerator':0,'denominator':'1'}),0)
        with self.assertRaises(ValueError):module.integer('1')

if __name__=='__main__':unittest.main()
