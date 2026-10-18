from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_incumbent_overlay import (
    NdxIncumbentOverlayError,
    build_identity_rows,
    build_overlay_plan,
    build_review_pack,
    load_identity_overrides,
    parse_submission_filings,
    resolve_sec_company_tickers,
    select_annual_filing,
)
from data.versioning import write_dataset_manifest


class NdxIncumbentOverlayTests(unittest.TestCase):
    def test_annual_selection_prefers_latest_filing_available_at_start(self):
        selected = select_annual_filing([
            {
                "form": "10-K",
                "filed_date": "2019-03-01",
                "evidence_available_date": "2019-03-02",
                "accession_number": "old",
            },
            {
                "form": "10-K",
                "filed_date": "2020-03-01",
                "evidence_available_date": "2020-03-02",
                "accession_number": "new",
            },
        ], "2019-09-30")

        self.assertEqual(selected["accession_number"], "old")
        self.assertEqual(selected["selection_method"], "latest_annual_filing_available_by_selection_start")
        self.assertEqual(selected["status"], "selected_pit_annual_filing")

    def test_parse_submissions_keeps_only_annual_forms(self):
        payload = {
            "cik": "0000001234",
            "filings": {
                "recent": {
                    "form": ["10-Q", "10-K"],
                    "reportDate": ["2019-09-30", "2018-12-31"],
                    "filingDate": ["2019-11-01", "2019-03-01"],
                    "accessionNumber": ["q", "0000001234-19-000001"],
                    "primaryDocument": ["q.htm", "annual.htm"],
                }
            },
        }
        rows = parse_submission_filings(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["form"], "10-K")
        self.assertEqual(rows[0]["evidence_available_date"], "2019-03-02")
        self.assertIn("/000000123419000001/annual.htm", rows[0]["document_url"])

    def test_parse_historical_sec_submission_file_uses_explicit_cik(self):
        payload = {
            "form": ["20-F", "6-K"],
            "reportDate": ["2018-12-31", "2019-03-31"],
            "filingDate": ["2019-04-17", "2019-05-01"],
            "accessionNumber": ["0001046179-19-000001", "0001046179-19-000002"],
            "primaryDocument": ["annual.htm", "quarterly.htm"],
        }
        rows = parse_submission_filings(payload, cik="0001046179")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["form"], "20-F")
        self.assertIn("/1046179/000104617919000001/annual.htm", rows[0]["document_url"])

    def test_amended_annual_filing_is_not_used_as_business_source(self):
        payload = {
            "cik": "0000001234",
            "filings": {
                "recent": {
                    "form": ["10-K/A", "10-K"],
                    "reportDate": ["2018-12-31", "2018-12-31"],
                    "filingDate": ["2019-03-10", "2019-03-01"],
                    "accessionNumber": ["amend", "original"],
                    "primaryDocument": ["amend.htm", "original.htm"],
                }
            },
        }
        rows = parse_submission_filings(payload)

        self.assertEqual([row["accession_number"] for row in rows], ["original"])

    def test_sec_submissions_identity_override_is_explicitly_sourced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity.yaml"
            path.write_text(
                """schema_version: 1\nidentities:\n  - ticker: TSM\n    cik: '0001046179'\n    source_type: sec_submissions\n    source_locator: https://data.sec.gov/submissions/CIK0001046179.json\n""",
                encoding="utf-8",
            )
            result = load_identity_overrides(path, ["TSM"])

        self.assertEqual(result["TSM"]["cik"], "0001046179")
        self.assertEqual(
            result["TSM"]["identity_status"],
            "incumbent_overlay_identity_by_sec_submissions_crosswalk",
        )

    def test_identity_rows_keep_tsm_as_separate_overlay(self):
        config = {"symbols": [{"ticker": "NVDA"}, {"ticker": "TSM"}]}
        with tempfile.TemporaryDirectory() as tmp:
            identity_path = Path(tmp) / "identity.csv"
            pd.DataFrame([{
                "security_id": "security:0001045810:67066G104",
                "issuer_id": "issuer:0001045810",
                "ticker": "NVDA",
                "cik": "0001045810",
                "cusip": "67066G104",
                "identity_status": "resolved",
            }]).to_csv(identity_path, index=False)

            identities = build_identity_rows(
                config,
                identity_path=identity_path,
                sec_company_tickers={"TSM": {"cik": "0001046179"}},
            )

        tsm = identities.loc[identities["ticker"].eq("TSM")].iloc[0]
        self.assertEqual(tsm["security_id"], "security:incumbent_overlay:TSM")
        self.assertEqual(tsm["issuer_id"], "issuer:0001046179")
        self.assertEqual(tsm["identity_status"], "incumbent_overlay_identity_by_sec_ticker_crosswalk")

    def test_unresolved_overlay_identity_is_not_classifiable(self):
        config = {"symbols": [{"ticker": "TSM"}]}
        with tempfile.TemporaryDirectory() as tmp:
            identity_path = Path(tmp) / "identity.csv"
            pd.DataFrame(columns=[
                "security_id", "issuer_id", "ticker", "cik", "cusip", "identity_status"
            ]).to_csv(identity_path, index=False)
            identities = build_identity_rows(config, identity_path=identity_path)
            plan = build_overlay_plan(identities)

        self.assertFalse(bool(plan.loc[0, "classification_allowed"]))
        self.assertEqual(plan.loc[0, "status"], "requires_sec_submissions_resolution")

    def test_review_pack_preserves_pending_status_and_source_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "raw_sec"
            raw = root / "filings" / "NVDA" / "annual.htm"
            raw.parent.mkdir(parents=True)
            raw.write_text(
                "<html><title>Annual</title><body>"
                "ITEM 1. BUSINESS. NVIDIA designs accelerated computing platforms. "
                "Our products are used across data center and professional markets. "
                "ITEM 1A. RISK FACTORS. Risks follow."
                "</body></html>",
                encoding="utf-8",
            )
            write_dataset_manifest(
                raw,
                dataset_type="test_raw",
                dataset_key="nvda",
                source="SEC",
                fetched_at_evidence="test",
                row_count=1,
            )
            plan = pd.DataFrame([{
                "overlay_id": "incumbent_overlay:NVDA",
                "ticker": "NVDA",
                "security_id": "security:1",
                "issuer_id": "issuer:1",
                "cik": "0000000001",
                "cusip": "",
                "form": "10-K",
                "report_date": "2018-12-31",
                "filed_date": "2019-03-01",
                "evidence_available_date": "2019-03-02",
                "accession_number": "0000000001-19-000001",
                "document_url": "https://www.sec.gov/annual.htm",
                "raw_path": raw.as_posix(),
            }])

            documents, template = build_review_pack(plan, raw_root=root)

        self.assertEqual(len(documents), 1)
        self.assertTrue(bool(documents.loc[0, "raw_manifest_verified"]))
        self.assertEqual(documents.loc[0, "review_status"], "pending_manual_review")
        self.assertEqual(template.loc[0, "risk_chain"], "")
        self.assertEqual(template.loc[0, "confidence"], "")
        self.assertEqual(template.loc[0, "status"], "pending_review")

    def test_company_ticker_resolution_rejects_ambiguous_ticker(self):
        payload = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [[1, "One", "TSM", "Nasdaq"], [2, "Two", "TSM", "NYSE"]],
        }
        with self.assertRaisesRegex(NdxIncumbentOverlayError, "not unique"):
            resolve_sec_company_tickers(payload, ["TSM"])

    def test_20f_integrated_report_fallback_exposes_source_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "raw_sec"
            raw = root / "filings" / "ASML" / "annual.htm"
            raw.parent.mkdir(parents=True)
            raw.write_text(
                "<html><body>Our main customer groups are memory and logic chip makers. "
                + ("ASML lithography systems serve chip makers. " * 40)
                + "ITEM 4A. UNRESOLVED STAFF COMMENTS</body></html>",
                encoding="utf-8",
            )
            write_dataset_manifest(
                raw,
                dataset_type="test_raw",
                dataset_key="asml",
                source="SEC",
                fetched_at_evidence="test",
                row_count=1,
            )
            plan = pd.DataFrame([{
                "overlay_id": "incumbent_overlay:ASML",
                "ticker": "ASML",
                "security_id": "security:asml",
                "issuer_id": "issuer:asml",
                "cik": "0000000002",
                "cusip": "",
                "form": "20-F",
                "report_date": "2018-12-31",
                "filed_date": "2019-02-01",
                "evidence_available_date": "2019-02-02",
                "accession_number": "0000000002-19-000001",
                "document_url": "https://www.sec.gov/Archives/annual.htm",
                "raw_path": raw.as_posix(),
            }])

            documents, template = build_review_pack(plan, raw_root=root)

        self.assertEqual(documents.loc[0, "extraction_status"], "business_text_fallback_candidate")
        self.assertIn("lithography systems", documents.loc[0, "business_excerpt"])
        self.assertEqual(template.loc[0, "status"], "pending_review")


if __name__ == "__main__":
    unittest.main()
