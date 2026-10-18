from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_identity_evidence_inventory import (
    NdxDynamicShadowIdentityEvidenceError,
    build_identity_evidence_inventory,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dataset_manifest(path: Path, *, dataset_type: str, fetched_at: str, extra=None) -> dict:
    manifest_path = Path(str(path) + ".manifest.json")
    payload = {
        "schema_version": 1,
        "dataset_type": dataset_type,
        "dataset_key": "fixture",
        "version_id": f"{dataset_type}:fixture:{_sha(path)[:16]}",
        "content_sha256": _sha(path),
        "content_bytes": path.stat().st_size,
        "cache_path": path.resolve().as_posix(),
        "manifest_path": manifest_path.resolve().as_posix(),
        "source": "fixture",
        "source_locator": "https://example.test/source",
        "fetched_at": fetched_at,
        "fetched_at_evidence": "runtime_fetch_utc",
        "row_count": 1,
        "data_start": None,
        "data_end": None,
        "generated_at": fetched_at,
        **(extra or {}),
    }
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _fixture(root: Path) -> dict[str, Path]:
    official = root / "data/cache/candidate_pools/snapshots/nasdaq_100/2026-10-01_fixture.csv"
    official.parent.mkdir(parents=True)
    pd.DataFrame([{
        "as_of_date": "2026-10-01", "source_type": "index_constituent",
        "source_id": "nasdaq_100", "ticker": "AAA", "name": "AAA CORP",
        "weight": "", "sector": "", "source_locator": "https://example.test/ndx",
    }]).to_csv(official, index=False, lineterminator="\n")
    _dataset_manifest(
        official, dataset_type="security_pool_snapshot",
        fetched_at="2026-10-01T20:30:00+00:00",
        extra={
            "as_of_date": "2026-10-01", "immutable_snapshot": True,
            "historical_backtest_allowed": False, "source_effective_date_known": False,
            "publication_time_known": False,
        },
    )

    taxonomy = root / "data/cache/candidate_pools/ndx_taxonomy_v2"
    taxonomy.mkdir(parents=True)
    identity = taxonomy / "security_identity.csv"
    pd.DataFrame([{
        "security_id": "security:0000000001:123456789", "issuer_id": "issuer:0000000001",
        "ticker": "AAA", "cik": "0000000001", "cusip": "123456789",
        "observation_from": "2026-03-31", "observation_to": "2026-03-31",
        "available_from": "2026-05-29", "available_to": "2026-05-29",
        "identity_status": "resolved", "identity_issue": "",
    }]).to_csv(identity, index=False, lineterminator="\n")
    records = taxonomy / "taxonomy_records.csv"
    pd.DataFrame([{
        "security_id": "security:0000000001:123456789", "issuer_id": "issuer:0000000001",
        "ticker": "AAA", "selection_dates": "2026-05-29", "risk_chain": "compute",
        "evidence_available_date": "2026-05-01", "status": "accepted",
    }]).to_csv(records, index=False, lineterminator="\n")
    issues = taxonomy / "identity_issues.csv"
    pd.DataFrame(columns=["issue_type", "security_id", "issuer_id", "ticker"]).to_csv(
        issues, index=False, lineterminator="\n",
    )
    descriptors = {
        "identities": {"filename": identity.name, "rows": 1, "sha256": _sha(identity)},
        "records": {"filename": records.name, "rows": 1, "sha256": _sha(records)},
        "identity_issues": {"filename": issues.name, "rows": 0, "sha256": _sha(issues)},
    }
    (taxonomy / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "manifest_type": "ndx_taxonomy_v2_bundle",
        "artifacts": descriptors,
    }), encoding="utf-8")

    sec = root / "data/cache/candidate_pools/ndx_history/sec_company_tickers_exchange.json"
    sec.parent.mkdir(parents=True)
    sec.write_text(json.dumps({
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[1, "AAA CORP", "AAA", "Nasdaq"]],
    }), encoding="utf-8")
    _dataset_manifest(
        sec, dataset_type="sec_company_ticker_crosswalk",
        fetched_at="2026-09-30T20:00:00+00:00",
        extra={"publication_time_known": False},
    )

    lifecycle = root / "config/ndx_security_lifecycle.yaml"
    lifecycle.parent.mkdir(parents=True)
    lifecycle.write_text(yaml.safe_dump({
        "schema_version": 1, "mapping_id": "fixture_lifecycle", "last_reviewed": "2026-09-30",
        "rules": [{
            "rule_id": "aaa_declared", "cik": "0000000001", "cusip": "123456789",
            "issuer_name": "AAA CORP", "recognized_tickers": ["AAA"],
            "intervals": [{"effective_from": None, "effective_to": None, "price_ticker": "AAA"}],
            "evidence": [{"effective_date": "2026-01-01", "url": "https://example.test/aaa"}],
        }],
    }, sort_keys=False), encoding="utf-8")
    return {"official": official, "identity": identity, "records": records, "sec": sec}


def _resign_taxonomy_artifact(root: Path, key: str, path: Path) -> None:
    manifest_path = root / "data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][key]["sha256"] = _sha(path)
    manifest["artifacts"][key]["rows"] = len(pd.read_csv(path, dtype=str, keep_default_na=False))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


class DynamicShadowIdentityEvidenceInventoryTests(unittest.TestCase):
    def test_nonzero_canonical_sources_remain_gap_only_not_execution_proof(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fixture(root)
            result = build_identity_evidence_inventory(
                root, decision_date="2026-10-01", valid_on_date="2026-10-02",
            )
        self.assertEqual(result["security_row_count"], 1)
        self.assertEqual(result["status"], "BLOCKED_CANDIDATE_DECISION_NOT_SEALED")
        self.assertFalse(result["admission_authority"])
        self.assertFalse(result["execution_valid_on_date_proved"])
        row = result["security_evidence"][0]
        self.assertEqual(row["security_id"], "security:0000000001:123456789")
        self.assertTrue(row["sec_issuer_cik_matches"])
        self.assertTrue(row["official_membership_observed_on_decision_date"])
        self.assertFalse(row["historical_identity_observed_on_decision_date"])
        self.assertFalse(row["execution_valid_on_date_proved"])
        self.assertIn("OFFICIAL_MEMBERSHIP_HAS_NO_CIK_OR_CUSIP", row["identity_gap_codes"])
        self.assertIn("SEC_CURRENT_TICKER_CROSSCHECK_HAS_NO_CUSIP", row["identity_gap_codes"])
        self.assertIn("EXECUTION_VALID_ON_DATE_SECURITY_IDENTITY_NOT_PROVED", row["identity_gap_codes"])

    def test_latest_available_share_class_is_not_mislabeled_as_sec_cik_mismatch(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            latest = pd.read_csv(paths["identity"], dtype=str, keep_default_na=False)
            old = latest.copy()
            old.loc[0, "security_id"] = "security:0000000001:OLD123456"
            old.loc[0, "cusip"] = "OLD123456"
            old.loc[0, "available_from"] = "2024-01-01"
            old.loc[0, "available_to"] = "2024-12-31"
            pd.concat([old, latest], ignore_index=True).to_csv(
                paths["identity"], index=False, lineterminator="\n",
            )
            _resign_taxonomy_artifact(root, "identities", paths["identity"])
            result = build_identity_evidence_inventory(root, decision_date="2026-10-01")
        row = result["security_evidence"][0]
        self.assertEqual(row["cusip"], "123456789")
        self.assertTrue(row["sec_issuer_cik_matches"])
        self.assertNotIn("SEC_ISSUER_CIK_CROSSCHECK_MISMATCH", row["identity_gap_codes"])
        self.assertFalse(row["execution_valid_on_date_proved"])

    def test_semicolon_ticker_alias_can_crosscheck_issuer_but_not_execution_identity(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            identity = pd.read_csv(paths["identity"], dtype=str, keep_default_na=False)
            identity.loc[0, "ticker"] = "OLD;AAA"
            identity.to_csv(paths["identity"], index=False, lineterminator="\n")
            _resign_taxonomy_artifact(root, "identities", paths["identity"])
            result = build_identity_evidence_inventory(root, decision_date="2026-10-01")
        row = result["security_evidence"][0]
        self.assertTrue(row["sec_issuer_cik_matches"])
        self.assertNotIn("SEC_ISSUER_CIK_CROSSCHECK_MISMATCH", row["identity_gap_codes"])
        self.assertFalse(row["execution_valid_on_date_proved"])

    def test_noncanonical_available_to_cannot_pass_by_string_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            identity = pd.read_csv(paths["identity"], dtype=str, keep_default_na=False)
            identity.loc[0, "available_to"] = "2026-05-29-after-cutoff"
            identity.to_csv(paths["identity"], index=False, lineterminator="\n")
            _resign_taxonomy_artifact(root, "identities", paths["identity"])
            with self.assertRaisesRegex(
                NdxDynamicShadowIdentityEvidenceError,
                "invalid historical identity available_to",
            ):
                build_identity_evidence_inventory(root, decision_date="2026-10-01")

    def test_future_taxonomy_evidence_is_not_exposed_as_available(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            records = pd.read_csv(paths["records"], dtype=str, keep_default_na=False)
            records.loc[0, "evidence_available_date"] = "2026-10-02"
            records.to_csv(paths["records"], index=False, lineterminator="\n")
            _resign_taxonomy_artifact(root, "records", paths["records"])
            result = build_identity_evidence_inventory(root, decision_date="2026-10-01")
        row = result["security_evidence"][0]
        self.assertEqual(row["risk_chain"], "")
        self.assertEqual(row["risk_chain_evidence_status"], "missing")
        self.assertIn("ACCEPTED_RISK_CHAIN_EVIDENCE_MISSING", row["identity_gap_codes"])
        self.assertFalse(row["execution_valid_on_date_proved"])

    def test_same_coordinate_taxonomy_conflict_is_rejected_in_any_row_order(self) -> None:
        for reverse in (False, True):
            with self.subTest(reverse=reverse), TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = _fixture(root)
                records = pd.read_csv(paths["records"], dtype=str, keep_default_na=False)
                conflicting = records.copy()
                conflicting.loc[0, "risk_chain"] = "different"
                conflicting.loc[0, "status"] = "rejected"
                combined = pd.concat([records, conflicting], ignore_index=True)
                if reverse:
                    combined = combined.iloc[::-1].reset_index(drop=True)
                combined.to_csv(paths["records"], index=False, lineterminator="\n")
                _resign_taxonomy_artifact(root, "records", paths["records"])
                with self.assertRaisesRegex(
                    NdxDynamicShadowIdentityEvidenceError, "taxonomy record is ambiguous",
                ):
                    build_identity_evidence_inventory(root, decision_date="2026-10-01")

    def test_existing_official_archive_hash_change_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            paths["official"].write_text(paths["official"].read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowIdentityEvidenceError, "path/content binding changed",
            ):
                build_identity_evidence_inventory(root, decision_date="2026-10-01")

    def test_existing_taxonomy_artifact_hash_change_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _fixture(root)
            paths["identity"].write_text(paths["identity"].read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowIdentityEvidenceError, "taxonomy artifact hash changed",
            ):
                build_identity_evidence_inventory(root, decision_date="2026-10-01")

    def test_requested_valid_date_cannot_precede_decision(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fixture(root)
            with self.assertRaisesRegex(NdxDynamicShadowIdentityEvidenceError, "precedes"):
                build_identity_evidence_inventory(
                    root, decision_date="2026-10-01", valid_on_date="2026-09-30",
                )

    def test_missing_sources_are_explicit_gaps_not_false_readiness(self) -> None:
        with TemporaryDirectory() as tmp:
            result = build_identity_evidence_inventory(
                Path(tmp), decision_date="2026-10-01",
            )
        self.assertEqual(result["security_row_count"], 0)
        self.assertFalse(result["execution_valid_on_date_proved"])
        self.assertIn("OFFICIAL_MEMBERSHIP_SOURCE_MISSING", result["gap_codes"])
        self.assertIn("HISTORICAL_IDENTITY_TAXONOMY_SOURCE_MISSING", result["gap_codes"])
        self.assertIn("SEC_CURRENT_TICKER_CROSSCHECK_SOURCE_MISSING", result["gap_codes"])


if __name__ == "__main__":
    unittest.main()
