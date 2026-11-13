import unittest
from fractions import Fraction as F
from core.broker_transfer_plan import plan_usmart_funding


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
