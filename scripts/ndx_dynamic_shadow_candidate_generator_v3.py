"""Prospective candidate generator v3 with reviewed decision-date identities.

This is a thin, versioned research wrapper.  Candidate-v2 continues to own the
reviewed calendar prefix and candidate-v1 continues to own source refresh,
economic panels, immutable snapshot writing, and the append-only decision seal.
Only membership identity normalization and its provenance are added here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Iterator, Mapping

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ndx_dynamic_shadow_candidate_generator as v1  # noqa: E402
import scripts.ndx_dynamic_shadow_candidate_generator_v2 as v2  # noqa: E402
from backtest.ndx_dynamic_shadow_candidate_generator_v3 import (  # noqa: E402
    CAPTURE_SOURCE_KEYS,
    CONTRACT_RELATIVE,
    FIRST_DECISION,
    NdxDynamicShadowCandidateGeneratorV3Error,
    SOURCE_ARCHIVE_DIRECTORY,
    SOURCE_ARCHIVE_MANIFEST,
    assess_candidate_v3_source_archive_readiness,
    build_candidate_v3_source_archive_payload,
    capture_nominal_liquidity_inputs_v3,
    load_candidate_generator_v3_contract,
    static_source_registry,
    validate_captured_official_archive_v3,
    validate_captured_identity_issues_v3,
    verify_candidate_v3_source_archive,
    verify_candidate_generator_v3_provenance,
)
from backtest.ndx_dynamic_shadow_candidate_membership_v3 import (  # noqa: E402
    build_runtime_official_eligible_membership_v3,
)
from backtest.ndx_dynamic_shadow_candidate_snapshot import (  # noqa: E402
    NdxDynamicShadowCandidateSnapshotError,
)
from data.ndx_security_identity import load_security_lifecycle  # noqa: E402


CONTRACT_PATH = (ROOT / CONTRACT_RELATIVE).resolve()
WRAPPER_PATH = Path(__file__).resolve()
LOCK_PATH = v1.DEFAULT_ROOT / ".candidate_generator_v3.lock"


def _decision_date(value: Any) -> date:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 decision_date is invalid"
        ) from exc
    if text != parsed.isoformat():
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 decision_date is not canonical YYYY-MM-DD"
        )
    return parsed


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _capture(path: Path) -> dict[str, Any]:
    target = path.resolve()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 source cannot be captured: {target}"
        ) from exc
    return {"path": target, "raw": raw, "sha256": _sha256(raw)}


def _json_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 captured {label} is invalid"
        ) from exc
    if not isinstance(value, dict):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 captured {label} is not an object"
        )
    return value


def _yaml_bytes(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 captured {label} is invalid"
        ) from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            f"candidate-v3 captured {label} is not an object"
        )
    return dict(value)


def _csv_bytes(raw: bytes, *, keep_default_na: bool = True) -> pd.DataFrame:
    return pd.read_csv(
        BytesIO(raw), keep_default_na=keep_default_na, low_memory=False,
        dtype={"cusip": str, "cusips": str, "cik": str},
    )


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


def _capture_decision_sources(
    args: argparse.Namespace,
    official_archive: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    paths = {
        "official_snapshot_sha256": Path(official_archive["archive_path"]),
        "official_snapshot_manifest_sha256": Path(official_archive["manifest_path"]),
        "membership_history_sha256": v1._resolve(args.membership_history),
        "membership_manifest_sha256": v1._resolve(args.membership_manifest),
        "taxonomy_manifest_sha256": v1._resolve(args.taxonomy_manifest),
        "taxonomy_records_sha256": v1._resolve(args.taxonomy_records),
        "taxonomy_identity_issues_sha256": (
            v1._resolve(args.taxonomy_manifest).parent / "identity_issues.csv"
        ),
        "search_plan_sha256": v1._resolve(args.search_plan),
        "security_lifecycle_sha256": v1._resolve(args.security_lifecycle),
        "cik_crosswalk_sha256": (
            ROOT / "data/cache/candidate_pools/ndx_fundamentals/cik_crosswalk.csv"
        ),
        "cik_crosswalk_manifest_sha256": (
            ROOT / "data/cache/candidate_pools/ndx_fundamentals/"
            "cik_crosswalk.csv.manifest.json"
        ),
    }
    return {key: _capture(path) for key, path in paths.items()}


def _validate_captured_source_relationships(
    captures: Mapping[str, Mapping[str, Any]],
) -> None:
    membership_manifest = _json_bytes(
        captures["membership_manifest_sha256"]["raw"], "membership manifest",
    )
    taxonomy_manifest = _json_bytes(
        captures["taxonomy_manifest_sha256"]["raw"], "taxonomy manifest",
    )
    validate_captured_official_archive_v3(
        captures["official_snapshot_sha256"]["raw"],
        captures["official_snapshot_manifest_sha256"]["raw"],
        archive_path=captures["official_snapshot_sha256"]["path"],
        manifest_path=captures["official_snapshot_manifest_sha256"]["path"],
    )
    membership_hash = captures["membership_history_sha256"]["sha256"]
    records_hash = captures["taxonomy_records_sha256"]["sha256"]
    issues_hash = captures["taxonomy_identity_issues_sha256"]["sha256"]
    membership = _csv_bytes(captures["membership_history_sha256"]["raw"])
    taxonomy_records = _csv_bytes(captures["taxonomy_records_sha256"]["raw"], keep_default_na=False)
    identity_issues = _csv_bytes(
        captures["taxonomy_identity_issues_sha256"]["raw"],
        keep_default_na=False,
    )
    if (
        membership_manifest.get("content_sha256") != membership_hash
        or int(membership_manifest.get("row_count", -1)) != len(membership)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "captured NPORT manifest does not bind captured membership bytes"
        )
    taxonomy_inputs = [
        item for item in (taxonomy_manifest.get("input_versions") or [])
        if isinstance(item, Mapping)
        and item.get("source_name") == "ndx_point_in_time_constituents"
    ]
    if len(taxonomy_inputs) != 1:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "captured taxonomy has no unique NPORT input"
        )
    taxonomy_input = taxonomy_inputs[0]
    artifacts = taxonomy_manifest.get("artifacts") or {}
    records = artifacts.get("records") or {}
    issues = artifacts.get("identity_issues") or {}
    if (
        Path(str(taxonomy_input.get("path") or "")).resolve()
        != Path(captures["membership_history_sha256"]["path"]).resolve()
        or taxonomy_input.get("content_sha256") != membership_hash
        or taxonomy_input.get("manifest_sha256")
        != captures["membership_manifest_sha256"]["sha256"]
        or int(taxonomy_input.get("row_count", -1)) != len(membership)
        or taxonomy_input.get("manifest_verified") is not True
        or records.get("filename")
        != Path(captures["taxonomy_records_sha256"]["path"]).name
        or records.get("sha256") != records_hash
        or int(records.get("rows", -1)) != len(taxonomy_records)
        or issues.get("filename")
        != Path(captures["taxonomy_identity_issues_sha256"]["path"]).name
        or issues.get("sha256") != issues_hash
        or int(issues.get("rows", -1)) != len(identity_issues)
        or int((taxonomy_manifest.get("summary") or {}).get(
            "identity_issue_count", -1
        )) != len(identity_issues)
    ):
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "captured taxonomy does not bind captured NPORT/records/issues bytes"
        )


def _assert_captures_unchanged(
    captures: Mapping[str, Mapping[str, Any]],
) -> None:
    for key, item in captures.items():
        path = Path(item["path"])
        if not path.is_file() or _sha256(path.read_bytes()) != item["sha256"]:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                f"candidate-v3 captured source changed during seal: {key}"
            )


def _capture_registry(
    captures: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    return (
        {key: str(captures[key]["sha256"]) for key in sorted(captures)},
        {key: Path(captures[key]["path"]).resolve().as_posix() for key in sorted(captures)},
    )


def _archive_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes_fsync(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def write_candidate_v3_source_archive(
    snapshot_directory: str | Path,
    *,
    decision_date: str,
    source_captures: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Atomically publish captured bytes below the immutable decision directory."""

    output = Path(snapshot_directory).resolve()
    expected_output = (v1.DEFAULT_ROOT / decision_date).resolve()
    if output != expected_output:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 source archive output is non-canonical"
        )
    output.mkdir(parents=True, exist_ok=True)
    manifest, source_files = build_candidate_v3_source_archive_payload(
        decision_date, source_captures,
    )
    manifest_raw = _archive_json_bytes(manifest)
    final_root = (output / SOURCE_ARCHIVE_DIRECTORY).resolve()
    final_manifest = final_root / SOURCE_ARCHIVE_MANIFEST
    descriptor = {
        "path": final_manifest.as_posix(),
        "sha256": _sha256(manifest_raw),
        "source_key_count": len(source_files),
        "verification_mode": "PARSE_IMMUTABLE_ARCHIVE_BYTES_IN_MEMORY",
        "canonical_source_restore_required": False,
        "canonical_source_writeback_allowed": False,
    }
    source_versions = {
        key: str(source_captures[key]["sha256"])
        for key in sorted(source_captures)
    }
    source_paths = {
        key: Path(source_captures[key]["path"]).resolve().as_posix()
        for key in sorted(source_captures)
    }
    if not final_root.exists():
        stage = Path(tempfile.mkdtemp(
            prefix=".v3_source_archive_stage_", dir=output,
        )).resolve()
        try:
            for filename, raw in sorted(source_files.items()):
                _write_bytes_fsync(stage / filename, raw)
            _write_bytes_fsync(stage / SOURCE_ARCHIVE_MANIFEST, manifest_raw)
            try:
                stage.rename(final_root)
            except FileExistsError:
                # A concurrent writer may only win with exactly the same bytes.
                pass
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    verify_candidate_v3_source_archive(
        descriptor,
        snapshot_manifest_path=output / "manifest.json",
        decision_date=decision_date,
        source_versions=source_versions,
        source_paths=source_paths,
        expected_source_keys=set(source_versions),
    )
    return descriptor


@contextmanager
def _patched_v1_membership_v3(args: argparse.Namespace) -> Iterator[None]:
    """Temporarily insert v3 identity normalization into the frozen v1 call."""

    old_archive_loader = v1._immutable_official_archive
    old_membership_builder = v1.build_runtime_official_eligible_membership
    old_source_loader = v1._load_taxonomy_memberships
    old_snapshot_builder = v1.build_fresh_candidate_input_snapshot
    old_snapshot_writer = v1.write_snapshot_bundle
    old_append = v1._append_decision_seal
    static_versions, static_paths = static_source_registry(repository_root=ROOT)
    contract = load_candidate_generator_v3_contract(
        ROOT / CONTRACT_RELATIVE, repository_root=ROOT,
    )
    state: dict[str, Any] = {}

    def captured_archive(meta):
        archive_path, manifest_path = old_archive_loader(meta)
        state["official_archive"] = {
            "archive_path": archive_path.resolve(),
            "manifest_path": manifest_path.resolve(),
        }
        return archive_path, manifest_path

    def membership_builder(
        _official, _nport, _taxonomy, _search_plan, **kwargs,
    ):
        if "captures" in state or "official_archive" not in state:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 membership capture order changed"
            )
        captures = _capture_decision_sources(args, state["official_archive"])
        _validate_captured_source_relationships(captures)
        official = _csv_bytes(captures["official_snapshot_sha256"]["raw"])
        membership = _csv_bytes(captures["membership_history_sha256"]["raw"])
        nport, nport_evidence = v1.constituents_asof(
            membership, args.decision_date,
        )
        taxonomy = _csv_bytes(captures["taxonomy_records_sha256"]["raw"], keep_default_na=False)
        issues = _csv_bytes(
            captures["taxonomy_identity_issues_sha256"]["raw"],
            keep_default_na=False,
        )
        required_issue_fields = {"security_id", "issuer_id", "ticker"}
        if not required_issue_fields.issubset(issues.columns):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "captured identity issue fields are incomplete"
            )
        search_plan = _yaml_bytes(
            captures["search_plan_sha256"]["raw"], "search plan",
        )
        lifecycle = _lifecycle_bytes(captures["security_lifecycle_sha256"]["raw"])
        identity_contract = contract["identity_contract"]
        if (
            captures["cik_crosswalk_sha256"]["sha256"]
            != identity_contract["frozen_sec_cik_crosswalk_sha256"]
            or captures["security_lifecycle_sha256"]["sha256"]
            != identity_contract["frozen_reviewed_lifecycle_sha256"]
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 frozen identity authority hash changed"
            )
        validate_captured_identity_issues_v3(
            captures["membership_history_sha256"]["raw"],
            captures["cik_crosswalk_sha256"]["raw"],
            captures["taxonomy_identity_issues_sha256"]["raw"],
            lifecycle,
        )
        state["captures"] = captures
        state["nport_evidence"] = dict(nport_evidence)
        return build_runtime_official_eligible_membership_v3(
            official,
            nport,
            taxonomy,
            search_plan,
            lifecycle,
            decision_date=str(kwargs["decision_date"]),
            observed_at_utc=str(kwargs["observed_at_utc"]),
            decision_close_timestamp_utc=str(kwargs["decision_close_timestamp_utc"]),
            seal_timestamp_utc=str(kwargs["seal_timestamp_utc"]),
            conservative_seal_deadline_utc=str(
                kwargs["conservative_seal_deadline_utc"]
            ),
            allow_degraded_reviewed_taxonomy_subset=bool(
                kwargs["allow_degraded_reviewed_taxonomy_subset"]
            ),
            excluded_identity_security_ids=(
                set(issues["security_id"].astype(str)) - {""}
            ),
            excluded_identity_issuer_ids=(
                set(issues["issuer_id"].astype(str)) - {""}
            ),
            excluded_identity_tickers=(
                set(issues["ticker"].astype(str).str.upper()) - {""}
            ),
        )

    def source_loader(*loader_args, **loader_kwargs):
        eligible, versions, paths, evidence = old_source_loader(
            *loader_args, **loader_kwargs,
        )
        captures = state.get("captures")
        if not isinstance(captures, Mapping):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 decision sources were not captured"
            )
        _assert_captures_unchanged(captures)
        capture_versions, capture_paths = _capture_registry(captures)
        for key in CAPTURE_SOURCE_KEYS:
            if key not in versions:
                if key not in {
                    "cik_crosswalk_sha256", "cik_crosswalk_manifest_sha256",
                }:
                    raise NdxDynamicShadowCandidateGeneratorV3Error(
                        f"candidate-v1 source registry omitted consumed v3 bytes: {key}"
                    )
                versions[key] = capture_versions[key]
                paths[key] = capture_paths[key]
            if versions.get(key) != capture_versions[key]:
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v1 source hash differs from consumed v3 bytes: {key}"
                )
            if Path(str(paths.get(key) or "")).resolve() != Path(
                capture_paths[key]
            ).resolve():
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v1 source path differs from consumed v3 bytes: {key}"
                )
        versions.update(static_versions)
        paths.update(static_paths)
        evidence = dict(evidence)
        if not isinstance(state.get("nport_evidence"), Mapping):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 captured NPORT evidence is absent"
            )
        evidence["nport"] = dict(state["nport_evidence"])
        evidence["candidate_v3_source_capture"] = {
            "schema_version": 1,
            "capture_mode": "READ_BYTES_ONCE_HASH_THEN_PARSE",
            "source_versions": capture_versions,
            "source_paths": capture_paths,
            "captured_sources_rechecked_before_seal": True,
        }
        state["membership_evidence"] = evidence
        return eligible, versions, paths, evidence

    def snapshot_builder(
        eligible_membership, adjusted_price_frames, nominal_price_frames,
        target_nav, **kwargs,
    ):
        versions = kwargs.get("source_versions")
        paths = kwargs.get("source_paths")
        if not isinstance(versions, Mapping) or not isinstance(paths, Mapping):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 nominal source registry is missing"
            )
        captured_frames, _computed_exclusions, liquidity_evidence = (
            capture_nominal_liquidity_inputs_v3(
                eligible_membership,
                versions,
                paths,
                decision_date=str(kwargs["decision_date"]),
                snapshot_directory=v1.DEFAULT_ROOT / str(kwargs["decision_date"]),
            )
        )
        combined_nominal = dict(nominal_price_frames)
        combined_nominal.update(captured_frames)
        membership_evidence = state.get("membership_evidence")
        if not isinstance(membership_evidence, dict):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 membership evidence is unavailable at liquidity capture"
            )
        membership_evidence["candidate_v3_nominal_liquidity_capture"] = (
            liquidity_evidence
        )
        state["nominal_capture_versions"] = dict(
            liquidity_evidence["source_versions"]
        )
        state["nominal_capture_paths"] = dict(liquidity_evidence["source_paths"])
        return old_snapshot_builder(
            eligible_membership,
            adjusted_price_frames,
            combined_nominal,
            target_nav,
            **kwargs,
        )

    def snapshot_writer(output_directory, snapshot):
        captures = state.get("captures")
        versions = snapshot.get("source_versions")
        paths = snapshot.get("source_paths")
        if (
            not isinstance(captures, Mapping)
            or not isinstance(versions, Mapping)
            or not isinstance(paths, Mapping)
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 source archive inputs are missing"
            )
        _assert_captures_unchanged(captures)
        archive_captures = dict(captures)
        nominal_versions = state.get("nominal_capture_versions")
        nominal_paths = state.get("nominal_capture_paths")
        if not isinstance(nominal_versions, Mapping) or not isinstance(
            nominal_paths, Mapping
        ) or set(nominal_versions) != set(nominal_paths):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 nominal source archive inputs are missing"
            )
        for key in sorted(nominal_versions):
            source = Path(str(nominal_paths[key])).resolve()
            item = _capture(source)
            if item["sha256"] != nominal_versions[key]:
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v3 captured nominal source changed before archive: {key}"
                )
            archive_captures[key] = item
        descriptor = write_candidate_v3_source_archive(
            output_directory,
            decision_date=str(snapshot.get("decision_date") or ""),
            source_captures=archive_captures,
        )
        evidence = snapshot.get("membership_evidence")
        if not isinstance(evidence, dict):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 membership evidence is unavailable at archive write"
            )
        evidence["candidate_v3_source_archive"] = descriptor
        state["source_archive_descriptor"] = descriptor
        return old_snapshot_writer(output_directory, snapshot)

    def guarded_append(ledger_path, manifest_path, manifest, **kwargs):
        captures = state.get("captures")
        if not isinstance(captures, Mapping):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 source capture is absent before seal append"
            )
        _assert_captures_unchanged(captures)
        for key, expected_hash in (
            state.get("nominal_capture_versions") or {}
        ).items():
            source = Path(state["nominal_capture_paths"][key])
            if not source.is_file() or _sha256(source.read_bytes()) != expected_hash:
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    f"candidate-v3 captured nominal source changed during seal: {key}"
                )
        current_static_versions, _ = static_source_registry(repository_root=ROOT)
        if current_static_versions != static_versions:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 static source changed during seal"
            )
        if (
            not isinstance(state.get("source_archive_descriptor"), Mapping)
            or (manifest.get("membership_evidence") or {}).get(
                "candidate_v3_source_archive"
            ) != state["source_archive_descriptor"]
        ):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 source archive was not sealed into the snapshot"
            )
        verify_candidate_generator_v3_provenance(
            manifest_path, manifest, repository_root=ROOT,
        )
        return old_append(ledger_path, manifest_path, manifest, **kwargs)

    v1._immutable_official_archive = captured_archive
    v1.build_runtime_official_eligible_membership = membership_builder
    v1._load_taxonomy_memberships = source_loader
    v1.build_fresh_candidate_input_snapshot = snapshot_builder
    v1.write_snapshot_bundle = snapshot_writer
    v1._append_decision_seal = guarded_append
    try:
        yield
    finally:
        v1._immutable_official_archive = old_archive_loader
        v1.build_runtime_official_eligible_membership = old_membership_builder
        v1._load_taxonomy_memberships = old_source_loader
        v1.build_fresh_candidate_input_snapshot = old_snapshot_builder
        v1.write_snapshot_bundle = old_snapshot_writer
        v1._append_decision_seal = old_append


@contextmanager
def single_instance_lock(path: Path = LOCK_PATH) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if handle.read(1) == b"":
                    handle.seek(0)
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 generator is already running"
            ) from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def seal(args: argparse.Namespace) -> dict[str, Any]:
    if _decision_date(args.decision_date) < FIRST_DECISION:
        raise NdxDynamicShadowCandidateGeneratorV3Error(
            "candidate-v3 retrospective seal/backfill is forbidden"
        )
    load_candidate_generator_v3_contract(CONTRACT_PATH, repository_root=ROOT)
    with _patched_v1_membership_v3(args):
        manifest = v2.seal(args)
    manifest_path = v1.DEFAULT_ROOT / str(args.decision_date) / "manifest.json"
    return verify(manifest_path, manifest=manifest)


def verify(
    manifest_path: str | Path,
    *,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    verified = dict(manifest or v2.verify(path))
    if manifest is not None:
        # A freshly sealed manifest has already passed the v2 pre-append guard;
        # its ledger record is verified by v2.seal before returning.
        verified = v2.verify(path)
    return verify_candidate_generator_v3_provenance(
        path, verified, repository_root=ROOT,
    )


def readiness(args: argparse.Namespace) -> dict[str, Any]:
    result = dict(v2.readiness(args))
    blockers = list(result.get("blockers") or [])
    try:
        load_candidate_generator_v3_contract(CONTRACT_PATH, repository_root=ROOT)
        versions, _ = static_source_registry(repository_root=ROOT)
        decision = _decision_date(args.decision_date)
        if decision < FIRST_DECISION:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 decision precedes prospective start"
            )
        lifecycle = load_security_lifecycle(v1._resolve(args.security_lifecycle))
        if pd.Timestamp(lifecycle.last_reviewed).date() > decision:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "candidate-v3 lifecycle review is later than decision"
            )
    except Exception as exc:
        blockers.append({
            "code": "CANDIDATE_IDENTITY_V3_NOT_READY",
            "reason": f"{type(exc).__name__}: {exc}",
        })
        versions = {}
    result.update({
        "manifest_type": "ndx_dynamic_shadow_candidate_generator_v3_readiness",
        "candidate_identity_lineage": "REVIEWED_DECISION_DATE_IDENTITY_V3",
        "candidate_generator_v3_contract": CONTRACT_PATH.as_posix(),
        "candidate_generator_v3_source_hashes": versions,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "historical_candidate_replay_used": False,
        "official_membership_effective_date_proved": False,
        "execution_valid_on_date_identity_proved": False,
        "blockers": blockers,
        "status": "BLOCKED" if blockers else "READY_TO_ATTEMPT_PROSPECTIVE_SEAL",
        "promotion_allowed": False,
        "live_mutation": False,
    })
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prospective candidate-v3 identity-normalized snapshot generator"
    )
    parser.add_argument("--contract", default="config/ndx_dynamic_shadow_candidate_generator_v1.yaml")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--decision-date", default="2026-10-01")
    parser.add_argument("--execution-date", default="")
    parser.add_argument("--as-of-timestamp-utc", default="")
    parser.add_argument("--session-calendar-manifest", default=str(v2.CALENDAR_V2))
    parser.add_argument("--membership-history", default="data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv")
    parser.add_argument("--membership-manifest", default="data/cache/candidate_pools/ndx_history/qqq_nport_constituents.csv.manifest.json")
    parser.add_argument("--taxonomy-manifest", default="data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json")
    parser.add_argument("--taxonomy-records", default="data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv")
    parser.add_argument("--search-plan", default="config/ndx_cardinality_search_v1_plan.yaml")
    parser.add_argument("--security-lifecycle", default="config/ndx_security_lifecycle.yaml")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--target-manifest", default="data/cache/funds/012922.csv.manifest.json")
    parser.add_argument("--original-8-manifest", default="data/cache/research/ndx_original_8_control_v1/manifest.json")
    parser.add_argument("--output-root", default=str(v1.DEFAULT_ROOT))
    parser.add_argument("--refresh-official", action="store_true")
    parser.add_argument("--refresh-membership", action="store_true")
    parser.add_argument("--rebuild-taxonomy", action="store_true")
    parser.add_argument("--refresh-prices", action="store_true")
    parser.add_argument("--refresh-nominal-prices", action="store_true")
    parser.add_argument("--refresh-target", action="store_true")
    parser.add_argument("--allow-degraded-reviewed-taxonomy-subset", action="store_true")
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--verify", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    protected_before = v1._protected_hashes()
    try:
        if args.dry_run and (args.seal or args.verify):
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "--dry-run is readiness-only"
            )
        if args.dry_run:
            if v1._resolve(args.output_root) != v1.DEFAULT_ROOT.resolve():
                raise NdxDynamicShadowCandidateGeneratorV3Error(
                    "candidate-v3 readiness output root must be canonical"
                )
            result = readiness(args)
        else:
            with single_instance_lock():
                if args.verify:
                    result = verify(v1._resolve(args.verify))
                elif args.seal:
                    result = seal(args)
                else:
                    if v1._resolve(args.output_root) != v1.DEFAULT_ROOT.resolve():
                        raise NdxDynamicShadowCandidateGeneratorV3Error(
                            "candidate-v3 readiness output root must be canonical"
                        )
                    result = readiness(args)
                    v1._atomic_json(v1.DEFAULT_ROOT / "readiness_v3.json", result)
        if v1._protected_hashes() != protected_before:
            raise NdxDynamicShadowCandidateGeneratorV3Error(
                "protected live files changed"
            )
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_candidate_generator_v3_failure",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "historical_candidate_replay_used": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        if not args.dry_run:
            v1._atomic_json(v1.DEFAULT_ROOT / "last_failure_v3.json", failure)
        print(
            f"dynamic shadow candidate generator v3 fail-closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        "dynamic shadow candidate generator v3 | "
        f"status={result['status']} | decision={result.get('decision_date')} | "
        "promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
