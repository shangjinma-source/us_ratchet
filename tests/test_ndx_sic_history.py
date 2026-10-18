from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd
import requests

from data.ndx_fundamentals import NdxFundamentalError
from data.ndx_sic_history import (
    build_sic_evidence_plan,
    filing_header_url,
    parse_sec_filing_header,
)
from scripts.ndx_sic_readiness import _fetch_header


HEADER = """<SEC-HEADER>test.hdr.sgml : 20240201
<ACCEPTANCE-DATETIME>20240201123456
ACCESSION NUMBER:               0000001001-24-000001
CONFORMED SUBMISSION TYPE:      10-K
FILED AS OF DATE:               20240201

FILER:
    COMPANY DATA:
        COMPANY CONFORMED NAME:         TEST SEMICONDUCTOR INC
        CENTRAL INDEX KEY:              0000001001
        STANDARD INDUSTRIAL CLASSIFICATION: SEMICONDUCTORS & RELATED DEVICE MFG [3674]
</SEC-HEADER>
"""


class NdxSicHistoryTests(unittest.TestCase):
    def test_header_download_retries_transient_ssl_failure(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                self.chunk_size = chunk_size
                yield HEADER.encode("latin-1")

        class Session:
            calls = 0

            def get(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise requests.exceptions.SSLError("temporary EOF")
                return Response()

        session = Session()
        with patch("scripts.ndx_sic_readiness.time.sleep") as sleep:
            content = _fetch_header(session, "https://www.sec.gov/test", attempts=2)

        self.assertIn(b"</SEC-HEADER>", content)
        self.assertEqual(session.calls, 2)
        sleep.assert_called_once()

    def test_filing_header_parser_preserves_point_in_time_sic_evidence(self):
        result = parse_sec_filing_header(
            HEADER.encode("latin-1"),
            expected_cik=1001,
            expected_accession="0000001001-24-000001",
        )

        self.assertEqual(result["sic"], 3674)
        self.assertEqual(result["sic_group_2d"], "36")
        self.assertEqual(result["sic_division"], "manufacturing")
        self.assertEqual(result["filed_date"], "2024-02-01")
        self.assertTrue(result["sic_available"])

    def test_filing_header_parser_fails_on_identity_mismatch(self):
        with self.assertRaisesRegex(NdxFundamentalError, "CIK mismatch"):
            parse_sec_filing_header(
                HEADER,
                expected_cik=2002,
                expected_accession="0000001001-24-000001",
            )

    def test_sic_plan_deduplicates_share_classes_without_losing_rows(self):
        plan = pd.DataFrame([
            {"selection_date": "2024-03-01", "ticker": "AAA", "cik": 1001},
            {"selection_date": "2024-03-01", "ticker": "AAB", "cik": 1001},
        ])
        components = pd.DataFrame([{
            "selection_date": "2024-03-01",
            "cik": 1001,
            "metric": "assets",
            "component_set": "current",
            "available_date": "2024-02-02",
            "accession_number": "0000001001-24-000001",
        }])

        jobs, mapped = build_sic_evidence_plan(plan, components)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(mapped), 2)
        self.assertTrue(bool(mapped["classification_guard_passed"].all()))
        self.assertEqual(
            jobs.iloc[0]["source_url"],
            filing_header_url(1001, "0000001001-24-000001"),
        )


if __name__ == "__main__":
    unittest.main()
