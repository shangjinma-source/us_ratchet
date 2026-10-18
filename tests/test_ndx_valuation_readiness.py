from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_valuation_readiness import (
    build_point_in_time_accounting_readiness,
    build_valuation_factor_readiness,
    point_in_time_price_rows,
    share_basis_events,
)


def _fact(
    *,
    metric: str,
    concept: str,
    value: float,
    period_end: str = "2024-03-31",
    available_date: str = "2024-04-10",
    namespace: str = "us-gaap",
    unit: str = "USD",
    form: str = "10-Q",
) -> dict:
    return {
        "cik": 1001,
        "metric": metric,
        "namespace": namespace,
        "concept": concept,
        "unit": unit,
        "value": value,
        "form": form,
        "available_date": available_date,
        "period_end": period_end,
        "accession_number": f"{concept}-{available_date}",
    }


def _plan(selection_date: str = "2024-04-20") -> pd.DataFrame:
    return pd.DataFrame([
        {"selection_date": selection_date, "ticker": "TEST", "cik": 1001}
    ])


def _units(selection_date: str = "2024-04-20") -> pd.DataFrame:
    return pd.DataFrame([
        {
            "selection_date": selection_date,
            "ticker": "TEST",
            "cik": 1001,
            "statement_unit": "USD",
        }
    ])


class NdxValuationReadinessTests(unittest.TestCase):
    def test_debt_crosscheck_prevents_double_counting(self):
        records = pd.DataFrame([
            _fact(
                metric="shares_outstanding",
                namespace="dei",
                concept="EntityCommonStockSharesOutstanding",
                unit="shares",
                value=1_000,
            ),
            _fact(metric="debt", concept="LongTermDebt", value=100),
            _fact(metric="debt", concept="LongTermDebtCurrent", value=10),
            _fact(metric="debt", concept="LongTermDebtNoncurrent", value=90),
            _fact(metric="debt", concept="ShortTermBorrowings", value=5),
        ])

        readiness, components = build_point_in_time_accounting_readiness(
            _plan(), records, _units()
        )
        row = readiness.iloc[0]

        self.assertTrue(bool(row["shares_ready"]))
        self.assertTrue(bool(row["debt_ready"]))
        self.assertTrue(bool(row["debt_strict_complete"]))
        self.assertEqual(row["debt_value"], 105)
        self.assertEqual(
            row["debt_method"],
            "us_long_term_total_crosschecked_plus_short_term",
        )
        selected_debt = components[
            components["metric"].eq("debt") & components["selected"]
        ]
        self.assertEqual(
            set(selected_debt["component_role"]),
            {"long_term_total", "short_term_borrowings"},
        )

    def test_inconsistent_debt_total_fails_closed(self):
        records = pd.DataFrame([
            _fact(
                metric="shares_outstanding",
                namespace="dei",
                concept="EntityCommonStockSharesOutstanding",
                unit="shares",
                value=1_000,
            ),
            _fact(metric="debt", concept="LongTermDebt", value=125),
            _fact(metric="debt", concept="LongTermDebtCurrent", value=10),
            _fact(metric="debt", concept="LongTermDebtNoncurrent", value=90),
        ])

        readiness, _ = build_point_in_time_accounting_readiness(
            _plan(), records, _units()
        )
        row = readiness.iloc[0]

        self.assertFalse(bool(row["debt_ready"]))
        self.assertEqual(row["debt_status"], "ambiguous_total_components")
        self.assertGreater(row["debt_crosscheck_relative_error"], 0.05)

    def test_reported_long_and_short_term_total_is_not_added_twice(self):
        records = pd.DataFrame([
            _fact(
                metric="shares_outstanding",
                namespace="dei",
                concept="EntityCommonStockSharesOutstanding",
                unit="shares",
                value=1_000,
            ),
            _fact(
                metric="debt",
                concept="DebtLongtermAndShorttermCombinedAmount",
                value=105,
            ),
            _fact(metric="debt", concept="LongTermDebt", value=100),
            _fact(metric="debt", concept="ShortTermBorrowings", value=5),
        ])

        readiness, components = build_point_in_time_accounting_readiness(
            _plan(), records, _units()
        )
        row = readiness.iloc[0]

        self.assertTrue(bool(row["debt_strict_complete"]))
        self.assertEqual(row["debt_value"], 105)
        self.assertEqual(
            row["debt_method"],
            "us_reported_long_and_short_term_total",
        )
        selected = components[
            components["metric"].eq("debt") & components["selected"]
        ]
        self.assertEqual(
            selected["concept"].tolist(),
            ["DebtLongtermAndShorttermCombinedAmount"],
        )

    def test_reported_combined_debt_mismatch_prefers_direct_total(self):
        records = pd.DataFrame([
            _fact(
                metric="debt",
                concept="DebtLongtermAndShorttermCombinedAmount",
                value=150,
            ),
            _fact(metric="debt", concept="LongTermDebt", value=100),
            _fact(metric="debt", concept="ShortTermBorrowings", value=5),
        ])

        readiness, _ = build_point_in_time_accounting_readiness(
            _plan(), records, _units()
        )
        row = readiness.iloc[0]

        self.assertTrue(bool(row["debt_ready"]))
        self.assertTrue(bool(row["debt_strict_complete"]))
        self.assertEqual(row["debt_value"], 150)
        self.assertEqual(
            row["debt_crosscheck_status"],
            "component_mismatch_reported_total_preferred",
        )
        self.assertGreater(row["debt_crosscheck_relative_error"], 0.05)

    def test_future_fact_is_not_visible_and_price_is_strictly_prior(self):
        records = pd.DataFrame([
            _fact(
                metric="shares_outstanding",
                namespace="dei",
                concept="EntityCommonStockSharesOutstanding",
                unit="shares",
                value=1_000,
                available_date="2024-04-21",
            ),
        ])
        readiness, components = build_point_in_time_accounting_readiness(
            _plan(), records, _units()
        )
        prices = point_in_time_price_rows(
            _plan(),
            {
                "TEST": pd.DataFrame(
                    {"Close": [99.0, 101.0]},
                    index=pd.to_datetime(["2024-04-19", "2024-04-20"]),
                )
            },
        )

        self.assertEqual(readiness.iloc[0]["shares_status"], "missing")
        self.assertTrue(components.empty)
        self.assertEqual(prices.iloc[0]["price"], 99.0)
        self.assertEqual(prices.iloc[0]["price_date"], "2024-04-19")
        self.assertTrue(bool(prices.iloc[0]["price_future_data_guard_passed"]))

    def test_adjusted_price_basis_blocks_factors_after_accounting_is_ready(self):
        accounting = pd.DataFrame([
            {
                "selection_date": "2024-04-20",
                "ticker": "TEST",
                "cik": 1001,
                "statement_unit": "USD",
                "foreign_filer_asof": False,
                "shares_ready": True,
                "shares_status": "ready",
                "debt_ready": True,
                "debt_status": "ready",
                "debt_strict_complete": True,
                "debt_unit": "USD",
            }
        ])
        factors = pd.DataFrame([
            {
                "selection_date": "2024-04-20",
                "ticker": "TEST",
                "cik": 1001,
                "revenue_value": 1_000,
                "revenue_unit": "USD",
                "operating_cash_flow_value": 200,
                "operating_cash_flow_unit": "USD",
                "capital_expenditure_value": 50,
                "capital_expenditure_unit": "USD",
                "cash_value": 100,
                "cash_unit": "USD",
                "free_cash_flow_margin_status": "ready",
                "revenue_growth_status": "ready",
            }
        ])
        prices = pd.DataFrame([
            {
                "selection_date": "2024-04-20",
                "ticker": "TEST",
                "price_status": "ready",
                "price_ready": True,
                "price": 10,
                "price_date": "2024-04-19",
                "price_age_days": 1,
                "price_future_data_guard_passed": True,
            }
        ])

        result = build_valuation_factor_readiness(
            accounting, factors, prices, price_basis_ready=False
        ).iloc[0]

        self.assertTrue(bool(result["fcf_yield_accounting_ready"]))
        self.assertTrue(bool(result["ev_sales_accounting_ready"]))
        self.assertFalse(bool(result["fcf_yield_ready"]))
        self.assertFalse(bool(result["ev_sales_ready"]))
        self.assertIn(
            "unadjusted_price_or_adjustment_factor_missing",
            result["fcf_yield_blockers"],
        )

    def test_share_basis_event_identifies_split_like_jump(self):
        accounting = pd.DataFrame([
            {
                "selection_date": "2024-01-01",
                "ticker": "TEST",
                "shares_ready": True,
                "shares_value": 100,
            },
            {
                "selection_date": "2024-04-01",
                "ticker": "TEST",
                "shares_ready": True,
                "shares_value": 400,
            },
        ])

        events = share_basis_events(accounting)

        self.assertEqual(len(events), 1)
        self.assertEqual(events.iloc[0]["nearest_split_ratio"], 4)
        self.assertTrue(bool(events.iloc[0]["split_like"]))


if __name__ == "__main__":
    unittest.main()
