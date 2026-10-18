from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_current_taxonomy import (
    build_current_taxonomy_plan,
    filing_html_index_url,
    filing_index_url,
    select_latest_business_filing,
)


def _submissions(cik: str = "0000000001") -> dict:
    return {
        "cik": cik,
        "filings": {
            "recent": {
                "form": ["10-K", "10-K/A", "10-K", "10-Q"],
                "filingDate": [
                    "2025-02-10",
                    "2025-02-10",
                    "2026-02-10",
                    "2026-05-01",
                ],
                "accessionNumber": [
                    "0000000001-25-000001",
                    "0000000001-25-000002",
                    "0000000001-26-000001",
                    "0000000001-26-000002",
                ],
                "primaryDocument": [
                    "annual.htm",
                    "amendment.htm",
                    "latest.htm",
                    "quarter.htm",
                ],
                "acceptanceDateTime": [
                    "20250210120000",
                    "20250210130000",
                    "20260210120000",
                    "20260501120000",
                ],
            }
        },
    }


class CurrentTaxonomyTests(unittest.TestCase):
    def test_selects_latest_eligible_annual_filing_without_future_data(self):
        selected = select_latest_business_filing(
            _submissions(), "2025-12-31"
        )
        # Same-day base form wins over its amendment; the 2026 annual filing
        # is outside the observation date and the 10-Q is not eligible.
        self.assertEqual(selected["status"], "planned")
        self.assertEqual(selected["form"], "10-K")
        self.assertEqual(selected["accession_number"], "0000000001-25-000001")
        self.assertLessEqual(selected["source_available_date"], "2025-12-31")

    def test_malformed_optional_acceptance_array_fails_closed_without_index_error(self):
        payload = _submissions()
        payload["filings"]["recent"]["acceptanceDateTime"] = ["20250210120000"]
        selected = select_latest_business_filing(payload, "2025-12-31")
        self.assertEqual(selected["status"], "planned")
        self.assertEqual(selected["acceptance_datetime"], "")

    def test_amendment_is_fallback_when_a_base_annual_filing_exists(self):
        payload = _submissions()
        recent = payload["filings"]["recent"]
        recent["form"] = ["10-K", "10-K/A"]
        recent["filingDate"] = ["2025-02-10", "2026-02-10"]
        recent["accessionNumber"] = [
            "0000000001-25-000001",
            "0000000001-26-000001",
        ]
        recent["primaryDocument"] = ["annual.htm", "amendment.htm"]
        recent["acceptanceDateTime"] = ["20250210120000", "20260210120000"]
        selected = select_latest_business_filing(payload, "2026-12-31")
        self.assertEqual(selected["form"], "10-K")
        self.assertEqual(selected["accession_number"], "0000000001-25-000001")
        self.assertEqual(
            selected["selection_method"],
            "latest_annual_business_filing_asof_observation",
        )

    def test_amendment_is_used_only_when_no_base_annual_filing_exists(self):
        payload = _submissions()
        recent = payload["filings"]["recent"]
        recent["form"] = ["10-K/A"]
        recent["filingDate"] = ["2026-02-10"]
        recent["accessionNumber"] = ["0000000001-26-000001"]
        recent["primaryDocument"] = ["amendment.htm"]
        recent["acceptanceDateTime"] = ["20260210120000"]
        selected = select_latest_business_filing(payload, "2026-12-31")
        self.assertEqual(selected["form"], "10-K/A")
        self.assertEqual(
            selected["selection_method"],
            "latest_annual_business_amendment_fallback_asof_observation",
        )

    def test_mismatched_required_arrays_are_rejected(self):
        payload = _submissions()
        payload["filings"]["recent"]["primaryDocument"] = ["only-one.htm"]
        selected = select_latest_business_filing(payload, "2025-12-31")
        self.assertEqual(selected["status"], "submissions_schema_invalid")

    def test_archive_urls_separate_json_and_html_fallback(self):
        accession = "0000000001-25-000001"
        self.assertTrue(filing_index_url("1", accession).endswith("/index.json"))
        self.assertTrue(filing_html_index_url("1", accession).endswith("-index.html"))

    def test_plan_shares_one_issuer_job_but_retains_security_ids(self):
        observations = pd.DataFrame([
            {
                "observation_date": "2025-12-31",
                "ticker": "AAA",
                "cik": "1",
                "issuer_id": "issuer:0000000001",
                "security_id": "security:0000000001:AAA",
            },
            {
                "observation_date": "2025-12-31",
                "ticker": "AAB",
                "cik": "1",
                "issuer_id": "issuer:0000000001",
                "security_id": "security:0000000001:AAB",
            },
            {
                "observation_date": "2025-12-31",
                "ticker": "BBB",
                "cik": "2",
                "issuer_id": "issuer:0000000002",
                "security_id": "security:0000000002:BBB",
            },
        ])
        plan = build_current_taxonomy_plan(
            observations,
            {
                "0000000001": _submissions("0000000001"),
            },
            observation_date="2025-12-31",
        )
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan["security_id"].nunique(), 3)
        self.assertEqual(
            plan.loc[plan["cik"].eq("0000000001"), "job_id"].nunique(), 1
        )
        self.assertEqual(
            plan.loc[plan["cik"].eq("0000000001"), "issuer_id"].nunique(), 1
        )
        self.assertEqual(
            plan.loc[plan["cik"].eq("0000000002"), "plan_status"].iloc[0],
            "submission_not_cached",
        )
        self.assertTrue(plan["classification_allowed"].eq(False).all())

    def test_qqq_is_rejected_from_current_taxonomy_plan(self):
        observations = pd.DataFrame([
            {
                "observation_date": "2025-12-31",
                "ticker": "QQQ",
                "cik": "1",
                "issuer_id": "issuer:0000000001",
                "security_id": "security:0000000001:QQQ",
            }
        ])
        with self.assertRaisesRegex(ValueError, "QQQ"):
            build_current_taxonomy_plan(
                observations, {}, observation_date="2025-12-31"
            )


if __name__ == "__main__":
    unittest.main()
