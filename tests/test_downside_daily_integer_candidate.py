import unittest
from fractions import Fraction as F
from backtest.downside_daily_integer_candidate import ExactDailyReturnIntegers
from scripts.research.preflight_downside_frontier_20261105 import bounds,classify


class DailyIntegerTests(unittest.TestCase):
    def test_exact_mixed_correlated_cash_and_large_denominators(self):
        prices={'A':F(7,3),'B':F(11,7),'C':F(2,13)}
        returns={'A':[F(-1,3),F(2,7)]*126,'B':[F(1,11),F(-1,17)]*126,'C':[F(-1,10**90+7)]*252}
        helper=ExactDailyReturnIntegers(prices=prices,equity=100,stock_returns=returns)
        for q in ({},{'A':3},{'A':0,'B':5},{'A':2,'B':7,'C':11}):
            expected=[sum((F(n)*prices[s]/100*returns[s][i] for s,n in q.items()),F(0)) for i in range(252)]
            self.assertEqual(helper.portfolio_returns(q),expected)
        values=helper.portfolio_returns({'A':3})
        self.assertTrue(classify(values,values,bounds(values))[0])
        self.assertFalse(classify([v-F(1,10**95) for v in values],values,bounds(values))[0])

    def test_invalid_quantities_and_input(self):
        helper=ExactDailyReturnIntegers(prices={'A':1},equity=10,stock_returns={'A':[F(0)]*252})
        for q in ({'A':True},{'A':-1},{'A':1.5},{'X':1}):
            with self.assertRaises(ValueError):helper.portfolio_returns(q)
        with self.assertRaises(ValueError):ExactDailyReturnIntegers(prices={'A':1},equity=10,stock_returns={'A':[F(0)]*251})


if __name__=='__main__':unittest.main()
