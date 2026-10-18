r"""Execute every verified prospective dynamic-k shard; never reads historical candidates.

PowerShell (future, after the PIT snapshot and frozen original-8 definition exist):
    python -B scripts\ndx_dynamic_shadow_fresh_search.py --execute `
      --snapshot-manifest <fresh-input-manifest> `
      --original-8-manifest <frozen-control-manifest> --resume
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_candidate_snapshot import verify_snapshot_bundle  # noqa: E402
from backtest.ndx_dynamic_shadow_fresh_search import (  # noqa: E402
    NdxDynamicShadowFreshSearchError,
    append_role_seal_record,
    canonical_sha256,
    coordinate_hash,
    execute_fresh_shard,
    freeze_cross_k_roles,
    load_executor_contract,
    load_frozen_original_8_definition,
    verify_completed_shard,
    verify_final_candidate_snapshot,
    verify_final_role_seal_record,
    write_completed_shard,
    write_final_candidate_snapshot,
)
from backtest.ndx_dynamic_shadow_selector_registry import (  # noqa: E402
    load_dynamic_shadow_selector_registry,
)
from data.versioning import file_sha256  # noqa: E402


PROTECTED = (ROOT / "config/config.yaml", ROOT / "data/state.json", ROOT / "data/broker_positions.json")
CANONICAL_SNAPSHOT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_candidate_generator_v1"
CANONICAL_OUTPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_fresh_search_v1"
CANONICAL_CONTRACT = ROOT / "config/ndx_dynamic_shadow_fresh_search_v1.yaml"
CANONICAL_ORIGINAL8 = ROOT / "data/cache/research/ndx_original_8_control_v1/manifest.json"
ROLE_SEAL_LEDGER = CANONICAL_OUTPUT_ROOT / "role_seals.jsonl"


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def _hashes() -> dict[str, str | None]:
    return {path.relative_to(ROOT).as_posix(): file_sha256(path) if path.is_file() else None for path in PROTECTED}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _artifact(manifest_path: Path, manifest: Mapping[str, Any], name: str) -> pd.DataFrame:
    item = (manifest.get("artifacts") or {}).get(name) or {}
    filename = str(item.get("filename") or "")
    if not filename or Path(filename).name != filename:
        raise NdxDynamicShadowFreshSearchError(f"snapshot artifact is missing: {name}")
    path = manifest_path.parent / filename
    if not path.is_file() or file_sha256(path) != item.get("sha256"):
        raise NdxDynamicShadowFreshSearchError(f"snapshot artifact hash mismatch: {name}")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(item.get("rows", -1)):
        raise NdxDynamicShadowFreshSearchError(f"snapshot artifact row count mismatch: {name}")
    return frame


def _shard_dir(root: Path, job: Mapping[str, Any]) -> Path:
    return (
        root / "shards" / str(job["snapshot_fingerprint"])[:16]
        / str(job["universe_track"]) / str(job["decision_date"])
        / f"holding_count_{int(job['holding_count']):04d}"
    )


def _aggregate_slice(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep a lossless-for-global-frontiers subset and one audit row per k.

    A global Pareto/extreme candidate must be on its own within-k constrained
    frontier.  USER_PREFERENCE is retained independently even when it fails
    concentration constraints.  One deterministic marker row keeps completed
    k coverage visible when a shard has neither.
    """
    tags = frame.get("constrained_frontier_tags", pd.Series("", index=frame.index)).fillna("").astype(str)
    preference = (
        frame["tickers"].astype(str).map(lambda value: set(value.split(";")) == {"AMAT", "AVGO", "CDNS", "GOOG"})
        & frame["weight_spec"].astype(str).eq("equal_weight")
    )
    selected = frame.loc[tags.ne("") | preference].copy()
    if selected.empty:
        selected = frame.sort_values(["portfolio_id", "weight_spec"], kind="stable").head(1).copy()
        selected["aggregate_marker_only"] = True
    else:
        selected["aggregate_marker_only"] = False
    return selected


def execute(args: argparse.Namespace) -> dict[str, Any]:
    snapshot_path = _resolve(args.snapshot_manifest)
    contract_path = _resolve(args.contract)
    if (
        contract_path != CANONICAL_CONTRACT.resolve()
        or _resolve(args.output_root) != CANONICAL_OUTPUT_ROOT.resolve()
        or _resolve(args.original_8_manifest) != CANONICAL_ORIGINAL8.resolve()
    ):
        raise NdxDynamicShadowFreshSearchError(
            "fresh search requires canonical snapshot/contract/output/original8 paths"
        )
    try:
        relative_snapshot = snapshot_path.relative_to(CANONICAL_SNAPSHOT_ROOT.resolve())
    except ValueError as exc:
        raise NdxDynamicShadowFreshSearchError(
            "fresh search snapshot must be inside the canonical generator root"
        ) from exc
    if len(relative_snapshot.parts) != 2 or relative_snapshot.name != "manifest.json":
        raise NdxDynamicShadowFreshSearchError(
            "fresh search snapshot must be a canonical decision manifest"
        )
    try:
        decision_directory = pd.Timestamp(relative_snapshot.parts[0]).date().isoformat()
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowFreshSearchError(
            "fresh search snapshot decision directory is invalid"
        ) from exc
    if decision_directory != relative_snapshot.parts[0]:
        raise NdxDynamicShadowFreshSearchError(
            "fresh search snapshot decision directory is not canonical ISO date"
        )
    snapshot = verify_snapshot_bundle(snapshot_path)
    expected_snapshot = CANONICAL_SNAPSHOT_ROOT / str(snapshot["decision_date"]) / "manifest.json"
    if snapshot_path != expected_snapshot.resolve():
        raise NdxDynamicShadowFreshSearchError(
            "fresh search snapshot decision path disagrees with its manifest"
        )
    from scripts.ndx_dynamic_shadow_candidate_generator import _verify_manifest_seal_record

    snapshot_seal_record = _verify_manifest_seal_record(snapshot_path, snapshot)
    contract = load_executor_contract(contract_path)
    if not args.original_8_manifest:
        raise NdxDynamicShadowFreshSearchError("--original-8-manifest is required")
    incumbent, incumbent_weights, original_hash = load_frozen_original_8_definition(
        _resolve(args.original_8_manifest)
    )
    eligible = _artifact(snapshot_path, snapshot, "eligible_securities")
    adjusted = _artifact(snapshot_path, snapshot, "training_adjusted_close")
    nominal = _artifact(snapshot_path, snapshot, "training_nominal_close")
    target = _artifact(snapshot_path, snapshot, "target_012922_aligned")
    liquidity = _artifact(snapshot_path, snapshot, "price_input_inventory")
    jobs = _artifact(snapshot_path, snapshot, "job_plan")
    expected_k = {
        track: list(range(1, int(eligible.loc[eligible["universe_track"].eq(track), "issuer_id"].nunique()) + 1))
        for track in ("strict_technology", "technology_plus_adjacent")
    }
    for track, expected in expected_k.items():
        observed = sorted(jobs.loc[jobs["universe_track"].eq(track), "holding_count"].astype(int).tolist())
        if observed != expected:
            raise NdxDynamicShadowFreshSearchError(f"verified snapshot job plan lacks full k coverage: {track}")
    output = _resolve(args.output_root)
    snapshot_manifest_hash = file_sha256(snapshot_path)
    selector_registry_path = ROOT / "config/ndx_dynamic_shadow_selector_registry_v1.yaml"
    selector_policy_path = ROOT / "backtest/ndx_dynamic_candidate_policy.py"
    selector_registry_module_path = ROOT / "backtest/ndx_dynamic_shadow_selector_registry.py"
    selector_registry = load_dynamic_shadow_selector_registry(selector_registry_path)
    if (
        selector_registry.get("status") != "INACTIVE_PRE_REGISTERED_RESEARCH_ONLY"
        or (selector_registry.get("activation") or {}).get("active") is not False
    ):
        raise NdxDynamicShadowFreshSearchError("selector registry must remain inactive research-only")
    executor_hash = canonical_sha256({
        "contract_sha256": file_sha256(contract_path),
        "module_sha256": file_sha256(ROOT / "backtest/ndx_dynamic_shadow_fresh_search.py"),
        "script_sha256": file_sha256(Path(__file__).resolve()),
        "search_kernel_sha256": file_sha256(ROOT / "backtest/ndx_cardinality_discovery.py"),
        "selector_policy_sha256": file_sha256(selector_policy_path),
        "selector_registry_sha256": file_sha256(selector_registry_path),
        "selector_registry_validator_sha256": file_sha256(selector_registry_module_path),
    })
    completed_frames = []
    verified_job_coordinates: set[str] = set()
    completed = resumed = attempted = 0
    limit = int(args.max_jobs)
    for row in jobs.itertuples(index=False):
        job = row._asdict()
        identity = coordinate_hash(
            job, snapshot_manifest_sha256=snapshot_manifest_hash,
            executor_sha256=executor_hash, original_8_sha256=original_hash,
        )
        directory = _shard_dir(output, job)
        checkpoint = directory / "checkpoint.json"
        if args.resume and checkpoint.is_file():
            frame, _ = verify_completed_shard(
                checkpoint, coordinate_hash=identity, expected_job=job,
            )
            completed_frames.append(_aggregate_slice(frame))
            verified_job_coordinates.add(identity)
            resumed += 1
            continue
        if limit > 0 and attempted >= limit:
            continue
        attempted += 1
        frame, audit = execute_fresh_shard(
            job,
            eligible=eligible,
            adjusted_close=adjusted,
            nominal_close=nominal,
            target_aligned=target,
            liquidity=liquidity,
            incumbent=incumbent,
            incumbent_weights=incumbent_weights,
            contract=contract,
        )
        frame["coordinate_hash"] = identity
        write_completed_shard(directory, frame, audit, coordinate_hash=identity)
        verified, _ = verify_completed_shard(
            checkpoint, coordinate_hash=identity, expected_job=job,
        )
        completed_frames.append(_aggregate_slice(verified))
        verified_job_coordinates.add(identity)
        completed += 1
    expected_total = len(jobs)
    progress = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_fresh_search_progress",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "COMPLETE" if len(verified_job_coordinates) == expected_total else "INCOMPLETE_FAIL_CLOSED",
        "snapshot_manifest_sha256": snapshot_manifest_hash,
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "planned": expected_total,
        "attempted": attempted,
        "completed": completed,
        "resumed": resumed,
        "verified_unique_coordinates": len(verified_job_coordinates),
        "aggregation_allowed": len(verified_job_coordinates) == expected_total,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    _atomic_json(output / "progress.json", progress)
    if len(verified_job_coordinates) != expected_total:
        return progress
    all_candidates = pd.concat(completed_frames, ignore_index=True)
    frozen_candidates, roles = freeze_cross_k_roles(all_candidates)
    final_dir = output / "final" / str(snapshot["decision_date"])
    final = write_final_candidate_snapshot(
        final_dir,
        frozen_candidates,
        roles,
        jobs,
        snapshot_manifest_sha256=snapshot_manifest_hash,
        snapshot_fingerprint=str(snapshot["snapshot_fingerprint"]),
        executor_sha256=executor_hash,
        original_8_sha256=original_hash,
        snapshot_seal_record_sha256=str(snapshot_seal_record["record_sha256"]),
        snapshot_conservative_deadline_utc=str(snapshot["conservative_seal_deadline_utc"]),
    )
    append_role_seal_record(
        ROLE_SEAL_LEDGER, final_dir / "manifest.json",
        expected_final_root=CANONICAL_OUTPUT_ROOT / "final",
    )
    return final


def readiness(args: argparse.Namespace) -> dict[str, Any]:
    blockers = []
    if not args.snapshot_manifest:
        blockers.append("FRESH_PIT_SNAPSHOT_MANIFEST_REQUIRED")
    if not args.original_8_manifest:
        blockers.append("FROZEN_ORIGINAL_8_DEFINITION_REQUIRED")
    if (
        _resolve(args.contract) != CANONICAL_CONTRACT.resolve()
        or _resolve(args.output_root) != CANONICAL_OUTPUT_ROOT.resolve()
        or _resolve(args.original_8_manifest) != CANONICAL_ORIGINAL8.resolve()
    ):
        blockers.append("CANONICAL_EXECUTOR_PATHS_REQUIRED")
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_fresh_search_readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED" if blockers else "READY_TO_VERIFY_INPUTS",
        "blockers": blockers,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute verified fresh dynamic-k search shards")
    parser.add_argument("--contract", default="config/ndx_dynamic_shadow_fresh_search_v1.yaml")
    parser.add_argument("--snapshot-manifest", default="")
    parser.add_argument("--original-8-manifest", default="data/cache/research/ndx_original_8_control_v1/manifest.json")
    parser.add_argument("--output-root", default="data/cache/research/ndx_dynamic_shadow_fresh_search_v1")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=0)
    parser.add_argument("--verify-final", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    before = _hashes()
    try:
        if args.verify_final:
            verify_path = _resolve(args.verify_final)
            if not verify_path.is_relative_to((CANONICAL_OUTPUT_ROOT / "final").resolve()):
                raise NdxDynamicShadowFreshSearchError("final verification path must be canonical")
            result = verify_final_candidate_snapshot(verify_path)
            expected_path = (
                CANONICAL_OUTPUT_ROOT / "final" / str(result["decision_date"]) / "manifest.json"
            ).resolve()
            if verify_path != expected_path:
                raise NdxDynamicShadowFreshSearchError(
                    "final verification path disagrees with its decision coordinate"
                )
            from scripts.ndx_dynamic_shadow_candidate_generator import _verify_manifest_seal_record

            input_path = (
                CANONICAL_SNAPSHOT_ROOT / str(result["decision_date"]) / "manifest.json"
            ).resolve()
            snapshot = verify_snapshot_bundle(input_path)
            input_seal = _verify_manifest_seal_record(input_path, snapshot)
            if (
                file_sha256(input_path) != result["snapshot_manifest_sha256"]
                or input_seal["record_sha256"] != result["snapshot_seal_record_sha256"]
            ):
                raise NdxDynamicShadowFreshSearchError(
                    "final verification disagrees with the append-only input seal"
                )
            verify_final_role_seal_record(
                verify_path, ROLE_SEAL_LEDGER,
                expected_final_root=CANONICAL_OUTPUT_ROOT / "final",
            )
        elif args.execute:
            if not args.snapshot_manifest:
                raise NdxDynamicShadowFreshSearchError("--snapshot-manifest is required")
            result = execute(args)
        else:
            result = readiness(args)
            if _resolve(args.output_root) != CANONICAL_OUTPUT_ROOT.resolve():
                raise NdxDynamicShadowFreshSearchError("fresh search readiness output root must be canonical")
            _atomic_json(_resolve(args.output_root) / "readiness.json", result)
        if _hashes() != before:
            raise NdxDynamicShadowFreshSearchError("protected live files changed")
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "manifest_type": "ndx_dynamic_shadow_fresh_search_failure",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "BLOCKED_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "historical_candidate_replay_used": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        _atomic_json(CANONICAL_OUTPUT_ROOT / "last_failure.json", failure)
        print(f"fresh search fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "fresh dynamic-k search | "
        f"status={result['status']} | historical_replay=False | promotion=False | live_mutation=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
