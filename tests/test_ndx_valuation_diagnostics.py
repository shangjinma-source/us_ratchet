from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_valuation_diagnostics import (
    NdxValuationDiagnosticError,
    calculate_valuation_values,
    valuation_distributions,
    valuation_integrity_failures,
)


def readiness_row(**overrides) -> dict:
    row = {
        "selection_date": "2024-04-01",
        "ticker": "TEST",
        "cik": 1001,
        "price": 100.0,
        "price_date": "2024-03-28",
        "shares_value": 1_000.0,
        "shares_period_end": "2024-03-20",
        "free_cash_flow_value": 10_000.0,
        "free_cash_flow_unit": "USD",
        "debt_value": 20_000.0,
        "debt_unit": "USD",
        "debt_method": "reported_total",
        "cash_value": 5_000.0,
        "cash_unit": "USD",
        "revenue_value": 50_000.0,
        "revenue_unit": "USD",
        "fcf_yield_ready": True,
        "ev_sales_ready": True,
        "fcf_yield_blockers": "",
        "ev_sales_blockers": "",
        "valuation_scoring_allowed": False,
    }
    row.update(overrides)
    return row


class NdxValuationDiagnosticTests(unittest.TestCase):
    def test_values_use_unadjusted_market_cap_identity(self):
        values = calculate_valuation_values(
            pd.DataFrame([readiness_row()])
        ).iloc[0]

        self.assertEqual(values["market_cap_value"], 100_000)
        self.assertAlmostEqual(values["fcf_yield_value"], 0.10)
        self.assertEqual(values["enterprise_value"], 115_000)
        self.assertAlmostEqual(values["ev_sales_value"], 2.30)
        self.assertTrue(bool(values["valuation_value_integrity_ready"]))
        self.assertFalse(bool(values["valuation_scoring_allowed"]))

    def test_not_ready_factor_does_not_leak_a_value(self):
        values = calculate_valuation_values(
            pd.DataFrame([
                readiness_row(
                    fcf_yield_ready=False,
                    ev_sales_ready=False,
                    fcf_yield_blockers="shares:missing",
                    ev_sales_blockers="debt:missing",
                )
            ])
        ).iloc[0]

        self.assertTrue(pd.isna(values["fcf_yield_value"]))
        self.assertTrue(pd.isna(values["ev_sales_value"]))
        self.assertTrue(bool(values["valuation_value_integrity_ready"]))

    def test_scoring_enabled_input_is_rejected(self):
        with self.assertRaisesRegex(
            NdxValuationDiagnosticError,
            "unexpectedly enables valuation scoring",
        ):
            calculate_valuation_values(
                pd.DataFrame([readiness_row(valuation_scoring_allowed=True)])
            )

    def test_distribution_and_integrity_are_descriptive_only(self):
        values = calculate_valuation_values(
            pd.DataFrame([
                readiness_row(ticker="A", fcf_yield_ready=True),
                readiness_row(ticker="B", free_cash_flow_value=-5_000),
            ])
        )
        distribution = valuation_distributions(values)
        fcf = distribution[distribution["factor"].eq("fcf_yield")].iloc[0]

        self.assertEqual(fcf["ready_count"], 2)
        self.assertEqual(fcf["negative_count"], 1)
        self.assertTrue(valuation_integrity_failures(values).empty)


if __name__ == "__main__":
    unittest.main()

