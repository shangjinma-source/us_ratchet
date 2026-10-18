r"""Resolve 012922 outcomes and evaluate prospective shadow paths, research-only.

PowerShell:
    python -B scripts\ndx_dynamic_shadow_outcome.py --readiness
    python -B scripts\ndx_dynamic_shadow_outcome.py --execute
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_shadow_daily import (  # noqa: E402
    canonical_sha256,
    verify_daily_run_manifest,
)
from backtest.ndx_dynamic_shadow_outcome import (  # noqa: E402
    NdxDynamicShadowOutcomeError,
    append_resolution_events,
    evaluate_dynamic_shadow_outcomes,
    load_outcome_contract,
    load_resolution_ledger,
)
from data.versioning import file_sha256  # noqa: E402


CONTRACT = ROOT / "config/ndx_dynamic_shadow_outcome_v1.yaml"
DAILY_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_daily_v1"
OUTPUT_ROOT = ROOT / "data/cache/research/ndx_dynamic_shadow_outcome_v1"
FIRST_TRACE = DAILY_ROOT / "benchmark_controls/target_012922_asof.jsonl"
ORIGINAL8 = DAILY_ROOT / "benchmark_controls/original_8_incumbent_v0.jsonl"
LANE_ROOT = DAILY_ROOT / "lane_paths"
DECISION_ROOT = DAILY_ROOT / "realized_decisions"
DAILY_RUN = DAILY_ROOT / "latest_run.json"
RESOLUTION_LEDGER = OUTPUT_ROOT / "target_012922_resolved_outcomes.jsonl"
SOURCE_ROOT = OUTPUT_ROOT / "source_snapshots"
TARGET_CSV = ROOT / "data/cache/funds/012922.csv"
TARGET_MANIFEST = ROOT / "data/cache/funds/012922.csv.manifest.json"
PROTECTED = (
    ROOT / "config/config.yaml", ROOT / "data/state.json",
    ROOT / "data/broker_positions.json",
)
TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")


def _protected_hashes() -> dict[str, str | None]:
    return {path.as_posix(): file_sha256(path) if path.is_file() else None for path in PROTECTED}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _selector_paths() -> dict[str, Path]:
    return {
        f"{track}__{role.lower()}__v1": LANE_ROOT / f"{track}__{role.lower()}__v1.jsonl"
        for track in TRACKS for role in ROLES
    }


def _freeze_target_source() -> tuple[Path, Path]:
    if not TARGET_CSV.is_file() or not TARGET_MANIFEST.is_file():
        raise NdxDynamicShadowOutcomeError("canonical 012922 source is missing")
    csv_hash, manifest_hash = file_sha256(TARGET_CSV), file_sha256(TARGET_MANIFEST)
    SOURCE_ROOT.mkdir(parents=True, exist_ok=True)
    csv_snapshot = SOURCE_ROOT / f"{csv_hash}.csv"
    manifest_snapshot = SOURCE_ROOT / f"{manifest_hash}.manifest.json"
    for source, destination in ((TARGET_CSV, csv_snapshot), (TARGET_MANIFEST, manifest_snapshot)):
        if destination.exists() and file_sha256(destination) != file_sha256(source):
            raise NdxDynamicShadowOutcomeError("immutable outcome source collision")
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
    return csv_snapshot, manifest_snapshot


def readiness() -> dict[str, Any]:
    load_outcome_contract(CONTRACT)
    selectors = _selector_paths()
    checks = {
        "first_observed_trace": FIRST_TRACE.is_file(),
        "original_8_control": ORIGINAL8.is_file(),
        "complete_10_selector_lanes": all(path.is_file() for path in selectors.values()),
        "realized_decision_chain": DECISION_ROOT.is_dir(),
        "target_source": TARGET_CSV.is_file() and TARGET_MANIFEST.is_file(),
        "verified_daily_run": DAILY_RUN.is_file(),
    }
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_outcome_readiness",
        "status": "READY_FOR_RESEARCH_UPDATE" if all(checks.values()) else "BLOCKED_NOT_YET_DUE",
        "checks": checks,
        "automation_registered": False,
        "performance_admission_allowed": False,
        "performance_veto_allowed": False,
        "formal_v5_gate_substitution_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def _evaluation_payload() -> dict[str, Any]:
    return evaluate_dynamic_shadow_outcomes(
        selector_lane_ledgers=_selector_paths(), original_8_ledger=ORIGINAL8,
        resolution_ledger=RESOLUTION_LEDGER, first_observed_trace_path=FIRST_TRACE,
        realized_decision_root=DECISION_ROOT,
    )


def execute() -> dict[str, Any]:
    before = _protected_hashes()
    load_outcome_contract(CONTRACT)
    verify_daily_run_manifest(DAILY_RUN, repository_root=ROOT)
    csv_snapshot, manifest_snapshot = _freeze_target_source()
    import pandas as pd

    append_resolution_events(
        RESOLUTION_LEDGER, first_observed_trace_path=FIRST_TRACE,
        target_nav=pd.read_csv(csv_snapshot), source_csv_snapshot_path=csv_snapshot,
        source_manifest_snapshot_path=manifest_snapshot,
    )
    result = {
        **_evaluation_payload(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_artifacts": {
            "contract": {"path": CONTRACT.resolve().as_posix(), "sha256": file_sha256(CONTRACT)},
            "daily_run": {"path": DAILY_RUN.resolve().as_posix(), "sha256": file_sha256(DAILY_RUN)},
            "first_observed_trace": {
                "path": FIRST_TRACE.resolve().as_posix(), "sha256": file_sha256(FIRST_TRACE),
            },
            "resolution_ledger": {
                "path": RESOLUTION_LEDGER.resolve().as_posix(),
                "sha256": file_sha256(RESOLUTION_LEDGER),
            },
            "source_csv_snapshot": {
                "path": csv_snapshot.resolve().as_posix(), "sha256": file_sha256(csv_snapshot),
            },
            "source_manifest_snapshot": {
                "path": manifest_snapshot.resolve().as_posix(),
                "sha256": file_sha256(manifest_snapshot),
            },
            "formal_forward_v5_contract": {
                "path": (ROOT / "config/ndx_challenger_forward_v5.yaml").resolve().as_posix(),
                "sha256": file_sha256(ROOT / "config/ndx_challenger_forward_v5.yaml"),
            },
        },
    }
    result["manifest_sha256"] = canonical_sha256(result)
    _atomic_json(OUTPUT_ROOT / "latest_evaluation.json", result)
    if _protected_hashes() != before:
        raise NdxDynamicShadowOutcomeError("protected live files changed")
    return result


def verify_current_evaluation(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path).resolve()
    expected = (OUTPUT_ROOT / "latest_evaluation.json").resolve()
    if manifest_path != expected:
        raise NdxDynamicShadowOutcomeError("outcome evaluation path is not canonical")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    unsigned = dict(manifest)
    declared = str(unsigned.pop("manifest_sha256", ""))
    recomputed = _evaluation_payload()
    expected_keys = set(recomputed) | {"generated_at_utc", "input_artifacts", "manifest_sha256"}
    if set(manifest) != expected_keys or canonical_sha256(unsigned) != declared:
        raise NdxDynamicShadowOutcomeError("outcome evaluation manifest hash changed")
    load_outcome_contract(CONTRACT)
    verify_daily_run_manifest(DAILY_RUN, repository_root=ROOT)
    artifacts = manifest.get("input_artifacts") or {}
    expected_artifact_paths = {
        "contract": CONTRACT.resolve(),
        "daily_run": DAILY_RUN.resolve(),
        "first_observed_trace": FIRST_TRACE.resolve(),
        "resolution_ledger": RESOLUTION_LEDGER.resolve(),
        "formal_forward_v5_contract": (ROOT / "config/ndx_challenger_forward_v5.yaml").resolve(),
    }
    if set(artifacts) != set(expected_artifact_paths) | {
        "source_csv_snapshot", "source_manifest_snapshot"
    }:
        raise NdxDynamicShadowOutcomeError("outcome evaluation input registry changed")
    for name, descriptor in artifacts.items():
        if set(descriptor) != {"path", "sha256"}:
            raise NdxDynamicShadowOutcomeError("outcome evaluation input descriptor changed")
        source = Path(str(descriptor.get("path") or ""))
        if not source.is_file() or file_sha256(source) != descriptor.get("sha256"):
            raise NdxDynamicShadowOutcomeError("outcome evaluation input hash changed")
        if name in expected_artifact_paths and source.resolve() != expected_artifact_paths[name]:
            raise NdxDynamicShadowOutcomeError("outcome evaluation input path changed")
        if name.startswith("source_") and source.resolve().parent != SOURCE_ROOT.resolve():
            raise NdxDynamicShadowOutcomeError("outcome source snapshot path changed")
    for key, value in recomputed.items():
        if manifest.get(key) != value:
            raise NdxDynamicShadowOutcomeError(f"outcome evaluation changed: {key}")
    load_resolution_ledger(RESOLUTION_LEDGER, first_observed_trace_path=FIRST_TRACE)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research-only resolved dynamic-shadow outcomes")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--readiness", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.execute:
            result = execute()
        elif args.verify:
            result = verify_current_evaluation(OUTPUT_ROOT / "latest_evaluation.json")
        else:
            result = readiness()
    except Exception as exc:
        print(f"dynamic shadow outcome fail-closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "dynamic shadow outcome | "
        f"status={result['status']} | sessions={result.get('resolved_trading_session_count', 0)} | "
        "admission=False | veto=False | promotion=False | live=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
