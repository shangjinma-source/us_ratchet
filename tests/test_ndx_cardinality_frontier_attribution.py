import unittest

from scripts.ndx_cardinality_frontier_attribution import (
    concentration_metrics,
    parse_weight_string,
    repair_whole_lot_allocation,
    whole_lot_weight_drift,
)


class NdxCardinalityFrontierAttributionTests(unittest.TestCase):
    def test_weight_string_is_strict_and_normalized(self):
        self.assertEqual(parse_weight_string("A:0.4;B:0.6"), {"A": 0.4, "B": 0.6})
        with self.assertRaises(ValueError):
            parse_weight_string("A:0.4;A:0.6")
        with self.assertRaises(ValueError):
            parse_weight_string("A:0.4;B:0.5")

    def test_whole_lot_drift_separates_cash_from_risky_normalization(self):
        result = whole_lot_weight_drift(
            {"A": 0.5, "B": 0.5}, {"A": 400.0, "B": 300.0}, 1000.0
        )
        self.assertAlmostEqual(result["deployment_ratio"], 0.7)
        self.assertAlmostEqual(result["actual_risky_weights"]["A"], 4 / 7)
        self.assertAlmostEqual(result["actual_total_cash_weights"]["A"], 0.4)

    def test_concentration_metrics(self):
        result = concentration_metrics({"A": 0.5, "B": 0.3, "C": 0.2})
        self.assertAlmostEqual(result["top3_weight"], 1.0)
        self.assertAlmostEqual(result["effective_n"], 1 / 0.38)

    def test_repair_adds_other_chain_to_remove_floor_cap_breach(self):
        shares = repair_whole_lot_allocation(
            {"A": 0.4, "B": 0.3, "C": 0.3},
            {"A": 100.0, "B": 140.0, "C": 140.0},
            {"A": "chain_a", "B": "chain_b", "C": "chain_c"},
            cash=1000.0, minimum_cash_buffer=100.0, risk_chain_top1_cap=0.4,
        )
        notionals = {ticker: shares[ticker] * price for ticker, price in {"A": 100.0, "B": 140.0, "C": 140.0}.items()}
        actual = whole_lot_weight_drift({"A": 0.4, "B": 0.3, "C": 0.3}, notionals, 1000.0)
        self.assertLessEqual(max(actual["actual_risky_weights"].values()), 0.4 + 1e-12)


if __name__ == "__main__":
    unittest.main()
