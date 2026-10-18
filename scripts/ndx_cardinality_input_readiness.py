r"""Audit real return and 012922 inputs before cardinality training.

PowerShell/PyCharm:
    python -B scripts\ndx_cardinality_input_readiness.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_cardinality_discovery import load_discovery_spec, validate_discovery_spec
from backtest.ndx_cardinality_input_readiness import (
    NdxCardinalityInputReadinessError,
    audit_membership_inputs,
    lifecycle_identity_audit,
    load_price_series,
    rebuild_job_readiness,
)
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _verified_artifact(bundle: dict, bundle_path: Path, key: str) -> tuple[pd.DataFrame, Path]:
    artifact = (bundle.get("artifacts") or {}).get(key) or {}
    path = Path(str(artifact.get("path") or ""))
    if not path.is_absolute():
        raise NdxCardinalityInputReadinessError(f"discovery artifact path is not absolute: {key}")
    if file_sha256(path) != str(artifact.get("sha256") or ""):
        raise NdxCardinalityInputReadinessError(f"discovery artifact hash mismatch: {key}")
    frame = pd.read_csv(path, low_memory=False)
    if len(frame) != int(artifact.get("rows") or -1):
        raise NdxCardinalityInputReadinessError(f"discovery artifact row count changed: {key}")
    return frame, path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run(args) -> dict:
    spec_path = _resolve(args.spec)
    discovery_manifest_path = _resolve(args.discovery_manifest)
    return_cache_dir = _resolve(args.return_cache_dir)
    identity_evidence_dir = _resolve(args.identity_evidence_dir)
    target_path = _resolve(args.target_nav)
    target_manifest_path = Path(f"{target_path}.manifest.json")
    output = _resolve(args.output_dir)
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    protected_before = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }

    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    contract = spec["real_input_contract"]
    discovery = json.loads(discovery_manifest_path.read_text(encoding="utf-8"))
    if discovery.get("manifest_type") != "ndx_variable_cardinality_discovery_preflight":
        raise NdxCardinalityInputReadinessError("unexpected discovery manifest type")
    if discovery.get("real_history_execution_allowed") is not False:
        raise NdxCardinalityInputReadinessError("discovery unexpectedly allows real execution")
    if discovery.get("taxonomy_membership_mode") != "LATEST_MANIFEST_VERIFIED_NPORT_SNAPSHOT_AS_OF_SELECTION_DATE":
        raise NdxCardinalityInputReadinessError("point-in-time membership mode changed")
    memberships, membership_path = _verified_artifact(
        discovery, discovery_manifest_path, "eligible_securities"
    )
    jobs, job_path = _verified_artifact(discovery, discovery_manifest_path, "training_job_plan")

    target_manifest = json.loads(target_manifest_path.read_text(encoding="utf-8"))
    if target_manifest.get("fund_code") != "012922":
        raise NdxCardinalityInputReadinessError("target fund changed")
    if file_sha256(target_path) != target_manifest.get("content_sha256"):
        raise NdxCardinalityInputReadinessError("target NAV hash mismatch")
    target_frame = pd.read_csv(target_path, low_memory=False)
    if len(target_frame) != int(target_manifest.get("row_count") or -1):
        raise NdxCardinalityInputReadinessError("target NAV row count changed")
    target_nav = load_price_series(target_path)

    identity = lifecycle_identity_audit(
        memberships,
        return_cache_dir=return_cache_dir,
        identity_evidence_dir=identity_evidence_dir,
        relative_tolerance=float(contract["lifecycle_identity_relative_tolerance"]),
    )
    membership_audit = audit_membership_inputs(
        memberships,
        return_cache_dir=return_cache_dir,
        target_nav=target_nav,
        identity_audit=identity,
        fit_days=int(contract["fit_days_strictly_before_selection"]),
        horizon_days=int(contract["evaluation_horizon_trading_days"]),
        target_endpoint_tolerance_days=int(contract["target_nav_endpoint_tolerance_calendar_days"]),
    )
    job_audit = rebuild_job_readiness(
        jobs,
        membership_audit,
        exact_limit=int(spec["search_contract"]["exact_enumeration_max_feasible_combinations"]),
    )
    output.mkdir(parents=True, exist_ok=True)
    identity_path = output / "lifecycle_identity_audit.csv"
    membership_audit_path = output / "membership_input_readiness.csv"
    job_audit_path = output / "training_job_input_readiness.csv"
    workbook_path = output / "ndx_cardinality_input_readiness.xlsx"
    _atomic_csv(identity, identity_path)
    _atomic_csv(membership_audit, membership_audit_path)
    _atomic_csv(job_audit, job_audit_path)
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            identity.to_excel(writer, sheet_name="生命周期身份", index=False)
            membership_audit.to_excel(writer, sheet_name="逐点时证券", index=False)
            job_audit.to_excel(writer, sheet_name="逐训练作业", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    protected_after = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }
    if protected_after != protected_before:
        raise NdxCardinalityInputReadinessError("protected config/state hash changed")
    complete_jobs = int(job_audit["complete_universe_job_ready"].sum())
    degraded_jobs = int(job_audit["degraded_research_job_ready"].sum())
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_real_input_readiness",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "TRAINING_INPUT_READINESS_ONLY_NOT_ADMISSION",
        "target_fund": "012922",
        "return_data_values_read_for_coverage_only": True,
        "portfolio_returns_calculated": False,
        "training_executed": False,
        "fresh_oos_consumed": False,
        "complete_universe_job_count": len(job_audit),
        "complete_universe_ready_job_count": complete_jobs,
        "degraded_research_ready_job_count": degraded_jobs,
        "complete_universe_execution_allowed": False,
        "degraded_research_execution_allowed": degraded_jobs > 0,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "protected_hashes_unchanged": True,
        "valuation_only_price_reused_for_returns": False,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "discovery_manifest": {"path": discovery_manifest_path.as_posix(), "sha256": file_sha256(discovery_manifest_path)},
            "memberships": {"path": membership_path.as_posix(), "sha256": file_sha256(membership_path)},
            "jobs": {"path": job_path.as_posix(), "sha256": file_sha256(job_path)},
            "target_nav": {"path": target_path.as_posix(), "sha256": file_sha256(target_path)},
            "target_manifest": {"path": target_manifest_path.as_posix(), "sha256": file_sha256(target_manifest_path)},
            "return_cache_dir": return_cache_dir.as_posix(),
            "identity_evidence_dir": identity_evidence_dir.as_posix(),
            "config": {"path": config_path.as_posix(), "sha256": protected_before["config"]},
            "state": {"path": state_path.as_posix(), "sha256": protected_before["state"]},
        },
        "artifacts": {
            "identity": {"path": identity_path.as_posix(), "rows": len(identity), "sha256": file_sha256(identity_path)},
            "membership_readiness": {"path": membership_audit_path.as_posix(), "rows": len(membership_audit), "sha256": file_sha256(membership_audit_path)},
            "job_readiness": {"path": job_audit_path.as_posix(), "rows": len(job_audit), "sha256": file_sha256(job_audit_path)},
            "workbook": {"path": workbook_path.as_posix(), "rows": None, "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="不固定持仓数真实价格与012922输入就绪审计")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--discovery-manifest", default="data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json")
    parser.add_argument("--return-cache-dir", default="data/cache")
    parser.add_argument("--identity-evidence-dir", default="data/cache/candidate_pools/ndx_fundamentals/price_basis_v1/raw")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_variable_cardinality_input_readiness_v1")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    return parser.parse_args()


def main() -> int:
    try:
        payload = run(parse_args())
    except Exception as exc:
        print(f"真实输入就绪审计失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "真实输入就绪审计完成 | "
        f"complete={payload['complete_universe_ready_job_count']}/{payload['complete_universe_job_count']} | "
        f"degraded={payload['degraded_research_ready_job_count']} | promotion_allowed=False"
    )
    print(f"Manifest: {_resolve(parse_args().output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
