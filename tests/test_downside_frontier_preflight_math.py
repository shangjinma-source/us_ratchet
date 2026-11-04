import unittest
from fractions import Fraction as F
from decimal import Decimal
from scripts.research.preflight_downside_frontier_20261105 import bounds,classify

class Tests(unittest.TestCase):
    def test_bounds_enclose_exact_downside(self):
        values=[F(-1,3),F(2,7),F(-1234567,98765431),F(0)]*63
        exact=sum(min(x,F(0))**2 for x in values)/252
        low,high=bounds(values)
        self.assertLessEqual(F(low),exact);self.assertGreaterEqual(F(high),exact)
    def test_equal_boundary_uses_exact_comparison(self):
        values=[F(-1,3),F(1,7)]*126
        passes,exact,_=classify(values,values,bounds(values))
        self.assertTrue(passes);self.assertTrue(exact)
    def test_strictly_above_and_below(self):
        ref=[F(-1,100),F(1,100)]*126
        self.assertEqual(classify([x*2 for x in ref],ref,bounds(ref))[:2],(False,False))
        self.assertEqual(classify([x/2 for x in ref],ref,bounds(ref))[:2],(True,False))
    def test_zero_cash_returns_pass(self):
        ref=[F(-1,100)]*252
        self.assertEqual(classify([F(0)]*252,ref,bounds(ref))[:2],(True,False))
if __name__=='__main__':unittest.main()
