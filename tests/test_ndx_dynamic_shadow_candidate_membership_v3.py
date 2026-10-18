from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_candidate_membership_v3 import (
    NdxDynamicShadowCandidateMembershipV3Error,
    build_runtime_official_eligible_membership_v3,
)
from backtest.ndx_dynamic_shadow_candidate_snapshot import (
    build_runtime_official_eligible_membership,
)
from backtest.ndx_cardinality_discovery import issuer_dedup_feasible_count
from data.ndx_security_identity import load_security_lifecycle


def _identity(
    ticker: str,
    index: int,
    *,
    cik: str | None = None,
    cusip: str | None = None,
    issuer_id: str | None = None,
    security_id: str | None = None,
    evidence_available_date: str = "2026-06-01",
) -> dict[str, str]:
    canonical_cik = cik or f"{index + 1:010d}"
    canonical_cusip = cusip or f"{index + 1:09d}"
    return {
        "ticker": ticker,
        "cik": canonical_cik,
        "cusip": canonical_cusip,
        "security_id": security_id or f"security:{canonical_cik}:{canonical_cusip}",
        "issuer_id": issuer_id or f"issuer:{canonical_cik}",
        "risk_chain": "semiconductor",
        "status": "accepted",
        "evidence_available_date": evidence_available_date,
        "selection_date_end": "2026-05-29",
    }


def _official(tickers: list[str]) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": tickers,
        "as_of_date": ["2026-10-01"] * len(tickers),
        "source_id": ["nasdaq_100"] * len(tickers),
        "source_type": ["index_constituent"] * len(tickers),
        "source_locator": ["https://www.nasdaq.com/official"] * len(tickers),
    })


def _search_plan() -> dict:
    return {"universe_tracks": {
        "strict_technology": {"accepted_risk_chains": ["semiconductor"]},
        "technology_plus_adjacent": {
            "inherits": "strict_technology",
            "additional_risk_chains": ["software"],
        },
    }}


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


def _meta_universe() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tickers = ["META"] + [f"T{index:03d}" for index in range(99)]
    rows = [
        _identity(
            "FB;META", 500,
            cik="0001326801", cusip="30303M102",
            issuer_id="issuer:0001326801",
            security_id="security:0001326801:30303M102",
        )
    ] + [_identity(ticker, index) for index, ticker in enumerate(tickers[1:])]
    return _official(tickers), pd.DataFrame({"ticker": tickers}), pd.DataFrame(rows)


def _kwargs() -> dict:
    return {
        "decision_date": "2026-10-01",
        "observed_at_utc": "2026-10-01T20:05:00+00:00",
        "decision_close_timestamp_utc": "2026-10-01T20:00:00+00:00",
        "seal_timestamp_utc": "2026-10-01T20:10:00+00:00",
        "conservative_seal_deadline_utc": "2026-10-02T13:30:00+00:00",
        "allow_degraded_reviewed_taxonomy_subset": True,
    }


class DynamicShadowCandidateMembershipV3Tests(unittest.TestCase):
    def test_adapter_recovers_meta_that_frozen_exact_ticker_builder_omits(self) -> None:
        official, nport, taxonomy = _meta_universe()
        old_eligible, old_audit = build_runtime_official_eligible_membership(
            official, nport, taxonomy, _search_plan(), **_kwargs()
        )
        self.assertNotIn("META", set(old_eligible["ticker"]))
        self.assertIn("META", old_audit["missing_taxonomy_identity_tickers"])

        eligible, audit = build_runtime_official_eligible_membership_v3(
            official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
        )
        self.assertIn("META", set(eligible["ticker"]))
        meta = eligible.loc[eligible["ticker"].eq("META")]
        self.assertEqual(set(meta["taxonomy_ticker_aliases"]), {"FB;META"})
        self.assertEqual(
            set(meta["ticker_resolution_status"]),
            {"REVIEWED_DECISION_DATE_LIFECYCLE"},
        )
        self.assertIn("META", audit["identity_resolution"]["reviewed_lifecycle_tickers"])
        self.assertFalse(audit["official_membership_effective_date_proved"])
        self.assertFalse(audit["execution_valid_on_date_identity_proved"])

    def test_identity_issue_exclusion_matches_every_raw_alias(self) -> None:
        for excluded in ({"FB"}, {"META"}):
            official, nport, taxonomy = _meta_universe()
            with self.subTest(excluded=excluded):
                eligible, audit = build_runtime_official_eligible_membership_v3(
                    official,
                    nport,
                    taxonomy,
                    _search_plan(),
                    _lifecycle(),
                    excluded_identity_tickers=excluded,
                    **_kwargs(),
                )
                self.assertNotIn("META", set(eligible["ticker"]))
                exclusion = audit["identity_issue_exclusion"]
                self.assertEqual(exclusion["excluded_raw_taxonomy_row_count"], 1)
                self.assertEqual(exclusion["excluded_by_ticker_alias_row_count"], 1)
                self.assertEqual(exclusion["excluded_raw_taxonomy_aliases"], ["FB", "META"])
                self.assertTrue(exclusion["post_resolution_exclusion_rechecked"])

    def test_security_and_issuer_issue_exclusions_are_retained(self) -> None:
        cases = (
            {"excluded_identity_security_ids": {"security:0001326801:30303M102"}},
            {"excluded_identity_issuer_ids": {"issuer:0001326801"}},
        )
        for exclusions in cases:
            official, nport, taxonomy = _meta_universe()
            with self.subTest(exclusions=exclusions):
                eligible, audit = build_runtime_official_eligible_membership_v3(
                    official, nport, taxonomy, _search_plan(), _lifecycle(),
                    **exclusions, **_kwargs(),
                )
                self.assertNotIn("META", set(eligible["ticker"]))
                self.assertEqual(
                    audit["identity_issue_exclusion"]["excluded_raw_taxonomy_row_count"],
                    1,
                )

    def test_excluded_old_alias_cannot_resurrect_through_later_exact_ticker_row(self) -> None:
        official, nport, taxonomy = _meta_universe()
        exact_meta = dict(
            taxonomy.loc[taxonomy["ticker"].eq("FB;META")].iloc[0].to_dict(),
            ticker="META",
            selection_date_end="2026-08-31",
        )
        taxonomy = pd.concat([taxonomy, pd.DataFrame([exact_meta])], ignore_index=True)
        eligible, audit = build_runtime_official_eligible_membership_v3(
            official,
            nport,
            taxonomy,
            _search_plan(),
            _lifecycle(),
            excluded_identity_tickers={"FB"},
            **_kwargs(),
        )
        self.assertNotIn("META", set(eligible["ticker"]))
        exclusion = audit["identity_issue_exclusion"]
        self.assertEqual(exclusion["directly_excluded_raw_taxonomy_row_count"], 1)
        self.assertEqual(exclusion["excluded_raw_taxonomy_row_count"], 2)
        self.assertTrue(exclusion["same_security_and_alias_connected_exclusion"])

    def test_excluded_latest_identity_cannot_fall_back_to_older_ticker_identity(self) -> None:
        official, nport, taxonomy = _meta_universe()
        old = taxonomy.loc[taxonomy["ticker"].eq("T000")].iloc[0].to_dict()
        old["selection_date_end"] = "2026-04-30"
        bad_latest = _identity(
            "T000",
            900,
            security_id="security:bad-latest",
        )
        bad_latest["selection_date_end"] = "2026-08-31"
        taxonomy = pd.concat([
            taxonomy.loc[~taxonomy["ticker"].eq("T000")],
            pd.DataFrame([old, bad_latest]),
        ], ignore_index=True)
        eligible, audit = build_runtime_official_eligible_membership_v3(
            official,
            nport,
            taxonomy,
            _search_plan(),
            _lifecycle(),
            excluded_identity_security_ids={"security:bad-latest"},
            **_kwargs(),
        )
        self.assertNotIn("T000", set(eligible["ticker"]))
        exclusion = audit["identity_issue_exclusion"]
        self.assertEqual(exclusion["directly_excluded_raw_taxonomy_row_count"], 1)
        self.assertEqual(exclusion["excluded_raw_taxonomy_row_count"], 2)
        self.assertFalse(exclusion["older_identity_fallback_allowed"])

    def test_share_classes_preserve_securities_but_dynamic_k_counts_issuers(self) -> None:
        tickers = ["GOOG", "GOOGL"] + [f"T{index:03d}" for index in range(98)]
        rows = [
            _identity(
                "GOOG", 700, cik="0001652044", cusip="02079K107",
                issuer_id="issuer:0001652044",
                security_id="security:0001652044:02079K107",
            ),
            _identity(
                "GOOGL", 701, cik="0001652044", cusip="02079K305",
                issuer_id="issuer:0001652044",
                security_id="security:0001652044:02079K305",
            ),
        ] + [_identity(ticker, index) for index, ticker in enumerate(tickers[2:])]
        eligible, audit = build_runtime_official_eligible_membership_v3(
            _official(tickers),
            pd.DataFrame({"ticker": tickers}),
            pd.DataFrame(rows),
            _search_plan(),
            _lifecycle(),
            **_kwargs(),
        )
        for track, track_audit in audit["track_dynamic_cardinality"].items():
            scoped = eligible.loc[eligible["universe_track"].eq(track)]
            self.assertEqual(scoped["security_id"].nunique(), 100)
            self.assertEqual(scoped["issuer_id"].nunique(), 99)
            self.assertEqual(track_audit["dynamic_k_maximum"], 99)
            self.assertEqual(issuer_dedup_feasible_count(scoped, 100), 0)
            self.assertGreater(issuer_dedup_feasible_count(scoped, 99), 0)
        self.assertTrue(audit["one_security_per_issuer_required"])
        self.assertEqual(
            audit["portfolio_optimization_holding_count_policy"],
            "DYNAMIC_K_1_TO_ELIGIBLE_UNIQUE_ISSUER_COUNT",
        )
        self.assertIsNone(audit["migration_control_holding_count_policy"])

    def test_future_taxonomy_evidence_stays_missing_and_cannot_gain_authority(self) -> None:
        official, nport, taxonomy = _meta_universe()
        taxonomy.loc[taxonomy["ticker"].eq("FB;META"), "evidence_available_date"] = "2026-10-02"
        eligible, audit = build_runtime_official_eligible_membership_v3(
            official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
        )
        self.assertNotIn("META", set(eligible["ticker"]))
        self.assertIn("META", audit["identity_resolution"]["missing_taxonomy_identity_tickers"])
        self.assertFalse(audit["admission_authority"])
        self.assertFalse(audit["promotion_allowed"])
        self.assertFalse(audit["live_mutation"])

    def test_official_observation_metadata_cannot_be_future_or_mixed(self) -> None:
        for dates, pattern in (
            (["2026-10-02"] * 100, "future official observation"),
            (["2026-09-30", "2026-10-01"] + ["2026-10-01"] * 98, "one observation date"),
        ):
            official, nport, taxonomy = _meta_universe()
            official["as_of_date"] = dates
            with self.subTest(pattern=pattern), self.assertRaisesRegex(
                NdxDynamicShadowCandidateMembershipV3Error, pattern,
            ):
                build_runtime_official_eligible_membership_v3(
                    official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
                )

    def test_stale_official_observation_is_preserved_and_explicitly_degraded(self) -> None:
        official, nport, taxonomy = _meta_universe()
        official["as_of_date"] = "2026-09-30"
        eligible, audit = build_runtime_official_eligible_membership_v3(
            official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
        )
        self.assertEqual(set(eligible["membership_snapshot_date"]), {"2026-09-30"})
        self.assertEqual(set(eligible["selection_date"]), {"2026-10-01"})
        self.assertEqual(audit["official_observation_lag_calendar_days"], 1)
        self.assertIn(
            "OFFICIAL_OBSERVATION_DATE_PRECEDES_DECISION",
            audit["degraded_reasons"],
        )
        self.assertEqual(
            audit["membership_snapshot_date_semantics"],
            "OFFICIAL_RUNTIME_OBSERVATION_DATE_NOT_DECISION_DATE",
        )

    def test_official_capture_must_have_one_source_locator(self) -> None:
        official, nport, taxonomy = _meta_universe()
        official.loc[0, "source_locator"] = "https://example.test/forged-second-source"
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateMembershipV3Error, "one nonblank source locator",
        ):
            build_runtime_official_eligible_membership_v3(
                official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
            )

    def test_lifecycle_review_must_be_canonical_and_available_by_decision(self) -> None:
        official, nport, taxonomy = _meta_universe()
        for last_reviewed, pattern in (
            ("2026-10-02", "reviewed after the decision"),
            ("2026-10-01T00:00:00", "invalid security lifecycle last_reviewed"),
        ):
            with self.subTest(last_reviewed=last_reviewed), self.assertRaisesRegex(
                NdxDynamicShadowCandidateMembershipV3Error, pattern,
            ):
                build_runtime_official_eligible_membership_v3(
                    official,
                    nport,
                    taxonomy,
                    _search_plan(),
                    replace(_lifecycle(), last_reviewed=last_reviewed),
                    **_kwargs(),
                )

        _, audit = build_runtime_official_eligible_membership_v3(
            official, nport, taxonomy, _search_plan(), _lifecycle(), **_kwargs()
        )
        self.assertEqual(audit["security_lifecycle_mapping_id"], "fixture_lifecycle")
        self.assertEqual(audit["security_lifecycle_last_reviewed"], "2026-09-01")
        self.assertTrue(audit["security_lifecycle_review_not_after_decision"])

    def test_invalid_or_duplicated_aliases_fail_closed_before_exclusion(self) -> None:
        official, nport, taxonomy = _meta_universe()
        taxonomy.loc[taxonomy["ticker"].eq("FB;META"), "ticker"] = "META;META"
        with self.assertRaisesRegex(
            NdxDynamicShadowCandidateMembershipV3Error, "aliases are empty or duplicated",
        ):
            build_runtime_official_eligible_membership_v3(
                official,
                nport,
                taxonomy,
                _search_plan(),
                _lifecycle(),
                excluded_identity_security_ids={"security:0001326801:30303M102"},
                **_kwargs(),
            )


if __name__ == "__main__":
    unittest.main()
