from __future__ import annotations

import unittest

import pandas as pd

from data import ndx_history


def _sample_xml(report_date: str, count: int = 100) -> bytes:
    holdings = []
    for i in range(count):
        holdings.append(
            "<invstOrSec>"
            f"<name>Company {i} Inc.</name><title>Company {i} Inc.</title>"
            f"<cusip>C{i:08d}</cusip>"
            f"<identifiers><isin value=\"US{i:010d}\"/></identifiers>"
            "<balance>100</balance><units>NS</units><curCd>USD</curCd>"
            "<valUSD>1000000</valUSD><pctVal>1.0</pctVal>"
            "<payoffProfile>Long</payoffProfile><assetCat>EC</assetCat>"
            "</invstOrSec>"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<edgarSubmission xmlns=\"http://www.sec.gov/edgar/nport\">"
        "<regName>INVESCO QQQ TRUST, SERIES 1</regName>"
        f"<repPdDate>{report_date}</repPdDate>"
        f"<invstOrSecs>{''.join(holdings)}</invstOrSecs>"
        "</edgarSubmission>"
    ).encode("utf-8")


def _company_payload(count: int = 100) -> dict:
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [
            [100000 + i, f"Company {i} Inc.", f"T{i:03d}", "Nasdaq"]
            for i in range(count)
        ],
    }


def _mapped_report(
    report_date: str,
    filed_date: str,
    accession: str,
) -> pd.DataFrame:
    raw = ndx_history.parse_nport_equities(
        _sample_xml(report_date),
        report_date=report_date,
        filed_date=filed_date,
        accession_number=accession,
        source_locator=f"https://www.sec.gov/{accession}.xml",
    )
    return ndx_history.resolve_nport_tickers(
        raw,
        company_ticker_payload=_company_payload(),
        overrides={},
    )


class NdxHistoryTests(unittest.TestCase):
    def test_nport_parser_requires_complete_equity_count_and_weight(self):
        frame = ndx_history.parse_nport_equities(
            _sample_xml("2025-03-31"),
            report_date="2025-03-31",
            filed_date="2025-05-29",
            accession_number="test-accession",
            source_locator="https://www.sec.gov/test.xml",
        )

        self.assertEqual(len(frame), 100)
        self.assertAlmostEqual(float(frame["weight"].sum()), 1.0)
        self.assertEqual(frame["available_date"].iloc[0], "2025-05-30")

    def test_incomplete_nport_report_is_rejected(self):
        with self.assertRaisesRegex(ndx_history.NdxHistoryError, "equity count"):
            ndx_history.parse_nport_equities(
                _sample_xml("2025-03-31", count=99),
                report_date="2025-03-31",
                filed_date="2025-05-29",
                accession_number="test-accession",
                source_locator="https://www.sec.gov/test.xml",
            )

    def test_unresolved_or_ambiguous_ticker_mapping_fails_closed(self):
        frame = ndx_history.parse_nport_equities(
            _sample_xml("2025-03-31"),
            report_date="2025-03-31",
            filed_date="2025-05-29",
            accession_number="test-accession",
            source_locator="https://www.sec.gov/test.xml",
        )
        payload = _company_payload()
        payload["data"] = payload["data"][:-1]

        with self.assertRaisesRegex(ndx_history.NdxHistoryError, "mapping incomplete"):
            ndx_history.resolve_nport_tickers(
                frame,
                company_ticker_payload=payload,
                overrides={},
            )

    def test_constituent_selection_never_uses_future_filing(self):
        first = _mapped_report("2024-12-31", "2025-02-26", "first")
        second = _mapped_report("2025-03-31", "2025-05-29", "second")
        history = pd.concat([first, second], ignore_index=True)

        snapshot, evidence = ndx_history.constituents_asof(history, "2025-05-29")

        self.assertEqual(evidence["report_date"], "2024-12-31")
        self.assertEqual(evidence["available_date"], "2025-02-27")
        self.assertTrue(evidence["future_data_guard_passed"])
        self.assertEqual(len(snapshot), 100)

    def test_historical_ticker_override_is_name_and_report_scoped(self):
        legacy = ndx_history.parse_nport_equities(
            _sample_xml("2020-03-31"),
            report_date="2020-03-31",
            filed_date="2020-05-29",
            accession_number="legacy",
            source_locator="https://www.sec.gov/legacy.xml",
        )
        current = ndx_history.parse_nport_equities(
            _sample_xml("2020-06-30"),
            report_date="2020-06-30",
            filed_date="2020-08-28",
            accession_number="current",
            source_locator="https://www.sec.gov/current.xml",
        )
        legacy.loc[0, "name"] = "Legacy Name Inc."
        current.loc[0, "name"] = "Current Name Inc."
        payload = _company_payload()
        payload["data"][0][1] = "Current Name Inc."
        payload["data"][0][2] = "NEW"
        combined = pd.concat([legacy, current], ignore_index=True)

        mapped = ndx_history.resolve_nport_tickers(
            combined,
            company_ticker_payload=payload,
            overrides={
                "C00000000": {
                    "ticker": "OLD",
                    "match_name": ndx_history._normalize_company_name("Legacy Name Inc."),
                    "min_report_date": "",
                    "max_report_date": "2020-03-31",
                },
            },
        )

        self.assertEqual(
            mapped.loc[mapped["report_date"] == "2020-03-31", "ticker"].iloc[0],
            "OLD",
        )
        self.assertEqual(
            mapped.loc[mapped["report_date"] == "2020-06-30", "ticker"].iloc[0],
            "NEW",
        )


if __name__ == "__main__":
    unittest.main()
