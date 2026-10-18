import unittest
from copy import deepcopy
from fractions import Fraction as F
from scripts.diagnose_saved_daily_sell_pairs import sell_pair

class SellPairTests(unittest.TestCase):
    def history(self):
        return [dict(open='10',close='10',low='9',high='11') for _ in range(6)]
    def test_strict_touch_expiry_and_inventory_not_cash(self):
        result=sell_pair(self.history(),dict(open='10',low='9',high='11',close='9'),3)
        self.assertEqual(result['limit'],'11');self.assertEqual(result['premium_status'],'EXPIRED_UNSOLD')
        self.assertEqual(result['premium_cash'],'0');self.assertEqual(result['unsold_mark'],'27')
        self.assertEqual(result['marked_opportunity_difference'],'-3')
    def test_open_better_limit_and_strict_intraday_cross(self):
        for opening,high,price in [('12','13','12'),('11','12','11'),('10','12','11')]:
            r=sell_pair(self.history(),dict(open=opening,high=high,low='9',close='10'),2)
            self.assertEqual(r['premium_price'],price);self.assertEqual(r['unsold_quantity'],0)
    def test_median_not_mean_causal_no_mutation_and_ceil(self):
        history=self.history();history[-1]['high']='100';before=deepcopy(history)
        r=sell_pair(history,dict(open='10',high='12',low='9',close='10'),1)
        self.assertEqual(r['median_five_tr'],'2');self.assertEqual(history,before)
        history=[dict(open='10.001',close='10.001',low='10',high='10.003') for _ in range(6)]
        a=sell_pair(history,dict(open='10',high='11',low='9',close='10'),1)
        b=sell_pair(history,dict(open='20',high='21',low='19',close='20'),1)
        self.assertEqual(a['limit'],str(F('10.01')));self.assertEqual(a['limit'],b['limit'])
    def test_bad_bars_and_missing_window_refuse(self):
        with self.assertRaises(ValueError):sell_pair(self.history()[:5],self.history()[0],1)
        with self.assertRaises(ValueError):sell_pair(self.history(),dict(open='10',high='9',low='8',close='10'),1)

if __name__=='__main__':unittest.main()
