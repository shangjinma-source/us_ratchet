from fractions import Fraction as F
import unittest
from scripts.audit_saved_cardinality_competition import inspect_target, exact_product


class SavedCardinalityTests(unittest.TestCase):
    def fixture(self):
        return dict(quantities={'A':99,'B':1},actual_k=2,actual_weights={'A':'99/100','B':'1/100'},
            notional='100',residual_cash='0',fees='0',training_mean_net_log_wealth=0.2)

    def test_two_names_are_not_two_effective_positions(self):
        row=inspect_target(self.fixture(),{'A':F(1),'B':F(1)},F(100),{'A':{'ticker':'A'},'B':{'ticker':'B'}})
        self.assertEqual(row['actual_k'],2)
        self.assertEqual(row['top1_total_capital_weight'],'99/100')
        self.assertLess(F(row['effective_stock_count']),F('11/10'))

    def test_saved_cash_or_weights_tamper_rejected(self):
        for field,value in [('residual_cash','1'),('actual_weights',{'A':'1/2','B':'1/2'})]:
            target=self.fixture();target[field]=value
            with self.assertRaises(ValueError):inspect_target(target,{'A':F(1),'B':F(1)},F(100),{'A':{'ticker':'A'},'B':{'ticker':'B'}})

    def test_recompute_only_saved_target_with_residual_cash(self):
        target=dict(quantities={'A':1},training_gross_growth_product='64/25')
        args=dict(prices={'A':'6'},training_scenarios=[{'A':'2'},{'A':'2'}])
        self.assertEqual(exact_product(target,args,F(10)),F('64/25'))
        target['training_gross_growth_product']='4'
        with self.assertRaisesRegex(ValueError,'SAVED_PRODUCT'):exact_product(target,args,F(10))


if __name__=='__main__':unittest.main()
