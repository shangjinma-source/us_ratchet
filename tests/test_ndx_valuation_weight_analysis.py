from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_valuation_weight_analysis import summarize_effects


class NdxValuationWeightAnalysisTests(unittest.TestCase):
    def test_shortlist_requires_return_breadth_and_bounded_drawdown_tail(self):
        candidate_rows = []
        window_rows = []
        for weight in (0.05, 0.10, 0.15):
            for index in range(36):
                improvement = 0.01 if weight == 0.05 or index < 18 else -0.01
                candidate_rows.append({
                    "declared_valuation_weight": weight,
                    "delta_strategy_xirr_p50": improvement,
                    "delta_strategy_xirr_p10": improvement / 2,
                })
            for index in range(648):
                improvement = 0.01 if weight == 0.05 or index < 324 else -0.01
                window_rows.append({
                    "declared_valuation_weight": weight,
                    "delta_strategy_xirr": improvement,
                    "delta_strategy_maxdd": 0.001,
                    "delta_turnover_x": 0.0,
                    "delta_cost_x": 0.0,
                })

        summary = summarize_effects(
            pd.DataFrame(candidate_rows), pd.DataFrame(window_rows)
        ).set_index("valuation_weight")

        self.assertTrue(bool(summary.loc[0.05, "shortlist_passed"]))
        self.assertFalse(bool(summary.loc[0.10, "shortlist_passed"]))
        self.assertFalse(bool(summary.loc[0.15, "shortlist_passed"]))


if __name__ == "__main__":
    unittest.main()
