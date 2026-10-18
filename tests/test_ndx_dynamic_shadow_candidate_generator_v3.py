from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
import unittest

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_candidate_generator_v3 import (
    CAPTURE_SOURCE_KEYS,
    CONTRACT_RELATIVE,
    NdxDynamicShadowCandidateGeneratorV3Error,
    OUTPUT_ROOT_RELATIVE,
    REQUIRED_EXISTING_SOURCE_PATHS,
    SOURCE_ARCHIVE_DIRECTORY,
    STATIC_SOURCE_PATHS,
    assess_candidate_v3_source_archive_readiness,
    build_candidate_v3_source_archive_payload,
    capture_nominal_liquidity_inputs_v3,
    load_candidate_generator_v3_contract,
    verify_candidate_generator_v3_provenance,
)
from backtest.ndx_dynamic_shadow_candidate_membership_v3 import (
    build_runtime_official_eligible_membership_v3,
)
from data.ndx_history import constituents_asof
from data.ndx_security_identity import load_security_lifecycle
from data.versioning import file_sha256
import scripts.ndx_dynamic_shadow_candidate_generator as v1
import scripts.ndx_dynamic_shadow_candidate_generator_v2 as v2
import scripts.ndx_dynamic_shadow_candidate_generator_v3 as runner


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def _lifecycle_text() -> str:
    return yaml.safe_dump({
        "schema_version": 1,
        "mapping_id": "fixture_lifecycle",
        "last_reviewed": "2026-09-01",
        "rules": [{
            "rule_id": "fixture_rename",
            "cik": "0000000001",
            "cusip": "123456789",
            "issuer_name": "Fixture",
            "recognized_tickers": ["OLD", "NEW"],
            "intervals": [
                {"effective_from": None, "effective_to": "2025-12-31", "price_ticker": "OLD"},
                {"effective_from": "2026-01-01", "effective_to": None, "price_ticker": "NEW"},
            ],
            "evidence": [{"effective_date": "2026-01-01", "url": "https://example.test/rename"}],
        }],
    }, sort_keys=False)


def _attach_source_archive(manifest_path: Path, manifest: dict) -> None:
    evidence = manifest["membership_evidence"]
    nominal = evidence["candidate_v3_nominal_liquidity_capture"]
    keys = set(CAPTURE_SOURCE_KEYS) | set(nominal["source_versions"])
    captures = {}
    for key in sorted(keys):
        source = Path(manifest["source_paths"][key]).resolve()
        raw = source.read_bytes()
        captures[key] = {
            "path": source,
            "raw": raw,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    archive, files = build_candidate_v3_source_archive_payload(
        manifest["decision_date"], captures,
    )
    archive_root = manifest_path.parent / SOURCE_ARCHIVE_DIRECTORY
    for filename, raw in files.items():
        _write(archive_root / filename, raw)
    archive_raw = (
        json.dumps(
            archive, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    archive_manifest = archive_root / "manifest.json"
    _write(archive_manifest, archive_raw)
    evidence["candidate_v3_source_archive"] = {
        "path": archive_manifest.resolve().as_posix(),
        "sha256": hashlib.sha256(archive_raw).hexdigest(),
        "source_key_count": len(files),
        "verification_mode": "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY",
        "canonical_source_restore_required": False,
        "canonical_source_writeback_allowed": False,
    }


def _fixture(root: Path) -> tuple[Path, dict]:
    for key, relative in STATIC_SOURCE_PATHS.items():
        if key == "candidate_generator_v3_contract_sha256":
            _write(root / relative, (ROOT / CONTRACT_RELATIVE).read_bytes())
        else:
            _write(root / relative, f"fixture static source {key}\n")
    for key, relative in REQUIRED_EXISTING_SOURCE_PATHS.items():
        if key == "security_lifecycle_sha256":
            _write(root / relative, _lifecycle_text())
        else:
            _write(root / relative, f"fixture existing source {key}\n")

    tickers = ["NEW"] + [f"O{index:03d}" for index in range(99)]
    official = pd.DataFrame({
        "as_of_date": ["2026-10-01"] * 100,
        "source_type": ["index_constituent"] * 100,
        "source_id": ["nasdaq_100"] * 100,
        "ticker": tickers,
        "name": [f"Fixture {ticker}" for ticker in tickers],
        "weight": [None] * 100,
        "sector": [""] * 100,
        "source_locator": [
            "https://www.nasdaq.com/solutions/global-indexes/"
            "nasdaq-100/companies"
        ] * 100,
    })
    archive = root / "data/cache/candidate_pools/snapshots/nasdaq_100/2026-10-01_fixture.csv"
    archive_bytes = official.to_csv(index=False, lineterminator="\n").encode("utf-8")
    _write(archive, archive_bytes)
    archive_manifest = Path(str(archive) + ".manifest.json")
    _write(archive_manifest, json.dumps({
        "allowed_uses": [
            "current_candidate_screen", "current_control_group",
            "forward_observation",
        ],
        "as_of_date": "2026-10-01",
        "as_of_date_evidence": "runtime_fetch_date_not_source_effective_date",
        "cache_path": archive.resolve().as_posix(),
        "completeness": "validated_unique_security_count_100_to_110",
        "content_bytes": len(archive_bytes),
        "data_end": "2026-10-01",
        "data_start": "2026-10-01",
        "dataset_key": (
            "nasdaq_100:2026-10-01:"
            f"{hashlib.sha256(archive_bytes).hexdigest()[:12]}"
        ),
        "dataset_type": "security_pool_snapshot",
        "fetched_at_evidence": "runtime_fetch_utc",
        "generated_at": "2026-10-01T20:05:01+00:00",
        "immutable_snapshot": True,
        "index_id": "NDX",
        "manifest_path": archive_manifest.resolve().as_posix(),
        "observed_added": [],
        "observed_change_date_kind": (
            "local_snapshot_comparison_not_official_effective_date"
        ),
        "observed_removed": [],
        "observed_security_count": 100,
        "point_in_time_scope": "current_snapshot_only",
        "previous_version_id": None,
        "prohibited_uses": [
            "historical_constituent_backtest",
            "historical_membership_inference", "backfill_before_as_of_date",
        ],
        "publication_time_known": False,
        "row_count": 100,
        "schema_version": 1,
        "sector_available": False,
        "source": "nasdaq_ndx_official_companies_page",
        "source_company_count_claim": 100,
        "source_confidence": "official_source_runtime_or_export",
        "historical_backtest_allowed": False,
        "source_effective_date_known": False,
        "source_locator": (
            "https://www.nasdaq.com/solutions/global-indexes/"
            "nasdaq-100/companies"
        ),
        "source_record_count": 100,
        "ticker_name_fallback_count": 0,
        "ticker_name_fallback_rule": (
            "exact_unique_company_name_from_last_complete_official_snapshot"
        ),
        "ticker_name_fallbacks": [],
        "version_id": (
            "security_pool_snapshot:nasdaq_100:2026-10-01:"
            f"{hashlib.sha256(archive_bytes).hexdigest()[:12]}:"
            f"{hashlib.sha256(archive_bytes).hexdigest()[:16]}"
        ),
        "weights_available": False,
        "content_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "fetched_at": "2026-10-01T20:05:00+00:00",
    }, sort_keys=True) + "\n")

    membership = pd.DataFrame([{
        "report_date": "2026-06-30",
        "filed_date": "2026-07-31",
        "available_date": "2026-08-01",
        "accession_number": "fixture-accession",
        "ticker": ticker,
        "name": ticker,
        "cusip": f"{index + 1:09d}",
        "isin": "",
        "weight": 0.01,
        "value_usd": 1_000_000.0,
        "mapping_method": "fixture",
        "source_locator": "https://example.test/nport",
    } for index, ticker in enumerate(tickers)])
    membership_path = root / REQUIRED_EXISTING_SOURCE_PATHS["membership_history_sha256"]
    _write(membership_path, membership.to_csv(index=False, lineterminator="\n"))
    _write(
        root / REQUIRED_EXISTING_SOURCE_PATHS["membership_manifest_sha256"],
        json.dumps({
            "content_sha256": file_sha256(membership_path),
            "row_count": len(membership),
        }, sort_keys=True) + "\n",
    )
    membership_manifest_path = (
        root / REQUIRED_EXISTING_SOURCE_PATHS["membership_manifest_sha256"]
    )
    crosswalk = pd.DataFrame([{
        "ticker": ticker,
        "cik": ("0000000001" if ticker == "NEW" else f"{index + 100:010d}"),
        "mapping_status": "mapped",
        "mapping_method": "fixture",
        "candidate_ciks": ("0000000001" if ticker == "NEW" else f"{index + 100:010d}"),
        "names": f"Fixture {ticker}",
        "cusips": f"{index + 1:09d}",
        "first_report_date": "2026-06-30",
        "last_report_date": "2026-06-30",
    } for index, ticker in enumerate(tickers)])
    crosswalk_path = root / REQUIRED_EXISTING_SOURCE_PATHS["cik_crosswalk_sha256"]
    _write(crosswalk_path, crosswalk.to_csv(index=False, lineterminator="\n"))
    crosswalk_manifest_path = (
        root / REQUIRED_EXISTING_SOURCE_PATHS["cik_crosswalk_manifest_sha256"]
    )
    _write(crosswalk_manifest_path, json.dumps({
        "content_sha256": file_sha256(crosswalk_path),
        "row_count": len(crosswalk),
        "dataset_type": "ndx_sec_cik_crosswalk",
        "dataset_key": "historical_ndx_tickers",
        "source": "sec_ticker_exchange_plus_historical_cik_names",
        "source_locator": "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt",
        "publication_time_known": False,
        "unresolved_tickers": [],
        "mapped_tickers": len(crosswalk),
    }, sort_keys=True) + "\n")
    fixture_contract_path = root / CONTRACT_RELATIVE
    fixture_contract = yaml.safe_load(
        fixture_contract_path.read_text(encoding="utf-8")
    )
    fixture_contract["identity_contract"][
        "frozen_sec_cik_crosswalk_sha256"
    ] = file_sha256(crosswalk_path)
    fixture_contract["identity_contract"][
        "frozen_reviewed_lifecycle_sha256"
    ] = file_sha256(
        root / REQUIRED_EXISTING_SOURCE_PATHS["security_lifecycle_sha256"]
    )
    _write(
        fixture_contract_path,
        yaml.safe_dump(fixture_contract, sort_keys=False),
    )
    taxonomy = pd.DataFrame([{
        "ticker": "OLD;NEW",
        "cik": "0000000001",
        "cusip": "123456789",
        "security_id": "security:0000000001:123456789",
        "issuer_id": "issuer:0000000001",
        "risk_chain": "semiconductor",
        "status": "accepted",
        "evidence_available_date": "2026-01-01",
        "selection_date_end": "2026-05-29",
    }])
    taxonomy_path = root / REQUIRED_EXISTING_SOURCE_PATHS["taxonomy_records_sha256"]
    _write(taxonomy_path, taxonomy.to_csv(index=False, lineterminator="\n"))
    issues = pd.DataFrame(columns=[
        "issue_type", "security_id", "issuer_id", "ticker", "cik", "cusip",
        "report_date", "detail",
    ])
    issues_path = root / REQUIRED_EXISTING_SOURCE_PATHS["taxonomy_identity_issues_sha256"]
    _write(issues_path, issues.to_csv(index=False, lineterminator="\n"))
    taxonomy_manifest_path = root / REQUIRED_EXISTING_SOURCE_PATHS["taxonomy_manifest_sha256"]
    _write(taxonomy_manifest_path, json.dumps({
        "input_versions": [{
            "source_name": "ndx_point_in_time_constituents",
            "path": membership_path.resolve().as_posix(),
            "content_sha256": file_sha256(membership_path),
            "manifest_sha256": file_sha256(membership_manifest_path),
            "row_count": len(membership),
            "manifest_verified": True,
        }, {
            "source_name": "ndx_sec_cik_crosswalk",
            "path": crosswalk_path.resolve().as_posix(),
            "content_sha256": file_sha256(crosswalk_path),
            "manifest_sha256": file_sha256(crosswalk_manifest_path),
            "row_count": len(crosswalk),
            "manifest_verified": True,
        }],
        "artifacts": {
            "records": {"filename": taxonomy_path.name, "rows": 1, "sha256": file_sha256(taxonomy_path)},
            "identity_issues": {"filename": issues_path.name, "rows": 0, "sha256": file_sha256(issues_path)},
        },
        "summary": {"identity_issue_count": 0},
    }, sort_keys=True) + "\n")
    search_plan = {"universe_tracks": {
        "strict_technology": {"accepted_risk_chains": ["semiconductor"]},
        "technology_plus_adjacent": {
            "inherits": "strict_technology", "additional_risk_chains": ["software"],
        },
    }}
    _write(
        root / REQUIRED_EXISTING_SOURCE_PATHS["search_plan_sha256"],
        yaml.safe_dump(search_plan, sort_keys=False),
    )

    versions = {}
    paths = {}
    for key, relative in {**STATIC_SOURCE_PATHS, **REQUIRED_EXISTING_SOURCE_PATHS}.items():
        target = (root / relative).resolve()
        versions[key] = file_sha256(target)
        paths[key] = target.as_posix()
    versions.update({
        "official_snapshot_sha256": file_sha256(archive),
        "official_snapshot_manifest_sha256": file_sha256(archive_manifest),
    })
    paths.update({
        "official_snapshot_sha256": archive.resolve().as_posix(),
        "official_snapshot_manifest_sha256": archive_manifest.resolve().as_posix(),
    })

    nport, nport_evidence = constituents_asof(membership, "2026-10-01")
    lifecycle = load_security_lifecycle(
        root / REQUIRED_EXISTING_SOURCE_PATHS["security_lifecycle_sha256"]
    )
    eligible, identity = build_runtime_official_eligible_membership_v3(
        official,
        nport,
        taxonomy,
        search_plan,
        lifecycle,
        decision_date="2026-10-01",
        observed_at_utc="2026-10-01T20:05:00+00:00",
        decision_close_timestamp_utc="2026-10-01T20:00:00+00:00",
        seal_timestamp_utc="2026-10-01T20:10:00+00:00",
        conservative_seal_deadline_utc="2026-10-02T13:30:00+00:00",
        allow_degraded_reviewed_taxonomy_subset=True,
    )
    output = root / OUTPUT_ROOT_RELATIVE / "2026-10-01"
    nominal_dates = pd.bdate_range(end="2026-10-01", periods=63)
    nominal = pd.DataFrame({
        "Date": nominal_dates.strftime("%Y-%m-%d"),
        "Open": [100.0] * 63,
        "High": [101.0] * 63,
        "Low": [99.0] * 63,
        "Close": [100.0] * 63,
        "Volume": [1_000_000.0] * 63,
    })
    nominal_path = output / "nominal_sources/NEW.csv"
    _write(nominal_path, nominal.to_csv(index=False, lineterminator="\n"))
    nominal_sidecar_path = nominal_path.with_suffix(".csv.manifest.json")
    _write(nominal_sidecar_path, json.dumps({
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_frozen_nominal_input",
        "ticker": "NEW",
        "decision_date": "2026-10-01",
        "price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
        "corporate_action_adjustment": "none",
        "source_mode": "eastmoney_fqt_0",
        "source_errors_before_success": {},
        "data_start": nominal_dates.min().date().isoformat(),
        "data_end": "2026-10-01",
        "rows": 63,
        "content_sha256": file_sha256(nominal_path),
        "rows_after_decision_date_included": False,
        "historical_backfill_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }, sort_keys=True) + "\n")
    versions["nominal_price_NEW_sha256"] = file_sha256(nominal_path)
    versions["nominal_price_NEW_manifest_sha256"] = file_sha256(
        nominal_sidecar_path
    )
    paths["nominal_price_NEW_sha256"] = nominal_path.resolve().as_posix()
    paths["nominal_price_NEW_manifest_sha256"] = (
        nominal_sidecar_path.resolve().as_posix()
    )
    _, exclusions, liquidity_evidence = capture_nominal_liquidity_inputs_v3(
        eligible,
        versions,
        paths,
        decision_date="2026-10-01",
        snapshot_directory=output,
    )
    eligible_path = output / "eligible_securities.csv"
    _write(eligible_path, eligible.to_csv(index=False, lineterminator="\n"))
    exclusions_path = output / "liquidity_exclusions.csv"
    _write(exclusions_path, exclusions.to_csv(index=False, lineterminator="\n"))
    manifest_path = output / "manifest.json"
    _write(manifest_path, "{}\n")
    capture_versions = {key: versions[key] for key in sorted(CAPTURE_SOURCE_KEYS)}
    capture_paths = {key: paths[key] for key in sorted(CAPTURE_SOURCE_KEYS)}
    manifest = {
        "decision_date": "2026-10-01",
        "decision_close_timestamp_utc": "2026-10-01T20:00:00+00:00",
        "seal_timestamp_utc": "2026-10-01T20:10:00+00:00",
        "conservative_seal_deadline_utc": "2026-10-02T13:30:00+00:00",
        "source_versions": versions,
        "source_paths": paths,
        "membership_evidence": {
            "official_runtime": identity,
            "nport": nport_evidence,
            "official_fetched_at_utc": "2026-10-01T20:05:00+00:00",
            "candidate_v3_nominal_liquidity_capture": liquidity_evidence,
            "candidate_v3_source_capture": {
                "schema_version": 1,
                "capture_mode": "READ_BYTES_ONCE_HASH_THEN_PARSE",
                "source_versions": capture_versions,
                "source_paths": capture_paths,
                "captured_sources_rechecked_before_seal": True,
            },
        },
        "artifacts": {
            "eligible_securities": {
                "filename": eligible_path.name,
                "rows": len(eligible),
                "sha256": file_sha256(eligible_path),
            },
            "liquidity_exclusions": {
                "filename": exclusions_path.name,
                "rows": 0,
                "sha256": file_sha256(exclusions_path),
            },
        },
    }
    _attach_source_archive(manifest_path, manifest)
    return manifest_path, manifest


class DynamicShadowCandidateGeneratorV3Tests(unittest.TestCase):
    def test_contract_and_static_registry_are_strict(self) -> None:
        contract = load_candidate_generator_v3_contract(
            ROOT / CONTRACT_RELATIVE, repository_root=ROOT,
        )
        self.assertEqual(contract["generator_id"], "ndx_dynamic_shadow_candidate_generator_v3")
        versions, paths = runner.static_source_registry(repository_root=ROOT)
        self.assertEqual(set(versions), set(STATIC_SOURCE_PATHS))
        self.assertEqual(set(versions), set(paths))

    def test_positive_fixture_and_source_drift_rejection(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            verified = verify_candidate_generator_v3_provenance(
                manifest_path, manifest, repository_root=root,
            )
            self.assertEqual(verified["decision_date"], "2026-10-01")
            drift = root / STATIC_SOURCE_PATHS["candidate_identity_v3_module_sha256"]
            drift.write_text("drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error, "source hash changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_historical_verification_uses_archive_without_canonical_restore(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            changed_paths = [
                Path(manifest["source_paths"]["taxonomy_records_sha256"]),
                Path(manifest["source_paths"]["security_lifecycle_sha256"]),
                Path(manifest["source_paths"]["nominal_price_NEW_sha256"]),
            ]
            for index, path in enumerate(changed_paths):
                path.write_bytes(f"later canonical revision {index}\n".encode("utf-8"))
            changed_bytes = {path: path.read_bytes() for path in changed_paths}
            removed_path = Path(
                manifest["source_paths"]["membership_history_sha256"]
            )
            removed_path.unlink()
            verified = verify_candidate_generator_v3_provenance(
                manifest_path, manifest, repository_root=root,
            )
            self.assertEqual(verified["decision_date"], "2026-10-01")
            self.assertEqual(
                {path: path.read_bytes() for path in changed_paths}, changed_bytes,
            )
            self.assertFalse(removed_path.exists())
            nominal = manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ]
            readiness = assess_candidate_v3_source_archive_readiness(
                manifest["membership_evidence"]["candidate_v3_source_archive"],
                snapshot_manifest_path=manifest_path,
                decision_date="2026-10-01",
                source_versions=manifest["source_versions"],
                source_paths=manifest["source_paths"],
                expected_source_keys=(
                    set(CAPTURE_SOURCE_KEYS) | set(nominal["source_versions"])
                ),
            )
            self.assertTrue(readiness["historical_archive_verified"])
            self.assertFalse(readiness["current_canonical_sources_match_capture"])
            self.assertFalse(readiness["canonical_source_writeback_allowed"])

    def test_archive_tamper_and_missing_archive_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            missing = deepcopy(manifest)
            missing["membership_evidence"].pop("candidate_v3_source_archive")
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "source archive descriptor schema changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, missing, repository_root=root,
                )
            archive_manifest = Path(
                manifest["membership_evidence"]["candidate_v3_source_archive"]["path"]
            )
            archive = json.loads(archive_manifest.read_text(encoding="utf-8"))
            source = archive_manifest.parent / archive["source_descriptors"][0][
                "archive_filename"
            ]
            source.write_bytes(source.read_bytes() + b"tamper")
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "source archive bytes changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_archive_writer_recovers_from_orphan_stage_and_is_immutable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            output_root = (root / OUTPUT_ROOT_RELATIVE).resolve()
            archive_root = manifest_path.parent / SOURCE_ARCHIVE_DIRECTORY
            shutil.rmtree(archive_root)
            orphan = manifest_path.parent / ".v3_source_archive_stage_interrupted"
            _write(orphan / "partial.bin", b"partial")
            nominal = manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ]
            keys = set(CAPTURE_SOURCE_KEYS) | set(nominal["source_versions"])
            captures = {}
            for key in sorted(keys):
                source = Path(manifest["source_paths"][key]).resolve()
                raw = source.read_bytes()
                captures[key] = {
                    "path": source, "raw": raw,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            with mock.patch.object(v1, "DEFAULT_ROOT", output_root):
                first = runner.write_candidate_v3_source_archive(
                    manifest_path.parent,
                    decision_date="2026-10-01",
                    source_captures=captures,
                )
                second = runner.write_candidate_v3_source_archive(
                    manifest_path.parent,
                    decision_date="2026-10-01",
                    source_captures=captures,
                )
                self.assertEqual(first, second)
                archive_manifest = Path(first["path"])
                archive = json.loads(archive_manifest.read_text(encoding="utf-8"))
                source_file = archive_manifest.parent / archive[
                    "source_descriptors"
                ][0]["archive_filename"]
                source_file.write_bytes(source_file.read_bytes() + b"tamper")
                with self.assertRaisesRegex(
                    NdxDynamicShadowCandidateGeneratorV3Error,
                    "source archive bytes changed",
                ):
                    runner.write_candidate_v3_source_archive(
                        manifest_path.parent,
                        decision_date="2026-10-01",
                        source_captures=captures,
                    )
            self.assertTrue(orphan.is_dir())

    def test_self_signed_non_nasdaq_official_locator_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            archive = Path(manifest["source_paths"]["official_snapshot_sha256"])
            sidecar_path = Path(
                manifest["source_paths"]["official_snapshot_manifest_sha256"]
            )
            official = pd.read_csv(archive, low_memory=False)
            official["source_locator"] = "https://evil.example/fabricated"
            _write(archive, official.to_csv(index=False, lineterminator="\n"))
            archive_hash = file_sha256(archive)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar.update({
                "content_sha256": archive_hash,
                "content_bytes": len(archive.read_bytes()),
                "dataset_key": f"nasdaq_100:2026-10-01:{archive_hash[:12]}",
                "source_locator": "https://evil.example/fabricated",
                "version_id": (
                    "security_pool_snapshot:nasdaq_100:2026-10-01:"
                    f"{archive_hash[:12]}:{archive_hash[:16]}"
                ),
            })
            _write(sidecar_path, json.dumps(sidecar, sort_keys=True) + "\n")
            sidecar_hash = file_sha256(sidecar_path)
            manifest["source_versions"]["official_snapshot_sha256"] = archive_hash
            manifest["source_versions"][
                "official_snapshot_manifest_sha256"
            ] = sidecar_hash
            capture = manifest["membership_evidence"][
                "candidate_v3_source_capture"
            ]["source_versions"]
            capture["official_snapshot_sha256"] = archive_hash
            capture["official_snapshot_manifest_sha256"] = sidecar_hash
            _attach_source_archive(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "Nasdaq source contract|authority",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_self_signed_liquidity_claim_is_recomputed_from_nominal_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            nominal_path = Path(
                manifest["source_paths"]["nominal_price_NEW_sha256"]
            )
            sidecar_path = Path(
                manifest["source_paths"]["nominal_price_NEW_manifest_sha256"]
            )
            nominal = pd.read_csv(nominal_path, low_memory=False)
            nominal["Volume"] = 1.0
            _write(nominal_path, nominal.to_csv(index=False, lineterminator="\n"))
            nominal_hash = file_sha256(nominal_path)
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["content_sha256"] = nominal_hash
            _write(sidecar_path, json.dumps(sidecar, sort_keys=True) + "\n")
            sidecar_hash = file_sha256(sidecar_path)
            manifest["source_versions"]["nominal_price_NEW_sha256"] = nominal_hash
            manifest["source_versions"][
                "nominal_price_NEW_manifest_sha256"
            ] = sidecar_hash
            liquidity = manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ]["source_versions"]
            liquidity["nominal_price_NEW_sha256"] = nominal_hash
            liquidity["nominal_price_NEW_manifest_sha256"] = sidecar_hash
            _attach_source_archive(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "post-liquidity issuer pool is empty",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_adjusted_or_unknown_nominal_source_mode_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            sidecar_path = Path(
                manifest["source_paths"]["nominal_price_NEW_manifest_sha256"]
            )
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            sidecar["source_mode"] = "provider_adjusted_close"
            _write(sidecar_path, json.dumps(sidecar, sort_keys=True) + "\n")
            sidecar_hash = file_sha256(sidecar_path)
            manifest["source_versions"][
                "nominal_price_NEW_manifest_sha256"
            ] = sidecar_hash
            manifest["membership_evidence"][
                "candidate_v3_nominal_liquidity_capture"
            ]["source_versions"][
                "nominal_price_NEW_manifest_sha256"
            ] = sidecar_hash
            _attach_source_archive(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "nominal sidecar semantics changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_self_signed_taxonomy_identity_issue_is_rebuilt_and_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            issues_path = Path(
                manifest["source_paths"]["taxonomy_identity_issues_sha256"]
            )
            issues = pd.DataFrame([{
                "issue_type": "identity",
                "security_id": "security:0000000001:123456789",
                "issuer_id": "issuer:0000000001",
                "ticker": "NEW",
                "cik": "0000000001",
                "cusip": "123456789",
                "report_date": "2026-06-30",
                "detail": "fabricated_identity_issue",
            }])
            _write(issues_path, issues.to_csv(index=False, lineterminator="\n"))
            issues_hash = file_sha256(issues_path)
            taxonomy_manifest_path = Path(
                manifest["source_paths"]["taxonomy_manifest_sha256"]
            )
            taxonomy_manifest = json.loads(
                taxonomy_manifest_path.read_text(encoding="utf-8")
            )
            taxonomy_manifest["artifacts"]["identity_issues"].update({
                "rows": 1,
                "sha256": issues_hash,
            })
            taxonomy_manifest["summary"]["identity_issue_count"] = 1
            _write(
                taxonomy_manifest_path,
                json.dumps(taxonomy_manifest, sort_keys=True) + "\n",
            )
            taxonomy_manifest_hash = file_sha256(taxonomy_manifest_path)
            manifest["source_versions"][
                "taxonomy_identity_issues_sha256"
            ] = issues_hash
            manifest["source_versions"][
                "taxonomy_manifest_sha256"
            ] = taxonomy_manifest_hash
            capture = manifest["membership_evidence"][
                "candidate_v3_source_capture"
            ]["source_versions"]
            capture["taxonomy_identity_issues_sha256"] = issues_hash
            capture["taxonomy_manifest_sha256"] = taxonomy_manifest_hash
            _attach_source_archive(manifest_path, manifest)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "identity issues cannot be rebuilt",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

    def test_valid_parent_result_without_v3_registry_is_rejected_for_that_reason(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            old = deepcopy(manifest)
            for key in STATIC_SOURCE_PATHS:
                old["source_versions"].pop(key)
                old["source_paths"].pop(key)
            def verify_under_fixture_root(path, parent_manifest, *, repository_root):
                return verify_candidate_generator_v3_provenance(
                    path, parent_manifest, repository_root=root,
                )

            with mock.patch.object(runner.v2, "verify", return_value=old), mock.patch.object(
                runner,
                "verify_candidate_generator_v3_provenance",
                side_effect=verify_under_fixture_root,
            ):
                with self.assertRaisesRegex(
                    NdxDynamicShadowCandidateGeneratorV3Error,
                    "lacks complete v3 provenance",
                ):
                    runner.verify(manifest_path)

    def test_capture_binding_and_track_audit_cannot_be_self_reported(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            forged = deepcopy(manifest)
            forged["membership_evidence"]["candidate_v3_source_capture"][
                "source_versions"
            ]["taxonomy_records_sha256"] = "f" * 64
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error, "captured source binding changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, forged, repository_root=root,
                )

            forged = deepcopy(manifest)
            forged["membership_evidence"]["nport"]["security_count"] -= 1
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "NPORT as-of evidence cannot be rebuilt",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, forged, repository_root=root,
                )

            taxonomy_manifest_path = Path(
                manifest["source_paths"]["taxonomy_manifest_sha256"]
            )
            taxonomy_manifest = json.loads(
                taxonomy_manifest_path.read_text(encoding="utf-8")
            )
            taxonomy_manifest["input_versions"][0]["manifest_sha256"] = "e" * 64
            _write(
                taxonomy_manifest_path,
                json.dumps(taxonomy_manifest, sort_keys=True) + "\n",
            )
            forged = deepcopy(manifest)
            new_hash = file_sha256(taxonomy_manifest_path)
            forged["source_versions"]["taxonomy_manifest_sha256"] = new_hash
            forged["membership_evidence"]["candidate_v3_source_capture"][
                "source_versions"
            ]["taxonomy_manifest_sha256"] = new_hash
            _attach_source_archive(manifest_path, forged)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "taxonomy/NPORT captured input binding changed",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, forged, repository_root=root,
                )

    def test_eligible_row_cannot_be_deleted_and_resigned_as_a_smaller_k_pool(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            eligible_item = manifest["artifacts"]["eligible_securities"]
            eligible_path = manifest_path.parent / eligible_item["filename"]
            original_eligible_bytes = eligible_path.read_bytes()
            original_eligible_rows = int(eligible_item["rows"])
            original_eligible_sha256 = str(eligible_item["sha256"])
            eligible = pd.read_csv(eligible_path, low_memory=False).iloc[1:].copy()
            _write(eligible_path, eligible.to_csv(index=False, lineterminator="\n"))
            eligible_item["rows"] = len(eligible)
            eligible_item["sha256"] = file_sha256(eligible_path)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "cannot be rebuilt from captured sources",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

            eligible_path.write_bytes(original_eligible_bytes)
            eligible_item["rows"] = original_eligible_rows
            eligible_item["sha256"] = original_eligible_sha256
            duplicated = pd.concat(
                [pd.read_csv(eligible_path, low_memory=False),
                 pd.read_csv(eligible_path, low_memory=False).iloc[[0]]],
                ignore_index=True,
            )
            _write(
                eligible_path,
                duplicated.to_csv(index=False, lineterminator="\n"),
            )
            eligible_item["rows"] = len(duplicated)
            eligible_item["sha256"] = file_sha256(eligible_path)
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "eligible identities cannot be rebuilt",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, manifest, repository_root=root,
                )

            eligible_path.write_bytes(original_eligible_bytes)
            eligible_item["rows"] = original_eligible_rows
            eligible_item["sha256"] = original_eligible_sha256
            forged = deepcopy(manifest)
            forged["membership_evidence"]["official_runtime"][
                "track_dynamic_cardinality"
            ]["strict_technology"]["dynamic_k_maximum"] = 2
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "membership audit cannot be rebuilt",
            ):
                verify_candidate_generator_v3_provenance(
                    manifest_path, forged, repository_root=root,
                )

    def test_patch_is_restored_when_parent_seal_fails(self) -> None:
        args = runner.parse_args(["--seal", "--decision-date", "2026-10-01"])
        original = (
            v1._immutable_official_archive,
            v1.build_runtime_official_eligible_membership,
            v1._load_taxonomy_memberships,
            v1.build_fresh_candidate_input_snapshot,
            v1.write_snapshot_bundle,
            v1._append_decision_seal,
        )
        with mock.patch.object(runner.v2, "seal", side_effect=RuntimeError("fixture stop")):
            with self.assertRaisesRegex(RuntimeError, "fixture stop"):
                runner.seal(args)
        self.assertEqual(original, (
            v1._immutable_official_archive,
            v1.build_runtime_official_eligible_membership,
            v1._load_taxonomy_memberships,
            v1.build_fresh_candidate_input_snapshot,
            v1.write_snapshot_bundle,
            v1._append_decision_seal,
        ))

    def test_successful_seal_routes_real_v1_loader_through_v2_and_v3(self) -> None:
        """Exercise the wrapper stack without network or a real decision write."""

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, manifest = _fixture(root)
            fixture_source_versions = deepcopy(manifest["source_versions"])
            fixture_source_paths = deepcopy(manifest["source_paths"])
            archive = Path(manifest["source_paths"]["official_snapshot_sha256"])
            archive_manifest = Path(
                manifest["source_paths"]["official_snapshot_manifest_sha256"]
            )
            official = pd.read_csv(archive, low_memory=False)
            output_root = (root / OUTPUT_ROOT_RELATIVE).resolve()
            args = runner.parse_args(["--seal", "--decision-date", "2026-10-01"])
            for name, source_key in {
                "membership_history": "membership_history_sha256",
                "membership_manifest": "membership_manifest_sha256",
                "taxonomy_manifest": "taxonomy_manifest_sha256",
                "taxonomy_records": "taxonomy_records_sha256",
                "search_plan": "search_plan_sha256",
                "security_lifecycle": "security_lifecycle_sha256",
            }.items():
                setattr(args, name, manifest["source_paths"][source_key])
            args.config = (root / "config/config.yaml").as_posix()
            for flag in (
                "refresh_official", "refresh_membership", "rebuild_taxonomy",
                "refresh_prices", "refresh_nominal_prices", "refresh_target",
                "allow_degraded_reviewed_taxonomy_subset",
            ):
                setattr(args, flag, True)

            timestamp_factory = mock.Mock(
                side_effect=lambda value=None, *a, **kw: pd.Timestamp(value, *a, **kw)
            )
            timestamp_factory.now = mock.Mock(
                return_value=pd.Timestamp("2026-10-01T20:10:00+00:00")
            )
            pandas_proxy = SimpleNamespace(
                Timestamp=timestamp_factory,
                read_csv=pd.read_csv,
            )
            official_meta = SimpleNamespace(
                stale=False,
                cached=False,
                manifest={"fetched_at": "2026-10-01T20:05:00+00:00"},
            )
            nport_meta = SimpleNamespace(stale=False, cached=False)
            append_calls: list[dict] = []

            def fake_snapshot_write(_output, snapshot):
                manifest["source_versions"] = dict(snapshot["source_versions"])
                manifest["source_paths"] = dict(snapshot["source_paths"])
                manifest["membership_evidence"] = dict(
                    snapshot["membership_evidence"]
                )
                return manifest

            def fake_terminal_append(_ledger, _path, payload, **_kwargs):
                append_calls.append(dict(payload))
                return {"record_sha256": "fixture"}

            def fake_v1_seal(parent_args):
                sessions, calendar_versions, calendar_paths = v1._load_calendar(
                    Path(parent_args.session_calendar_manifest)
                )
                self.assertTrue(bool(sessions["completed"].all()))
                timing = {
                    "decision_close_timestamp_utc": "2026-10-01T20:00:00+00:00",
                    "conservative_seal_deadline_utc": "2026-10-02T13:30:00+00:00",
                }
                eligible, versions, paths, evidence = v1._load_taxonomy_memberships(
                    parent_args, {}, timing=timing,
                )
                self.assertGreater(len(eligible), 0)
                self.assertEqual(
                    evidence["official_runtime"]["adapter_id"],
                    "ndx_dynamic_shadow_candidate_membership_v3",
                )
                for key in (
                    "generator_contract_sha256", "generator_module_sha256",
                    "generator_script_sha256",
                ):
                    source = root / REQUIRED_EXISTING_SOURCE_PATHS[key]
                    versions[key] = file_sha256(source)
                    paths[key] = source.resolve().as_posix()
                for key in (
                    "nominal_price_NEW_sha256",
                    "nominal_price_NEW_manifest_sha256",
                ):
                    versions[key] = fixture_source_versions[key]
                    paths[key] = fixture_source_paths[key]
                versions.update(calendar_versions)
                paths.update(calendar_paths)
                nominal = pd.read_csv(paths["nominal_price_NEW_sha256"])
                v1.build_fresh_candidate_input_snapshot(
                    eligible,
                    {},
                    {"NEW": nominal},
                    pd.DataFrame(),
                    decision_date="2026-10-01",
                    source_versions=versions,
                    source_paths=paths,
                )
                eligible_path = manifest_path.parent / "eligible_securities.csv"
                _write(
                    eligible_path,
                    eligible.to_csv(index=False, lineterminator="\n"),
                )
                manifest["artifacts"]["eligible_securities"] = {
                    "filename": eligible_path.name,
                    "rows": len(eligible),
                    "sha256": file_sha256(eligible_path),
                }
                snapshot = {
                    "decision_date": "2026-10-01",
                    "source_versions": versions,
                    "source_paths": paths,
                    "membership_evidence": evidence,
                }
                written_manifest = v1.write_snapshot_bundle(
                    output_root / "2026-10-01", snapshot,
                )
                v1._append_decision_seal(
                    root / "decision_seals.jsonl", manifest_path, written_manifest,
                )
                return written_manifest

            def passthrough_v2(_path, payload):
                self.assertIn(
                    "session_calendar_v2_prefix_evidence_sha256",
                    payload["source_versions"],
                )
                return payload

            calendar_frame = pd.DataFrame([{
                "date": "2026-10-01", "completed": True,
            }])
            with mock.patch.object(runner, "ROOT", root), mock.patch.object(
                runner, "CONTRACT_PATH", root / CONTRACT_RELATIVE,
            ), mock.patch.object(v1, "DEFAULT_ROOT", output_root), mock.patch.object(
                v1, "_immutable_official_archive",
                return_value=(archive, archive_manifest),
            ), mock.patch.object(
                v1, "get_nasdaq_100_snapshot",
                return_value=(official, official_meta),
            ), mock.patch.object(
                v1, "get_ndx_point_in_time_history",
                return_value=(pd.DataFrame(), nport_meta),
            ), mock.patch.object(v1, "_rebuild_taxonomy"), mock.patch.object(
                v1, "load_config", return_value={},
            ), mock.patch.object(v1, "pd", pandas_proxy), mock.patch.object(
                v1, "_append_decision_seal", side_effect=fake_terminal_append,
            ), mock.patch.object(
                v1, "build_fresh_candidate_input_snapshot", return_value={},
            ), mock.patch.object(
                v1, "write_snapshot_bundle", side_effect=fake_snapshot_write,
            ), mock.patch.object(v1, "seal", side_effect=fake_v1_seal), mock.patch.object(
                v2, "capture_candidate_calendar_evidence_v2",
                return_value=(
                    calendar_frame,
                    {"session_calendar_v2_prefix_evidence_sha256": "a" * 64},
                    {"session_calendar_v2_prefix_evidence_sha256": (root / "calendar.json").as_posix()},
                ),
            ), mock.patch.object(
                v2, "_require_v2_snapshot_provenance", side_effect=passthrough_v2,
            ), mock.patch.object(v2, "verify", return_value=manifest):
                verified = runner.seal(args)

            self.assertEqual(verified["decision_date"], "2026-10-01")
            self.assertEqual(len(append_calls), 1)
            self.assertIn(
                "candidate_v3_source_capture", verified["membership_evidence"],
            )

    def test_preprospective_seal_is_rejected_before_parent_call(self) -> None:
        args = runner.parse_args(["--seal", "--decision-date", "2026-09-01"])
        with mock.patch.object(runner.v2, "seal") as parent:
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error, "backfill is forbidden",
            ):
                runner.seal(args)
        parent.assert_not_called()

        noncanonical = runner.parse_args([
            "--seal", "--decision-date", "2026-10-01T00:00:00",
        ])
        with mock.patch.object(runner.v2, "seal") as parent:
            with self.assertRaisesRegex(
                NdxDynamicShadowCandidateGeneratorV3Error,
                "decision_date is invalid",
            ):
                runner.seal(noncanonical)
        parent.assert_not_called()

    def test_readiness_dry_run_does_not_write_v3_artifacts(self) -> None:
        watched = [
            v1.DEFAULT_ROOT / "readiness_v3.json",
            v1.DEFAULT_ROOT / "last_failure_v3.json",
            runner.LOCK_PATH,
        ]
        before = {
            path: (path.read_bytes() if path.exists() else None)
            for path in watched
        }
        self.assertEqual(runner.main(["--dry-run"]), 0)
        after = {
            path: (path.read_bytes() if path.exists() else None)
            for path in watched
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
