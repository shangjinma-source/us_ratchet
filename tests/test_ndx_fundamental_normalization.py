from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_fundamental_normalization import (
    build_quality_factor_inputs,
    normalize_point_in_time_facts,
)


def _fact(
    *,
    metric: str,
    concept: str,
    value: float,
    available: str,
    start: str,
    end: str,
    unit: str = "USD",
    accession: str = "0001",
) -> dict:
    return {
        "cik": 1001,
        "entity_name": "Test Corp",
        "metric": metric,
        "namespace": "us-gaap",
        "concept": concept,
        "unit": unit,
        "value": value,
        "form": "10-Q",
        "filed_date": available,
        "available_date": available,
        "period_start": start,
        "period_end": end,
        "fiscal_year": 2024,
        "fiscal_period": "Q1",
        "accession_number": accession,
        "frame": "",
    }


def _plan(*dates: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"selection_date": value, "ticker": "TEST", "cik": 1001}
        for value in dates
    ])


class NdxFundamentalNormalizationTests(unittest.TestCase):
    def test_annual_plus_ytd_uses_only_revisions_available_asof_selection(self):
        concept = "RevenueFromContractWithCustomerExcludingAssessedTax"
        records = pd.DataFrame([
            _fact(
                metric="revenue",
                concept=concept,
                value=100,
                available="2024-02-01",
                start="2023-01-01",
                end="2023-12-31",
                accession="annual",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=20,
                available="2024-05-01",
                start="2023-01-01",
                end="2023-03-31",
                accession="prior-ytd",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=30,
                available="2024-05-01",
                start="2024-01-01",
                end="2024-03-31",
                accession="current-ytd",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=35,
                available="2024-06-01",
                start="2024-01-01",
                end="2024-03-31",
                accession="current-ytd-amended",
            ),
        ])

        values, components, _ = normalize_point_in_time_facts(
            _plan("2024-04-30", "2024-05-01", "2024-06-02"),
            records,
        )
        revenue = values[values["metric"].eq("revenue")].set_index(
            "selection_date"
        )

        self.assertEqual(revenue.loc["2024-04-30", "value"], 100)
        self.assertEqual(revenue.loc["2024-04-30", "normalization_method"], "annual")
        self.assertEqual(revenue.loc["2024-05-01", "value"], 110)
        self.assertEqual(
            revenue.loc["2024-05-01", "normalization_method"],
            "annual_plus_ytd",
        )
        self.assertEqual(revenue.loc["2024-06-02", "value"], 115)
        may_components = components[
            components["selection_date"].eq("2024-05-01")
            & components["metric"].eq("revenue")
        ]
        self.assertEqual(
            may_components["signed_component_value"].sum(),
            110,
        )
        self.assertTrue(bool(revenue["future_data_guard_passed"].all()))

    def test_flow_normalization_never_combines_currencies(self):
        concept = "RevenueFromContractWithCustomerExcludingAssessedTax"
        records = pd.DataFrame([
            _fact(
                metric="revenue",
                concept=concept,
                value=100,
                available="2024-02-01",
                start="2023-01-01",
                end="2023-12-31",
                unit="USD",
                accession="annual",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=20,
                available="2024-05-01",
                start="2023-01-01",
                end="2023-03-31",
                unit="EUR",
                accession="prior-ytd",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=30,
                available="2024-05-01",
                start="2024-01-01",
                end="2024-03-31",
                unit="EUR",
                accession="current-ytd",
            ),
        ])

        values, _, _ = normalize_point_in_time_facts(
            _plan("2024-05-02"), records
        )
        revenue = values[values["metric"].eq("revenue")].iloc[0]

        self.assertEqual(revenue["value"], 100)
        self.assertEqual(revenue["unit"], "USD")
        self.assertEqual(revenue["normalization_method"], "annual")

    def test_revenue_prefers_total_over_narrower_standard_concept(self):
        records = pd.DataFrame([
            _fact(
                metric="revenue",
                concept="RevenueFromContractWithCustomerIncludingAssessedTax",
                value=1_100,
                available="2024-02-01",
                start="2023-01-01",
                end="2023-12-31",
                accession="narrow",
            ),
            _fact(
                metric="revenue",
                concept="Revenues",
                value=54_022,
                available="2024-02-01",
                start="2023-01-01",
                end="2023-12-31",
                accession="total",
            ),
        ])

        values, _, _ = normalize_point_in_time_facts(
            _plan("2024-02-02"), records
        )
        revenue = values[values["metric"].eq("revenue")].iloc[0]

        self.assertEqual(revenue["value"], 54_022)
        self.assertEqual(revenue["concepts"], "us-gaap:Revenues")

    def test_revenue_growth_uses_same_concept_currency_and_asof_comparison(self):
        concept = "Revenues"
        records = pd.DataFrame([
            _fact(
                metric="revenue",
                concept=concept,
                value=80,
                available="2023-02-01",
                start="2022-01-01",
                end="2022-12-31",
                accession="annual-2022",
            ),
            _fact(
                metric="revenue",
                concept=concept,
                value=100,
                available="2024-02-01",
                start="2023-01-01",
                end="2023-12-31",
                accession="annual-2023",
            ),
        ])

        values, components, _ = normalize_point_in_time_facts(
            _plan("2024-02-02"), records
        )
        factors, _ = build_quality_factor_inputs(values)
        revenue = values[values["metric"].eq("revenue")].iloc[0]

        self.assertEqual(revenue["comparison_value"], 80)
        self.assertEqual(revenue["comparison_gap_days"], 365)
        self.assertAlmostEqual(factors.iloc[0]["revenue_growth"], 0.25)
        self.assertEqual(factors.iloc[0]["revenue_growth_status"], "ready")
        self.assertEqual(
            set(components["component_set"]),
            {"current", "prior_year"},
        )

    def test_direct_four_quarters_is_a_strict_flow_fallback(self):
        concept = "OperatingIncomeLoss"
        periods = [
            ("2023-01-01", "2023-03-31", 1),
            ("2023-04-01", "2023-06-30", 2),
            ("2023-07-01", "2023-09-30", 3),
            ("2023-10-01", "2023-12-31", 4),
        ]
        records = pd.DataFrame([
            _fact(
                metric="operating_income",
                concept=concept,
                value=value,
                available="2024-02-01",
                start=start,
                end=end,
                accession=f"q{value}",
            )
            for start, end, value in periods
        ])

        values, _, _ = normalize_point_in_time_facts(
            _plan("2024-02-02"), records
        )
        operating_income = values[
            values["metric"].eq("operating_income")
        ].iloc[0]

        self.assertEqual(operating_income["value"], 10)
        self.assertEqual(
            operating_income["normalization_method"],
            "direct_four_quarters",
        )

    def test_stale_instant_fact_is_exported_but_not_usable(self):
        records = pd.DataFrame([
            _fact(
                metric="assets",
                concept="Assets",
                value=500,
                available="2022-02-01",
                start="",
                end="2021-12-31",
            )
        ])

        values, _, _ = normalize_point_in_time_facts(
            _plan("2024-06-03"), records
        )
        assets = values[values["metric"].eq("assets")].iloc[0]

        self.assertEqual(assets["status"], "stale")
        self.assertFalse(bool(assets["usable"]))
        self.assertEqual(assets["confidence"], "rejected")

    def test_quality_inputs_subtract_capex_and_reject_unit_mismatch(self):
        rows = []
        values = {
            "revenue": (100, "USD"),
            "operating_income": (25, "USD"),
            "net_income": (20, "USD"),
            "operating_cash_flow": (20, "USD"),
            "capital_expenditure": (5, "USD"),
            "research_and_development": (10, "USD"),
            "assets": (200, "USD"),
            "equity": (120, "USD"),
            "cash": (40, "USD"),
        }
        for metric, (value, unit) in values.items():
            rows.append({
                "selection_date": "2024-06-03",
                "ticker": "TEST",
                "cik": 1001,
                "metric": metric,
                "usable": True,
                "value": value,
                "unit": unit,
            })
        normalized = pd.DataFrame(rows)

        factors, _ = build_quality_factor_inputs(normalized)
        result = factors.iloc[0]

        self.assertAlmostEqual(result["free_cash_flow_margin"], 0.15)
        self.assertEqual(result["free_cash_flow_margin_status"], "ready")
        normalized.loc[
            normalized["metric"].eq("capital_expenditure"), "unit"
        ] = "EUR"
        factors, _ = build_quality_factor_inputs(normalized)
        self.assertEqual(
            factors.iloc[0]["free_cash_flow_margin_status"],
            "unit_mismatch",
        )


if __name__ == "__main__":
    unittest.main()
