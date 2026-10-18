from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_valuation_score import (
    VALUATION_OVERPAY_GUARD_POLICY_ID,
    ValuationScorePolicy,
    build_neutral_missing_scores,
    build_overpay_guard_scores,
)


class NdxValuationScoreTests(unittest.TestCase):
    def test_missing_rows_are_exactly_neutral_and_observed_rows_are_ranked(self):
        values = pd.DataFrame([
            {
                "selection_date": "2024-01-02",
                "ticker": ticker,
                "cik": index + 1,
                "fcf_yield_value": value,
                "fcf_yield_value_ready": ready,
                "ev_sales_value_ready": False,
            }
            for index, (ticker, value, ready) in enumerate([
                ("A", 0.02, True),
                ("B", 0.08, True),
                ("C", None, False),
                ("D", None, False),
            ])
        ])
        scores, coverage = build_neutral_missing_scores(
            values,
            policy=ValuationScorePolicy(
                minimum_factor_coverage=0.5,
                minimum_observations=2,
            ),
        )
        result = scores.set_index("ticker")
        self.assertEqual(result.at["A", "valuation_score"], 0.0)
        self.assertEqual(result.at["B", "valuation_score"], 100.0)
        self.assertEqual(result.at["C", "valuation_score"], 50.0)
        self.assertEqual(result.at["D", "valuation_score"], 50.0)
        self.assertTrue(bool(coverage.iloc[0]["factor_active"]))

    def test_low_coverage_disables_factor_instead_of_rewarding_observed_rows(self):
        values = pd.DataFrame([
            {
                "selection_date": "2024-01-02",
                "ticker": ticker,
                "cik": index + 1,
                "fcf_yield_value": value,
                "fcf_yield_value_ready": ready,
                "ev_sales_value_ready": False,
            }
            for index, (ticker, value, ready) in enumerate([
                ("A", 0.10, True),
                ("B", None, False),
                ("C", None, False),
            ])
        ])
        scores, coverage = build_neutral_missing_scores(
            values,
            policy=ValuationScorePolicy(
                minimum_factor_coverage=0.7,
                minimum_observations=2,
            ),
        )
        self.assertTrue(scores["valuation_score"].eq(50.0).all())
        self.assertFalse(bool(coverage.iloc[0]["factor_active"]))

    def test_overpay_guard_penalizes_only_low_fcf_yield_tail(self):
        values = pd.DataFrame([
            {
                "selection_date": "2024-01-02",
                "ticker": ticker,
                "cik": index + 1,
                "fcf_yield_value": value,
                "fcf_yield_value_ready": value is not None,
                "ev_sales_value_ready": False,
            }
            for index, (ticker, value) in enumerate([
                ("A", -0.10),
                ("B", 0.01),
                ("C", 0.03),
                ("D", 0.06),
                ("E", 0.10),
                ("F", None),
            ])
        ])
        scores, _ = build_overpay_guard_scores(
            values,
            policy=ValuationScorePolicy(
                minimum_factor_coverage=0.5,
                minimum_observations=2,
            ),
            penalty_quantile=0.30,
        )
        result = scores.set_index("ticker")
        self.assertLess(result.at["A", "valuation_score"], 50.0)
        self.assertEqual(result.at["D", "valuation_score"], 50.0)
        self.assertEqual(result.at["E", "valuation_score"], 50.0)
        self.assertEqual(result.at["F", "valuation_score"], 50.0)
        self.assertFalse(result["valuation_cheap_reward_allowed"].astype(bool).any())
        self.assertTrue(
            result["valuation_policy_id"].eq(
                VALUATION_OVERPAY_GUARD_POLICY_ID
            ).all()
        )


if __name__ == "__main__":
    unittest.main()
