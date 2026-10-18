from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_candidate_identity_v3 import (
    NdxDynamicShadowCandidateIdentityV3Error,
    resolve_decision_date_taxonomy_identities,
)
from data.ndx_security_identity import load_security_lifecycle


def _official(*tickers: str) -> pd.DataFrame:
    return pd.DataFrame({"ticker": list(tickers)})


def _row(
    ticker: str,
    *,
    cik: str = "0001326801",
    cusip: str = "30303M102",
    security_id: str = "security:0001326801:30303M102",
    issuer_id: str = "issuer:0001326801",
    selection_date_end: str = "2026-05-29",
    evidence_available_date: str = "2022-02-04",
) -> dict[str, str]:
    return {
        "ticker": ticker,
        "cik": cik,
        "cusip": cusip,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "selection_date_end": selection_date_end,
        "evidence_available_date": evidence_available_date,
        "risk_chain": "platform_advertising",
        "status": "accepted",
    }


def _lifecycle():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "lifecycle.yaml"
        path.write_text(yaml.safe_dump({
            "schema_version": 1,
            "mapping_id": "fixture_lifecycle",
            "last_reviewed": "2026-09-01",
            "rules": [{
                "rule_id": "meta_fb_to_meta_2022",
                "cik": "0001326801",
                "cusip": "30303M102",
                "issuer_name": "Meta Platforms, Inc.",
                "recognized_tickers": ["FB", "META"],
                "intervals": [
                    {"effective_from": None, "effective_to": "2022-06-08", "price_ticker": "FB"},
                    {"effective_from": "2022-06-09", "effective_to": None, "price_ticker": "META"},
                ],
                "evidence": [{
                    "effective_date": "2022-06-09",
                    "url": "https://example.test/meta-ticker-change",
                }],
            }],
        }, sort_keys=False), encoding="utf-8")
        return load_security_lifecycle(path)


class DynamicShadowCandidateIdentityV3Tests(unittest.TestCase):
    def test_meta_post_change_resolves_only_to_meta(self) -> None:
        resolved, audit = resolve_decision_date_taxonomy_identities(
            _official("META"), pd.DataFrame([_row("FB;META")]), _lifecycle(),
            decision_date="2026-10-01",
        )
        self.assertEqual(resolved.loc[0, "ticker"], "META")
        self.assertEqual(resolved.loc[0, "taxonomy_ticker_aliases"], "FB;META")
        self.assertEqual(
            resolved.loc[0, "ticker_resolution_status"],
            "REVIEWED_DECISION_DATE_LIFECYCLE",
        )
        self.assertEqual(audit["reviewed_lifecycle_tickers"], ["META"])
        self.assertFalse(audit["execution_valid_on_date_identity_proved"])
        self.assertFalse(audit["admission_authority"])

    def test_fb_pre_change_resolves_only_to_fb(self) -> None:
        row = _row(
            "FB;META", selection_date_end="2022-05-31",
            evidence_available_date="2022-02-04",
        )
        resolved, _ = resolve_decision_date_taxonomy_identities(
            _official("FB"), pd.DataFrame([row]), _lifecycle(),
            decision_date="2022-06-08",
        )
        self.assertEqual(resolved.loc[0, "ticker"], "FB")

    def test_cross_date_aliases_are_rejected(self) -> None:
        cases = (("META", "2022-06-08"), ("FB", "2026-10-01"))
        for ticker, decision in cases:
            with self.subTest(ticker=ticker, decision=decision), self.assertRaisesRegex(
                NdxDynamicShadowCandidateIdentityV3Error, "decision-date interval",
            ):
                resolve_decision_date_taxonomy_identities(
                    _official(ticker), pd.DataFrame([_row(
                        "FB;META",
                        selection_date_end="2022-05-31" if decision < "2023" else "2026-05-29",
                    )]), _lifecycle(), decision_date=decision,
                )

    def test_multi_ticker_alias_without_reviewed_rule_is_rejected(self) -> None:
        row = _row(
            "OLD;NEW", cik="0000000001", cusip="123456789",
            security_id="security:0000000001:123456789",
            issuer_id="issuer:0000000001",
        )
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "lacks a reviewed lifecycle",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("NEW"), pd.DataFrame([row]), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_lifecycle_cik_cusip_and_issuer_binding_is_strict(self) -> None:
        mutations = (
            {"cik": "0000000001", "issuer_id": "issuer:0000000001"},
            {"cusip": "999999999", "security_id": "security:0001326801:999999999"},
            {"issuer_id": "issuer:0000000001"},
        )
        for mutation in mutations:
            row = _row("FB;META")
            row.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(
                NdxDynamicShadowCandidateIdentityV3Error,
            ):
                resolve_decision_date_taxonomy_identities(
                    _official("META"), pd.DataFrame([row]), _lifecycle(),
                    decision_date="2026-10-01",
                )

    def test_security_id_must_be_derived_from_cik_and_cusip(self) -> None:
        forged = _row("META", security_id="security:0001326801:999999999")
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "security_id disagrees",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("META"), pd.DataFrame([forged]), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_known_single_ticker_cannot_bypass_lifecycle_with_wrong_cusip(self) -> None:
        wrong_cusip = _row(
            "META", cusip="999999999",
            security_id="security:0001326801:999999999",
            selection_date_end="2022-05-31",
        )
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "CUSIP disagrees",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("META"), pd.DataFrame([wrong_cusip]), _lifecycle(),
                decision_date="2022-06-08",
            )

    def test_known_lifecycle_cik_cannot_escape_through_unknown_exact_ticker(self) -> None:
        renamed = _row("ZZZ")
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "not recognized",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("ZZZ"), pd.DataFrame([renamed]), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_known_lifecycle_ticker_cannot_bind_to_a_different_cik(self) -> None:
        forged = _row(
            "META", cik="0000000001", cusip="123456789",
            security_id="security:0000000001:123456789",
            issuer_id="issuer:0000000001",
        )
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "lifecycle CIK disagrees",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("META"), pd.DataFrame([forged]), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_same_security_cannot_resolve_to_two_official_tickers(self) -> None:
        rows = [
            _row("AAA", cik="1", cusip="123456789", security_id="same", issuer_id="issuer:0000000001"),
            _row("BBB", cik="1", cusip="123456789", security_id="same", issuer_id="issuer:0000000001"),
        ]
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "security_id",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("AAA", "BBB"), pd.DataFrame(rows), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_same_cusip_cannot_resolve_to_two_distinct_securities(self) -> None:
        rows = [
            _row("AAA", cik="1", cusip="123456789", security_id="security:0000000001:123456789", issuer_id="issuer:0000000001"),
            _row("BBB", cik="2", cusip="123456789", security_id="security:0000000002:123456789", issuer_id="issuer:0000000002"),
        ]
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "CUSIP",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("AAA", "BBB"), pd.DataFrame(rows), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_ambiguous_latest_identity_for_one_ticker_is_rejected(self) -> None:
        rows = [
            _row("AAA", cik="1", cusip="123456789", security_id="s1", issuer_id="issuer:0000000001"),
            _row("AAA", cik="2", cusip="987654321", security_id="s2", issuer_id="issuer:0000000002"),
        ]
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "ambiguous latest",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("AAA"), pd.DataFrame(rows), _lifecycle(),
                decision_date="2026-10-01",
            )

    def test_distinct_share_classes_of_one_issuer_are_preserved_but_not_counted_twice_for_k(self) -> None:
        rows = [
            _row(
                "GOOG", cik="1652044", cusip="02079K107",
                security_id="security:0001652044:02079K107",
                issuer_id="issuer:0001652044",
            ),
            _row(
                "GOOGL", cik="1652044", cusip="02079K305",
                security_id="security:0001652044:02079K305",
                issuer_id="issuer:0001652044",
            ),
        ]
        resolved, audit = resolve_decision_date_taxonomy_identities(
            _official("GOOG", "GOOGL"), pd.DataFrame(rows), _lifecycle(),
            decision_date="2026-10-01",
        )
        self.assertEqual(set(resolved["ticker"]), {"GOOG", "GOOGL"})
        self.assertEqual(audit["resolved_security_count"], 2)
        self.assertEqual(audit["resolved_unique_issuer_count"], 1)
        self.assertEqual(audit["multi_security_issuer_ids"], ["issuer:0001652044"])
        self.assertTrue(audit["one_security_per_issuer_must_be_enforced_by_portfolio_search"])

    def test_future_or_noncanonical_dates_cannot_enter_decision_snapshot(self) -> None:
        future = _row("AAA", cik="1", cusip="123456789", security_id="s1", issuer_id="issuer:0000000001")
        future["evidence_available_date"] = "2026-10-02"
        resolved, audit = resolve_decision_date_taxonomy_identities(
            _official("AAA"), pd.DataFrame([future]), _lifecycle(),
            decision_date="2026-10-01",
        )
        self.assertTrue(resolved.empty)
        self.assertEqual(audit["missing_taxonomy_identity_tickers"], ["AAA"])

        invalid = dict(future, evidence_available_date="2026-09-30-after")
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateIdentityV3Error, "invalid taxonomy evidence_available_date",
        ):
            resolve_decision_date_taxonomy_identities(
                _official("AAA"), pd.DataFrame([invalid]), _lifecycle(),
                decision_date="2026-10-01",
            )


if __name__ == "__main__":
    unittest.main()
