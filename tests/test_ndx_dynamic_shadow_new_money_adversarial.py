"""Independent algebraic checks for the research-only migration heuristic."""
from __future__ import annotations

import copy
import random
import unittest

from backtest.ndx_dynamic_shadow_new_money_preview import simulate_research_new_money_preview


class NewMoneyAlgebraAdversarialTest(unittest.TestCase):
    def test_seeded_dynamic_targets_preserve_cash_shares_and_inputs(self):
        generator = random.Random(732)
        for count in range(1, 13):
            with self.subTest(target_k=count):
                raw_weights = [generator.randint(1, 20) for _ in range(count)]
                identities = [{
                    "security_id": f"S{index}", "issuer_id": f"I{index}",
                    "ticker": f"T{index}",
                } for index in range(count + 1)]
                target = [{**identities[index], "target_weight": weight / sum(raw_weights)}
                          for index, weight in enumerate(raw_weights)]
                current = [{**identity, "quantity": generator.randint(0, 4)} for identity in identities]
                prices = [{
                    **identity, "price_usd": float(generator.randint(5, 400)),
                    "session_date": "2026-09-04", "observed_at": "2026-09-05T02:00:00Z",
                } for identity in identities]
                money = float(generator.randint(0, 2200))
                inputs = copy.deepcopy((current, target, prices))
                result = simulate_research_new_money_preview(
                    current, target, prices, new_money_usd=money,
                    valuation_session_date="2026-09-04",
                    valuation_timestamp="2026-09-05T02:00:00Z",
                )
                self.assertEqual((current, target, prices), inputs)
                price_by_id = {row["security_id"]: row["price_usd"] for row in prices}
                current_by_id = {row["security_id"]: row["quantity"] for row in current}
                spent = 0.0
                bought = {}
                for row in result["buy_plan"]:
                    self.assertIsInstance(row["shares"], int)
                    self.assertGreater(row["shares"], 0)
                    self.assertEqual(row["sell_shares"], 0)
                    bought[row["security_id"]] = row["shares"]
                    spent += row["shares"] * price_by_id[row["security_id"]]
                self.assertNotIn(f"S{count}", bought)
                self.assertAlmostEqual(
                    spent * 1.001 + result["uninvested_new_money_usd"], money, places=7,
                )
                self.assertAlmostEqual(result["estimated_fees_usd"], spent * 0.001, places=7)
                for row in result["position_changes"]:
                    self.assertEqual(row["quantity_after"],
                                     current_by_id[row["security_id"]] + bought.get(row["security_id"], 0))
                final_stock = sum(row["quantity_after"] * price_by_id[row["security_id"]]
                                  for row in result["position_changes"])
                initial_stock = sum(current_by_id[key] * price_by_id[key] for key in current_by_id)
                self.assertAlmostEqual(final_stock + result["uninvested_new_money_usd"],
                                       initial_stock + money - spent * 0.001, places=7)
                self.assertLessEqual(result["target_l1_error_after"], result["target_l1_error_before"] + 1e-12)
                self.assertFalse(result["execution_eligible"])
                self.assertFalse(result["orders_created"])


if __name__ == "__main__":
    unittest.main()
