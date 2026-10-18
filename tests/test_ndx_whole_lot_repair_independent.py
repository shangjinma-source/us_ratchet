"""Independent rational-arithmetic checks for the research lot projection."""
from fractions import Fraction
from itertools import product
import math
import unittest

from backtest.ndx_whole_lot_repair_diagnostic import project_whole_lot_rebalance


class WholeLotRepairIndependentTests(unittest.TestCase):
    def test_rational_enumeration_and_bilateral_fee_conservation(self):
        for quantities in ((0, 0, 0), (9, 2, 5), (2, 15, 1)):
            with self.subTest(quantities=quantities):
                names = ("A", "B", "C")
                marks = dict(zip(names, (Fraction(103), Fraction(157), Fraction(211))))
                old = dict(zip(names, quantities))
                cash = Fraction(2500)
                buffer = Fraction(100)
                rate = Fraction(25, 10000)
                equity = cash + sum(old[name] * marks[name] for name in names)
                targets = {name: (equity - buffer) / 3 / marks[name] for name in names}
                options = [sorted({math.floor(targets[name]), math.ceil(targets[name])}) for name in names]
                feasible = []
                for vector in product(*options):
                    costs = sum(abs(vector[i] - old[name]) * marks[name] for i, name in enumerate(names)) * rate
                    invested = sum(vector[i] * marks[name] for i, name in enumerate(names))
                    residual = equity - invested - costs
                    if min(vector) < 1 or residual < buffer:
                        continue
                    weights = [vector[i] * marks[name] / invested for i, name in enumerate(names)]
                    if min(weights) < Fraction(5, 100):
                        continue
                    feasible.append(sum(abs(value - Fraction(1, 3)) for value in weights))
                result = project_whole_lot_rebalance(
                    current_shares=old, current_cash_usd=float(cash),
                    prices={name: float(value) for name, value in marks.items()},
                    target_weights={name: 1 / 3 for name in names},
                    risk_chain_by_ticker={name: name for name in names},
                    minimum_cash_buffer_usd=100, transaction_cost_bps=25,
                    max_single_weight=1, min_single_weight=.05, top_weight_cap=1,
                    minimum_effective_n_ratio=0, risk_chain_top1_cap=1,
                    max_evaluations=8,
                )
                self.assertEqual(result["feasible_projection_found"], bool(feasible))
                self.assertTrue(result["search_complete"])
                self.assertEqual(result["search_space_size"], math.prod(map(len, options)))
                if feasible:
                    chosen = result["projected_shares"]
                    exact_fee = sum(abs(chosen[name] - old[name]) * marks[name] for name in names) * rate
                    exact_cash = equity - sum(chosen[name] * marks[name] for name in names) - exact_fee
                    self.assertAlmostEqual(result["transaction_cost_usd"], float(exact_fee), places=9)
                    self.assertAlmostEqual(result["posttrade_cash_usd"], float(exact_cash), places=9)
                    self.assertAlmostEqual(result["risky_weight_l1_drift"], float(min(feasible)), places=12)

    def test_exact_integer_target_has_one_choice_not_floor_plus_one(self):
        result = project_whole_lot_rebalance(
            current_shares={"A": 9}, current_cash_usd=100,
            prices={"A": 100}, target_weights={"A": 1}, risk_chain_by_ticker={"A": "a"},
            minimum_cash_buffer_usd=100, transaction_cost_bps=10,
            max_single_weight=1, min_single_weight=0, top_weight_cap=1,
            minimum_effective_n_ratio=0, risk_chain_top1_cap=1, max_evaluations=1,
        )
        self.assertTrue(result["feasible_projection_found"])
        self.assertEqual(result["search_space_size"], 1)
        self.assertEqual(result["projected_shares"], {"A": 9})
        self.assertEqual(result["transaction_cost_usd"], 0)


if __name__ == "__main__":
    unittest.main()
