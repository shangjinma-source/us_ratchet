"""Strict contract and provenance verifier for candidate-generator v3.

The executable wrapper lives in ``scripts``.  This module deliberately has no
network or write path: it validates the new identity lineage on top of an
already verified candidate-v2 snapshot.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any

import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_candidate_membership_v3 import (
    ADAPTER_ID as MEMBERSHIP_ADAPTER_ID,
    IDENTITY_RESOLVER_ID,
    build_runtime_official_eligible_membership_v3,
)
from data.ndx_history import constituents_asof
from data.ndx_price_basis import RECOGNIZED_SOURCE_MODES
from data.ndx_security_identity import load_security_lifecycle
from data.ndx_taxonomy import build_security_universe
from data.versioning import file_sha256


class NdxDynamicShadowCandidateGeneratorV3Error(ValueError):
    """Raised when the candidate-v3 lineage cannot be independently verified."""


CONTRACT_RELATIVE = Path("config/ndx_dynamic_shadow_candidate_generator_v3.yaml")
OUTPUT_ROOT_RELATIVE = Path(
    "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1"
)
FIRST_DECISION = date(2026, 10, 1)
STATIC_SOURCE_PATHS = {
    "candidate_generator_v1_script_sha256": Path(
        "scripts/ndx_dynamic_shadow_candidate_generator.py"
    ),
    "candidate_generator_v2_script_sha256": Path(
        "scripts/ndx_dynamic_shadow_candidate_generator_v2.py"
    ),
    "candidate_generator_v3_script_sha256": Path(
        "scripts/ndx_dynamic_shadow_candidate_generator_v3.py"
    ),
    "candidate_generator_v3_verifier_sha256": Path(
        "backtest/ndx_dynamic_shadow_candidate_generator_v3.py"
    ),
    "candidate_generator_v3_contract_sha256": CONTRACT_RELATIVE,
    "candidate_identity_v3_module_sha256": Path(
        "backtest/ndx_dynamic_shadow_candidate_identity_v3.py"
    ),
    "candidate_membership_v3_module_sha256": Path(
        "backtest/ndx_dynamic_shadow_candidate_membership_v3.py"
    ),
    "official_candidate_pool_module_sha256": Path("data/candidate_pool.py"),
    "nominal_price_basis_module_sha256": Path("data/ndx_price_basis.py"),
    "taxonomy_identity_engine_sha256": Path("data/ndx_taxonomy.py"),
}
REQUIRED_EXISTING_SOURCE_PATHS = {
    "generator_contract_sha256": Path(
        "config/ndx_dynamic_shadow_candidate_generator_v1.yaml"
    ),
    "generator_module_sha256": Path(
        "backtest/ndx_dynamic_shadow_candidate_snapshot.py"
    ),
    "generator_script_sha256": Path(
        "scripts/ndx_dynamic_shadow_candidate_generator_v2.py"
    ),
    "membership_history_sha256": Path(
        "data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv"
    ),
    "membership_manifest_sha256": Path(
        "data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json"
    ),
    "taxonomy_manifest_sha256": Path(
        "data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json"
    ),
    "taxonomy_records_sha256": Path(
        "data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv"
    ),
    "taxonomy_identity_issues_sha256": Path(
        "data/cache/candidate_pools/ndx_taxonomy_v2/identity_issues.csv"
    ),
    "search_plan_sha256": Path("config/ndx_cardinality_search_v1_plan.yaml"),
    "security_lifecycle_sha256": Path("config/ndx_security_lifecycle.yaml"),
    "cik_crosswalk_sha256": Path(
        "data/cache/candidate_pools/ndx_fundamentals/cik_crosswalk.csv"
    ),
    "cik_crosswalk_manifest_sha256": Path(
        "data/cache/candidate_pools/ndx_fundamentals/cik_crosswalk.csv.manifest.json"
    ),
}
CAPTURE_SOURCE_KEYS = {
    "official_snapshot_sha256",
    "official_snapshot_manifest_sha256",
    "membership_history_sha256",
    "membership_manifest_sha256",
    "taxonomy_manifest_sha256",
    "taxonomy_records_sha256",
    "taxonomy_identity_issues_sha256",
    "search_plan_sha256",
    "security_lifecycle_sha256",
    "cik_crosswalk_sha256",
    "cik_crosswalk_manifest_sha256",
}
CONTRACT_FIELDS = {
    "schema_version", "generator_id", "status", "research_track",
    "migration_control_included", "lineage_contract", "schedule_contract",
    "identity_contract", "cardinality_contract", "source_binding_contract",
    "source_archive_contract", "mutation_boundary",
}
SOURCE_ARCHIVE_DIRECTORY = "v3_source_archive"
SOURCE_ARCHIVE_MANIFEST = "manifest.json"
SOURCE_ARCHIVE_MANIFEST_FIELDS = {
    "schema_version", "manifest_type", "decision_date", "capture_mode",
    "verification_mode", "source_key_count", "source_descriptors",
    "canonical_source_restore_required", "canonical_source_writeback_allowed",
    "research_only", "promotion_allowed", "live_mutation",
    "manifest_payload_sha256",
}
SOURCE_ARCHIVE_DESCRIPTOR_FIELDS = {
    "path", "sha256", "source_key_count", "verification_mode",
    "canonical_source_restore_required", "canonical_source_writeback_allowed",
}
SOURCE_ARCHIVE_ENTRY_FIELDS = {
    "source_key", "original_path", "archive_filename", "sha256",
    "content_bytes",
}
OFFICIAL_SOURCE_LOCATOR = (
    "https://www.nasdaq.com/solutions/global-indexes/nasdaq-100/companies"
)
OFFICIAL_SNAPSHOT_COLUMNS = [
    "as_of_date", "source_type", "source_id", "ticker", "name", "weight",
    "sector", "source_locator",
]
OFFICIAL_MANIFEST_FIELDS = {
    "allowed_uses", "as_of_date", "as_of_date_evidence", "cache_path",
    "completeness", "content_bytes", "content_sha256", "data_end",
    "data_start", "dataset_key", "dataset_type", "fetched_at",
    "fetched_at_evidence", "generated_at", "historical_backtest_allowed",
    "immutable_snapshot", "index_id", "manifest_path", "observed_added",
    "observed_change_date_kind", "observed_removed",
    "observed_security_count", "point_in_time_scope", "previous_version_id",
    "prohibited_uses", "publication_time_known", "row_count",
    "schema_version", "sector_available", "source",
    "source_company_count_claim", "source_confidence",
    "source_effective_date_known", "source_locator", "source_record_count",
    "ticker_name_fallback_count", "ticker_name_fallback_rule",
    "ticker_name_fallbacks", "version_id", "weights_available",
}
NOMINAL_SIDECAR_FIELDS = {
    "schema_version", "manifest_type", "ticker", "decision_date",
    "price_basis", "corporate_action_adjustment", "source_mode",
    "source_errors_before_success", "data_start", "data_end", "rows",
    "content_sha256", "rows_after_decision_date_included",
    "historical_backfill_allowed", "promotion_allowed", "live_mutation",
}
NOMINAL_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
LIQUIDITY_LOOKBACK_ROWS = 63
MINIMUM_MEDIAN_DOLLAR_VOLUME_USD = 50_000_000.0
ALLOWED_NOMINAL_SOURCE_MODES = {"eastmoney_fqt_0", "sina_raw_daily"}


def _mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise NdxDynamicShadowCandidateGeneratorV3Error(f"{label} schema changed")
    return value


def _false(mapping: Mapping[str, Any], keys: set[str], label: str) -> None:
    if any(mapping.get(key) is not False for key in keys):
        raise NdxDynamicShadowCandidateGeneratorV3Error(f"{label} false boundary changed")


def _canonical_date(value: Any, label: str) -> date:
    text = str(value or "").strip()
    try:
        result = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(f"invalid {label}") from exc
    if text != result.isoformat():
        raise NdxDynamicShadowCandidateGeneratorV3Error(f"non-canonical {label}")
    return result


def load_candidate_generator_v3_contract(
    path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    target = Path(path).resolve()
    if target != (root / CONTRACT_RELATIVE).resolve():
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 contract path is not canonical"
        )
    try:
        value = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 contract is unreadable"
        ) from exc
    contract = dict(_mapping(value, CONTRACT_FIELDS, "candidate-v3 contract"))
    if (
        contract["schema_version"] != 1
        or contract["generator_id"] != "ndx_dynamic_shadow_candidate_generator_v3"
        or contract["status"] != "IMPLEMENTED_RESEARCH_ONLY_NOT_REGISTERED"
        or contract["research_track"] != "portfolio_optimization"
        or contract["migration_control_included"] is not False
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 contract identity changed"
        )
    lineage = _mapping(contract["lineage_contract"], {
        "parent_generator", "parent_snapshot_schema", "parent_output_root",
        "reviewed_calendar_lineage", "identity_resolver", "membership_adapter",
        "existing_parent_files_mutated",
    }, "candidate-v3 lineage")
    if lineage != {
        "parent_generator": "ndx_dynamic_shadow_candidate_generator_v2",
        "parent_snapshot_schema": "ndx_dynamic_shadow_candidate_input_snapshot",
        "parent_output_root": OUTPUT_ROOT_RELATIVE.as_posix(),
        "reviewed_calendar_lineage": "ndx_observed_us_session_calendar_v2",
        "identity_resolver": IDENTITY_RESOLVER_ID,
        "membership_adapter": MEMBERSHIP_ADAPTER_ID,
        "existing_parent_files_mutated": False,
    }:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 lineage changed"
        )
    schedule = _mapping(contract["schedule_contract"], {
        "first_decision_not_before", "decision_coordinate",
        "execution_coordinate_rule", "system_clock_required",
        "retrospective_backfill_allowed", "late_seal_action",
    }, "candidate-v3 schedule")
    if (
        str(schedule["first_decision_not_before"]) != FIRST_DECISION.isoformat()
        or schedule["decision_coordinate"]
        != "FIRST_PROSPECTIVELY_OBSERVED_MONTHLY_SESSION_CLOSE"
        or schedule["execution_coordinate_rule"]
        != "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        or schedule["system_clock_required"] is not True
        or schedule["retrospective_backfill_allowed"] is not False
        or schedule["late_seal_action"] != "NO_DECISION_NO_BACKFILL"
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 prospective schedule changed"
        )
    identity = _mapping(contract["identity_contract"], {
        "taxonomy_alias_delimiter", "reviewed_lifecycle_required_for_aliases",
        "lifecycle_last_reviewed_must_not_exceed_decision",
        "identity_issue_exclusion_scope", "arbitrary_issuer_wide_exclusion_allowed",
        "explicit_issuer_issue_exclusion_allowed", "official_observation_date_preserved",
        "official_membership_effective_date_proved",
        "execution_valid_on_date_identity_proved", "complete_universe_claimed",
        "identity_issue_rebuild", "frozen_sec_cik_crosswalk_sha256",
        "frozen_reviewed_lifecycle_sha256",
    }, "candidate-v3 identity")
    if (
        identity["taxonomy_alias_delimiter"] != ";"
        or identity["reviewed_lifecycle_required_for_aliases"] is not True
        or identity["lifecycle_last_reviewed_must_not_exceed_decision"] is not True
        or identity["identity_issue_exclusion_scope"]
        != "SAME_SECURITY_OR_SHARED_ALIAS_CONNECTED_CLOSURE"
        or identity["explicit_issuer_issue_exclusion_allowed"] is not True
        or identity["official_observation_date_preserved"] is not True
        or identity["identity_issue_rebuild"]
        != "NPORT_PLUS_FROZEN_SEC_CIK_CROSSWALK_PLUS_REVIEWED_LIFECYCLE"
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(identity["frozen_sec_cik_crosswalk_sha256"])
        )
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(identity["frozen_reviewed_lifecycle_sha256"])
        )
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 identity policy changed"
        )
    _false(identity, {
        "arbitrary_issuer_wide_exclusion_allowed",
        "official_membership_effective_date_proved",
        "execution_valid_on_date_identity_proved", "complete_universe_claimed",
    }, "candidate-v3 identity")
    cardinality = _mapping(contract["cardinality_contract"], {
        "holding_count_policy", "fixed_holding_count",
        "one_security_per_issuer_required",
        "multiple_share_classes_may_be_retained_in_pool",
        "multiple_share_classes_increase_k_upper_bound", "portfolio_optimization",
        "migration_control",
    }, "candidate-v3 cardinality")
    if cardinality != {
        "holding_count_policy": "DYNAMIC_K_1_TO_ELIGIBLE_UNIQUE_ISSUER_COUNT",
        "fixed_holding_count": None,
        "one_security_per_issuer_required": True,
        "multiple_share_classes_may_be_retained_in_pool": True,
        "multiple_share_classes_increase_k_upper_bound": False,
        "portfolio_optimization": True,
        "migration_control": False,
    }:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 cardinality policy changed"
        )
    binding = _mapping(contract["source_binding_contract"], {
        "consumed_tabular_sources_parsed_from_single_captured_bytes",
        "captured_bytes_hashed_before_parse",
        "captured_sources_rechecked_before_decision_seal_append",
        "source_path_and_sha256_registry_required",
        "missing_v3_provenance_allowed", "required_v3_source_keys",
    }, "candidate-v3 source binding")
    if (
        any(binding[key] is not True for key in (
            "consumed_tabular_sources_parsed_from_single_captured_bytes",
            "captured_bytes_hashed_before_parse",
            "captured_sources_rechecked_before_decision_seal_append",
            "source_path_and_sha256_registry_required",
        ))
        or binding["missing_v3_provenance_allowed"] is not False
        or binding["required_v3_source_keys"] != list(STATIC_SOURCE_PATHS)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source binding changed"
        )
    archive_contract = _mapping(contract["source_archive_contract"], {
        "archive_directory", "archive_manifest", "capture_mode",
        "historical_verification_mode", "current_window_source_recheck_required",
        "canonical_source_restore_required", "canonical_source_writeback_allowed",
        "missing_archive_allowed", "research_only", "promotion_allowed",
        "live_mutation",
    }, "candidate-v3 source archive")
    if (
        archive_contract["archive_directory"] != SOURCE_ARCHIVE_DIRECTORY
        or archive_contract["archive_manifest"] != SOURCE_ARCHIVE_MANIFEST
        or archive_contract["capture_mode"]
        != "READ_CAPTURED_BYTES_HASH_THEN_ATOMIC_ARCHIVE"
        or archive_contract["historical_verification_mode"]
        != "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY"
        or archive_contract["current_window_source_recheck_required"] is not True
        or archive_contract["research_only"] is not True
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive contract changed"
        )
    _false(archive_contract, {
        "canonical_source_restore_required", "canonical_source_writeback_allowed",
        "missing_archive_allowed", "promotion_allowed", "live_mutation",
    }, "candidate-v3 source archive")
    mutation = _mapping(contract["mutation_boundary"], {
        "research_output_only", "existing_activation_mutation_allowed",
        "scheduler_mutation_allowed", "live_config_mutation_allowed",
        "state_mutation_allowed", "broker_snapshot_mutation_allowed",
        "today_advice_mutation_allowed", "order_creation_allowed",
        "promotion_allowed",
    }, "candidate-v3 mutation")
    if mutation["research_output_only"] is not True:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 research-only boundary changed"
        )
    _false(mutation, set(mutation) - {"research_output_only"}, "candidate-v3 mutation")
    return contract


def static_source_registry(*, repository_root: str | Path) -> tuple[dict[str, str], dict[str, str]]:
    root = Path(repository_root).resolve()
    versions: dict[str, str] = {}
    paths: dict[str, str] = {}
    for key, relative in STATIC_SOURCE_PATHS.items():
        path = (root / relative).resolve()
        if not path.is_file():
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 static source is missing: {key}"
            )
        versions[key] = file_sha256(path)
        paths[key] = path.as_posix()
    return versions, paths


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def build_candidate_v3_source_archive_payload(
    decision_date: str,
    source_captures: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build deterministic archive bytes without reading or writing canonical sources."""

    decision = _canonical_date(decision_date, "candidate archive decision_date")
    if not source_captures:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive is empty"
        )
    entries: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    for key in sorted(source_captures):
        if not re.fullmatch(r"[A-Za-z0-9_]+_sha256", str(key)):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive key is invalid: {key}"
            )
        item = source_captures[key]
        if not isinstance(item, Mapping) or set(item) != {"path", "raw", "sha256"}:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive capture schema changed: {key}"
            )
        path = Path(str(item["path"])).resolve()
        raw = item["raw"]
        if not path.is_absolute() or not isinstance(raw, bytes):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive capture is invalid: {key}"
            )
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item["sha256"]:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive captured hash changed: {key}"
            )
        filename = f"sources/{key}.bin"
        entries.append({
            "source_key": str(key),
            "original_path": path.as_posix(),
            "archive_filename": filename,
            "sha256": digest,
            "content_bytes": len(raw),
        })
        files[filename] = raw
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_candidate_v3_source_archive",
        "decision_date": decision.isoformat(),
        "capture_mode": "READ_CAPTURED_BYTES_HASH_THEN_ATOMIC_ARCHIVE",
        "verification_mode": "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY",
        "source_key_count": len(entries),
        "source_descriptors": entries,
        "canonical_source_restore_required": False,
        "canonical_source_writeback_allowed": False,
        "research_only": True,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    payload["manifest_payload_sha256"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return payload, files


def verify_candidate_v3_source_archive(
    descriptor: Any,
    *,
    snapshot_manifest_path: str | Path,
    decision_date: str,
    source_versions: Mapping[str, Any],
    source_paths: Mapping[str, Any],
    expected_source_keys: set[str],
) -> dict[str, bytes]:
    """Verify and return immutable bytes; never restore them to canonical paths."""

    manifest_path = Path(snapshot_manifest_path).resolve()
    expected_path = (
        manifest_path.parent / SOURCE_ARCHIVE_DIRECTORY / SOURCE_ARCHIVE_MANIFEST
    ).resolve()
    item = _mapping(
        descriptor, SOURCE_ARCHIVE_DESCRIPTOR_FIELDS,
        "candidate-v3 source archive descriptor",
    )
    path = Path(str(item["path"])).resolve()
    if path != expected_path or not path.is_file():
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 immutable source archive is missing or non-canonical"
        )
    raw_manifest = path.read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != item["sha256"]:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 immutable source archive manifest hash changed"
        )
    manifest = _json_bytes(raw_manifest, "source archive manifest")
    _mapping(
        manifest, SOURCE_ARCHIVE_MANIFEST_FIELDS,
        "candidate-v3 source archive manifest",
    )
    if raw_manifest != _canonical_json_bytes(manifest):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive manifest is not canonical"
        )
    payload = dict(manifest)
    payload_hash = payload.pop("manifest_payload_sha256", None)
    if hashlib.sha256(_canonical_json_bytes(payload)).hexdigest() != payload_hash:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive payload hash changed"
        )
    decision = _canonical_date(decision_date, "candidate archive decision_date")
    entries = manifest.get("source_descriptors")
    if not isinstance(entries, list):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive descriptors are invalid"
        )
    if (
        manifest["schema_version"] != 1
        or manifest["manifest_type"]
        != "ndx_dynamic_shadow_candidate_v3_source_archive"
        or manifest["decision_date"] != decision.isoformat()
        or manifest["capture_mode"]
        != "READ_CAPTURED_BYTES_HASH_THEN_ATOMIC_ARCHIVE"
        or manifest["verification_mode"]
        != "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY"
        or manifest["source_key_count"] != len(entries)
        or item["source_key_count"] != len(entries)
        or item["verification_mode"] != manifest["verification_mode"]
        or item["canonical_source_restore_required"] is not False
        or item["canonical_source_writeback_allowed"] is not False
        or manifest["canonical_source_restore_required"] is not False
        or manifest["canonical_source_writeback_allowed"] is not False
        or manifest["research_only"] is not True
        or manifest["promotion_allowed"] is not False
        or manifest["live_mutation"] is not False
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive boundary changed"
        )
    archived: dict[str, bytes] = {}
    for entry in entries:
        row = _mapping(
            entry, SOURCE_ARCHIVE_ENTRY_FIELDS,
            "candidate-v3 source archive entry",
        )
        key = str(row["source_key"])
        expected_filename = f"sources/{key}.bin"
        filename = str(row["archive_filename"])
        source_path = (path.parent / filename).resolve()
        if (
            key in archived
            or key not in expected_source_keys
            or filename != expected_filename
            or not source_path.is_relative_to((path.parent / "sources").resolve())
            or source_path.parent != (path.parent / "sources").resolve()
            or not source_path.is_file()
            or Path(str(row["original_path"])).resolve()
            != Path(str(source_paths.get(key) or "")).resolve()
            or row["sha256"] != source_versions.get(key)
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive entry binding changed: {key}"
            )
        raw = source_path.read_bytes()
        if (
            hashlib.sha256(raw).hexdigest() != row["sha256"]
            or len(raw) != row["content_bytes"]
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 source archive bytes changed: {key}"
            )
        archived[key] = raw
    if set(archived) != expected_source_keys:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive key set is incomplete"
        )
    return archived


def assess_candidate_v3_source_archive_readiness(
    descriptor: Any,
    *,
    snapshot_manifest_path: str | Path,
    decision_date: str,
    source_versions: Mapping[str, Any],
    source_paths: Mapping[str, Any],
    expected_source_keys: set[str],
) -> dict[str, Any]:
    """Report archive replay readiness without restoring or mutating any source."""

    archived = verify_candidate_v3_source_archive(
        descriptor,
        snapshot_manifest_path=snapshot_manifest_path,
        decision_date=decision_date,
        source_versions=source_versions,
        source_paths=source_paths,
        expected_source_keys=expected_source_keys,
    )
    current_matches = True
    for key in sorted(expected_source_keys):
        current = Path(str(source_paths[key])).resolve()
        if not current.is_file() or hashlib.sha256(current.read_bytes()).hexdigest() != source_versions[key]:
            current_matches = False
            break
    return {
        "schema_version": 1,
        "status": "HISTORICAL_ARCHIVE_REPLAY_READY",
        "historical_archive_verified": True,
        "current_canonical_sources_match_capture": current_matches,
        "source_key_count": len(archived),
        "verification_mode": "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY",
        "canonical_source_restore_required": False,
        "canonical_source_writeback_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def _verify_path_hash(
    versions: Mapping[str, Any], paths: Mapping[str, Any], key: str,
    expected_path: Path,
) -> bytes:
    path = Path(str(paths.get(key) or "")).resolve()
    if path != expected_path.resolve() or not path.is_file():
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 source path changed: {key}"
        )
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != versions.get(key):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 source hash changed: {key}"
        )
    return raw


def _json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} is unreadable"
        ) from exc
    if not isinstance(value, dict):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} is not an object"
        )
    return value


def _csv_bytes(raw: bytes, *, keep_default_na: bool = True) -> pd.DataFrame:
    return pd.read_csv(
        BytesIO(raw), keep_default_na=keep_default_na, low_memory=False,
        dtype={"cusip": str, "cusips": str, "cik": str},
    )


def _aware_utc(value: Any, label: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} is invalid"
        ) from exc
    if timestamp.tzinfo is None:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} is timezone-naive"
        )
    return timestamp.tz_convert("UTC")


def validate_captured_official_archive_v3(
    archive_bytes: bytes,
    manifest_bytes: bytes,
    *,
    archive_path: str | Path,
    manifest_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate source authority and immutable bytes for the official input."""

    archive = Path(archive_path).resolve()
    sidecar = Path(manifest_path).resolve()
    frame = _csv_bytes(archive_bytes)
    manifest = _json_bytes(manifest_bytes, "official archive manifest")
    if set(manifest) != OFFICIAL_MANIFEST_FIELDS:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive manifest schema changed"
        )
    if list(frame.columns) != OFFICIAL_SNAPSHOT_COLUMNS:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive columns changed"
        )
    row_count = len(frame)
    content_hash = hashlib.sha256(archive_bytes).hexdigest()
    as_of_values = set(frame["as_of_date"].astype(str))
    if len(as_of_values) != 1:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive has multiple observation dates"
        )
    as_of_date = next(iter(as_of_values))
    _canonical_date(as_of_date, "official archive as_of_date")
    tickers = frame["ticker"].astype(str)
    names = frame["name"].astype(str).str.strip()
    if (
        not 100 <= row_count <= 110
        or tickers.duplicated().any()
        or not tickers.map(lambda value: bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", value))).all()
        or names.eq("").any()
        or set(frame["source_type"].astype(str)) != {"index_constituent"}
        or set(frame["source_id"].astype(str)) != {"nasdaq_100"}
        or set(frame["source_locator"].astype(str)) != {OFFICIAL_SOURCE_LOCATOR}
        or frame["weight"].notna().any()
        or frame["sector"].fillna("").astype(str).str.strip().ne("").any()
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive rows violate the Nasdaq source contract"
        )
    expected_dataset_key = f"nasdaq_100:{as_of_date}:{content_hash[:12]}"
    expected_version = (
        f"security_pool_snapshot:{expected_dataset_key}:{content_hash[:16]}"
    )
    if (
        int(manifest.get("schema_version", -1)) != 1
        or manifest.get("dataset_type") != "security_pool_snapshot"
        or manifest.get("dataset_key") != expected_dataset_key
        or manifest.get("version_id") != expected_version
        or manifest.get("content_sha256") != content_hash
        or int(manifest.get("content_bytes", -1)) != len(archive_bytes)
        or Path(str(manifest.get("cache_path") or "")).resolve() != archive
        or Path(str(manifest.get("manifest_path") or "")).resolve() != sidecar
        or manifest.get("source") != "nasdaq_ndx_official_companies_page"
        or manifest.get("source_locator") != OFFICIAL_SOURCE_LOCATOR
        or manifest.get("fetched_at_evidence") != "runtime_fetch_utc"
        or manifest.get("as_of_date") != as_of_date
        or manifest.get("data_start") != as_of_date
        or manifest.get("data_end") != as_of_date
        or manifest.get("as_of_date_evidence")
        != "runtime_fetch_date_not_source_effective_date"
        or manifest.get("completeness")
        != "validated_unique_security_count_100_to_110"
        or int(manifest.get("row_count", -1)) != row_count
        or int(manifest.get("source_record_count", -1)) != row_count
        or int(manifest.get("observed_security_count", -1)) != row_count
        or manifest.get("index_id") != "NDX"
        or int(manifest.get("source_company_count_claim", -1)) != 100
        or manifest.get("source_confidence")
        != "official_source_runtime_or_export"
        or manifest.get("point_in_time_scope") != "current_snapshot_only"
        or manifest.get("observed_change_date_kind")
        != "local_snapshot_comparison_not_official_effective_date"
        or manifest.get("ticker_name_fallback_rule")
        != "exact_unique_company_name_from_last_complete_official_snapshot"
        or manifest.get("allowed_uses") != [
            "current_candidate_screen", "current_control_group",
            "forward_observation",
        ]
        or manifest.get("prohibited_uses") != [
            "historical_constituent_backtest", "historical_membership_inference",
            "backfill_before_as_of_date",
        ]
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive authority or byte binding changed"
        )
    for key in (
        "historical_backtest_allowed", "source_effective_date_known",
        "publication_time_known", "weights_available", "sector_available",
    ):
        if manifest.get(key) is not False:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 official archive false boundary changed: {key}"
            )
    if manifest.get("immutable_snapshot") is not True:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive is not immutable"
        )
    for key in ("observed_added", "observed_removed", "ticker_name_fallbacks"):
        if not isinstance(manifest.get(key), list):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 official archive {key} is not a list"
            )
    fallbacks = manifest["ticker_name_fallbacks"]
    if (
        int(manifest.get("ticker_name_fallback_count", -1)) != len(fallbacks)
        or any(not isinstance(item, Mapping) or set(item) != {"name", "ticker"} for item in fallbacks)
        or any(
            not ((names == str(item["name"]).strip()) & (tickers == str(item["ticker"]))).any()
            for item in fallbacks
        )
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive ticker fallback evidence changed"
        )
    fetched_at = _aware_utc(manifest.get("fetched_at"), "official fetched_at")
    generated_at = _aware_utc(manifest.get("generated_at"), "official generated_at")
    if fetched_at.date().isoformat() != as_of_date or generated_at < fetched_at:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive observation clock changed"
        )
    previous = manifest.get("previous_version_id")
    if previous is not None and not re.fullmatch(
        r"security_pool_current:nasdaq_100:[0-9a-f]{16}", str(previous)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive previous version is invalid"
        )
    return frame, manifest


def capture_nominal_liquidity_inputs_v3(
    pre_liquidity_membership: pd.DataFrame,
    source_versions: Mapping[str, Any],
    source_paths: Mapping[str, Any],
    *,
    decision_date: str,
    snapshot_directory: str | Path,
    captured_source_bytes: Mapping[str, bytes] | None = None,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, Any]]:
    """Capture and recompute the dynamic-pool liquidity partition."""

    decision = _canonical_date(decision_date, "candidate decision_date")
    required_identity = {"universe_track", "ticker", "security_id", "issuer_id"}
    if not required_identity.issubset(pre_liquidity_membership.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 pre-liquidity identity fields are incomplete"
        )
    tickers = sorted(set(pre_liquidity_membership["ticker"].astype(str)))
    if not tickers:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 pre-liquidity ticker pool is empty"
        )
    nominal_root = (Path(snapshot_directory).resolve() / "nominal_sources").resolve()
    frames: dict[str, pd.DataFrame] = {}
    medians: dict[str, float] = {}
    capture_versions: dict[str, str] = {}
    capture_paths: dict[str, str] = {}
    for ticker in tickers:
        data_key = f"nominal_price_{ticker}_sha256"
        sidecar_key = f"nominal_price_{ticker}_manifest_sha256"
        data_path = (nominal_root / f"{ticker}.csv").resolve()
        sidecar_path = data_path.with_suffix(".csv.manifest.json").resolve()
        if captured_source_bytes is None:
            data_raw = _verify_path_hash(
                source_versions, source_paths, data_key, data_path,
            )
            sidecar_raw = _verify_path_hash(
                source_versions, source_paths, sidecar_key, sidecar_path,
            )
        else:
            if (
                Path(str(source_paths.get(data_key) or "")).resolve() != data_path
                or Path(str(source_paths.get(sidecar_key) or "")).resolve()
                != sidecar_path
                or data_key not in captured_source_bytes
                or sidecar_key not in captured_source_bytes
            ):
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v3 archived nominal source binding changed: {ticker}"
                )
            data_raw = captured_source_bytes[data_key]
            sidecar_raw = captured_source_bytes[sidecar_key]
            if (
                hashlib.sha256(data_raw).hexdigest() != source_versions.get(data_key)
                or hashlib.sha256(sidecar_raw).hexdigest()
                != source_versions.get(sidecar_key)
            ):
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v3 archived nominal source hash changed: {ticker}"
                )
        frame = _csv_bytes(data_raw)
        sidecar = _json_bytes(sidecar_raw, f"{ticker} nominal sidecar")
        if set(sidecar) != NOMINAL_SIDECAR_FIELDS or list(frame.columns) != NOMINAL_COLUMNS:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal source schema changed: {ticker}"
            )
        raw_dates = frame["Date"].astype(str)
        if not raw_dates.map(lambda value: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))).all():
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal source has non-canonical dates: {ticker}"
            )
        parsed_dates = pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="raise")
        if parsed_dates.duplicated().any() or not parsed_dates.is_monotonic_increasing:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal source dates are not unique/sorted: {ticker}"
            )
        numeric = frame[["Open", "High", "Low", "Close", "Volume"]].apply(
            pd.to_numeric, errors="raise",
        )
        if (
            numeric.isna().any().any()
            or not numeric.map(math.isfinite).all().all()
            or numeric[["Open", "High", "Low", "Close"]].le(0).any().any()
            or numeric["Volume"].lt(0).any()
            or (numeric["High"] < numeric[["Open", "Close", "Low"]].max(axis=1)).any()
            or (numeric["Low"] > numeric[["Open", "Close", "High"]].min(axis=1)).any()
            or len(frame) < LIQUIDITY_LOOKBACK_ROWS
            or parsed_dates.max().date() != decision
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal source values/cutoff changed: {ticker}"
            )
        if (
            int(sidecar.get("schema_version", -1)) != 1
            or sidecar.get("manifest_type")
            != "ndx_dynamic_shadow_frozen_nominal_input"
            or sidecar.get("ticker") != ticker
            or sidecar.get("decision_date") != decision.isoformat()
            or sidecar.get("price_basis") != "UNADJUSTED_NOMINAL_TRADE_PRICE"
            or sidecar.get("corporate_action_adjustment") != "none"
            or sidecar.get("data_start") != parsed_dates.min().date().isoformat()
            or sidecar.get("data_end") != decision.isoformat()
            or int(sidecar.get("rows", -1)) != len(frame)
            or sidecar.get("content_sha256") != hashlib.sha256(data_raw).hexdigest()
            or sidecar.get("rows_after_decision_date_included") is not False
            or sidecar.get("historical_backfill_allowed") is not False
            or sidecar.get("promotion_allowed") is not False
            or sidecar.get("live_mutation") is not False
            or sidecar.get("source_mode") not in ALLOWED_NOMINAL_SOURCE_MODES
            or set(RECOGNIZED_SOURCE_MODES) != ALLOWED_NOMINAL_SOURCE_MODES
            or not isinstance(sidecar.get("source_errors_before_success"), Mapping)
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal sidecar semantics changed: {ticker}"
            )
        median = float(
            (numeric["Close"] * numeric["Volume"])
            .tail(LIQUIDITY_LOOKBACK_ROWS)
            .median()
        )
        if not math.isfinite(median) or median < 0:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 nominal liquidity is invalid: {ticker}"
            )
        normalized = numeric.copy()
        normalized.insert(0, "Date", parsed_dates)
        frames[ticker] = normalized
        medians[ticker] = median
        capture_versions[data_key] = str(source_versions[data_key])
        capture_versions[sidecar_key] = str(source_versions[sidecar_key])
        capture_paths[data_key] = data_path.as_posix()
        capture_paths[sidecar_key] = sidecar_path.as_posix()

    excluded_tickers = sorted(
        ticker for ticker, median in medians.items()
        if median < MINIMUM_MEDIAN_DOLLAR_VOLUME_USD
    )
    exclusions = pd.DataFrame([{
        "ticker": ticker,
        "median_dollar_volume_usd": medians[ticker],
        "liquidity_lookback_rows": LIQUIDITY_LOOKBACK_ROWS,
        "nominal_consumed_max_date": decision.isoformat(),
        "exclusion_reason": "MEDIAN_DOLLAR_VOLUME_BELOW_PREREGISTERED_MINIMUM",
        "minimum_median_dollar_volume_usd": MINIMUM_MEDIAN_DOLLAR_VOLUME_USD,
    } for ticker in excluded_tickers], columns=[
        "ticker", "median_dollar_volume_usd", "liquidity_lookback_rows",
        "nominal_consumed_max_date", "exclusion_reason",
        "minimum_median_dollar_volume_usd",
    ])
    passing = pre_liquidity_membership.loc[
        ~pre_liquidity_membership["ticker"].astype(str).isin(excluded_tickers)
    ]
    track_audit: dict[str, dict[str, int]] = {}
    for track in ("strict_technology", "technology_plus_adjacent"):
        scoped = passing.loc[passing["universe_track"].eq(track)]
        issuer_count = int(scoped["issuer_id"].nunique())
        if issuer_count < 1:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 post-liquidity issuer pool is empty: {track}"
            )
        track_audit[track] = {
            "eligible_security_count": int(scoped["security_id"].nunique()),
            "eligible_unique_issuer_count": issuer_count,
            "dynamic_k_minimum": 1,
            "dynamic_k_maximum": issuer_count,
        }
    evidence = {
        "schema_version": 1,
        "capture_mode": "READ_BYTES_ONCE_HASH_THEN_PARSE_AND_RECOMPUTE_MDV",
        "source_versions": dict(sorted(capture_versions.items())),
        "source_paths": dict(sorted(capture_paths.items())),
        "liquidity_lookback_rows": LIQUIDITY_LOOKBACK_ROWS,
        "minimum_median_dollar_volume_usd": MINIMUM_MEDIAN_DOLLAR_VOLUME_USD,
        "computed_excluded_tickers": excluded_tickers,
        "track_post_liquidity_cardinality": track_audit,
        "captured_sources_rechecked_before_seal": True,
    }
    return frames, exclusions, evidence


def _lifecycle_bytes(raw: bytes):
    handle = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False)
    path = Path(handle.name)
    try:
        handle.write(raw)
        handle.close()
        return load_security_lifecycle(path)
    finally:
        try:
            handle.close()
        finally:
            path.unlink(missing_ok=True)


def _artifact_csv_bytes(
    manifest_path: Path,
    artifact: Any,
    label: str,
) -> pd.DataFrame:
    if not isinstance(artifact, Mapping) or set(artifact) != {
        "filename", "rows", "sha256",
    }:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} artifact schema changed"
        )
    filename = str(artifact.get("filename") or "")
    path = (manifest_path.parent / filename).resolve()
    if not filename or Path(filename).name != filename or path.parent != manifest_path.parent:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} artifact path changed"
        )
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} artifact is missing"
        ) from exc
    if hashlib.sha256(raw).hexdigest() != artifact.get("sha256"):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} artifact hash changed"
        )
    # Empty lifecycle rule IDs are valid for exact-ticker identities. Preserve
    # their serialized spelling; turning them into NaN breaks source replay.
    frame = _csv_bytes(raw, keep_default_na=False)
    if len(frame) != int(artifact.get("rows", -1)):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 {label} artifact row count changed"
        )
    return frame


def _validate_captured_lineage(
    captured_bytes: Mapping[str, bytes],
    versions: Mapping[str, Any],
    paths: Mapping[str, Any],
) -> None:
    membership_manifest = _json_bytes(
        captured_bytes["membership_manifest_sha256"], "NPORT manifest",
    )
    taxonomy_manifest = _json_bytes(
        captured_bytes["taxonomy_manifest_sha256"], "taxonomy manifest",
    )
    membership = _csv_bytes(captured_bytes["membership_history_sha256"])
    records = _csv_bytes(captured_bytes["taxonomy_records_sha256"], keep_default_na=False)
    issues = _csv_bytes(
        captured_bytes["taxonomy_identity_issues_sha256"],
        keep_default_na=False,
    )
    crosswalk = _csv_bytes(captured_bytes["cik_crosswalk_sha256"])
    crosswalk_manifest = _json_bytes(
        captured_bytes["cik_crosswalk_manifest_sha256"], "CIK crosswalk manifest",
    )
    if (
        membership_manifest.get("content_sha256")
        != versions["membership_history_sha256"]
        or int(membership_manifest.get("row_count", -1)) != len(membership)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 captured NPORT manifest/content binding changed"
        )
    membership_inputs = [
        item for item in (taxonomy_manifest.get("input_versions") or [])
        if isinstance(item, Mapping)
        and item.get("source_name") == "ndx_point_in_time_constituents"
    ]
    if len(membership_inputs) != 1:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 taxonomy has no unique captured NPORT input"
        )
    membership_input = membership_inputs[0]
    crosswalk_inputs = [
        item for item in (taxonomy_manifest.get("input_versions") or [])
        if isinstance(item, Mapping)
        and item.get("source_name") == "ndx_sec_cik_crosswalk"
    ]
    if len(crosswalk_inputs) != 1:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 taxonomy has no unique captured CIK crosswalk input"
        )
    crosswalk_input = crosswalk_inputs[0]
    if (
        Path(str(membership_input.get("path") or "")).resolve()
        != Path(str(paths["membership_history_sha256"])).resolve()
        or membership_input.get("content_sha256")
        != versions["membership_history_sha256"]
        or membership_input.get("manifest_sha256")
        != versions["membership_manifest_sha256"]
        or int(membership_input.get("row_count", -1)) != len(membership)
        or membership_input.get("manifest_verified") is not True
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 taxonomy/NPORT captured input binding changed"
        )
    if (
        crosswalk_manifest.get("content_sha256")
        != versions["cik_crosswalk_sha256"]
        or int(crosswalk_manifest.get("row_count", -1)) != len(crosswalk)
        or crosswalk_manifest.get("dataset_type") != "ndx_sec_cik_crosswalk"
        or crosswalk_manifest.get("dataset_key") != "historical_ndx_tickers"
        or crosswalk_manifest.get("source")
        != "sec_ticker_exchange_plus_historical_cik_names"
        or crosswalk_manifest.get("source_locator")
        != "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
        or crosswalk_manifest.get("publication_time_known") is not False
        or crosswalk_manifest.get("unresolved_tickers") != []
        or int(crosswalk_manifest.get("mapped_tickers", -1)) != len(crosswalk)
        or Path(str(crosswalk_input.get("path") or "")).resolve()
        != Path(str(paths["cik_crosswalk_sha256"])).resolve()
        or crosswalk_input.get("content_sha256")
        != versions["cik_crosswalk_sha256"]
        or crosswalk_input.get("manifest_sha256")
        != versions["cik_crosswalk_manifest_sha256"]
        or int(crosswalk_input.get("row_count", -1)) != len(crosswalk)
        or crosswalk_input.get("manifest_verified") is not True
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 frozen CIK crosswalk binding changed"
        )
    artifacts = taxonomy_manifest.get("artifacts") or {}
    summary = taxonomy_manifest.get("summary") or {}
    for artifact_name, key, frame in (
        ("records", "taxonomy_records_sha256", records),
        ("identity_issues", "taxonomy_identity_issues_sha256", issues),
    ):
        artifact = artifacts.get(artifact_name) or {}
        if (
            artifact.get("filename")
            != Path(str(paths[key])).name
            or artifact.get("sha256") != versions[key]
            or int(artifact.get("rows", -1)) != len(frame)
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 taxonomy {artifact_name} binding changed"
            )
    if int(summary.get("identity_issue_count", -1)) != len(issues):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 taxonomy identity-issue count changed"
        )


def validate_captured_identity_issues_v3(
    membership_bytes: bytes,
    crosswalk_bytes: bytes,
    identity_issue_bytes: bytes,
    lifecycle,
) -> pd.DataFrame:
    """Rebuild identity issues from the frozen identity inputs."""

    membership = _csv_bytes(membership_bytes)
    crosswalk = _csv_bytes(crosswalk_bytes)
    actual = pd.read_csv(
        BytesIO(identity_issue_bytes), dtype=str, keep_default_na=False,
        low_memory=False,
    )
    try:
        expected = build_security_universe(
            membership, crosswalk, lifecycle=lifecycle,
        ).issues
    except Exception as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 identity issue rebuild failed"
        ) from exc
    if list(actual.columns) != list(expected.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 identity issue columns changed"
        )

    def rows(frame: pd.DataFrame) -> list[tuple[str, ...]]:
        normalized = frame.fillna("").astype(str)
        return sorted(
            tuple(row)
            for row in normalized.itertuples(index=False, name=None)
        )

    if rows(actual) != rows(expected):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 identity issues cannot be rebuilt from frozen inputs"
        )
    return actual


def verify_candidate_generator_v3_provenance(
    manifest_path: str | Path,
    verified_manifest: Mapping[str, Any],
    *,
    repository_root: str | Path,
) -> dict[str, Any]:
    """Verify v3 additions after the parent v2 snapshot verifier succeeds."""

    root = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    if not path.is_relative_to((root / OUTPUT_ROOT_RELATIVE).resolve()):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 snapshot path is outside the canonical research root"
        )
    manifest = dict(verified_manifest)
    decision = _canonical_date(manifest.get("decision_date"), "candidate decision_date")
    if decision < FIRST_DECISION:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 snapshot predates the prospective boundary"
        )
    versions = manifest.get("source_versions")
    paths = manifest.get("source_paths")
    if not isinstance(versions, Mapping) or not isinstance(paths, Mapping):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 snapshot lacks its source registry"
        )
    required = set(STATIC_SOURCE_PATHS) | set(REQUIRED_EXISTING_SOURCE_PATHS) | {
        "official_snapshot_sha256", "official_snapshot_manifest_sha256",
    }
    if not required.issubset(versions) or set(versions) != set(paths):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 snapshot lacks complete v3 provenance"
        )
    contract = load_candidate_generator_v3_contract(
        root / CONTRACT_RELATIVE, repository_root=root,
    )
    evidence = manifest.get("membership_evidence")
    if not isinstance(evidence, Mapping):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 membership evidence is missing"
        )
    capture = evidence.get("candidate_v3_source_capture")
    if not isinstance(capture, Mapping) or set(capture) != {
        "schema_version", "capture_mode", "source_versions", "source_paths",
        "captured_sources_rechecked_before_seal",
    }:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source capture evidence is missing"
        )
    nominal_capture = evidence.get("candidate_v3_nominal_liquidity_capture")
    nominal_versions = (
        nominal_capture.get("source_versions")
        if isinstance(nominal_capture, Mapping) else None
    )
    nominal_paths = (
        nominal_capture.get("source_paths")
        if isinstance(nominal_capture, Mapping) else None
    )
    if (
        not isinstance(nominal_versions, Mapping)
        or not isinstance(nominal_paths, Mapping)
        or not nominal_versions
        or set(nominal_versions) != set(nominal_paths)
        or any(key not in versions for key in nominal_versions)
        or any(versions[key] != nominal_versions[key] for key in nominal_versions)
        or any(paths[key] != nominal_paths[key] for key in nominal_paths)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 nominal archive source registry is missing"
        )
    expected_archive_keys = set(CAPTURE_SOURCE_KEYS) | set(nominal_versions)
    captured_bytes = verify_candidate_v3_source_archive(
        evidence.get("candidate_v3_source_archive"),
        snapshot_manifest_path=path,
        decision_date=decision.isoformat(),
        source_versions=versions,
        source_paths=paths,
        expected_source_keys=expected_archive_keys,
    )
    for key, relative in STATIC_SOURCE_PATHS.items():
        _verify_path_hash(versions, paths, key, root / relative)
    for key, relative in REQUIRED_EXISTING_SOURCE_PATHS.items():
        expected_path = (root / relative).resolve()
        if key in CAPTURE_SOURCE_KEYS:
            if (
                Path(str(paths.get(key) or "")).resolve() != expected_path
                or hashlib.sha256(captured_bytes[key]).hexdigest()
                != versions.get(key)
            ):
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v3 archived source path/hash changed: {key}"
                )
        else:
            _verify_path_hash(versions, paths, key, expected_path)
    archive = Path(str(paths["official_snapshot_sha256"])).resolve()
    archive_manifest = Path(str(paths["official_snapshot_manifest_sha256"])).resolve()
    archive_root = (root / "data/cache/candidate_pools/snapshots/nasdaq_100").resolve()
    if (
        not archive.is_relative_to(archive_root)
        or archive_manifest != Path(str(archive) + ".manifest.json").resolve()
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official archive path changed"
        )
    if (
        hashlib.sha256(captured_bytes["official_snapshot_sha256"]).hexdigest()
        != versions["official_snapshot_sha256"]
        or hashlib.sha256(
            captured_bytes["official_snapshot_manifest_sha256"]
        ).hexdigest() != versions["official_snapshot_manifest_sha256"]
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 archived official source hash changed"
        )
    _validate_captured_lineage(captured_bytes, versions, paths)
    identity_contract = contract["identity_contract"]
    if (
        versions["cik_crosswalk_sha256"]
        != identity_contract["frozen_sec_cik_crosswalk_sha256"]
        or versions["security_lifecycle_sha256"]
        != identity_contract["frozen_reviewed_lifecycle_sha256"]
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 frozen identity authority hash changed"
        )
    official, official_meta = validate_captured_official_archive_v3(
        captured_bytes["official_snapshot_sha256"],
        captured_bytes["official_snapshot_manifest_sha256"],
        archive_path=archive,
        manifest_path=archive_manifest,
    )
    if (
        capture["schema_version"] != 1
        or capture["capture_mode"] != "READ_BYTES_ONCE_HASH_THEN_PARSE"
        or capture["captured_sources_rechecked_before_seal"] is not True
        or capture["source_versions"] != {
            key: versions[key] for key in sorted(CAPTURE_SOURCE_KEYS)
        }
        or capture["source_paths"] != {
            key: paths[key] for key in sorted(CAPTURE_SOURCE_KEYS)
        }
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 captured source binding changed"
        )
    identity = evidence.get("official_runtime")
    if not isinstance(identity, Mapping) or (
        identity.get("schema_version") != 3
        or identity.get("adapter_id") != MEMBERSHIP_ADAPTER_ID
        or identity.get("identity_resolver_id") != IDENTITY_RESOLVER_ID
        or identity.get("portfolio_optimization_holding_count_policy")
        != "DYNAMIC_K_1_TO_ELIGIBLE_UNIQUE_ISSUER_COUNT"
        or identity.get("migration_control_holding_count_policy") is not None
        or identity.get("official_membership_effective_date_proved") is not False
        or identity.get("execution_valid_on_date_identity_proved") is not False
        or identity.get("admission_authority") is not False
        or identity.get("promotion_allowed") is not False
        or identity.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 membership identity audit changed"
        )
    lifecycle = _lifecycle_bytes(captured_bytes["security_lifecycle_sha256"])
    validate_captured_identity_issues_v3(
        captured_bytes["membership_history_sha256"],
        captured_bytes["cik_crosswalk_sha256"],
        captured_bytes["taxonomy_identity_issues_sha256"],
        lifecycle,
    )
    if (
        identity.get("security_lifecycle_mapping_id") != lifecycle.mapping_id
        or identity.get("security_lifecycle_last_reviewed") != lifecycle.last_reviewed
        or _canonical_date(lifecycle.last_reviewed, "security lifecycle last_reviewed")
        > decision
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 lifecycle audit is not decision-available"
        )
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 artifact registry is missing"
        )
    eligible = _artifact_csv_bytes(
        path, artifacts.get("eligible_securities"), "eligible securities",
    )
    liquidity_exclusions = _artifact_csv_bytes(
        path, artifacts.get("liquidity_exclusions"), "liquidity exclusions",
    )
    required_columns = {
        "universe_track", "selection_date", "membership_snapshot_date", "ticker",
        "security_id", "issuer_id", "taxonomy_ticker_aliases",
        "ticker_resolution_status", "ticker_lifecycle_resolved_on_date",
    }
    if not required_columns.issubset(eligible.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 eligible identities lack lifecycle provenance"
        )
    if (
        not eligible["selection_date"].astype(str).eq(decision.isoformat()).all()
        or not eligible["ticker_lifecycle_resolved_on_date"].astype(str).eq(
            decision.isoformat()
        ).all()
        or not eligible["membership_snapshot_date"].astype(str).eq(
            str(identity.get("official_observation_date") or "")
        ).all()
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 eligible identity coordinate changed"
        )
    membership = _csv_bytes(captured_bytes["membership_history_sha256"])
    nport, nport_evidence = constituents_asof(membership, decision.isoformat())
    if evidence.get("nport") != nport_evidence:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 NPORT as-of evidence cannot be rebuilt"
        )
    taxonomy = _csv_bytes(captured_bytes["taxonomy_records_sha256"], keep_default_na=False)
    issues = _csv_bytes(
        captured_bytes["taxonomy_identity_issues_sha256"], keep_default_na=False,
    )
    if not {"security_id", "issuer_id", "ticker"}.issubset(issues.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 captured identity issue schema changed"
        )
    try:
        search_plan = yaml.safe_load(
            captured_bytes["search_plan_sha256"].decode("utf-8")
        )
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 captured search plan is unreadable"
        ) from exc
    if not isinstance(search_plan, Mapping):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 captured search plan is not an object"
        )
    official_fetched = str(evidence.get("official_fetched_at_utc") or "")
    try:
        if pd.Timestamp(official_fetched).tzinfo is None or pd.Timestamp(
            official_meta.get("fetched_at")
        ).tzinfo is None or pd.Timestamp(official_fetched).tz_convert("UTC") != pd.Timestamp(
            official_meta.get("fetched_at")
        ).tz_convert("UTC"):
            raise ValueError("official fetch timestamp mismatch")
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 official fetch timestamp binding changed"
        ) from exc
    rebuilt_membership, rebuilt_audit = build_runtime_official_eligible_membership_v3(
        official,
        nport,
        taxonomy,
        search_plan,
        lifecycle,
        decision_date=decision.isoformat(),
        observed_at_utc=official_fetched,
        decision_close_timestamp_utc=str(manifest.get("decision_close_timestamp_utc") or ""),
        seal_timestamp_utc=str(manifest.get("seal_timestamp_utc") or ""),
        conservative_seal_deadline_utc=str(
            manifest.get("conservative_seal_deadline_utc") or ""
        ),
        allow_degraded_reviewed_taxonomy_subset=True,
        excluded_identity_security_ids=set(issues["security_id"].astype(str)) - {""},
        excluded_identity_issuer_ids=set(issues["issuer_id"].astype(str)) - {""},
        excluded_identity_tickers=set(issues["ticker"].astype(str).str.upper()) - {""},
    )
    if rebuilt_audit != identity:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 membership audit cannot be rebuilt from captured sources"
        )
    _nominal_frames, expected_exclusions, expected_liquidity_evidence = (
        capture_nominal_liquidity_inputs_v3(
            rebuilt_membership,
            versions,
            paths,
            decision_date=decision.isoformat(),
            snapshot_directory=path.parent,
            captured_source_bytes=captured_bytes,
        )
    )
    if evidence.get("candidate_v3_nominal_liquidity_capture") != (
        expected_liquidity_evidence
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 nominal liquidity capture cannot be rebuilt"
        )
    if list(liquidity_exclusions.columns) != list(expected_exclusions.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 liquidity exclusion schema changed"
        )
    try:
        pd.testing.assert_frame_equal(
            liquidity_exclusions.sort_values("ticker").reset_index(drop=True),
            expected_exclusions.sort_values("ticker").reset_index(drop=True),
            check_dtype=False,
            check_exact=True,
        )
    except AssertionError as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 liquidity exclusions cannot be recomputed"
        ) from exc
    identity_columns = [
        "universe_track", "ticker", "security_id", "issuer_id", "risk_chain",
        "taxonomy_ticker_aliases", "ticker_resolution_status",
        "ticker_lifecycle_rule_id", "ticker_lifecycle_resolved_on_date",
        "membership_snapshot_date",
    ]
    if not set(identity_columns).issubset(eligible.columns) or not set(
        identity_columns
    ).issubset(rebuilt_membership.columns):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 rebuilt identity columns are incomplete"
        )
    rebuilt_rows = sorted(
        tuple(str(value) for value in row)
        for row in rebuilt_membership[identity_columns].itertuples(index=False, name=None)
    )
    eligible_rows = sorted(
        tuple(str(value) for value in row)
        for row in eligible[identity_columns].itertuples(index=False, name=None)
    )
    if "ticker" not in liquidity_exclusions.columns:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 liquidity exclusion ticker evidence is missing"
        )
    exclusion_tickers = expected_exclusions["ticker"].astype(str)
    if exclusion_tickers.duplicated().any():
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 liquidity exclusion identity is duplicated"
        )
    excluded_tickers = set(exclusion_tickers)
    rebuilt_tickers = set(rebuilt_membership["ticker"].astype(str))
    if (
        not excluded_tickers.issubset(rebuilt_tickers)
        or excluded_tickers & set(eligible["ticker"].astype(str))
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 liquidity exclusion identity changed"
        )
    expected_rows = sorted(
        tuple(str(value) for value in row)
        for row in rebuilt_membership.loc[
            ~rebuilt_membership["ticker"].astype(str).isin(excluded_tickers),
            identity_columns,
        ].itertuples(index=False, name=None)
    )
    if not eligible_rows or eligible_rows != expected_rows:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 eligible identities cannot be rebuilt from captured sources"
        )
    track_audit = identity.get("track_dynamic_cardinality")
    if not isinstance(track_audit, Mapping) or set(track_audit) != {
        "strict_technology", "technology_plus_adjacent",
    }:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 track cardinality audit is missing"
        )
    for track, item in track_audit.items():
        scoped = eligible.loc[eligible["universe_track"].eq(track)]
        post_item = expected_liquidity_evidence[
            "track_post_liquidity_cardinality"
        ][track]
        if not isinstance(item, Mapping) or (
            int(item.get("eligible_security_count", -1))
            < int(scoped["security_id"].nunique())
            or int(item.get("eligible_unique_issuer_count", -1))
            < int(scoped["issuer_id"].nunique())
            or int(item.get("dynamic_k_minimum", -1)) != 1
            or int(item.get("dynamic_k_maximum", -1))
            != int(item.get("eligible_unique_issuer_count", -2))
            or item.get("dynamic_k_upper_bound_basis")
            != "ELIGIBLE_UNIQUE_ISSUER_COUNT"
            or post_item != {
                "eligible_security_count": int(scoped["security_id"].nunique()),
                "eligible_unique_issuer_count": int(scoped["issuer_id"].nunique()),
                "dynamic_k_minimum": 1,
                "dynamic_k_maximum": int(scoped["issuer_id"].nunique()),
            }
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 dynamic issuer cardinality changed: {track}"
            )
    return manifest


__all__ = [
    "CAPTURE_SOURCE_KEYS",
    "CONTRACT_RELATIVE",
    "FIRST_DECISION",
    "NdxDynamicShadowCandidateGeneratorV3Error",
    "OUTPUT_ROOT_RELATIVE",
    "SOURCE_ARCHIVE_DIRECTORY",
    "SOURCE_ARCHIVE_MANIFEST",
    "STATIC_SOURCE_PATHS",
    "assess_candidate_v3_source_archive_readiness",
    "build_candidate_v3_source_archive_payload",
    "capture_nominal_liquidity_inputs_v3",
    "load_candidate_generator_v3_contract",
    "static_source_registry",
    "validate_captured_identity_issues_v3",
    "validate_captured_official_archive_v3",
    "verify_candidate_v3_source_archive",
    "verify_candidate_generator_v3_provenance",
]
