import unittest

import pandas as pd

from scripts.ndx_cardinality_common_structure_stability import aggregate_common_structures


class NdxCardinalityCommonStructureStabilityTests(unittest.TestCase):
    def test_requires_structure_at_every_start_and_uses_conservative_variant(self):
        rows = []
        for date, value in [("2023-01-01", 0.2), ("2024-01-01", 0.1)]:
            rows.append({
                "holding_count": 2, "issuer_structure": "i1;i2", "selection_date": date,
                "tickers": "A;B", "paired_return_p50_vs_incumbent": value,
                "return_p50": 0.4 + value, "return_p10": 0.2 + value,
                "max_drawdown_p50": 0.1, "max_drawdown_p90": 0.2,
                "paired_return_p10_vs_incumbent": value - 0.1,
                "paired_drawdown_cost_p50_vs_incumbent": 0.01,
                "paired_drawdown_cost_p90_vs_incumbent": 0.02,
                "target_012922_distance": 0.5,
                "return_p50_vs_012922": value - 0.2,
                "max_drawdown_p90_vs_012922": 0.03 + value,
                "risk_chain_top1_p90": 0.4 + value,
                "effective_n_min": 3.0 + value,
                "turnover_p90": 0.1 + value,
                "whole_lot_total_transaction_cost_usd": 8.0 + value,
            })
        rows.append({**rows[0], "tickers": "A2;B", "paired_return_p50_vs_incumbent": -0.3})
        rows.append({**rows[0], "issuer_structure": "i3;i4", "tickers": "C;D"})
        _, structures = aggregate_common_structures(pd.DataFrame(rows))
        self.assertEqual(len(structures), 1)
        self.assertAlmostEqual(structures.iloc[0]["worst_paired_return_p50_vs_incumbent"], -0.3)
        self.assertAlmostEqual(structures.iloc[0]["worst_return_p50"], 0.5)
        self.assertAlmostEqual(structures.iloc[0]["worst_return_p50_vs_012922"], -0.1)
        self.assertAlmostEqual(structures.iloc[0]["worst_max_drawdown_p90_vs_012922"], 0.23)
        self.assertAlmostEqual(structures.iloc[0]["worst_risk_chain_top1_p90"], 0.6)
        self.assertAlmostEqual(structures.iloc[0]["worst_effective_n_min"], 3.1)
        self.assertAlmostEqual(structures.iloc[0]["worst_turnover_p90"], 0.3)
        self.assertAlmostEqual(structures.iloc[0]["worst_whole_lot_total_transaction_cost_usd"], 8.2)

    def test_entire_missing_start_fails_closed(self):
        row = {
            "holding_count": 2, "issuer_structure": "i1;i2", "selection_date": "2024-01-01",
            "tickers": "A;B", "paired_return_p50_vs_incumbent": 0.1,
            "return_p50": 0.2, "return_p10": 0.0,
            "max_drawdown_p50": 0.1, "max_drawdown_p90": 0.2,
            "paired_return_p10_vs_incumbent": -0.1,
            "paired_drawdown_cost_p50_vs_incumbent": 0.01,
            "paired_drawdown_cost_p90_vs_incumbent": 0.02,
            "target_012922_distance": 0.5,
        }
        with self.assertRaisesRegex(ValueError, "entire selection start"):
            aggregate_common_structures(
                pd.DataFrame([row]), expected_dates=["2023-01-01", "2024-01-01"],
            )


if __name__ == "__main__":
    unittest.main()
