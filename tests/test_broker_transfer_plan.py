import unittest
from fractions import Fraction as F
from core.broker_transfer_plan import plan_usmart_funding, fit_integer_buys
from core.usmart_standard_fees import estimate_base_fee


class FundingPlanTests(unittest.TestCase):
    def plan(self, **changes):
        args = dict(hsbc_cash='1000', usmart_cash='0',
                    buys=[dict(symbol='ABC', quantity=2, limit_price='100')],
                    other_fee_reserve='2', transfer_fee_reserve='5',
                    hsbc_waiver_exhausted=True)
        args.update(changes)
        return plan_usmart_funding(**args)

    def test_transfer_does_not_create_available_cash(self):
        result = self.plan()
        self.assertEqual(F(result['proposed_transfer_credit_usd']), F('203.88'))
        self.assertEqual(F(result['hsbc_remaining_if_funded_usd']), F('791.12'))
        self.assertEqual(result['confirmed_usmart_cash_usd'], '0')
        self.assertFalse(result['executable'])

    def test_already_funded_no_transfer_fee(self):
        result = self.plan(usmart_cash='300')
        self.assertEqual(result['hsbc_debit_budget_usd'], '0')

    def test_insufficient_cash_not_negative_plan(self):
        result = self.plan(hsbc_cash='100')
        self.assertEqual(result['status'], 'INSUFFICIENT_TOTAL_CASH')
        self.assertIsNone(result['hsbc_remaining_if_funded_usd'])

    def test_preserve_free_hsbc_priority(self):
        with self.assertRaises(ValueError):
            self.plan(hsbc_waiver_exhausted=False)

    def test_duplicate_order_rejected(self):
        with self.assertRaises(ValueError):
            self.plan(buys=[dict(symbol='ABC', quantity=1, limit_price='10')]*2)

    def test_empty_plan_no_reserves(self):
        self.assertEqual(self.plan(buys=[])['hsbc_debit_budget_usd'], '0')

    def test_minimum_hsbc_cash_cannot_fund_buys(self):
        result = self.plan(hsbc_cash='38064.83', hsbc_minimum_cash='1300',
                           buys=[dict(symbol='ABC',quantity=1,limit_price='37000')])
        self.assertEqual(result['status'], 'INSUFFICIENT_TOTAL_CASH')
        self.assertEqual(F(result['maximum_transfer_credit_usd']), F('36759.83'))
        self.assertIsNone(result['hsbc_remaining_if_funded_usd'])

    def test_scaled_basket_respects_cash_fees_and_original_targets(self):
        original=[dict(symbol='A',quantity=12,limit_price='311.50'),
                  dict(symbol='B',quantity=28,limit_price='131.71'),
                  dict(symbol='C',quantity=7,limit_price='535.54')]
        for budget in ('0','25','100','1000','5000','10000','20000'):
            rows=fit_integer_buys(buys=original,available_cash=budget,other_fee_reserve='25')
            amount=F(25) if rows else F(0)
            for row in rows:
                maximum=next(item['quantity'] for item in original if item['symbol']==row['symbol'])
                self.assertGreater(row['quantity'],0)
                self.assertLessEqual(row['quantity'],maximum)
                amount+=row['quantity']*F(row['limit_price'])+F(estimate_base_fee(
                    quantity=row['quantity'],price_usd=row['limit_price'])['platform_fee_reserve_usd'])
            self.assertLessEqual(amount,F(budget))
        self.assertEqual([row['quantity'] for row in original],[12,28,7])
