from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_sensitivity_analysis import (
    apply_sensitivity_search_summary,
    sensitivity_effects,
)


class NdxSensitivityAnalysisTests(unittest.TestCase):
    def test_curve_headline_counts_cover_full_sensitivity_matrix(self):
        payload = {
            "search_summary": {
                "evaluated_candidate_rows": 3,
                "canonical_candidate_rows": 1,
                "concentration_compliant_rows": 1,
                "incumbent_beating_rows": 0,
            }
        }
        candidates = pd.DataFrame([
            {
                "concentration_guard_passed": True,
                "incumbent_win_rate": 0.60,
                "incumbent_xirr_p50_margin": 0.01,
                "incumbent_xirr_p10_margin": 0.001,
            },
            {
                "concentration_guard_passed": True,
                "incumbent_win_rate": 0.40,
                "incumbent_xirr_p50_margin": 0.02,
                "incumbent_xirr_p10_margin": 0.01,
            },
            {
                "concentration_guard_passed": False,
                "incumbent_win_rate": 0.60,
                "incumbent_xirr_p50_margin": -0.01,
                "incumbent_xirr_p10_margin": -0.02,
            },
        ])

        result = apply_sensitivity_search_summary(payload, candidates)
        summary = result["search_summary"]

        self.assertEqual(summary["concentration_compliant_rows"], 2)
        self.assertEqual(summary["canonical_concentration_compliant_rows"], 1)
        self.assertEqual(summary["incumbent_beating_rows"], 1)
        self.assertEqual(summary["canonical_incumbent_beating_rows"], 0)
        self.assertEqual(
            summary["headline_count_scope"], "all_sensitivity_candidate_rows"
        )

    def test_sensitivity_pairs_every_profile_against_one_baseline(self):
        profiles = {"baseline": "baseline", "a": "role_a", "b": "role_b"}
        candidate_rows = []
        window_rows = []
        for lookback in (1.0, 2.0, 3.0):
            for cost in (5.0, 10.0, 25.0):
                for profile_id, improvement in (
                    ("baseline", 0.0),
                    ("a", 0.01),
                    ("b", 0.02),
                ):
                    candidate_rows.append({
                        "profile_id": profile_id,
                        "lookback_years": lookback,
                        "trade_cost_bps": cost,
                        "incumbent_win_rate": 0.2 + improvement,
                        "incumbent_xirr_p50_margin": -0.08 + improvement,
                        "incumbent_xirr_p10_margin": -0.13 + improvement,
                        "incumbent_dd_relief_p50": 0.02,
                        "incumbent_dd_relief_p90": 0.01,
                        "turnover_x_p50": 5.0,
                    })
                    for start in ("2022-01-11", "2022-02-01"):
                        window_rows.append({
                            "profile_id": profile_id,
                            "lookback_years": lookback,
                            "trade_cost_bps": cost,
                            "start": start,
                            "incumbent_xirr_margin": -0.08 + improvement,
                            "incumbent_dd_relief": 0.02,
                            "strategy_xirr": 0.30 + improvement,
                            "strategy_maxdd": 0.20,
                            "turnover_x": 5.0,
                        })

        candidate_effects, window_effects, summaries = sensitivity_effects(
            pd.DataFrame(candidate_rows),
            pd.DataFrame(window_rows),
            baseline_profile_id="baseline",
            profile_roles=profiles,
        )

        self.assertEqual(len(candidate_effects), 18)
        self.assertEqual(len(window_effects), 36)
        self.assertEqual(set(summaries["profile_role"]), {"role_a", "role_b"})
        self.assertTrue(
            (summaries["candidate_p50_return_improvement_count"] == 9).all()
        )


if __name__ == "__main__":
    unittest.main()
