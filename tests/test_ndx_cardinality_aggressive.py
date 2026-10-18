import unittest

import pandas as pd

from backtest.ndx_cardinality_aggressive import (
    NdxCardinalityAggressiveError,
    compress_local_action_families,
    compress_aggressive_shortlist,
    mark_incumbent_risk_reward_pareto,
)


def _row(name, r50, r10, dd50, dd90, distance):
    return {
        "holding_count": 2,
        "issuer_structure": f"issuer:{name}1;issuer:{name}2",
        "canonical_tickers": name,
        "worst_return_p50": 0.4,
        "worst_return_p10": 0.1,
        "worst_max_drawdown_p50": 0.1,
        "worst_max_drawdown_p90": 0.15,
        "worst_paired_return_p50_vs_incumbent": r50,
        "worst_paired_return_p10_vs_incumbent": r10,
        "worst_paired_drawdown_cost_p50_vs_incumbent": dd50,
        "worst_paired_drawdown_cost_p90_vs_incumbent": dd90,
        "worst_target_012922_distance": distance,
    }


class NdxCardinalityAggressiveTests(unittest.TestCase):
    def test_pareto_rejects_four_dimension_dominated_row(self):
        frame = pd.DataFrame([
            _row("A;B", 0.1, 0.0, 0.01, 0.02, 0.4),
            _row("C;D", 0.2, 0.1, 0.00, 0.01, 0.5),
        ])
        self.assertEqual(mark_incumbent_risk_reward_pareto(frame).tolist(), [False, True])

    def test_compression_keeps_roles_and_preference_without_composite_score(self):
        frame = pd.DataFrame([
            _row("AMAT;AVGO", 0.1, -0.1, 0.02, 0.03, 0.5),
            _row("CDNS;GOOG", 0.0, 0.1, -0.01, -0.02, 0.1),
        ])
        result = compress_aggressive_shortlist(
            frame, preference_tickers=["AMAT", "AVGO"], per_role=1,
        )
        self.assertIn("USER_PREFERENCE", set(result["selection_role"]))
        self.assertFalse(result["safe_leg_included"].any())
        self.assertNotIn("score", " ".join(result.columns).lower())

    def test_missing_preference_anchor_fails_closed(self):
        frame = pd.DataFrame([_row("A;B", 0.1, 0.0, 0.01, 0.02, 0.4)])
        with self.assertRaises(NdxCardinalityAggressiveError):
            compress_aggressive_shortlist(frame, preference_tickers=["X", "Y"])

    def test_local_compression_keeps_each_family_and_role(self):
        rows = []
        for operation in ("ADD_0.025", "SINGLE_REPLACE", "DOUBLE_REPLACE"):
            for index in range(2):
                rows.append({
                    "structure_key": f"{operation}|{index}", "operation": operation,
                    "holding_count": 9, "worst_paired_return_p50": 0.01 + index,
                    "worst_paired_return_p10": -0.01 + index,
                    "worst_paired_drawdown_cost_p50": 0.001,
                    "worst_paired_drawdown_cost_p90": 0.002 - index,
                    "median_target_012922_distance": 0.5 + index,
                    "turnover": 0.1,
                })
        result = compress_local_action_families(pd.DataFrame(rows))
        self.assertEqual(set(result["action_family"]), {"ADD_ONLY", "SINGLE_REPLACEMENT", "DOUBLE_REPLACEMENT"})
        self.assertEqual(set(result["selection_role"]), {"RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"})
        self.assertEqual(len(result), 12)
        self.assertFalse(result["safe_leg_included"].any())


if __name__ == "__main__":
    unittest.main()
