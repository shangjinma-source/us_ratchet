import unittest

import pandas as pd

from backtest.ndx_incumbent_pit_attribution import (
    INCUMBENT_TICKERS,
    NdxIncumbentPitAttributionError,
    build_incumbent_pit_attribution,
)


def _evidence() -> pd.DataFrame:
    return pd.DataFrame([{
        "ticker": ticker,
        "security_id": f"security:{index}",
        "issuer_id": f"issuer:{index}",
        "risk_chain": f"chain_{index}",
        "effective_from": "2019-01-01",
        "effective_to": "",
        "evidence_source_type": "sec_filing_business_description",
        "evidence_locator": f"https://www.sec.gov/Archives/{index}",
        "evidence_available_date": "2019-01-02",
        "status": "accepted",
    } for index, ticker in enumerate(INCUMBENT_TICKERS)])


def _manifest() -> dict:
    return {
        "manifest_type": "ndx_incumbent_overlay_reviewed_bundle",
        "historical_backfill_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
        "summary": {"historical_backfill_allowed": False},
    }


class NdxIncumbentPitAttributionTests(unittest.TestCase):
    def test_builds_complete_attribution_only_panel(self):
        result = build_incumbent_pit_attribution(
            _evidence(), ["2023-07-03", "2024-06-03"], source_manifest=_manifest(),
        )
        self.assertEqual(len(result), 16)
        self.assertFalse(result["candidate_selection_allowed"].any())
        self.assertFalse(result["historical_backfill_created"].any())

    def test_future_evidence_fails_closed(self):
        evidence = _evidence()
        evidence.loc[evidence["ticker"].eq("NVDA"), "evidence_available_date"] = "2025-01-01"
        with self.assertRaises(NdxIncumbentPitAttributionError):
            build_incumbent_pit_attribution(
                evidence, ["2024-06-03"], source_manifest=_manifest(),
            )

    def test_missing_incumbent_and_changed_backfill_policy_fail(self):
        with self.assertRaises(NdxIncumbentPitAttributionError):
            build_incumbent_pit_attribution(
                _evidence().iloc[:-1], ["2024-06-03"], source_manifest=_manifest(),
            )
        manifest = _manifest()
        manifest["historical_backfill_allowed"] = True
        with self.assertRaises(NdxIncumbentPitAttributionError):
            build_incumbent_pit_attribution(
                _evidence(), ["2024-06-03"], source_manifest=manifest,
            )


if __name__ == "__main__":
    unittest.main()
