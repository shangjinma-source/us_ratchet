from __future__ import annotations

import unittest

import pandas as pd

from backtest.ndx_quality import (
    CORE_FACTORS,
    DIAGNOSTIC_FACTORS,
    QualityPolicy,
    build_quality_scores,
    select_with_sic_name_caps,
    sic_capped_weights,
)


def _evidence(count: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_rows = []
    sic_rows = []
    for index in range(count):
        ticker = f"T{index}"
        row = {
            "selection_date": "2024-06-03",
            "ticker": ticker,
            "cik": 1000 + index,
        }
        for factor in CORE_FACTORS + DIAGNOSTIC_FACTORS:
            row[factor] = float(index + 1)
            row[f"{factor}_status"] = "ready"
        factor_rows.append(row)
        sic_rows.append({
            "selection_date": "2024-06-03",
            "ticker": ticker,
            "cik": 1000 + index,
            "sic": 7372 if index < 4 else 3674,
            "sic_description": "SOFTWARE" if index < 4 else "SEMICONDUCTORS",
            "sic_group_2d": "73" if index < 4 else "36",
            "sic_division": "services" if index < 4 else "manufacturing",
            "sic_available": True,
            "sic_future_data_guard_passed": True,
        })
    return pd.DataFrame(factor_rows), pd.DataFrame(sic_rows)


class NdxQualityTests(unittest.TestCase):
    def test_three_sleeve_score_requires_growth_and_five_core_factors(self):
        factors, sic = _evidence()
        factors.loc[factors["ticker"].eq("T0"), "revenue_growth_status"] = (
            "missing_component"
        )
        factors.loc[
            factors["ticker"].eq("T1"), "operating_margin_status"
        ] = "missing_component"
        factors.loc[
            factors["ticker"].eq("T2"),
            ["operating_margin_status", "free_cash_flow_margin_status"],
        ] = "missing_component"

        scores, audit, coverage = build_quality_scores(factors, sic)
        result = scores.set_index("ticker")

        self.assertFalse(bool(result.loc["T0", "quality_eligible"]))
        self.assertTrue(bool(result.loc["T1", "quality_eligible"]))
        self.assertEqual(result.loc["T1", "quality_confidence"], "medium")
        self.assertFalse(bool(result.loc["T2", "quality_eligible"]))
        self.assertEqual(int(coverage.iloc[0]["eligible_count"]), 6)
        self.assertTrue(
            bool(
                audit.loc[
                    audit["factor"].eq("research_and_development_intensity"),
                    "included_in_quality_score",
                ].eq(False).all()
            )
        )

    def test_diagnostic_rd_does_not_change_equal_core_scores(self):
        factors, sic = _evidence()
        for factor in CORE_FACTORS:
            factors.loc[factors["ticker"].isin(["T0", "T1"]), factor] = 5.0
        factors.loc[factors["ticker"].eq("T0"), "research_and_development_intensity"] = 0.0
        factors.loc[factors["ticker"].eq("T1"), "research_and_development_intensity"] = 100.0

        scores, _, _ = build_quality_scores(factors, sic)
        result = scores.set_index("ticker")

        self.assertAlmostEqual(
            result.loc["T0", "quality_score"],
            result.loc["T1", "quality_score"],
        )

    def test_sic_name_caps_force_industry_diversification(self):
        factors, sic = _evidence()
        scores, _, _ = build_quality_scores(factors, sic)

        selected, rejected = select_with_sic_name_caps(
            scores,
            top_n=4,
            max_names_per_sic4=2,
            max_names_per_sic2=2,
        )

        self.assertEqual(len(selected), 4)
        self.assertLessEqual(int(selected.groupby("sic").size().max()), 2)
        self.assertLessEqual(
            int(selected.groupby("sic_group_2d").size().max()),
            2,
        )
        self.assertTrue(bool(rejected["reason"].eq("sic4_name_cap").any()))

    def test_policy_rejects_non_unit_sleeve_weights(self):
        with self.assertRaisesRegex(ValueError, "sum to one"):
            QualityPolicy(
                sleeve_weight_growth=0.5,
                sleeve_weight_profitability=0.5,
                sleeve_weight_balance=0.5,
            ).validate()

    def test_sic_weight_caps_bound_nested_industry_exposure(self):
        raw = pd.Series({
            "A": 0.40,
            "B": 0.30,
            "C": 0.10,
            "D": 0.10,
            "E": 0.05,
            "F": 0.05,
        })
        classifications = pd.DataFrame({
            "sic": [7372, 7372, 7370, 3674, 2834, 2086],
            "sic_group_2d": ["73", "73", "73", "36", "28", "20"],
        }, index=raw.index)

        weights = sic_capped_weights(
            raw,
            classifications,
            max_weight=0.35,
            min_weight=0.02,
            max_weight_sic4=0.50,
            max_weight_sic2=0.60,
        )

        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertLessEqual(float(weights[["A", "B"]].sum()), 0.50 + 1e-8)
        self.assertLessEqual(float(weights[["A", "B", "C"]].sum()), 0.60 + 1e-8)
        self.assertLessEqual(float(weights.max()), 0.35 + 1e-8)


if __name__ == "__main__":
    unittest.main()
