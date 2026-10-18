from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from backtest.ndx_current_competition import (
    build_current_competition,
    build_current_quality_scores,
    load_local_price_series,
)


ROOT = Path(__file__).resolve().parents[1]


class NdxCurrentCompetitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factors = pd.read_csv(ROOT / "data/cache/research/ndx_v11_current_fundamental_evidence_v1/quality_factor_inputs.csv")
        cls.taxonomy = pd.read_csv(ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/current_review_20260713/reviewed/evidence_reviewed.csv")

    def test_current_quality_uses_frozen_policy_and_scores_expected_coverage(self):
        scores, audit, coverage = build_current_quality_scores(self.factors)
        self.assertEqual(len(scores), 101)
        self.assertEqual(int(scores["quality_eligible"].sum()), 97)
        self.assertEqual(len(audit), 101 * 8)
        self.assertEqual(int(coverage.iloc[0]["eligible_count"]), 97)
        self.assertEqual(scores["quality_policy_id"].nunique(), 1)

    def test_competition_excludes_incumbents_unclassified_and_qqq(self):
        scores, _, _ = build_current_quality_scores(self.factors)
        series, _ = load_local_price_series(
            self.taxonomy["ticker"].tolist(), cache_dir=ROOT / "data/cache"
        )
        audit, shortlist = build_current_competition(self.taxonomy, scores, series)
        self.assertEqual(len(audit), 101)
        self.assertNotIn("QQQ", set(audit["ticker"]))
        self.assertFalse(audit.loc[audit["ticker"].isin({"NVDA", "MSFT", "GOOG"}), "competition_eligible"].any())
        self.assertTrue(audit.loc[~audit["status"].eq("accepted"), "competition_eligible"].eq(False).all())
        self.assertEqual(shortlist["risk_chain"].nunique(), len(shortlist))
        self.assertEqual(set(shortlist["selection_date"]), {"2026-07-13"})
        self.assertTrue(shortlist["admission_status"].eq("RESEARCH_SHORTLIST_ONLY_NOT_ADMITTED").all())
        self.assertTrue((pd.to_datetime(shortlist["asof_date"]) < pd.Timestamp("2026-07-13")).all())


if __name__ == "__main__":
    unittest.main()
