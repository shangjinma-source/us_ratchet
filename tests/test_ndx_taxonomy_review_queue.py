from __future__ import annotations

import unittest

import pandas as pd

from data.ndx_taxonomy_review_queue import build_historical_review_queue


class NdxTaxonomyReviewQueueTests(unittest.TestCase):
    def test_current_hint_never_assigns_historical_chain(self):
        evidence = pd.DataFrame([{"evidence_id": "sec:a", "issuer_id": "issuer:a", "status": "pending_review", "evidence_available_date": "2022-01-01", "evidence_excerpt": "Historical business text"}])
        documents = pd.DataFrame([{"job_id": "a", "tickers": "AAA", "form": "10-K", "accession_number": "x", "extraction_status": "business_section_extracted", "raw_manifest_verified": True, "raw_sha256": "raw", "business_excerpt_sha256": "excerpt", "section_text_chars": 1000}])
        registry = {"decisions": [{"decision_id": "current:AAA", "tickers": ["AAA"], "risk_chain": "consumer", "confidence": "high", "status": "accepted", "evidence_phrase": "consumer products"}]}

        queue = build_historical_review_queue(evidence, documents, registry)

        self.assertEqual(queue.loc[0, "current_hint_risk_chain"], "consumer")
        self.assertFalse(bool(queue.loc[0, "risk_chain_assignment_performed"]))
        self.assertFalse(bool(queue.loc[0, "historical_backfill_from_current_allowed"]))
        self.assertEqual(queue.loc[0, "review_status"], "manual_historical_source_review_required")

    def test_nonstandard_extraction_remains_repair_required(self):
        evidence = pd.DataFrame([{"evidence_id": "sec:a", "issuer_id": "issuer:a", "status": "pending_review", "evidence_available_date": "2022-01-01", "evidence_excerpt": "Candidate text"}])
        documents = pd.DataFrame([{"job_id": "a", "tickers": "AAA", "form": "20-F", "accession_number": "x", "extraction_status": "business_text_fallback_candidate", "raw_manifest_verified": True, "raw_sha256": "raw", "business_excerpt_sha256": "excerpt", "section_text_chars": 1000}])

        queue = build_historical_review_queue(evidence, documents, {"decisions": []})

        self.assertFalse(bool(queue.loc[0, "historical_evidence_reviewable"]))
        self.assertEqual(queue.loc[0, "review_status"], "source_extraction_repair_required")


if __name__ == "__main__":
    unittest.main()
