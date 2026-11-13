from fractions import Fraction as F
import unittest
from core.usmart_standard_fees import estimate_base_fee, affordable_integer_buy


class StandardFeeTests(unittest.TestCase):
    def test_quantity_boundary_no_promotion(self):
        for quantity, expected in [('0.9999', '0.99'), (1, '1.88'), ('1.5', '1.88')]:
            self.assertEqual(F(estimate_base_fee(quantity=quantity, price_usd=300)['platform_fee_reserve_usd']), F(expected))

    def test_minimum_cap_and_large_orders(self):
        for quantity, price, expected in [(1, 1, '1.88'), (1000, '0.5', '5'), (1000, 100, '9'), (211, 100, '1.90')]:
            self.assertEqual(F(estimate_base_fee(quantity=quantity, price_usd=price)['platform_fee_reserve_usd']), F(expected))

    def test_cash_boundaries(self):
        for cash, other, quantity in [('1000', '0', 9), ('1001.88', '0', 10), ('1001.88', '0.01', 9), ('100', '0', 0)]:
            result = affordable_integer_buy(cash_usd=cash, target_quantity=10, limit_price_usd=100, other_fee_reserve_usd=other)
            self.assertEqual(result['quantity'], quantity)
            self.assertGreaterEqual(F(result['remaining_cash']), 0)
            self.assertFalse(result['executable'])
            if not quantity:
                self.assertEqual(result['estimated_cash_required'], '0')

    def test_invalid_quantity(self):
        for quantity in [0, -1, True, 1.2]:
            with self.assertRaises(ValueError):
                estimate_base_fee(quantity=quantity, price_usd=100)

    def test_maximal_affordable_quantity(self):
        for price in ['0.1', '1', '100', '344.77']:
            for cash in ['0', '1.88', '100', '1000', '38064.83']:
                result = affordable_integer_buy(cash_usd=cash, target_quantity=1000, limit_price_usd=price, other_fee_reserve_usd='0.1')
                quantity = result['quantity']
                self.assertLessEqual(F(result['estimated_cash_required']), F(cash))
                if quantity < 1000:
                    fee = F(estimate_base_fee(quantity=quantity+1, price_usd=price)['platform_fee_reserve_usd'])
                    self.assertGreater((quantity+1)*F(price)+fee+F('0.1'), F(cash))


if __name__ == '__main__':
    unittest.main()
