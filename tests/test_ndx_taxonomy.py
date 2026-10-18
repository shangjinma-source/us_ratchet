from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data.ndx_security_identity import load_security_lifecycle
from data.ndx_taxonomy import (
    NdxTaxonomyError,
    build_evidence_plan,
    build_security_universe,
    build_taxonomy_records,
    load_evidence_csv,
    load_taxonomy_definition,
    normalize_and_expand_evidence,
    select_business_document,
    select_business_document_from_index_html,
)
from scripts.ndx_taxonomy_v2 import _align_fetch_attempts


def _history_rows() -> pd.DataFrame:
    rows = []
    for ticker, cik, cusip, dates in [
        ("FB", 1326801, "30303M102", ["2022-06-08", "2022-06-30"]),
        ("META", 1326801, "30303M102", ["2022-09-30"]),
        ("GOOG", 1652044, "02079K107", ["2022-06-30", "2022-09-30"]),
        ("GOOGL", 1652044, "02079K305", ["2022-06-30", "2022-09-30"]),
        ("FISV", 798354, "337738108", ["2023-06-06", "2023-06-30"]),
    ]:
        for report_date in dates:
            rows.append({
                "report_date": report_date,
                "filed_date": "2023-01-01",
                "available_date": report_date,
                "accession_number": f"0000000000-{report_date.replace('-', '')}",
                "ticker": ticker,
                "name": ticker,
                "cusip": cusip,
                "isin": "",
                "weight": 0.2,
                "value_usd": 100.0,
                "mapping_method": "test",
                "source_locator": "https://www.sec.gov/test",
            })
    return pd.DataFrame(rows)


def _crosswalk() -> pd.DataFrame:
    return pd.DataFrame([
        {"ticker": "FB", "cik": 1326801, "mapping_status": "mapped", "cusips": "30303M102"},
        {"ticker": "META", "cik": 1326801, "mapping_status": "mapped", "cusips": "30303M102"},
        {"ticker": "GOOG", "cik": 1652044, "mapping_status": "mapped", "cusips": "02079K107"},
        {"ticker": "GOOGL", "cik": 1652044, "mapping_status": "mapped", "cusips": "02079K305"},
        {"ticker": "FISV", "cik": 798354, "mapping_status": "mapped", "cusips": "337738108"},
    ])


class NdxTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.taxonomy = load_taxonomy_definition("config/candidate_taxonomy_v2.yaml")
        cls.lifecycle = load_security_lifecycle("config/ndx_security_lifecycle.yaml")
        cls.universe = build_security_universe(
            _history_rows(), _crosswalk(), lifecycle=cls.lifecycle
        )

    def test_identity_preserves_share_classes_and_symbol_lifecycles(self):
        identities = self.universe.identities
        fb = identities[identities["ticker"].str.contains("FB|META", regex=True)]
        goog = identities[identities["ticker"].str.contains("GOOG", regex=True)]
        self.assertEqual(fb["security_id"].nunique(), 1)
        self.assertEqual(fb["issuer_id"].nunique(), 1)
        self.assertEqual(goog["security_id"].nunique(), 2)
        self.assertEqual(goog["issuer_id"].nunique(), 1)
        fisv = self.universe.observations[self.universe.observations["ticker"].eq("FISV")]
        self.assertIn("FI", set(fisv["price_ticker"]))
        self.assertTrue(self.universe.lifecycle_aliases["recognized_ticker"].isin(["FISV", "FI"]).any())

    def test_history_union_never_adds_qqq(self):
        self.assertNotIn("QQQ", set(self.universe.observations["ticker"]))
        with self.assertRaisesRegex(NdxTaxonomyError, "QQQ"):
            bad = _history_rows()
            bad.loc[0, "ticker"] = "QQQ"
            build_security_universe(bad, _crosswalk(), lifecycle=self.lifecycle)

    def test_evidence_applies_only_after_available_date(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        evidence = pd.DataFrame([{
            "security_id": "",
            "issuer_id": goog.issuer_id,
            "ticker": "",
            "risk_chain": "cloud_application_software",
            "effective_from": "2022-07-01",
            "effective_to": "",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": "SEC 10-K Item 1",
            "evidence_locator": "https://www.sec.gov/Archives/edgar/data/test",
            "evidence_available_date": "2022-07-01",
            "evidence_excerpt": "The reviewed business description supports the classification.",
            "confidence": "high",
            "status": "accepted",
        }])
        expanded, issues = normalize_and_expand_evidence(evidence, self.universe, self.taxonomy)
        self.assertTrue(issues.empty)
        records, conflicts, future = build_taxonomy_records(
            self.universe, self.taxonomy, expanded
        )
        goog_records = records[records["issuer_id"].eq(goog.issuer_id)]
        self.assertTrue(goog_records["status"].eq("accepted").any())
        self.assertTrue(goog_records["risk_chain"].eq("unclassified").any())
        self.assertTrue(conflicts.empty)
        self.assertTrue(future["future_data_guard_passed"].all())

    def test_future_evidence_cannot_be_used_as_historical_classification(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        evidence = pd.DataFrame([{
            "issuer_id": goog.issuer_id,
            "risk_chain": "cloud_application_software",
            "effective_from": "2022-01-01",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": "SEC",
            "evidence_locator": "https://www.sec.gov/Archives/edgar/data/test",
            "evidence_available_date": "2023-01-01",
            "evidence_excerpt": "Business description excerpt.",
            "confidence": "high",
            "status": "accepted",
        }])
        expanded, issues = normalize_and_expand_evidence(evidence, self.universe, self.taxonomy)
        self.assertFalse(issues.empty)
        self.assertTrue(expanded["validation_status"].eq("rejected").all())
        records, _, _ = build_taxonomy_records(self.universe, self.taxonomy, expanded)
        self.assertTrue(records[records["issuer_id"].eq(goog.issuer_id)]["status"].ne("accepted").all())

    def test_overlapping_accepted_chains_fail_closed_as_conflict(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        base = {
            "issuer_id": goog.issuer_id,
            "effective_from": "2022-01-01",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": "SEC",
            "evidence_locator": "https://www.sec.gov/Archives/edgar/data/test",
            "evidence_available_date": "2022-01-01",
            "evidence_excerpt": "Reviewed excerpt.",
            "confidence": "high",
            "status": "accepted",
        }
        evidence = pd.DataFrame([
            {**base, "risk_chain": "cloud_application_software"},
            {**base, "risk_chain": "platform_advertising"},
        ])
        expanded, issues = normalize_and_expand_evidence(evidence, self.universe, self.taxonomy)
        self.assertTrue(issues.empty)
        records, conflicts, _ = build_taxonomy_records(self.universe, self.taxonomy, expanded)
        self.assertTrue(conflicts["security_id"].nunique() >= 2)
        self.assertTrue(records[records["issuer_id"].eq(goog.issuer_id)]["status"].eq("conflict").any())

    def test_evidence_plan_cannot_promote_sic_by_itself(self):
        plan = build_evidence_plan(self.universe)
        self.assertEqual(len(plan), self.universe.identities.shape[0])
        self.assertTrue(plan["classification_allowed"].eq(False).all())

    def test_evidence_plan_prefers_point_in_time_annual_over_latest_quarterly(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        start = str(goog.observation_from)
        sic = pd.DataFrame([
            {
                "ticker": "GOOG", "cik": goog.cik,
                "available_date": "2021-01-15",
                "accession_number": "annual", "source_url": "annual.txt",
                "form": "10-K",
            },
            {
                "ticker": "GOOG", "cik": goog.cik,
                "available_date": start,
                "accession_number": "quarterly", "source_url": "quarterly.txt",
                "form": "10-Q",
            },
        ])

        plan = build_evidence_plan(self.universe, sic_selection=sic)
        row = plan[plan["security_id"].eq(goog.security_id)].iloc[0]

        self.assertEqual(row["accession_number"], "annual")
        self.assertEqual(row["form"], "10-K")
        self.assertEqual(row["plan_status"], "ready_for_point_in_time_review")
        self.assertTrue(bool(row["point_in_time_for_observation_start"]))

    def test_evidence_plan_uses_future_base_annual_before_amendment_and_never_quarterly(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        sic = pd.DataFrame([
            {
                "ticker": "GOOG", "cik": goog.cik,
                "available_date": str(goog.observation_from),
                "accession_number": "quarterly", "source_url": "quarterly.txt",
                "form": "10-Q",
            },
            {
                "ticker": "GOOG", "cik": goog.cik,
                "available_date": "2099-01-02",
                "accession_number": "amendment", "source_url": "amendment.txt",
                "form": "10-K/A",
            },
            {
                "ticker": "GOOG", "cik": goog.cik,
                "available_date": "2099-01-01",
                "accession_number": "base", "source_url": "base.txt",
                "form": "10-K",
            },
        ])

        plan = build_evidence_plan(self.universe, sic_selection=sic)
        row = plan[plan["security_id"].eq(goog.security_id)].iloc[0]

        self.assertEqual(row["accession_number"], "base")
        self.assertEqual(row["form"], "10-K")
        self.assertEqual(row["plan_status"], "source_after_observation_start")
        self.assertFalse(bool(row["point_in_time_for_observation_start"]))

    def test_superseded_fetch_attempts_are_preserved_but_not_reviewable(self):
        attempts = pd.DataFrame([
            {"job_id": "annual", "status": "fetched"},
            {"job_id": "quarterly", "status": "fetched"},
        ])
        plan = pd.DataFrame([{"job_id": "annual"}])

        active, stale = _align_fetch_attempts(attempts, plan)

        self.assertEqual(active["job_id"].tolist(), ["annual"])
        self.assertEqual(stale["job_id"].tolist(), ["quarterly"])
        self.assertEqual(
            stale["status"].tolist(),
            ["stale_plan_job_preserved_not_reviewable"],
        )

    def test_pending_review_is_not_counted_as_invalid_evidence(self):
        goog = self.universe.identities[
            self.universe.identities["ticker"].eq("GOOG")
        ].iloc[0]
        evidence = pd.DataFrame([{
            "issuer_id": goog.issuer_id,
            "evidence_source_type": "sec_filing_business_description",
            "evidence_source": "SEC review pending",
            "evidence_locator": "https://www.sec.gov/Archives/edgar/data/test",
            "evidence_available_date": "2022-07-01",
            "status": "pending_review",
        }])
        expanded, issues = normalize_and_expand_evidence(
            evidence, self.universe, self.taxonomy
        )
        self.assertTrue(issues.empty)
        self.assertTrue(expanded["validation_status"].eq("pending").all())

    def test_sec_document_selection_is_fail_closed(self):
        payload = {
            "directory": {"item": [{"name": "company.htm", "type": "10-K", "size": 1000}]}
        }
        self.assertEqual(select_business_document(payload, "10-K")["name"], "company.htm")
        with self.assertRaisesRegex(NdxTaxonomyError, "tied"):
            select_business_document({
                "directory": {"item": [
                    {"name": "a.htm", "type": "10-K", "size": 1000},
                    {"name": "b.htm", "type": "10-K", "size": 1000},
                ]}
            }, "10-K")

    def test_sec_index_html_fallback_selects_form_document(self):
        html = """
        <html><body><table>
          <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
          <tr><td>1</td><td>10-Q</td><td><a href="/ix?doc=/Archives/edgar/data/1/main.htm">main.htm</a></td><td>10-Q</td><td>1,200</td></tr>
          <tr><td>2</td><td>EX-10.1</td><td><a href="/Archives/edgar/data/1/exhibit.htm">exhibit.htm</a></td><td>EX-10.1</td><td>9,999</td></tr>
        </table></body></html>
        """
        selected = select_business_document_from_index_html(html, "10-Q")
        self.assertEqual(selected["name"], "main.htm")
        self.assertEqual(selected["size"], 1200)

    def test_evidence_csv_loader_accepts_empty_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.csv"
            pd.DataFrame(columns=["发行人编号", "风险链", "状态"]).to_csv(
                path, index=False, encoding="utf-8-sig"
            )
            frame = load_evidence_csv(path)
            self.assertEqual(list(frame.columns), [
                "evidence_id", "security_id", "issuer_id", "ticker", "risk_chain",
                "effective_from", "effective_to", "evidence_source_type", "evidence_source",
                "evidence_locator", "evidence_available_date", "accession_number",
                "evidence_excerpt", "confidence", "status", "notes",
            ])


if __name__ == "__main__":
    unittest.main()
