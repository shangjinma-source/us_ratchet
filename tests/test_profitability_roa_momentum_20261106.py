import unittest
from fractions import Fraction as F
from scripts.research.screen_profitability_roa_momentum_20261106 import percentiles,build_decision
class RankTests(unittest.TestCase):
 def test_ties_average_rank(self):self.assertEqual(percentiles({'a':F(1),'b':F(1),'c':F(2)}),{'a':F(1,2),'b':F(1,2),'c':F(1)})
 def test_higher_is_better(self):
  p=percentiles({'a':F(-1),'b':F(0),'c':F(3)});self.assertLess(p['a'],p['b']);self.assertLess(p['b'],p['c'])
 def test_empty_single(self):self.assertEqual(percentiles({}),{});self.assertEqual(percentiles({'a':F(1)}),{'a':F(1)})
if __name__=='__main__':unittest.main()
