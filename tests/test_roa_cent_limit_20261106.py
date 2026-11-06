import unittest
from fractions import Fraction
from data.roa_limit_policy import cent_last_price_limit
from data.roa_target_account_bridge import sequential_cash_allocation

class CentLimitTests(unittest.TestCase):
    def allocate(self,cash,limit):
        return sequential_cash_allocation(dict(status='READY',new_orders=[dict(side='BUY',security_id='X',quantity=1)],waiting_cash=[],spendable_cash=cash,binding={'fee_bps':'0','limits':{'X':limit}}))
    def test_fractional_quote_becomes_exact_display_cent(self):
        self.assertEqual(cent_last_price_limit('209.039993','OPEN'),{'buy':'209.04','sell':'209.04'})
        self.assertEqual(cent_last_price_limit('1.005','CLOSE')['buy'],'1.01')
        self.assertEqual(cent_last_price_limit('209.034','OPEN')['sell'],'209.03')
    def test_rounding_before_budget_prevents_displayed_price_overdraft(self):
        limit=cent_last_price_limit('209.039993','OPEN')
        result=self.allocate('209.039995',limit)
        self.assertEqual(result['new_orders'],[])
        self.assertEqual(result['waiting_cash'][0]['quantity'],1)
        self.assertEqual(Fraction(result['unallocated_spendable_cash']),Fraction('209.039995'))
        result=self.allocate('209.04',limit)
        self.assertEqual(result['new_orders'][0]['quantity'],1)
        self.assertEqual(Fraction(result['new_orders'][0]['limit_price']),Fraction('209.04'))
        self.assertEqual(Fraction(result['unallocated_spendable_cash']),0)
    def test_scope_and_float_refused(self):
        for price in ('0.999',True,209.04):
            with self.assertRaises(ValueError):cent_last_price_limit(price,'OPEN')
        with self.assertRaises(ValueError):cent_last_price_limit('200','MIDDAY')

if __name__=='__main__':unittest.main()
