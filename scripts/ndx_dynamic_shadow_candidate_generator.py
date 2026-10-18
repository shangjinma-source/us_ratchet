r"""Seal a fresh prospective dynamic-cardinality input snapshot and full-k shard plan.

Readiness only (safe before 2026-10):
    python -B scripts\ndx_dynamic_shadow_candidate_generator.py

Prospective seal (requires a verified session calendar and an explicit post-close run):
    python -B scripts\ndx_dynamic_shadow_candidate_generator.py --seal `
      --decision-date 2026-10-01 `
      --session-calendar-manifest data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json `
      --refresh-official --refresh-membership --rebuild-taxonomy `
      --refresh-prices --refresh-nominal-prices --refresh-target `
      --allow-degraded-reviewed-taxonomy-subset
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_candidate_snapshot import (  # noqa: E402
    NdxDynamicShadowCandidateSnapshotError,
    build_fresh_candidate_input_snapshot,
    build_runtime_official_eligible_membership,
    canonical_sha256,
    load_generator_contract,
    verify_snapshot_bundle,
    write_snapshot_bundle,
)
from backtest.ndx_dynamic_shadow_fresh_search import (  # noqa: E402
    load_frozen_original_8_definition,
)
from core.config import load_config  # noqa: E402
from data.candidate_pool import get_nasdaq_100_snapshot  # noqa: E402
from data.fetch import get_bars  # noqa: E402
from data.funds import get_fund_nav  # noqa: E402
from data.ndx_history import constituents_asof, get_ndx_point_in_time_history  # noqa: E402
from data.ndx_price_basis import fetch_unadjusted_bars  # noqa: E402
from data.versioning import file_sha256  # noqa: E402


DEFAULT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1"
DEFAULT_CALENDAR = ROOT / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
PROTECTED = (ROOT / "config/config.yaml", ROOT / "data/state.json", ROOT / "data/broker_positions.json")
SEAL_LEDGER = DEFAULT_ROOT / "decision_seals.jsonl"
SEAL_RECORD_KEYS = {
    "schema_version", "sequence", "decision_date", "decision_close_timestamp_utc",
    "seal_timestamp_utc", "conservative_seal_deadline_utc", "execution_coordinate_rule",
    "snapshot_manifest_path",
    "snapshot_manifest_sha256", "snapshot_fingerprint", "calendar_manifest_sha256",
    "official_snapshot_sha256", "previous_record_sha256", "record_sha256",
}

CANONICAL_ARGUMENT_PATHS = {
    "contract": ROOT / "config/ndx_dynamic_shadow_candidate_generator_v1.yaml",
    "config": ROOT / "config/config.yaml",
    "membership_history": ROOT / "data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv",
    "membership_manifest": ROOT / "data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json",
    "taxonomy_manifest": ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json",
    "taxonomy_records": ROOT / "data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv",
    "search_plan": ROOT / "config/ndx_cardinality_search_v1_plan.yaml",
    "security_lifecycle": ROOT / "config/ndx_security_lifecycle.yaml",
    "target_nav": ROOT / "data/cache/funds/012922.csv",
    "target_manifest": ROOT / "data/cache/funds/012922.csv.manifest.json",
    "original_8_manifest": ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json",
}


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NdxDynamicShadowCandidateSnapshotError(f"expected JSON object: {path}")
    return value


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NdxDynamicShadowCandidateSnapshotError(f"expected YAML mapping: {path}")
    return value


def _protected_hashes() -> dict[str, str | None]:
    return {path.relative_to(ROOT).as_posix(): file_sha256(path) if path.is_file() else None for path in PROTECTED}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _load_and_validate_seal_ledger(
    path: Path, *, expected_root: Path = DEFAULT_ROOT
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    previous_hash = None
    previous_date = None
    with path.open("r", encoding="utf-8") as handle:
        for sequence, line in enumerate(handle, start=1):
            if not line.strip():
                raise NdxDynamicShadowCandidateSnapshotError("blank decision-seal ledger row")
            record = json.loads(line)
            if not isinstance(record, dict) or set(record) != SEAL_RECORD_KEYS:
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger schema changed")
            if int(record.get("schema_version", -1)) != 1 or int(record.get("sequence", -1)) != sequence:
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger sequence changed")
            record_hash = str(record.get("record_sha256") or "")
            without_hash = dict(record)
            without_hash.pop("record_sha256")
            if record.get("previous_record_sha256") != previous_hash or canonical_sha256(without_hash) != record_hash:
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger hash chain changed")
            decision = pd.Timestamp(record["decision_date"]).normalize()
            if previous_date is not None and decision <= previous_date:
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger dates are not increasing")
            manifest_path = Path(str(record["snapshot_manifest_path"])).resolve()
            if (
                manifest_path != (expected_root / str(record["decision_date"]) / "manifest.json").resolve()
                or not manifest_path.is_file()
                or file_sha256(manifest_path) != record["snapshot_manifest_sha256"]
            ):
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger manifest binding changed")
            if pd.Timestamp(record["seal_timestamp_utc"]).tzinfo is None:
                raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger timestamp is naive")
            records.append(record)
            previous_hash = record_hash
            previous_date = decision
    return records


def _append_decision_seal(
    ledger_path: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    *,
    expected_root: Path = DEFAULT_ROOT,
) -> dict[str, Any]:
    records = _load_and_validate_seal_ledger(ledger_path, expected_root=expected_root)
    record = {
        "schema_version": 1,
        "sequence": len(records) + 1,
        "decision_date": manifest["decision_date"],
        "decision_close_timestamp_utc": manifest["decision_close_timestamp_utc"],
        "seal_timestamp_utc": manifest["seal_timestamp_utc"],
        "conservative_seal_deadline_utc": manifest["conservative_seal_deadline_utc"],
        "execution_coordinate_rule": manifest["execution_coordinate_rule"],
        "snapshot_manifest_path": manifest_path.resolve().as_posix(),
        "snapshot_manifest_sha256": file_sha256(manifest_path),
        "snapshot_fingerprint": manifest["snapshot_fingerprint"],
        "calendar_manifest_sha256": manifest["source_versions"]["session_calendar_manifest_sha256"],
        "official_snapshot_sha256": manifest["source_versions"]["official_snapshot_sha256"],
        "previous_record_sha256": records[-1]["record_sha256"] if records else None,
    }
    record["record_sha256"] = canonical_sha256(record)
    same_date = [item for item in records if item["decision_date"] == record["decision_date"]]
    if same_date:
        comparable = dict(record)
        comparable["sequence"] = same_date[0]["sequence"]
        comparable["previous_record_sha256"] = same_date[0]["previous_record_sha256"]
        comparable["record_sha256"] = same_date[0]["record_sha256"]
        if comparable != same_date[0]:
            raise NdxDynamicShadowCandidateSnapshotError("decision seal already exists with different evidence")
        return same_date[0]
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    _load_and_validate_seal_ledger(ledger_path, expected_root=expected_root)
    return record


def _verify_manifest_seal_record(manifest_path: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    records = _load_and_validate_seal_ledger(SEAL_LEDGER)
    matching = [record for record in records if record["decision_date"] == manifest["decision_date"]]
    if len(matching) != 1:
        raise NdxDynamicShadowCandidateSnapshotError("decision snapshot has no unique append-only seal record")
    record = matching[0]
    checks = {
        "snapshot_manifest_path": manifest_path.resolve().as_posix(),
        "snapshot_manifest_sha256": file_sha256(manifest_path),
        "snapshot_fingerprint": manifest["snapshot_fingerprint"],
        "decision_close_timestamp_utc": manifest["decision_close_timestamp_utc"],
        "seal_timestamp_utc": manifest["seal_timestamp_utc"],
        "conservative_seal_deadline_utc": manifest["conservative_seal_deadline_utc"],
        "execution_coordinate_rule": manifest["execution_coordinate_rule"],
        "calendar_manifest_sha256": manifest["source_versions"]["session_calendar_manifest_sha256"],
        "official_snapshot_sha256": manifest["source_versions"]["official_snapshot_sha256"],
    }
    if any(record.get(key) != value for key, value in checks.items()):
        raise NdxDynamicShadowCandidateSnapshotError("decision-seal ledger record disagrees with snapshot")
    return record


def _require_canonical_seal_paths(args: argparse.Namespace) -> None:
    for field, expected in CANONICAL_ARGUMENT_PATHS.items():
        supplied = _resolve(getattr(args, field))
        if supplied != expected.resolve():
            raise NdxDynamicShadowCandidateSnapshotError(
                f"non-canonical seal input path: {field}"
            )
    if _resolve(args.output_root) != DEFAULT_ROOT.resolve():
        raise NdxDynamicShadowCandidateSnapshotError("candidate output root must be canonical")
    if _resolve(args.session_calendar_manifest) != DEFAULT_CALENDAR.resolve():
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate seal requires the canonical observed-session calendar"
        )


def _registration_clock(
    caller_timestamp_utc: str | None,
    *,
    observed_now_utc: pd.Timestamp | None = None,
    maximum_skew_seconds: int = 300,
) -> pd.Timestamp:
    observed = observed_now_utc if observed_now_utc is not None else pd.Timestamp.now(tz="UTC")
    if observed.tzinfo is None:
        raise NdxDynamicShadowCandidateSnapshotError("observed system clock must be timezone-aware")
    observed = observed.tz_convert("UTC")
    if caller_timestamp_utc:
        supplied = pd.Timestamp(caller_timestamp_utc)
        if supplied.tzinfo is None:
            raise NdxDynamicShadowCandidateSnapshotError("caller as-of timestamp must be timezone-aware")
        supplied = supplied.tz_convert("UTC")
        if abs((supplied - observed).total_seconds()) > int(maximum_skew_seconds):
            raise NdxDynamicShadowCandidateSnapshotError(
                "caller as-of timestamp differs from the observed system clock"
            )
    return observed


def _load_calendar(
    manifest_path: Path,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    if manifest_path.resolve() != DEFAULT_CALENDAR.resolve():
        raise NdxDynamicShadowCandidateSnapshotError("US session calendar path is not canonical")
    verifier = ROOT / "scripts/ndx_observed_session_calendar.py"
    verification = subprocess.run(
        [sys.executable, "-B", str(verifier), "--verify-only"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if verification.returncode != 0:
        raise NdxDynamicShadowCandidateSnapshotError(
            "observed-session calendar failed independent verification: "
            + (verification.stderr or verification.stdout).strip()
        )
    manifest = _json(manifest_path)
    if (
        manifest.get("manifest_type") != "ndx_observed_us_session_calendar"
        or manifest.get("append_only_ledger") is not True
        or manifest.get("retrospective_backfill_allowed") is not False
        or manifest.get("future_or_in_progress_sessions_included") is not False
    ):
        raise NdxDynamicShadowCandidateSnapshotError("unexpected US session calendar manifest type")
    artifacts = manifest.get("artifacts") or {}
    artifact = artifacts.get("session_projection") or {}
    path = Path(str(artifact.get("path") or "")).resolve()
    expected_projection = manifest_path.parent / "sessions.csv"
    if path != expected_projection.resolve():
        raise NdxDynamicShadowCandidateSnapshotError("US session calendar projection path is invalid")
    if not path.is_file() or file_sha256(path) != artifact.get("sha256"):
        raise NdxDynamicShadowCandidateSnapshotError("US session calendar artifact hash mismatch")
    sessions = pd.read_csv(path, low_memory=False)
    if len(sessions) != int(artifact.get("rows", -1)):
        raise NdxDynamicShadowCandidateSnapshotError("US session calendar row count mismatch")
    ledger = artifacts.get("append_only_ledger") or {}
    ledger_path = Path(str(ledger.get("path") or "")).resolve()
    expected_ledger = manifest_path.parent / "sessions.jsonl"
    if (
        ledger_path != expected_ledger.resolve()
        or not ledger_path.is_file()
        or file_sha256(ledger_path) != ledger.get("sha256")
    ):
        raise NdxDynamicShadowCandidateSnapshotError("US session calendar ledger hash mismatch")
    versions = {
        "session_calendar_manifest_sha256": file_sha256(manifest_path),
        "session_calendar_projection_sha256": file_sha256(path),
        "session_calendar_ledger_sha256": file_sha256(ledger_path),
        "session_calendar_verifier_sha256": file_sha256(verifier),
        "session_calendar_engine_sha256": file_sha256(ROOT / "backtest/ndx_observed_session_calendar.py"),
    }
    paths = {
        "session_calendar_manifest_sha256": manifest_path.as_posix(),
        "session_calendar_projection_sha256": path.as_posix(),
        "session_calendar_ledger_sha256": ledger_path.as_posix(),
        "session_calendar_verifier_sha256": verifier.as_posix(),
        "session_calendar_engine_sha256": (ROOT / "backtest/ndx_observed_session_calendar.py").as_posix(),
    }
    return sessions, versions, paths


def _taxonomy_membership_input(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    for row in manifest.get("input_versions", []):
        if isinstance(row, Mapping) and row.get("source_name") == "ndx_point_in_time_constituents":
            return row
    raise NdxDynamicShadowCandidateSnapshotError("taxonomy membership input is missing")


def _reviewed_evidence_path(manifest: Mapping[str, Any]) -> Path | None:
    for row in manifest.get("input_versions", []):
        if isinstance(row, Mapping) and row.get("source_name") == "reviewed_taxonomy_evidence":
            path = Path(str(row.get("path") or ""))
            return path if path.is_file() else None
    return None


def _rebuild_taxonomy(taxonomy_manifest_path: Path) -> None:
    prior = _json(taxonomy_manifest_path)
    evidence = _reviewed_evidence_path(prior)
    command = [sys.executable, "-B", str(ROOT / "scripts/ndx_taxonomy_v2.py"), "--plan-only"]
    if evidence is not None:
        command.extend(["--evidence-csv", str(evidence)])
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"taxonomy rebuild failed closed: {(result.stderr or result.stdout).strip()}"
        )


def _immutable_official_archive(meta) -> tuple[Path, Path]:
    archive = Path(str(meta.manifest.get("archive_path") or "")).resolve()
    archive_root = (ROOT / "data/cache/candidate_pools/snapshots/nasdaq_100").resolve()
    if not archive.is_file() or not archive.is_relative_to(archive_root):
        raise NdxDynamicShadowCandidateSnapshotError("official Nasdaq archive path is invalid")
    archive_manifest = Path(str(archive) + ".manifest.json")
    payload = _json(archive_manifest)
    if (
        payload.get("dataset_type") != "security_pool_snapshot"
        or payload.get("immutable_snapshot") is not True
        or payload.get("content_sha256") != file_sha256(archive)
        or payload.get("historical_backtest_allowed") is not False
        or payload.get("source_effective_date_known") is not False
    ):
        raise NdxDynamicShadowCandidateSnapshotError("official Nasdaq archive manifest is invalid")
    return archive, archive_manifest


def _load_taxonomy_memberships(
    args: argparse.Namespace,
    cfg,
    *,
    timing: Mapping[str, str],
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str], dict[str, Any]]:
    membership_path = _resolve(args.membership_history)
    membership_manifest_path = _resolve(args.membership_manifest)
    taxonomy_manifest_path = _resolve(args.taxonomy_manifest)
    taxonomy_records_path = _resolve(args.taxonomy_records)

    if not args.refresh_official:
        raise NdxDynamicShadowCandidateSnapshotError(
            "prospective seal requires --refresh-official; CURRENT cache reuse is forbidden"
        )
    official, official_meta = get_nasdaq_100_snapshot(cfg, refresh=True)
    if official_meta.stale or official_meta.cached:
        raise NdxDynamicShadowCandidateSnapshotError("official Nasdaq refresh fell back to stale/cache data")
    official_fetched = pd.Timestamp(official_meta.manifest.get("fetched_at"))
    if official_fetched.tzinfo is None:
        raise NdxDynamicShadowCandidateSnapshotError("official Nasdaq fetched_at must be timezone-aware")
    official_fetched = official_fetched.tz_convert("UTC")
    decision_close = pd.Timestamp(timing["decision_close_timestamp_utc"]).tz_convert("UTC")
    observed_after_refresh = pd.Timestamp.now(tz="UTC")
    if not decision_close <= official_fetched <= observed_after_refresh:
        raise NdxDynamicShadowCandidateSnapshotError(
            "official Nasdaq snapshot was not fetched in the current decision-seal window"
        )
    archive_path, archive_manifest_path = _immutable_official_archive(official_meta)

    if not args.refresh_membership:
        raise NdxDynamicShadowCandidateSnapshotError(
            "prospective seal requires a fresh NPORT cross-check"
        )
    if args.refresh_membership:
        _, nport_meta = get_ndx_point_in_time_history(cfg, refresh=True)
        if nport_meta.stale or nport_meta.cached:
            raise NdxDynamicShadowCandidateSnapshotError("membership refresh fell back to stale/cache data")
    membership_manifest = _json(membership_manifest_path)
    if membership_manifest.get("content_sha256") != file_sha256(membership_path):
        raise NdxDynamicShadowCandidateSnapshotError("membership manifest/content hash mismatch")
    if args.rebuild_taxonomy:
        _rebuild_taxonomy(taxonomy_manifest_path)
    taxonomy_manifest = _json(taxonomy_manifest_path)
    membership_input = _taxonomy_membership_input(taxonomy_manifest)
    if membership_input.get("content_sha256") != file_sha256(membership_path):
        raise NdxDynamicShadowCandidateSnapshotError("taxonomy is not bound to refreshed membership hash")
    artifact = (taxonomy_manifest.get("artifacts") or {}).get("records") or {}
    if artifact.get("filename") != taxonomy_records_path.name or artifact.get("sha256") != file_sha256(taxonomy_records_path):
        raise NdxDynamicShadowCandidateSnapshotError("taxonomy records artifact hash mismatch")
    records = pd.read_csv(taxonomy_records_path, low_memory=False)
    if len(records) != int(artifact.get("rows", -1)):
        raise NdxDynamicShadowCandidateSnapshotError("taxonomy records row count mismatch")
    summary = taxonomy_manifest.get("summary") or {}
    issue_artifact = (taxonomy_manifest.get("artifacts") or {}).get("identity_issues") or {}
    issue_path = taxonomy_manifest_path.parent / str(issue_artifact.get("filename") or "")
    if (
        issue_path.resolve() != (taxonomy_manifest_path.parent / "identity_issues.csv").resolve()
        or not issue_path.is_file()
        or issue_artifact.get("sha256") != file_sha256(issue_path)
    ):
        raise NdxDynamicShadowCandidateSnapshotError(
            "taxonomy identity-issue exclusion artifact hash mismatch"
        )
    identity_issues = pd.read_csv(issue_path, keep_default_na=False, low_memory=False)
    if (
        len(identity_issues) != int(issue_artifact.get("rows", -1))
        or len(identity_issues) != int(summary.get("identity_issue_count", -1))
    ):
        raise NdxDynamicShadowCandidateSnapshotError(
            "taxonomy identity-issue exclusion count mismatch"
        )
    issue_required = {"security_id", "issuer_id", "ticker"}
    if not issue_required.issubset(identity_issues.columns):
        raise NdxDynamicShadowCandidateSnapshotError(
            "taxonomy identity-issue exclusion fields are incomplete"
        )
    excluded_security_ids = set(identity_issues["security_id"].astype(str)) - {""}
    excluded_issuer_ids = set(identity_issues["issuer_id"].astype(str)) - {""}
    excluded_tickers = set(identity_issues["ticker"].astype(str).str.upper()) - {""}
    membership = pd.read_csv(membership_path, low_memory=False)
    nport_snapshot, membership_evidence = constituents_asof(membership, args.decision_date)
    search_plan = _yaml(_resolve(args.search_plan))
    eligible, official_audit = build_runtime_official_eligible_membership(
        official,
        nport_snapshot,
        records,
        search_plan,
        decision_date=args.decision_date,
        observed_at_utc=official_fetched.isoformat(),
        decision_close_timestamp_utc=timing["decision_close_timestamp_utc"],
        seal_timestamp_utc=observed_after_refresh.isoformat(),
        conservative_seal_deadline_utc=timing["conservative_seal_deadline_utc"],
        allow_degraded_reviewed_taxonomy_subset=bool(
            args.allow_degraded_reviewed_taxonomy_subset
        ),
        excluded_identity_security_ids=excluded_security_ids,
        excluded_identity_issuer_ids=excluded_issuer_ids,
        excluded_identity_tickers=excluded_tickers,
    )
    membership_evidence = {
        "role": "NPORT_IDENTITY_AND_LAG_CROSSCHECK_NOT_PRIMARY",
        "nport": membership_evidence,
        "official_runtime": official_audit,
        "official_fetched_at_utc": official_fetched.isoformat(),
        "official_archive_path": archive_path.as_posix(),
        "official_archive_sha256": file_sha256(archive_path),
        "official_archive_manifest_path": archive_manifest_path.as_posix(),
        "official_archive_manifest_sha256": file_sha256(archive_manifest_path),
        "identity_issue_exclusion_artifact_path": issue_path.resolve().as_posix(),
        "identity_issue_exclusion_artifact_sha256": file_sha256(issue_path),
        "affected_identity_security_ids": sorted(excluded_security_ids),
        "affected_identity_issuer_ids": sorted(excluded_issuer_ids),
        "affected_identity_tickers": sorted(excluded_tickers),
    }
    versions = {
        "official_snapshot_sha256": file_sha256(archive_path),
        "official_snapshot_manifest_sha256": file_sha256(archive_manifest_path),
        "membership_history_sha256": file_sha256(membership_path),
        "membership_manifest_sha256": file_sha256(membership_manifest_path),
        "taxonomy_manifest_sha256": file_sha256(taxonomy_manifest_path),
        "taxonomy_records_sha256": file_sha256(taxonomy_records_path),
        "taxonomy_identity_issues_sha256": file_sha256(issue_path),
        "search_plan_sha256": file_sha256(_resolve(args.search_plan)),
        "security_lifecycle_sha256": file_sha256(_resolve(args.security_lifecycle)),
    }
    paths = {
        "official_snapshot_sha256": archive_path.as_posix(),
        "official_snapshot_manifest_sha256": archive_manifest_path.as_posix(),
        "membership_history_sha256": membership_path.as_posix(),
        "membership_manifest_sha256": membership_manifest_path.as_posix(),
        "taxonomy_manifest_sha256": taxonomy_manifest_path.as_posix(),
        "taxonomy_records_sha256": taxonomy_records_path.as_posix(),
        "taxonomy_identity_issues_sha256": issue_path.resolve().as_posix(),
        "search_plan_sha256": _resolve(args.search_plan).as_posix(),
        "security_lifecycle_sha256": _resolve(args.security_lifecycle).as_posix(),
    }
    return eligible, versions, paths, membership_evidence


def _load_prices(
    args: argparse.Namespace, cfg, tickers: list[str]
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict[str, str]]:
    frames: dict[str, pd.DataFrame] = {}
    versions: dict[str, str] = {}
    paths: dict[str, str] = {}
    for ticker in tickers:
        if args.refresh_prices:
            frame, meta = get_bars(ticker, cfg)
            if meta.cached:
                raise NdxDynamicShadowCandidateSnapshotError(
                    f"adjusted price refresh fell back to cache: {ticker}"
                )
        else:
            path = Path(cfg.cache_dir) / f"{ticker}.csv"
            if not path.is_file():
                raise NdxDynamicShadowCandidateSnapshotError(f"adjusted price cache missing: {ticker}")
            frame = pd.read_csv(path)
        path = Path(cfg.cache_dir) / f"{ticker}.csv"
        frames[ticker] = frame
        key = f"adjusted_price_{ticker}_sha256"
        versions[key] = file_sha256(path)
        paths[key] = path.resolve().as_posix()
    return frames, versions, paths


def _load_and_freeze_nominal_prices(
    args: argparse.Namespace,
    tickers: list[str],
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict[str, str]]:
    if not args.refresh_nominal_prices:
        raise NdxDynamicShadowCandidateSnapshotError(
            "prospective seal requires --refresh-nominal-prices"
        )
    decision = pd.Timestamp(args.decision_date).normalize()
    begin = decision - pd.Timedelta(days=900)
    output = DEFAULT_ROOT / args.decision_date / "nominal_sources"
    frames: dict[str, pd.DataFrame] = {}
    versions: dict[str, str] = {}
    paths: dict[str, str] = {}
    for ticker in tickers:
        frame, source_mode, source_errors = fetch_unadjusted_bars(
            ticker, begin=begin, end=decision
        )
        if frame.index.max().normalize() != decision:
            raise NdxDynamicShadowCandidateSnapshotError(
                f"fresh nominal source does not end at decision close: {ticker}"
            )
        frozen = frame.copy()
        frozen.index = frozen.index.strftime("%Y-%m-%d")
        frozen.index.name = "Date"
        content = frozen.to_csv(index=True, lineterminator="\n")
        data_path = output / f"{ticker}.csv"
        if data_path.exists() and data_path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowCandidateSnapshotError(
                f"immutable nominal source collision: {ticker}"
            )
        if not data_path.exists():
            _atomic_text(data_path, content)
        sidecar = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_frozen_nominal_input",
            "ticker": ticker,
            "decision_date": args.decision_date,
            "price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
            "corporate_action_adjustment": "none",
            "source_mode": source_mode,
            "source_errors_before_success": source_errors,
            "data_start": frame.index.min().date().isoformat(),
            "data_end": frame.index.max().date().isoformat(),
            "rows": len(frame),
            "content_sha256": file_sha256(data_path),
            "rows_after_decision_date_included": False,
            "historical_backfill_allowed": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        sidecar_path = data_path.with_suffix(".csv.manifest.json")
        sidecar_content = json.dumps(sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if sidecar_path.exists() and sidecar_path.read_text(encoding="utf-8") != sidecar_content:
            raise NdxDynamicShadowCandidateSnapshotError(
                f"immutable nominal source manifest collision: {ticker}"
            )
        if not sidecar_path.exists():
            _atomic_text(sidecar_path, sidecar_content)
        data_key = f"nominal_price_{ticker}_sha256"
        manifest_key = f"nominal_price_{ticker}_manifest_sha256"
        versions[data_key] = file_sha256(data_path)
        versions[manifest_key] = file_sha256(sidecar_path)
        paths[data_key] = data_path.resolve().as_posix()
        paths[manifest_key] = sidecar_path.resolve().as_posix()
        frames[ticker] = frame.reset_index()
    return frames, versions, paths


def _load_target(
    args: argparse.Namespace, cfg
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    target_path = _resolve(args.target_nav)
    manifest_path = _resolve(args.target_manifest)
    if args.refresh_target:
        _, meta = get_fund_nav("012922", cfg, refresh=True)
        if getattr(meta, "cached", False) or getattr(meta, "stale", False):
            raise NdxDynamicShadowCandidateSnapshotError(
                "012922 refresh fell back to stale/cache data"
            )
    manifest = _json(manifest_path)
    if manifest.get("dataset_key") != "012922" or manifest.get("content_sha256") != file_sha256(target_path):
        raise NdxDynamicShadowCandidateSnapshotError("012922 target manifest/content hash mismatch")
    versions = {
        "target_012922_sha256": file_sha256(target_path),
        "target_012922_manifest_sha256": file_sha256(manifest_path),
    }
    paths = {
        "target_012922_sha256": target_path.as_posix(),
        "target_012922_manifest_sha256": manifest_path.as_posix(),
    }
    return pd.read_csv(target_path), versions, paths


def _validate_decision_seal_timing(
    sessions: pd.DataFrame,
    *,
    decision_date: str,
    observed_system_utc: pd.Timestamp,
) -> dict[str, str]:
    required = {
        "session_date", "close_timestamp_utc", "completed",
        "is_first_observed_session_of_month", "origin", "decision_eligible",
    }
    if sessions.empty or not required.issubset(sessions.columns):
        raise NdxDynamicShadowCandidateSnapshotError(
            "observed decision calendar is incomplete"
        )
    frame = sessions.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"], errors="raise").dt.normalize()
    if frame["session_date"].duplicated().any() or not frame["session_date"].is_monotonic_increasing:
        raise NdxDynamicShadowCandidateSnapshotError("observed session dates must be unique and sorted")
    decision = pd.Timestamp(decision_date).normalize()
    if decision < pd.Timestamp("2026-10-01"):
        raise NdxDynamicShadowCandidateSnapshotError("retrospective pre-activation seal is forbidden")
    row = frame.loc[frame["session_date"].eq(decision)]
    if len(row) != 1:
        raise NdxDynamicShadowCandidateSnapshotError("decision session is not in the observed calendar")
    item = row.iloc[0]
    truthy = lambda value: value is True or str(value).strip().lower() == "true"
    if (
        not truthy(item["completed"])
        or not truthy(item["is_first_observed_session_of_month"])
        or not truthy(item["decision_eligible"])
        or item["origin"] != "PROSPECTIVE_OBSERVED_APPEND"
    ):
        raise NdxDynamicShadowCandidateSnapshotError(
            "decision is not the first prospectively observed completed session of month"
        )
    if frame["session_date"].gt(decision).any():
        raise NdxDynamicShadowCandidateSnapshotError(
            "a later completed session already exists; late decision sealing/backfill is forbidden"
        )
    close_timestamp = pd.Timestamp(item["close_timestamp_utc"])
    if close_timestamp.tzinfo is None:
        raise NdxDynamicShadowCandidateSnapshotError("decision close timestamp is not timezone-aware")
    close_timestamp = close_timestamp.tz_convert("UTC")
    observed = observed_system_utc.tz_convert("UTC")
    if observed < close_timestamp:
        raise NdxDynamicShadowCandidateSnapshotError("decision session has not reached its close boundary")
    next_weekday = decision.date() + timedelta(days=1)
    while next_weekday.weekday() >= 5:
        next_weekday += timedelta(days=1)
    conservative_deadline = pd.Timestamp(
        datetime.combine(next_weekday, time(9, 30), tzinfo=ZoneInfo("America/New_York"))
    ).tz_convert("UTC")
    if observed >= conservative_deadline:
        raise NdxDynamicShadowCandidateSnapshotError(
            "decision seal missed conservative next-weekday open boundary; NO_DECISION_NO_BACKFILL"
        )
    return {
        "decision_date": decision.date().isoformat(),
        "decision_close_timestamp_utc": close_timestamp.isoformat(),
        "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        "conservative_seal_deadline_utc": conservative_deadline.isoformat(),
    }


def seal(args: argparse.Namespace) -> dict[str, Any]:
    if not args.session_calendar_manifest:
        raise NdxDynamicShadowCandidateSnapshotError("--session-calendar-manifest is required for seal")
    if args.execution_date:
        raise NdxDynamicShadowCandidateSnapshotError(
            "execution date is resolved later from the observed calendar, not supplied at decision seal"
        )
    _require_canonical_seal_paths(args)
    required_refresh_flags = (
        "refresh_official", "refresh_membership", "rebuild_taxonomy",
        "refresh_prices", "refresh_nominal_prices", "refresh_target",
    )
    missing_flags = [flag for flag in required_refresh_flags if not bool(getattr(args, flag))]
    if missing_flags:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"prospective seal requires fresh inputs: {missing_flags}"
        )
    contract_path = _resolve(args.contract)
    contract = load_generator_contract(contract_path)
    sessions, calendar_versions, calendar_paths = _load_calendar(
        _resolve(args.session_calendar_manifest)
    )
    observed_clock = _registration_clock(
        args.as_of_timestamp_utc,
        maximum_skew_seconds=int(contract["schedule_contract"]["caller_asof_max_skew_seconds"]),
    )
    timing = _validate_decision_seal_timing(
        sessions,
        decision_date=args.decision_date,
        observed_system_utc=observed_clock,
    )
    if timing["decision_date"] != args.decision_date:
        raise NdxDynamicShadowCandidateSnapshotError("calendar timing normalization changed coordinate")
    cfg = load_config(_resolve(args.config))
    eligible, versions, source_paths, membership_evidence = _load_taxonomy_memberships(
        args, cfg, timing=timing
    )
    original8_tickers, _, original8_hash = load_frozen_original_8_definition(
        _resolve(args.original_8_manifest)
    )
    versions.update({
        "frozen_original8_manifest_sha256": original8_hash,
        "frozen_original8_verifier_sha256": file_sha256(
            ROOT / "backtest/ndx_dynamic_shadow_fresh_search.py"
        ),
    })
    source_paths.update({
        "frozen_original8_manifest_sha256": _resolve(args.original_8_manifest).as_posix(),
        "frozen_original8_verifier_sha256": (
            ROOT / "backtest/ndx_dynamic_shadow_fresh_search.py"
        ).as_posix(),
    })
    price_tickers = sorted(
        set(eligible["ticker"].astype(str).str.upper()) | set(original8_tickers)
    )
    prices, price_versions, price_paths = _load_prices(
        args, cfg, price_tickers
    )
    nominal_prices, nominal_versions, nominal_paths = _load_and_freeze_nominal_prices(
        args, price_tickers
    )
    target, target_versions, target_paths = _load_target(args, cfg)
    versions.update(price_versions)
    versions.update(nominal_versions)
    versions.update(target_versions)
    versions.update(calendar_versions)
    source_paths.update(price_paths)
    source_paths.update(nominal_paths)
    source_paths.update(target_paths)
    source_paths.update(calendar_paths)
    seal_timestamp = _registration_clock(
        args.as_of_timestamp_utc,
        maximum_skew_seconds=int(contract["schedule_contract"]["caller_asof_max_skew_seconds"]),
    )
    versions.update({
        "generator_contract_sha256": file_sha256(contract_path),
        "generator_module_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_candidate_snapshot.py"),
        "generator_script_sha256": file_sha256(Path(__file__).resolve()),
    })
    source_paths.update({
        "generator_contract_sha256": contract_path.as_posix(),
        "generator_module_sha256": (ROOT / "backtest/ndx_dynamic_shadow_candidate_snapshot.py").as_posix(),
        "generator_script_sha256": Path(__file__).resolve().as_posix(),
    })
    snapshot = build_fresh_candidate_input_snapshot(
        eligible,
        prices,
        nominal_prices,
        target,
        decision_date=args.decision_date,
        decision_close_timestamp_utc=timing["decision_close_timestamp_utc"],
        seal_timestamp_utc=seal_timestamp.isoformat(),
        conservative_seal_deadline_utc=timing["conservative_seal_deadline_utc"],
        source_versions=versions,
        source_paths=source_paths,
        frozen_original8_tickers=list(original8_tickers),
        exact_enumeration_limit=int(contract["search_contract"]["exact_enumeration_max_feasible_combinations"]),
        minimum_common_price_rows=int(contract["input_contract"]["minimum_common_adjusted_price_rows"]),
        training_lookback_rows=int(contract["input_contract"]["training_lookback_rows"]),
        nominal_liquidity_lookback_rows=int(
            contract["input_contract"]["nominal_price_liquidity_lookback_rows"]
        ),
        minimum_median_dollar_volume_usd=float(
            contract["input_contract"]["minimum_median_dollar_volume_usd"]
        ),
    )
    snapshot["membership_evidence"] = membership_evidence
    snapshot["membership_evidence"]["decision_seal_timestamp_utc"] = seal_timestamp.isoformat()
    output = DEFAULT_ROOT / args.decision_date
    manifest = write_snapshot_bundle(output, snapshot)
    manifest_path = output / "manifest.json"
    _append_decision_seal(SEAL_LEDGER, manifest_path, manifest)
    _verify_manifest_seal_record(manifest_path, manifest)
    return manifest


def readiness(args: argparse.Namespace) -> dict[str, Any]:
    decision = pd.Timestamp(args.decision_date).normalize()
    now = pd.Timestamp.now(tz="UTC")
    history_manifest = _json(_resolve(args.membership_manifest))
    taxonomy_manifest = _json(_resolve(args.taxonomy_manifest))
    taxonomy_input = _taxonomy_membership_input(taxonomy_manifest)
    membership_hash = file_sha256(_resolve(args.membership_history))
    blockers = []
    if now < decision.tz_localize("UTC"):
        blockers.append({"code": "DECISION_CLOSE_NOT_REACHED", "reason": "prospective snapshot cannot be sealed before its observed completed decision session"})
    if taxonomy_input.get("content_sha256") != membership_hash:
        blockers.append({"code": "TAXONOMY_MEMBERSHIP_HASH_MISMATCH", "reason": "rebuild taxonomy after membership refresh"})
    blockers.extend([
        {"code": "PROSPECTIVE_OBSERVED_DECISION_SESSION_REQUIRED", "reason": "decision seal requires the first completed monthly session in the append-only observed calendar"},
        {"code": "FRESH_OFFICIAL_NASDAQ_DECISION_WINDOW_REFRESH_REQUIRED", "reason": "official current Nasdaq snapshot must be fetched after decision close and archived; source effective date remains unknown/degraded"},
        {"code": "FRESH_PRICE_AND_NAV_REFRESH_REQUIRED", "reason": "all eligible adjusted prices must end at decision close; 012922 must be non-future"},
    ])
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_candidate_generator_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED" if blockers else "READY_TO_ATTEMPT_PROSPECTIVE_SEAL",
        "decision_date": args.decision_date,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "historical_runner_registry_read": False,
        "historical_candidate_snapshot_read": False,
        "frozen_forward_candidate_source_used": False,
        "execution_date_known_at_decision_seal": False,
        "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        "official_membership_source_effective_date_known": False,
        "exact_ndx_membership_claimed": False,
        "membership_data_end": history_manifest.get("data_end"),
        "latest_membership_report_date": max((str(x) for x in history_manifest.get("report_dates", []) if x), default=None),
        "taxonomy_membership_hash_matches": taxonomy_input.get("content_sha256") == membership_hash,
        "taxonomy_identity_issue_count": int((taxonomy_manifest.get("summary") or {}).get("identity_issue_count") or 0),
        "taxonomy_identity_issue_handling": "HASH_BOUND_AFFECTED_SECURITY_ISSUER_TICKER_EXCLUSION_IN_DEGRADED_RESEARCH",
        "complete_universe_claimed": False,
        "blockers": blockers,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fresh PIT dynamic-shadow candidate input snapshot and full-k planner")
    parser.add_argument("--contract", default="config/ndx_dynamic_shadow_candidate_generator_v1.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--decision-date", default="2026-10-01")
    parser.add_argument("--execution-date", default="")
    parser.add_argument("--as-of-timestamp-utc", default="")
    parser.add_argument("--session-calendar-manifest", default="")
    parser.add_argument("--membership-history", default="data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv")
    parser.add_argument("--membership-manifest", default="data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json")
    parser.add_argument("--taxonomy-manifest", default="data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json")
    parser.add_argument("--taxonomy-records", default="data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv")
    parser.add_argument("--search-plan", default="config/ndx_cardinality_search_v1_plan.yaml")
    parser.add_argument("--security-lifecycle", default="config/ndx_security_lifecycle.yaml")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--target-manifest", default="data/cache/funds/012922.csv.manifest.json")
    parser.add_argument("--original-8-manifest", default="data/cache/research/ndx_original_8_control_v1/manifest.json")
    parser.add_argument("--output-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--refresh-official", action="store_true")
    parser.add_argument("--refresh-membership", action="store_true")
    parser.add_argument("--rebuild-taxonomy", action="store_true")
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--refresh-nominal-prices", action="store_true")
    parser.add_argument("--refresh-target", action="store_true")
    parser.add_argument("--allow-degraded-reviewed-taxonomy-subset", action="store_true")
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--verify", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protected_before = _protected_hashes()
    try:
        if args.verify:
            verify_path = _resolve(args.verify)
            if not verify_path.is_relative_to(DEFAULT_ROOT.resolve()):
                raise NdxDynamicShadowCandidateSnapshotError(
                    "candidate verification path must stay under the canonical research root"
                )
            result = verify_snapshot_bundle(verify_path)
            _verify_manifest_seal_record(verify_path, result)
        elif args.seal:
            result = seal(args)
        else:
            if _resolve(args.output_root) != DEFAULT_ROOT.resolve():
                raise NdxDynamicShadowCandidateSnapshotError(
                    "candidate readiness output root must be canonical"
                )
            result = readiness(args)
            _atomic_json(DEFAULT_ROOT / "readiness.json", result)
        if _protected_hashes() != protected_before:
            raise NdxDynamicShadowCandidateSnapshotError("protected live files changed")
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_candidate_generator_failure",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "historical_candidate_replay_used": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        _atomic_json(DEFAULT_ROOT / "last_failure.json", failure)
        print(f"dynamic shadow candidate generator fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "dynamic shadow candidate generator | "
        f"status={result['status']} | decision={result.get('decision_date')} | "
        "promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
