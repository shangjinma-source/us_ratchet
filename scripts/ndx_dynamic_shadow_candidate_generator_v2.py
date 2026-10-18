"""Prospective candidate seal adapter for the reviewed calendar-v2 lineage.

The economic snapshot, dynamic-k plan, immutable output namespace and seal
ledger remain the v1 implementation.  This adapter replaces only the calendar
input with a verified append-only v2 prefix whose proof survives later normal
calendar appends.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ndx_dynamic_shadow_candidate_generator as v1  # noqa: E402
from backtest.ndx_dynamic_shadow_candidate_calendar_v2 import (  # noqa: E402
    ADAPTER_RELATIVE,
    CALENDAR_RELATIVE,
    CALENDAR_SCRIPT_RELATIVE,
    ENGINE_RELATIVE,
    candidate_calendar_evidence_path,
    capture_candidate_calendar_evidence_v2,
    verify_candidate_calendar_evidence_v2,
)
from backtest.ndx_dynamic_shadow_candidate_snapshot import (  # noqa: E402
    NdxDynamicShadowCandidateSnapshotError,
    verify_snapshot_bundle,
)
from data.versioning import file_sha256  # noqa: E402


CALENDAR_V2 = (ROOT / CALENDAR_RELATIVE).resolve()
WRAPPER_PATH = Path(__file__).resolve()
REQUIRED_V2_SOURCE_KEYS = {
    "session_calendar_manifest_sha256",
    "session_calendar_projection_sha256",
    "session_calendar_ledger_sha256",
    "session_calendar_verifier_sha256",
    "session_calendar_engine_sha256",
    "session_calendar_v2_prefix_evidence_sha256",
    "candidate_calendar_v2_adapter_sha256",
    "generator_script_sha256",
}


def _absolute(value: Any) -> Path:
    return Path(str(value or "")).resolve()


def _load_evidence(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate calendar-v2 prefix evidence is unreadable"
        ) from exc
    if not isinstance(value, dict):
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate calendar-v2 prefix evidence is not an object"
        )
    return value


def _require_v2_snapshot_provenance(
    manifest_path: str | Path, manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild v2 prefix proof and bind every compatibility registry entry."""

    path = Path(manifest_path).resolve()
    verified = dict(manifest or verify_snapshot_bundle(path))
    decision_date = str(verified.get("decision_date") or "")
    expected_evidence = candidate_calendar_evidence_path(
        decision_date, repository_root=ROOT,
    ).resolve()
    versions = verified.get("source_versions")
    source_paths = verified.get("source_paths")
    if not isinstance(versions, Mapping) or not isinstance(source_paths, Mapping):
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate snapshot lacks its source registry"
        )
    if not REQUIRED_V2_SOURCE_KEYS.issubset(versions) or set(versions) != set(source_paths):
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate snapshot lacks complete calendar-v2 provenance"
        )
    if _absolute(source_paths["session_calendar_v2_prefix_evidence_sha256"]) != expected_evidence:
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate snapshot points to a non-canonical calendar-v2 prefix"
        )
    if (
        not expected_evidence.is_file()
        or versions["session_calendar_v2_prefix_evidence_sha256"]
        != file_sha256(expected_evidence)
    ):
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate calendar-v2 prefix evidence hash changed"
        )
    sessions = verify_candidate_calendar_evidence_v2(
        expected_evidence, repository_root=ROOT,
    )
    if sessions.empty or str(sessions.iloc[-1]["session_date"]) != decision_date:
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate calendar-v2 decision coordinate changed"
        )
    evidence = _load_evidence(expected_evidence)
    event_prefix = evidence["event_ledger_prefix"]
    projection = evidence["session_projection_prefix"]
    source_code = evidence["source_code"]
    expected_values = {
        "session_calendar_manifest_sha256": evidence["calendar_manifest"]["sha256_at_capture"],
        "session_calendar_projection_sha256": projection["sha256"],
        "session_calendar_ledger_sha256": event_prefix["prefix_bytes_sha256"],
        "session_calendar_verifier_sha256": source_code["calendar_script"]["sha256_at_capture"],
        "session_calendar_engine_sha256": source_code["calendar_engine"]["sha256_at_capture"],
        "candidate_calendar_v2_adapter_sha256": source_code["candidate_calendar_adapter"]["sha256_at_capture"],
        "generator_script_sha256": file_sha256(WRAPPER_PATH),
    }
    expected_paths = {
        "session_calendar_manifest_sha256": CALENDAR_V2,
        "session_calendar_projection_sha256": expected_evidence.parent / "decision_sessions_prefix.csv",
        "session_calendar_ledger_sha256": ROOT / "data/cache/research/ndx_observed_us_session_calendar_v2/events.jsonl",
        "session_calendar_verifier_sha256": ROOT / CALENDAR_SCRIPT_RELATIVE,
        "session_calendar_engine_sha256": ROOT / ENGINE_RELATIVE,
        "session_calendar_v2_prefix_evidence_sha256": expected_evidence,
        "candidate_calendar_v2_adapter_sha256": ROOT / ADAPTER_RELATIVE,
        "generator_script_sha256": WRAPPER_PATH,
    }
    for key, expected_value in expected_values.items():
        if versions.get(key) != expected_value:
            raise NdxDynamicShadowCandidateSnapshotError(
                f"candidate calendar-v2 source hash changed: {key}"
            )
    for key, expected_path in expected_paths.items():
        if _absolute(source_paths.get(key)) != expected_path.resolve():
            raise NdxDynamicShadowCandidateSnapshotError(
                f"candidate calendar-v2 source path changed: {key}"
            )
    return verified


def _load_calendar_v2(
    manifest_path: Path, *, decision_date: str,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
    sessions, versions, paths = capture_candidate_calendar_evidence_v2(
        manifest_path, decision_date=decision_date, repository_root=ROOT,
    )
    result = sessions.copy()
    result["completed"] = True
    return result, versions, paths


@contextmanager
def _patched_v1_calendar(decision_date: str) -> Iterator[None]:
    old_calendar = v1.DEFAULT_CALENDAR
    old_loader = v1._load_calendar
    old_append = v1._append_decision_seal
    old_file = v1.__file__
    v1.DEFAULT_CALENDAR = CALENDAR_V2
    v1._load_calendar = lambda manifest_path: _load_calendar_v2(  # type: ignore[assignment]
        manifest_path, decision_date=decision_date,
    )
    def guarded_append(ledger_path, manifest_path, manifest, **kwargs):
        # A v2 proof is a prerequisite of the append-only decision seal, not a
        # post-write diagnostic.  A failed proof therefore cannot create a
        # record that another runtime could mistake for a sealed decision.
        _require_v2_snapshot_provenance(manifest_path, manifest)
        return old_append(ledger_path, manifest_path, manifest, **kwargs)

    v1._append_decision_seal = guarded_append  # type: ignore[assignment]
    v1.__file__ = str(WRAPPER_PATH)
    try:
        yield
    finally:
        v1.DEFAULT_CALENDAR = old_calendar
        v1._load_calendar = old_loader  # type: ignore[assignment]
        v1._append_decision_seal = old_append  # type: ignore[assignment]
        v1.__file__ = old_file


def seal(args) -> dict[str, Any]:
    with _patched_v1_calendar(str(args.decision_date)):
        manifest = v1.seal(args)
    manifest_path = v1.DEFAULT_ROOT / str(args.decision_date) / "manifest.json"
    return _require_v2_snapshot_provenance(manifest_path, manifest)


def verify(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    if not path.is_relative_to(v1.DEFAULT_ROOT.resolve()):
        raise NdxDynamicShadowCandidateSnapshotError(
            "candidate verification path must stay under the canonical research root"
        )
    manifest = verify_snapshot_bundle(path)
    v1._verify_manifest_seal_record(path, manifest)
    return _require_v2_snapshot_provenance(path, manifest)


def readiness(args) -> dict[str, Any]:
    result = dict(v1.readiness(args))
    result["manifest_type"] = "ndx_dynamic_shadow_candidate_generator_v2_readiness"
    result["calendar_lineage"] = "REVIEWED_APPEND_ONLY_V2_PREFIX"
    result["calendar_manifest_path"] = CALENDAR_V2.as_posix()
    result["candidate_generator_v2_script_sha256"] = file_sha256(WRAPPER_PATH)
    blockers = list(result.get("blockers") or [])
    try:
        from backtest.ndx_observed_session_calendar_v2 import (
            verify_canonical_reviewed_calendar_v2,
        )

        verify_canonical_reviewed_calendar_v2(CALENDAR_V2, repository_root=ROOT)
    except Exception as exc:
        blockers.append({
            "code": "REVIEWED_CALENDAR_V2_NOT_VERIFIED",
            "reason": f"{type(exc).__name__}: {exc}",
        })
    result["blockers"] = blockers
    result["status"] = "BLOCKED" if blockers else "READY_TO_ATTEMPT_PROSPECTIVE_SEAL"
    result["promotion_allowed"] = False
    result["live_mutation"] = False
    return result


def parse_args():
    args = v1.parse_args()
    if not args.session_calendar_manifest:
        args.session_calendar_manifest = str(CALENDAR_V2)
    return args


def main() -> int:
    args = parse_args()
    protected_before = v1._protected_hashes()
    try:
        if args.verify:
            result = verify(v1._resolve(args.verify))
        elif args.seal:
            result = seal(args)
        else:
            if v1._resolve(args.output_root) != v1.DEFAULT_ROOT.resolve():
                raise NdxDynamicShadowCandidateSnapshotError(
                    "candidate readiness output root must be canonical"
                )
            result = readiness(args)
            v1._atomic_json(v1.DEFAULT_ROOT / "readiness_v2.json", result)
        if v1._protected_hashes() != protected_before:
            raise NdxDynamicShadowCandidateSnapshotError("protected live files changed")
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_candidate_generator_v2_failure",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "calendar_lineage": "REVIEWED_APPEND_ONLY_V2_PREFIX",
            "historical_candidate_replay_used": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        v1._atomic_json(v1.DEFAULT_ROOT / "last_failure_v2.json", failure)
        print(
            f"dynamic shadow candidate generator v2 fail-closed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        "dynamic shadow candidate generator v2 | "
        f"status={result['status']} | decision={result.get('decision_date')} | "
        "promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
