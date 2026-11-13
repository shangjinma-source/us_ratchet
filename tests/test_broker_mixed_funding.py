import unittest
from fractions import Fraction as F

from core.broker_transfer_plan import plan_mixed_funding


class MixedFundingTests(unittest.TestCase):
    def plan(self, **changes):
        arguments = dict(hsbc_cash='5000', usmart_cash='0',
            buys=[dict(symbol='A', quantity=20, limit_price='100')],
            hsbc_free_buy_budget_usd='1000', other_fee_reserve='5',
            transfer_fee_reserve='2', hsbc_minimum_cash='1300')
        arguments.update(changes)
        return plan_mixed_funding(**arguments)

    def test_split_without_duplicate_capital(self):
        result = self.plan()
        self.assertEqual(result['planned_hsbc_buys'][0]['quantity'], 10)
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'], 10)
        self.assertEqual(F(result['hsbc_debit_budget_usd']), F('1008.88'))
        self.assertEqual(F(result['hsbc_remaining_if_funded_usd']), F('2986.12'))
        self.assertEqual(result['total_confirmed_cash_usd'], '5000')
        self.assertFalse(result['executable'])

    def test_transfer_floor_does_not_block_hsbc_investing(self):
        result = self.plan(hsbc_cash='1000', hsbc_free_buy_budget_usd='5000',
                           buys=[dict(symbol='A', quantity=9, limit_price='100')])
        self.assertEqual(result['planned_hsbc_buys'][0]['quantity'], 9)
        self.assertEqual(result['hsbc_debit_budget_usd'], '0')

    def test_budget_shortage_never_increases_target_or_spends_floor_on_transfer(self):
        for cash in ('0', '100', '1300', '1500', '5000'):
            for quota in ('0', '99', '500', '5000'):
                result = self.plan(hsbc_cash=cash, hsbc_free_buy_budget_usd=quota)
                quantities = sum(row['quantity'] for key in
                    ('planned_hsbc_buys', 'planned_usmart_buys') for row in result[key])
                self.assertLessEqual(quantities, 20)
                debit = F(result['hsbc_debit_budget_usd'])
                self.assertLessEqual(debit+F(result['hsbc_buy_budget_usd']), F(cash))
                if debit:
                    self.assertGreaterEqual(F(cash)-debit, 1300)

    def test_existing_usmart_cash_not_transferred_again(self):
        result = self.plan(usmart_cash='2000')
        self.assertEqual(result['hsbc_debit_budget_usd'], '0')

    def test_duplicate_rejected_and_inputs_preserved(self):
        orders = [dict(symbol='A', quantity=20, limit_price='100')]
        self.plan(buys=orders)
        self.assertEqual(orders[0]['quantity'], 20)
        with self.assertRaises(ValueError):
            self.plan(buys=orders*2)
