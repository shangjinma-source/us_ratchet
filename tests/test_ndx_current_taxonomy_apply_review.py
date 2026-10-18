from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from data.ndx_taxonomy import load_taxonomy_definition
from scripts.ndx_v11_current_taxonomy_apply_review import (
    CurrentTaxonomyReviewError,
    _normalise_spaces,
    _read_seed,
    _valid_tickers,
)


ROOT = Path(__file__).resolve().parents[1]


class CurrentTaxonomyApplyReviewTests(unittest.TestCase):
    def test_authored_current_seed_is_issuer_scoped_and_qqq_free(self):
        taxonomy = load_taxonomy_definition(ROOT / "config/candidate_taxonomy_v2.yaml")
        seed = _read_seed(
            ROOT / "config/ndx_v11_current_taxonomy_review_decisions.yaml",
            taxonomy,
        )

        tickers = {
            ticker
            for decision in seed["decisions"]
            for ticker in _valid_tickers(decision)
        }
        self.assertEqual(len(seed["decisions"]), 90)
        self.assertEqual(len(tickers), 91)
        self.assertNotIn("QQQ", tickers)
        self.assertTrue(all(decision["status"] == "accepted" for decision in seed["decisions"]))
        self.assertTrue(all(decision["risk_chain"] != "unclassified" for decision in seed["decisions"]))

    def test_ticker_validation_rejects_qqq_and_duplicate_tickers(self):
        with self.assertRaisesRegex(CurrentTaxonomyReviewError, "QQQ"):
            _valid_tickers({"tickers": ["QQQ"]})
        with self.assertRaisesRegex(CurrentTaxonomyReviewError, "duplicate"):
            _valid_tickers({"tickers": ["AAA", "aaa"]})

    def test_source_phrase_normalisation_is_whitespace_and_case_insensitive(self):
        self.assertEqual(
            _normalise_spaces("  Analog,\u00a0 mixed-signal\n"),
            "analog, mixed-signal",
        )

    def test_seed_rejects_unclassified_as_an_accepted_decision(self):
        taxonomy = load_taxonomy_definition(ROOT / "config/candidate_taxonomy_v2.yaml")
        payload = {
            "schema_version": 1,
            "review_registry_id": "test",
            "taxonomy_id": taxonomy["taxonomy_id"],
            "decisions": [{
                "decision_id": "test:AAA",
                "tickers": ["AAA"],
                "risk_chain": "unclassified",
                "confidence": "high",
                "status": "accepted",
                "evidence_phrase": "direct business description",
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.yaml"
            path.write_text(yaml.safe_dump(payload), encoding="utf-8")
            with self.assertRaisesRegex(CurrentTaxonomyReviewError, "unsupported accepted risk chain"):
                _read_seed(path, taxonomy)


if __name__ == "__main__":
    unittest.main()
