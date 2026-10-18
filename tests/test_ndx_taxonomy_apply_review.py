from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_taxonomy_review import REVIEW_TEMPLATE_COLUMNS
from scripts.ndx_taxonomy_v2_apply_review import _validate_and_apply


class NdxTaxonomyApplyReviewTests(unittest.TestCase):
    def test_hash_locked_decision_applies_from_evidence_available_date(self):
        template = pd.DataFrame([{
            **{column: "" for column in REVIEW_TEMPLATE_COLUMNS},
            "evidence_id": "sec:job-a",
            "issuer_id": "issuer:1",
            "evidence_source_type": "sec_filing_business_description",
            "evidence_locator": "https://www.sec.gov/Archives/edgar/data/test",
            "evidence_available_date": "2022-01-02",
            "status": "pending_review",
        }], columns=REVIEW_TEMPLATE_COLUMNS)
        documents = pd.DataFrame([{
            "job_id": "job-a",
            "issuer_id": "issuer:1",
            "tickers": "AAA",
            "extraction_status": "business_section_extracted",
            "raw_manifest_verified": True,
            "raw_sha256": "raw-hash",
            "business_excerpt_sha256": "excerpt-hash",
        }])
        registry = {
            "review_registry_id": "test",
            "decision_policy": {"effective_from_rule": "evidence_available_date"},
            "decisions": [{
                "ticker": "AAA",
                "evidence_id": "sec:job-a",
                "issuer_id": "issuer:1",
                "expected_raw_sha256": "raw-hash",
                "expected_excerpt_sha256": "excerpt-hash",
                "risk_chain": "consumer",
                "confidence": "high",
                "status": "accepted",
                "notes": "direct business description",
            }],
        }
        taxonomy = {"risk_chains": {"consumer": {}, "unclassified": {}}}

        reviewed, audit = _validate_and_apply(template, documents, registry, taxonomy)

        self.assertEqual(len(audit), 1)
        self.assertEqual(reviewed.loc[0, "risk_chain"], "consumer")
        self.assertEqual(reviewed.loc[0, "effective_from"], "2022-01-02")
        self.assertEqual(reviewed.loc[0, "status"], "accepted")


if __name__ == "__main__":
    unittest.main()
