import unittest

import pandas as pd

from backtest.ndx_local_action_execution import (
    evaluate_local_action_execution,
    select_execution_aware_local_leaders,
)


class NdxLocalActionExecutionTests(unittest.TestCase):
    def test_reports_compliant_whole_share_result(self):
        result = evaluate_local_action_execution(
            {"A": 0.4, "B": 0.3, "C": 0.3},
            {"A": 100.0, "B": 140.0, "C": 140.0},
            {"A": "one", "B": "two", "C": "three"},
            cash=1000.0, minimum_cash_buffer=100.0,
            min_single_weight=0.0, max_single_weight=0.5, top3_cap=1.0,
            minimum_effective_n_ratio=0.0, risk_chain_top1_cap=0.5,
        )
        self.assertTrue(result["constraints_passed"])
        self.assertGreaterEqual(result["residual_cash_usd"], 100.0)

    def test_expensive_name_is_reported_not_hidden(self):
        result = evaluate_local_action_execution(
            {"A": 0.5, "B": 0.5}, {"A": 2000.0, "B": 100.0},
            {"A": "one", "B": "two"}, cash=1000.0,
            minimum_cash_buffer=100.0, min_single_weight=0.05,
            max_single_weight=0.8, top3_cap=1.0,
            minimum_effective_n_ratio=0.5, risk_chain_top1_cap=0.8,
        )
        self.assertFalse(result["constraints_passed"])
        self.assertIn("whole_lot", result["constraint_failures"])

    def test_execution_aware_selection_preserves_failed_metric_control(self):
        rows = []
        for family, operation in (
            ("add", "ADD_0.100"), ("single", "SINGLE_REPLACE"), ("double", "DOUBLE_REPLACE")
        ):
            for suffix, score in (("best", 2.0), ("fallback", 1.0)):
                rows.append({
                    "structure_key": f"{family}_{suffix}", "operation": operation,
                    "removed": "", "added": suffix, "holding_count": 3,
                    "worst_paired_return_p50": score, "worst_paired_return_p10": score,
                    "worst_paired_drawdown_cost_p50": -score,
                    "worst_paired_drawdown_cost_p90": -score,
                    "median_target_012922_distance": 3.0 - score, "turnover": 0.1,
                })
        stability = pd.DataFrame(rows)
        audit = pd.DataFrame({
            "structure_key": stability["structure_key"],
            "execution_eligible": ~stability["structure_key"].eq("add_best"),
        })
        selected = select_execution_aware_local_leaders(stability, audit)
        add_rows = selected.loc[selected["action_family"].eq("ADD_ONLY")]
        self.assertTrue(add_rows["fallback_used"].all())
        self.assertTrue(add_rows["metric_first_structure_key"].eq("add_best").all())
        self.assertTrue(add_rows["structure_key"].eq("add_fallback").all())


if __name__ == "__main__":
    unittest.main()
