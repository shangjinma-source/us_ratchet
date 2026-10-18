from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_fundamentals import (
    METRIC_CONCEPTS,
    NdxFundamentalError,
    build_cik_crosswalk,
    companyfacts_records,
    parse_cik_lookup,
    point_in_time_coverage,
)


class NdxFundamentalTests(unittest.TestCase):
    def test_cik_lookup_skips_official_rows_without_names(self):
        result = parse_cik_lookup(":1001:\nNAMED COMPANY:1002:\n")

        self.assertEqual(result[["name", "cik"]].to_dict("records"), [{
            "name": "NAMED COMPANY",
            "cik": 1002,
        }])
        self.assertEqual(result.attrs["skipped_empty_name_rows"], 1)

    def test_cik_lookup_still_rejects_malformed_rows(self):
        with self.assertRaisesRegex(NdxFundamentalError, "invalid SEC CIK lookup row"):
            parse_cik_lookup("<html>access denied</html>\n")

    def test_crosswalk_preserves_legal_entity_terms_for_exact_name_matching(self):
        history = pd.DataFrame([{
            "ticker": "OLD",
            "name": "Example N.V.",
            "cusip": "000000001",
            "report_date": "2023-03-31",
        }])
        ticker_payload = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1001, "Unrelated Corp", "LIVE", "Nasdaq"]],
        }
        historical = parse_cik_lookup(
            "EXAMPLE INC:2001:\nEXAMPLE N.V.:2002:\n"
        )

        result = build_cik_crosswalk(
            history,
            company_ticker_payload=ticker_payload,
            historical_cik_names=historical,
        ).iloc[0]

        self.assertEqual(result["cik"], 2002)
        self.assertEqual(result["mapping_method"], "sec_historical_name_exact")

    def test_crosswalk_can_disambiguate_duplicate_current_ticker_by_normalized_name(self):
        history = pd.DataFrame([{
            "ticker": "OLD",
            "name": "Target",
            "cusip": "000000001",
            "report_date": "2023-03-31",
        }])
        ticker_payload = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [1001, "Unrelated One", "OLD", "Nasdaq"],
                [1002, "Unrelated Two", "OLD", "Nasdaq"],
            ],
        }
        historical = parse_cik_lookup("TARGET INC:2001:\n")

        result = build_cik_crosswalk(
            history,
            company_ticker_payload=ticker_payload,
            historical_cik_names=historical,
        ).iloc[0]

        self.assertEqual(result["cik"], 2001)
        self.assertEqual(
            result["mapping_method"],
            "sec_historical_name_normalized_unique",
        )

    def test_crosswalk_uses_official_ticker_then_historical_name_without_fuzzy_match(self):
        history = pd.DataFrame([
            {
                "ticker": "LIVE",
                "name": "Live Corp.",
                "cusip": "000000001",
                "report_date": "2023-03-31",
            },
            {
                "ticker": "OLD",
                "name": "Old Company Inc.",
                "cusip": "000000002",
                "report_date": "2021-03-31",
            },
        ])
        ticker_payload = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1001, "Live Corp", "LIVE", "Nasdaq"]],
        }
        historical = parse_cik_lookup("OLD COMPANY INC:2002:\n")

        result = build_cik_crosswalk(
            history,
            company_ticker_payload=ticker_payload,
            historical_cik_names=historical,
        ).set_index("ticker")

        self.assertEqual(result.loc["LIVE", "cik"], 1001)
        self.assertEqual(result.loc["LIVE", "mapping_method"], "sec_current_ticker_exact")
        self.assertEqual(result.loc["OLD", "cik"], 2002)
        self.assertEqual(result.loc["OLD", "mapping_method"], "sec_historical_name_exact")

    def test_companyfacts_availability_is_filing_date_plus_one(self):
        payload = {
            "cik": 1001,
            "entityName": "Live Corp",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [{
                                "start": "2022-01-01",
                                "end": "2022-12-31",
                                "filed": "2023-03-01",
                                "form": "10-K",
                                "accn": "0001",
                                "val": 100,
                            }]
                        }
                    }
                }
            },
        }
        records = companyfacts_records(payload)
        self.assertEqual(records.iloc[0]["value"], 100.0)
        crosswalk = pd.DataFrame([{
            "ticker": "LIVE",
            "cik": 1001,
            "mapping_status": "mapped",
            "mapping_method": "sec_current_ticker_exact",
        }])
        plan = pd.DataFrame([
            {
                "selection_date": "2023-03-01",
                "report_date": "2022-12-31",
                "membership_available_date": "2023-02-28",
                "ticker": "LIVE",
            },
            {
                "selection_date": "2023-03-02",
                "report_date": "2022-12-31",
                "membership_available_date": "2023-02-28",
                "ticker": "LIVE",
            },
        ])

        detail, summary = point_in_time_coverage(plan, crosswalk, records)
        revenue = detail[detail["metric"].eq("revenue")].set_index("selection_date")

        self.assertFalse(bool(revenue.loc["2023-03-01", "available"]))
        self.assertTrue(bool(revenue.loc["2023-03-02", "available"]))
        self.assertTrue(bool(summary["future_data_guard_passed"].all()))

    def test_point_in_time_coverage_accepts_plan_with_cik_column(self):
        crosswalk = pd.DataFrame([{
            "ticker": "LIVE",
            "cik": 1001,
            "mapping_status": "mapped",
            "mapping_method": "sec_current_ticker_exact",
        }])
        plan = pd.DataFrame([{
            "selection_date": "2023-03-02",
            "report_date": "2022-12-31",
            "membership_available_date": "2023-02-28",
            "ticker": "LIVE",
            "cik": "0000001001",
        }])
        records = pd.DataFrame([
            {
                "cik": 1001,
                "metric": metric,
                "available_date": "2023-03-01",
                "period_end": "2022-12-31",
                "namespace": "us-gaap",
                "concept": metric,
                "unit": "USD",
                "form": "10-K",
                "accession_number": f"{metric}-1",
            }
            for metric in METRIC_CONCEPTS
        ])

        detail, summary = point_in_time_coverage(plan, crosswalk, records)

        self.assertEqual(set(detail["cik"].dropna().astype(int)), {1001})
        self.assertEqual(len(summary), len(METRIC_CONCEPTS))

    def test_point_in_time_coverage_rejects_cik_conflict(self):
        crosswalk = pd.DataFrame([{
            "ticker": "LIVE",
            "cik": 1001,
            "mapping_status": "mapped",
            "mapping_method": "sec_current_ticker_exact",
        }])
        plan = pd.DataFrame([{
            "selection_date": "2023-03-02",
            "report_date": "2022-12-31",
            "membership_available_date": "2023-02-28",
            "ticker": "LIVE",
            "cik": "0000001002",
        }])

        with self.assertRaises(ValueError):
            point_in_time_coverage(plan, crosswalk, pd.DataFrame())

    def test_companyfacts_can_extract_versioned_debt_extension_separately(self):
        payload = {
            "cik": 1001,
            "entityName": "Live Corp",
            "facts": {
                "us-gaap": {
                    "DebtLongtermAndShorttermCombinedAmount": {
                        "units": {
                            "USD": [{
                                "end": "2023-12-31",
                                "filed": "2024-02-01",
                                "form": "10-K",
                                "accn": "debt-1",
                                "val": 250,
                            }]
                        }
                    }
                }
            },
        }
        records = companyfacts_records(
            payload,
            metric_concepts={
                "debt": {
                    "us-gaap": ("DebtLongtermAndShorttermCombinedAmount",),
                }
            },
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records.iloc[0]["metric"], "debt")
        self.assertEqual(
            records.iloc[0]["concept"],
            "DebtLongtermAndShorttermCombinedAmount",
        )
        self.assertEqual(records.iloc[0]["available_date"], "2024-02-02")


if __name__ == "__main__":
    unittest.main()
