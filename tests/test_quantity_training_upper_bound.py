"""Check relaxation bounds against complete tiny integer domains."""
from fractions import Fraction as F
from itertools import product
import unittest

from backtest.quantity_training_upper_bound import training_product_upper_bound, public_bound


class TrainingBoundTests(unittest.TestCase):
    def test_every_candidate_bounds_exhaustive_feasible_domain(self):
        for fee, buffer in [(F(0), F(0)), (F(1, 100), F(1)), (F(0), F(20))]:
            args = dict(cash=F(12), fee=fee, buffer=buffer, prices={'A': F(2), 'B': F(3)},
                        scenarios=[{'A': F(2), 'B': F(1, 2)}, {'A': F(1, 3), 'B': F(3)}])
            feasible = []
            for a, b in product(range(7), range(5)):
                residual = F(12)-(2*a+3*b)*(1+fee)
                if residual < 0 or (a+b and residual < buffer):
                    continue
                quantity = {sid: q for sid, q in [('A', a), ('B', b)] if q}
                # Independent direct terminal wealth/product calculation.
                value = ((residual+4*a+F(3, 2)*b)/12)*((residual+F(2, 3)*a+9*b)/12)
                feasible.append((quantity, value))
            optimum = max(value for _, value in feasible)
            for quantity, value in feasible:
                bound = training_product_upper_bound(**args, quantities=quantity)
                self.assertEqual(bound['candidate_product'], value)
                self.assertGreaterEqual(bound['product_upper_bound'], optimum)
                if bound['objective_value_optimal']:
                    self.assertEqual(value, optimum)

    def test_interior_global_objective_certificate_and_nonoptimal_bound(self):
        args = dict(cash=100, fee=0, buffer=0, prices={'A': 1},
                    scenarios=[{'A': F(2)}, {'A': F(1, 2)}])
        optimum = training_product_upper_bound(**args, quantities={'A': 50})
        self.assertTrue(optimum['objective_value_optimal'])
        self.assertEqual(optimum['product_upper_bound'], F(9, 8))
        self.assertEqual(optimum['product_ratio_upper_bound'], 1)
        poor = training_product_upper_bound(**args, quantities={'A': 100})
        self.assertFalse(poor['objective_value_optimal'])
        self.assertGreaterEqual(poor['product_upper_bound'], F(9, 8))
        self.assertFalse(public_bound(optimum)['tie_break_optimality_established'])

    def test_cash_optimum_and_invalid_candidate(self):
        args = dict(cash=10, fee=F(1, 100), buffer=0, prices={'A': 1}, scenarios=[{'A': F(1)}])
        self.assertTrue(training_product_upper_bound(**args, quantities={})['objective_value_optimal'])
        for quantity in [{'A': 11}, {'UNKNOWN': 1}, {'A': -1}]:
            with self.assertRaises(ValueError):
                training_product_upper_bound(**args, quantities=quantity)


if __name__ == '__main__':
    unittest.main()
