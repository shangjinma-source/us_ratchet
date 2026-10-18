"""Rebuild the canonical P4 forward gate from immutable evaluation evidence.

The verifier deliberately ignores the mutable latest-summary booleans.  It
loads the latest pointer only to locate one hash-bound immutable evaluation
run, validates that run against the frozen v5 registry/specification, and then
recomputes the maturity and research-track summaries from the archived raw
evaluation rows.
"""
from __future__ import annotations

import json
import io
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from backtest.ndx_challenger_forward_evaluation import (
    summarize_forward_readiness,
    summarize_research_tracks,
)
from backtest.ndx_challenger_forward_registry import (
    validate_forward_spec,
    validate_registry_spec_binding,
)
from backtest.ndx_marginal_forward import read_cohort_index
from data.versioning import file_sha256
from backtest.ndx_dynamic_shadow_p4_replay import (
    canonical_replay_bundle_path,
    verify_p4_economic_replay,
)


class NdxDynamicShadowP4EvidenceError(ValueError):
    """Raised when canonical P4 evidence cannot be independently rebuilt."""


SPEC_RELATIVE = Path("config/ndx_challenger_forward_v5.yaml")
REGISTRY_RELATIVE = Path(
    "data/cache/research/ndx_challenger_forward_registry_v5/manifest.json"
)
EVALUATION_ROOT_RELATIVE = Path("data/cache/research/ndx_challenger_forward_v5")
LATEST_RELATIVE = EVALUATION_ROOT_RELATIVE / "latest_evaluation/manifest.json"
PASS_STATUS = (
    "FORWARD_POLICY_GATE_PASSED_REQUIRES_TODAY_DIFF_ROLLBACK_AND_USER_APPROVAL"
)
IMMUTABLE_ARTIFACT_FILENAMES = {
    "evaluations": "cohort_evaluations.csv",
    "summary": "maturity_summary.csv",
    "research_track_summary": "research_track_summary.csv",
}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4EvidenceError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise NdxDynamicShadowP4EvidenceError(f"{label} must be a mapping")
    return payload


def _bound_path(
    item: Mapping[str, Any], *, expected: Path, label: str, rows: bool = False,
) -> Path:
    try:
        declared = Path(str(item["path"])).resolve()
        declared_hash = str(item["sha256"])
    except (KeyError, OSError, ValueError) as exc:
        raise NdxDynamicShadowP4EvidenceError(f"{label} binding is incomplete") from exc
    if declared != expected.resolve() or not declared.is_file():
        raise NdxDynamicShadowP4EvidenceError(f"{label} path is not canonical")
    if file_sha256(declared) != declared_hash:
        raise NdxDynamicShadowP4EvidenceError(f"{label} hash changed")
    if rows and int(item.get("rows", -1)) < 0:
        raise NdxDynamicShadowP4EvidenceError(f"{label} row count is invalid")
    return declared


def _read_csv(path: Path, *, expected_rows: int, label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, low_memory=False, keep_default_na=False)
    except pd.errors.EmptyDataError:
        frame = pd.DataFrame()
    if len(frame) != int(expected_rows):
        raise NdxDynamicShadowP4EvidenceError(f"{label} row count changed")
    return frame


def _assert_frame_equal(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> None:
    # Normalize through the same CSV boundary used by the immutable evaluator;
    # otherwise scalar-looking audit strings (for example "2") compare unequal
    # to pandas' inferred integer even when the archived bytes are faithful.
    buffer = io.StringIO()
    actual.to_csv(buffer, index=False)
    buffer.seek(0)
    try:
        normalized = pd.read_csv(buffer, low_memory=False, keep_default_na=False)
    except pd.errors.EmptyDataError:
        normalized = pd.DataFrame()
    try:
        pd.testing.assert_frame_equal(
            normalized.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )
    except AssertionError as exc:
        raise NdxDynamicShadowP4EvidenceError(
            f"P4 {label} does not match the independently rebuilt result"
        ) from exc


def rebuild_p4_summaries(
    active_registry: pd.DataFrame,
    evaluations: pd.DataFrame,
    spec: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute the only P4 summary values accepted by the transition gate."""

    summary = summarize_forward_readiness(
        active_registry,
        evaluations,
        spec["forward_contract"],
        spec["promotion_contract"],
    )
    return summary, summarize_research_tracks(summary)


def _verify_cohort_index(
    run: Mapping[str, Any], *, root: Path, evaluation_root: Path,
    active_count: int, spec_path: Path, registry_path: Path,
    registry_content_sha256: str,
) -> list[dict[str, Any]]:
    declared_count = int(run.get("registered_cohorts", -1))
    item = run.get("cohort_index")
    canonical = evaluation_root / "cohort_index.jsonl"
    if declared_count == 0:
        if item is not None:
            raise NdxDynamicShadowP4EvidenceError(
                "zero-cohort immutable run unexpectedly binds a cohort index"
            )
        return []
    if not isinstance(item, Mapping):
        raise NdxDynamicShadowP4EvidenceError("mature P4 run has no cohort index binding")
    index_path = _bound_path(item, expected=canonical, label="P4 cohort index")
    records = read_cohort_index(index_path)
    if len(records) != declared_count:
        raise NdxDynamicShadowP4EvidenceError("P4 registered cohort count changed")
    first_fresh = pd.Timestamp(
        yaml.safe_load(spec_path.read_text(encoding="utf-8"))["forward_contract"]
        ["first_fresh_observation_on_or_after"]
    ).normalize()
    seen_dates: set[str] = set()
    for record in records:
        date_text = str(record.get("observation_date") or "")
        if date_text in seen_dates or pd.Timestamp(date_text).normalize() < first_fresh:
            raise NdxDynamicShadowP4EvidenceError("P4 cohort date is duplicated or pre-v5")
        seen_dates.add(date_text)
        if record.get("fresh_oos_eligible") is not True:
            raise NdxDynamicShadowP4EvidenceError("P4 cohort is not fresh OOS")
        expected_manifest = evaluation_root / "observations" / date_text / "manifest.json"
        manifest_path = Path(str(record.get("cohort_manifest_path") or "")).resolve()
        if (
            manifest_path != expected_manifest.resolve()
            or not manifest_path.is_file()
            or file_sha256(manifest_path) != record.get("cohort_manifest_sha256")
        ):
            raise NdxDynamicShadowP4EvidenceError("P4 cohort manifest binding changed")
        manifest = _load_json(manifest_path, "P4 cohort manifest")
        if (
            manifest.get("manifest_type") != "ndx_challenger_forward_cohort"
            or manifest.get("observation_date") != date_text
            or manifest.get("fresh_oos_eligible") is not True
            or int(manifest.get("active_candidate_count", -1)) != active_count
        ):
            raise NdxDynamicShadowP4EvidenceError("P4 cohort identity changed")
        inputs = manifest.get("inputs") or {}
        for key, expected, expected_hash in (
            ("spec", spec_path, file_sha256(spec_path)),
            ("registry_manifest", registry_path, file_sha256(registry_path)),
        ):
            _bound_path(inputs.get(key) or {}, expected=expected, label=f"cohort {key}")
            if str((inputs.get(key) or {}).get("sha256")) != expected_hash:
                raise NdxDynamicShadowP4EvidenceError(f"cohort {key} hash changed")
        if inputs.get("registry_content_sha256") != registry_content_sha256:
            raise NdxDynamicShadowP4EvidenceError("cohort registry content hash changed")
        for key, record_hash in (
            ("cohort_candidates", "cohort_candidates_sha256"),
            ("cohort_positions", "cohort_positions_sha256"),
        ):
            artifact = (manifest.get("artifacts") or {}).get(key) or {}
            path = Path(str(artifact.get("path") or "")).resolve()
            if (
                path.parent != manifest_path.parent
                or not path.is_file()
                or artifact.get("sha256") != file_sha256(path)
                or record.get(record_hash) != artifact.get("sha256")
                or int(artifact.get("rows", -1)) < 0
            ):
                raise NdxDynamicShadowP4EvidenceError(f"P4 cohort {key} changed")
    return records


def verify_p4_evaluation_evidence(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Verify canonical v5 evidence and rebuild its admission summary."""

    root = Path(repository_root).resolve()
    expected_latest = (root / LATEST_RELATIVE).resolve()
    source = Path(manifest_path).resolve()
    if source != expected_latest or not source.is_file():
        raise NdxDynamicShadowP4EvidenceError("P4 latest manifest path is not canonical")
    latest = _load_json(source, "P4 latest manifest")
    if (
        latest.get("schema_version") != 1
        or latest.get("manifest_type") != "ndx_challenger_forward_evaluation"
        or latest.get("promotion_allowed") is not False
        or latest.get("live_config_changed") is not False
        or latest.get("state_changed") is not False
        or latest.get("today_advice_changed") is not False
    ):
        raise NdxDynamicShadowP4EvidenceError("P4 latest manifest boundary changed")

    spec_path = (root / SPEC_RELATIVE).resolve()
    registry_path = (root / REGISTRY_RELATIVE).resolve()
    _bound_path(latest.get("spec") or {}, expected=spec_path, label="P4 v5 spec")
    _bound_path(
        latest.get("registry_manifest") or {},
        expected=registry_path,
        label="P4 v5 registry manifest",
    )
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    registry = _load_json(registry_path, "P4 v5 registry manifest")
    validate_forward_spec(spec)
    validate_registry_spec_binding(registry, spec, spec_sha256=file_sha256(spec_path))

    immutable = latest.get("immutable_evaluation_run") or {}
    run_id = str(immutable.get("evaluation_run_id") or "")
    run_path = (
        root / EVALUATION_ROOT_RELATIVE / "evaluation_runs" / run_id / "manifest.json"
    ).resolve()
    _bound_path(immutable, expected=run_path, label="P4 immutable evaluation run")
    run = _load_json(run_path, "P4 immutable evaluation run")
    if (
        run.get("manifest_type") != "ndx_challenger_forward_evaluation_run"
        or run.get("evaluation_run_id") != run_id
        or run.get("promotion_allowed") is not False
        or run.get("live_config_changed") is not False
        or run.get("state_changed") is not False
        or run.get("today_advice_changed") is not False
    ):
        raise NdxDynamicShadowP4EvidenceError("P4 immutable run boundary changed")
    for key in (
        "status", "registered_cohorts", "fresh_oos_cohorts", "mature_evaluation_rows",
        "portfolio_optimization_active_candidates", "migration_control_active_candidates",
        "policy_gate_ready_count", "policy_gate_passed_count", "candidate_admission_count",
        "spec", "registry_manifest", "target_012922_version",
    ):
        if latest.get(key) != run.get(key):
            raise NdxDynamicShadowP4EvidenceError(f"latest/immutable P4 mismatch: {key}")

    active_item = (registry.get("artifacts") or {}).get("active_registry") or {}
    active_path = root / "data/cache/research/ndx_challenger_forward_registry_v5/active_forward_registry.csv"
    _bound_path(active_item, expected=active_path, label="P4 active registry", rows=True)
    active = _read_csv(
        active_path, expected_rows=int(active_item["rows"]), label="P4 active registry"
    )
    if len(active) != int(registry.get("active_candidate_count", -1)):
        raise NdxDynamicShadowP4EvidenceError("P4 active candidate count changed")

    artifacts = run.get("artifacts") or {}
    frames: dict[str, pd.DataFrame] = {}
    for key, filename in IMMUTABLE_ARTIFACT_FILENAMES.items():
        item = artifacts.get(key) or {}
        expected = run_path.parent / filename
        _bound_path(item, expected=expected, label=f"P4 immutable {key}", rows=True)
        frames[key] = _read_csv(
            expected, expected_rows=int(item["rows"]), label=f"P4 immutable {key}"
        )

    records = _verify_cohort_index(
        run,
        root=root,
        evaluation_root=root / EVALUATION_ROOT_RELATIVE,
        active_count=len(active),
        spec_path=spec_path,
        registry_path=registry_path,
        registry_content_sha256=str(active_item["sha256"]),
    )
    evaluations = frames["evaluations"]
    if len(evaluations) != len(records) * len(active):
        raise NdxDynamicShadowP4EvidenceError("P4 evaluation/cohort Cartesian count changed")
    if not evaluations.empty:
        required = {"observation_date", "registry_entry_id", "fresh_oos_eligible"}
        if not required.issubset(evaluations.columns):
            raise NdxDynamicShadowP4EvidenceError("P4 evaluation identity columns are missing")
        pairs = evaluations[["observation_date", "registry_entry_id"]].astype(str)
        if pairs.duplicated().any():
            raise NdxDynamicShadowP4EvidenceError("P4 evaluation coordinate is duplicated")
        expected_pairs = {
            (str(record["observation_date"]), str(registry_id))
            for record in records
            for registry_id in active["registry_entry_id"].astype(str)
        }
        if set(map(tuple, pairs.to_records(index=False))) != expected_pairs:
            raise NdxDynamicShadowP4EvidenceError("P4 evaluation coordinate set changed")

    rebuilt_summary, rebuilt_tracks = rebuild_p4_summaries(active, evaluations, spec)
    _assert_frame_equal(rebuilt_summary, frames["summary"], "maturity summary")
    _assert_frame_equal(rebuilt_tracks, frames["research_track_summary"], "track summary")

    portfolio = rebuilt_summary.loc[
        rebuilt_summary["research_track"].astype(str).eq("portfolio_optimization")
    ].copy()
    diagnostic_eligible = portfolio.loc[
        portfolio["policy_gate_ready"].astype(bool)
        & portfolio["policy_gate_passed"].astype(bool)
        & portfolio["admission_status"].astype(str).eq(PASS_STATUS)
        & ~portfolio["promotion_allowed"].astype(bool)
    ]
    diagnostic_gate_passed_ids = sorted(
        diagnostic_eligible["candidate_id"].astype(str).unique()
    )
    replay_bundle_path = canonical_replay_bundle_path(run_id, repository_root=root)
    replay_evidence: dict[str, Any] | None = None
    eligible_ids: list[str] = []
    if replay_bundle_path.is_file():
        replay = verify_p4_economic_replay(replay_bundle_path, repository_root=root)
        replay_summary = replay.pop("summary")
        replay.pop("research_track_summary")
        _assert_frame_equal(replay_summary, rebuilt_summary, "economic replay summary")
        replay_portfolio = replay_summary.loc[
            replay_summary["research_track"].astype(str).eq("portfolio_optimization")
        ]
        replay_eligible = replay_portfolio.loc[
            replay_portfolio["policy_gate_ready"].astype(bool)
            & replay_portfolio["policy_gate_passed"].astype(bool)
            & replay_portfolio["admission_status"].astype(str).eq(PASS_STATUS)
            & ~replay_portfolio["promotion_allowed"].astype(bool)
        ]
        eligible_ids = sorted(replay_eligible["candidate_id"].astype(str).unique())
        replay_evidence = replay
    raw_replay = replay_evidence is not None
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_p4_rebuilt_evidence",
        "status": "P4_SUMMARY_REBUILT_DIAGNOSTIC_ONLY",
        "latest_manifest": {"path": source.as_posix(), "sha256": file_sha256(source)},
        "immutable_evaluation_run": {"path": run_path.as_posix(), "sha256": file_sha256(run_path)},
        "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
        "registry_manifest": {"path": registry_path.as_posix(), "sha256": file_sha256(registry_path)},
        "registered_fresh_cohorts": len(records),
        "minimum_fresh_mature_cohorts": int(spec["forward_contract"]["minimum_fresh_mature_cohorts"]),
        "minimum_distinct_regimes": int(spec["forward_contract"]["minimum_distinct_regimes"]),
        "diagnostic_summary_gate_passed_candidate_ids": diagnostic_gate_passed_ids,
        "eligible_portfolio_optimization_candidate_ids": eligible_ids,
        "summary_recomputed_from_immutable_evaluations": True,
        "raw_economic_path_replay_capability_implemented": True,
        "raw_economic_path_replay_implemented": True,
        "raw_economic_path_replay_verified": raw_replay,
        "economic_replay_evidence": replay_evidence,
        "expected_replay_bundle_path": replay_bundle_path.as_posix(),
        "admission_blocker": (
            None if raw_replay else (
                "NO_FRESH_COHORTS" if not records
                else "RAW_ECONOMIC_REPLAY_BUNDLE_MISSING"
            )
        ),
        "latest_summary_booleans_trusted": False,
        "caller_supplied_gate_booleans_trusted": False,
        "migration_control_eligible": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


__all__ = [
    "NdxDynamicShadowP4EvidenceError",
    "PASS_STATUS",
    "rebuild_p4_summaries",
    "verify_p4_evaluation_evidence",
]
