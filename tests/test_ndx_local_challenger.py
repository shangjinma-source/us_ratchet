import unittest

import numpy as np
import pandas as pd

from backtest.ndx_local_challenger import (
    aggregate_local_challenger_stability,
    evaluate_fixed_weight_challenger,
    tag_local_frontiers,
)


class NdxLocalChallengerTests(unittest.TestCase):
    def test_fixed_replacement_is_paired_against_actual_incumbent_weights(self):
        index = pd.bdate_range("2023-01-02", periods=180)
        returns = pd.DataFrame({
            "A": np.repeat(0.001, len(index)),
            "B": np.repeat(0.0002, len(index)),
            "C": np.repeat(0.002, len(index)),
        }, index=index)
        target = pd.Series(np.repeat(0.0005, len(index)), index=index)
        result = evaluate_fixed_weight_challenger(
            operation="SINGLE_REPLACE", removed=("B",), added=("C",),
            weights={"A": 0.8, "C": 0.2}, returns=returns, target=target,
            incumbent_weights={"A": 0.8, "B": 0.2}, fit_days=63,
            window_days=42, step_days=21, transaction_cost_bps=0,
        )
        self.assertGreater(result["paired_return_p50_vs_incumbent"], 0)
        self.assertAlmostEqual(result["turnover"], 0.2)
        self.assertEqual(result["holding_count"], 2)
        self.assertFalse(result["promotion_allowed"])

    def test_frontiers_are_tagged_within_each_operation(self):
        frame = pd.DataFrame([
            {"operation": "ADD", "return_p50": 2.0, "return_p10": 2.0, "max_drawdown_p50": 1.0, "max_drawdown_p90": 1.0, "target_012922_distance": 1.0, "turnover": 0.1},
            {"operation": "ADD", "return_p50": 1.0, "return_p10": 1.0, "max_drawdown_p50": 2.0, "max_drawdown_p90": 2.0, "target_012922_distance": 2.0, "turnover": 0.2},
            {"operation": "DROP", "return_p50": 0.5, "return_p10": 0.5, "max_drawdown_p50": 0.5, "max_drawdown_p90": 0.5, "target_012922_distance": 0.5, "turnover": 0.1},
        ])
        tagged = tag_local_frontiers(frame)
        self.assertIn("PARETO", tagged.loc[0, "frontier_tags"])
        self.assertEqual(tagged.loc[1, "frontier_tags"], "")
        self.assertIn("RETURN", tagged.loc[2, "frontier_tags"])

    def test_stability_requires_the_same_structure_to_pass_every_start(self):
        base = {
            "operation": "SINGLE_REPLACE", "removed": "A", "added": "C", "holding_count": 2,
            "paired_return_p50_vs_incumbent": 0.02, "paired_return_p10_vs_incumbent": 0.01,
            "paired_drawdown_cost_p50_vs_incumbent": -0.01,
            "paired_drawdown_cost_p90_vs_incumbent": -0.01,
            "target_012922_distance": 0.2, "turnover": 0.2,
        }
        failed = dict(base)
        failed["paired_return_p10_vs_incumbent"] = -0.001
        result = aggregate_local_challenger_stability({
            "2023-01-01": pd.DataFrame([base]),
            "2024-01-01": pd.DataFrame([failed]),
        })
        self.assertEqual(result.loc[0, "four_dimension_pass_count"], 1)
        self.assertFalse(result.loc[0, "four_dimension_pass_all_starts"])
        self.assertAlmostEqual(result.loc[0, "worst_paired_return_p10"], -0.001)


if __name__ == "__main__":
    unittest.main()
