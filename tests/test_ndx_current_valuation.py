from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_current_competition import (
    build_current_competition,
    build_current_quality_scores,
    load_local_price_series,
)
from backtest.ndx_current_valuation import (
    OVERPAY_PENALTY_QUANTILE,
    VALUATION_WEIGHT,
    attach_overpay_guard,
    build_current_valuation_guard,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxCurrentValuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence = ROOT / "data/cache/research/ndx_v11_current_fundamental_evidence_v1"
        price_basis = ROOT / "data/cache/research/ndx_v11_current_price_basis_v2"
        cls.readiness = pd.read_csv(evidence / "valuation_readiness.csv", low_memory=False)
        cls.factors = pd.read_csv(evidence / "quality_factor_inputs.csv", low_memory=False)
        cls.raw_prices = pd.read_csv(price_basis / "coverage.csv", low_memory=False)
        cls.gate, cls.values, cls.scores, cls.coverage = build_current_valuation_guard(
            cls.readiness, cls.factors, cls.raw_prices
        )

    def test_current_guard_uses_frozen_active_one_sided_contract(self):
        row = self.coverage.iloc[0]
        self.assertTrue(bool(row["factor_active"]))
        self.assertEqual(int(row["fcf_yield_observed_count"]), 78)
        self.assertEqual(int(row["missing_neutral_count"]), 23)
        self.assertAlmostEqual(float(row["overpay_penalty_quantile"]), OVERPAY_PENALTY_QUANTILE)
        self.assertFalse(bool(row["cheap_reward_allowed"]))
        self.assertLessEqual(float(self.scores["valuation_score"].max()), 50.0)
        missing = self.scores["valuation_missing_neutral_applied"].astype(bool)
        self.assertTrue(self.scores.loc[missing, "valuation_score"].eq(50.0).all())
        self.assertFalse(self.scores["return_data_read"].astype(bool).any())

    def test_guard_normalizes_score_before_ten_percent_mix(self):
        competition = pd.DataFrame({
            "ticker": ["A", "B"],
            "attack_score": [0.80, 0.80],
        })
        scores = pd.DataFrame({
            "selection_date": ["2026-07-13", "2026-07-13"],
            "ticker": ["A", "B"],
            "valuation_score": [50.0, 0.0],
            "valuation_policy_id": ["ndx_fcf_yield_overpay_guard_v1"] * 2,
            "valuation_factor_active": [True, True],
            "valuation_missing_neutral_applied": [False, False],
            "valuation_cheap_reward_allowed": [False, False],
        })
        attached = attach_overpay_guard(
            competition, scores, selection_date="2026-07-13"
        ).set_index("ticker")
        self.assertAlmostEqual(
            float(attached.loc["A", "valuation_guarded_price_score"]),
            (1.0 - VALUATION_WEIGHT) * 0.80 + VALUATION_WEIGHT * 0.50,
        )
        self.assertAlmostEqual(
            float(attached.loc["B", "valuation_guarded_price_score"]),
            (1.0 - VALUATION_WEIGHT) * 0.80,
        )

    def test_current_competition_consumes_guard_and_keeps_admission_closed(self):
        taxonomy = pd.read_csv(
            ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/evidence_reviewed.csv"
        )
        quality, _, _ = build_current_quality_scores(self.factors)
        series, _ = load_local_price_series(
            taxonomy["ticker"].tolist(), cache_dir=ROOT / "data/cache"
        )
        audit, shortlist = build_current_competition(
            taxonomy, quality, series, valuation_scores=self.scores
        )
        self.assertEqual(len(shortlist), 22)
        self.assertTrue(shortlist["valuation_guard_ready"].astype(bool).all())
        self.assertFalse(shortlist["admission_blockers"].str.contains("VALUATION_OVERPAY").any())
        self.assertTrue(shortlist["admission_status"].eq("RESEARCH_SHORTLIST_ONLY_NOT_ADMITTED").all())
        self.assertIn("KLAC", set(shortlist["ticker"]))
        self.assertIn("GILD", set(shortlist["ticker"]))
        self.assertEqual(len(audit), 101)


if __name__ == "__main__":
    unittest.main()
