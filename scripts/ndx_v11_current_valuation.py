"""Build the hash-locked current NDX FCF Yield overpay-guard bundle."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_current_valuation import (  # noqa: E402
    CURRENT_VALUATION_POLICY_ID,
    OVERPAY_PENALTY_QUANTILE,
    VALUATION_WEIGHT,
    NdxCurrentValuationError,
    build_current_valuation_guard,
)
from backtest.ndx_marginal_stage1 import verify_sidecar  # noqa: E402
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import (  # noqa: E402
    file_sha256,
    manifest_path,
    utc_now_iso,
    write_dataset_manifest,
)


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _verified_csv(path: Path, *, require_return_proof: bool = True) -> tuple[pd.DataFrame, dict]:
    if require_return_proof:
        version = verify_sidecar(path)
        payload = _read_json(manifest_path(path))
    else:
        payload = _read_json(manifest_path(path))
        if payload.get("content_sha256") != file_sha256(path):
            raise NdxCurrentValuationError(f"content hash mismatch: {path}")
        version = {
            "path": path.as_posix(),
            "sha256": payload["content_sha256"],
            "version_id": payload.get("version_id"),
            "rows": payload.get("row_count"),
        }
    return pd.read_csv(path, low_memory=False), {**version, "sidecar": payload}


def _write_frame(frame: pd.DataFrame, path: Path, key: str, *, extra: dict) -> dict:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    manifest = write_dataset_manifest(
        path,
        dataset_type="ndx_v11_current_valuation_guard",
        dataset_key=f"{CURRENT_VALUATION_POLICY_ID}:{key}",
        source="derived_from_sec_point_in_time_evidence_and_raw_nominal_prices",
        fetched_at=utc_now_iso(),
        fetched_at_evidence="derived_runtime_utc",
        row_count=len(frame),
        data_start=str(frame["selection_date"].min()) if "selection_date" in frame and not frame.empty else None,
        data_end=str(frame["selection_date"].max()) if "selection_date" in frame and not frame.empty else None,
        extra=extra,
    )
    return {
        "path": path.as_posix(),
        "rows": len(frame),
        "sha256": manifest["content_sha256"],
        "version_id": manifest["version_id"],
    }


def prepare_price_plan(factors_path: Path, plan_path: Path) -> dict:
    factors, source = _verified_csv(factors_path)
    plan = factors[["selection_date", "ticker", "cik"]].copy()
    if plan.duplicated(["selection_date", "ticker"]).any():
        raise NdxCurrentValuationError("current valuation price plan contains duplicates")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = _write_frame(
        plan,
        plan_path,
        "raw_price_plan",
        extra={
            "return_data_read": False,
            "research_only": True,
            "candidate_admission_allowed": False,
            "source_factor_sha256": source["sha256"],
        },
    )
    return artifact


def build_bundle(args: argparse.Namespace) -> dict:
    readiness_path = _resolve(args.current_readiness)
    factors_path = _resolve(args.factors)
    price_basis_dir = _resolve(args.price_basis_dir)
    output = _resolve(args.output_dir)
    readiness, readiness_version = _verified_csv(readiness_path)
    factors, factors_version = _verified_csv(factors_path)
    coverage_path = price_basis_dir / "coverage.csv"
    prices, price_version = _verified_csv(coverage_path, require_return_proof=False)
    price_manifest = _read_json(price_basis_dir / "manifest.json")
    if not price_manifest.get("consumption_allowed"):
        raise NdxCurrentValuationError("raw nominal-price bundle is not consumable")
    evidence = price_manifest.get("evidence_files", {}).get("coverage", {})
    if evidence.get("sha256") != price_version["sha256"]:
        raise NdxCurrentValuationError("raw price root manifest does not lock coverage.csv")
    if prices["selection_date"].astype(str).nunique() != 1 or not prices[
        "selection_date"
    ].astype(str).eq(args.selection_date).all():
        raise NdxCurrentValuationError("raw prices do not match the current selection date")

    gate, values, scores, score_coverage = build_current_valuation_guard(
        readiness, factors, prices
    )
    gate_columns = gate[[
        "selection_date", "ticker", "price_ready", "price_basis_ready",
        "price_future_data_guard_passed", "fcf_yield_ready", "ev_sales_ready",
        "fcf_yield_blockers", "ev_sales_blockers",
    ]]
    valuation_gate = scores.merge(
        gate_columns, on=["selection_date", "ticker"], how="left", validate="one_to_one"
    )
    valuation_gate["valuation_blockers"] = valuation_gate.apply(
        lambda row: (
            "FCF_YIELD_MISSING_NEUTRAL_50_APPLIED"
            if bool(row["valuation_missing_neutral_applied"]) else ""
        ),
        axis=1,
    )
    output.mkdir(parents=True, exist_ok=True)
    common = {
        "policy_id": CURRENT_VALUATION_POLICY_ID,
        "upstream_score_policy_id": "ndx_fcf_yield_overpay_guard_v1",
        "overpay_penalty_quantile": OVERPAY_PENALTY_QUANTILE,
        "valuation_weight": VALUATION_WEIGHT,
        "missing_value_policy": "exact_neutral_50",
        "cheap_reward_allowed": False,
        "return_data_read": False,
        "research_only": True,
        "candidate_admission_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
    }
    artifacts = {}
    for key, frame in {
        "valuation_readiness": gate,
        "valuation_values": values,
        "valuation_scores": scores,
        "valuation_coverage": score_coverage,
        "valuation_gate": valuation_gate,
    }.items():
        artifacts[key] = _write_frame(frame, output / f"{key}.csv", key, extra=common)

    workbook = output / "ndx_v11_current_valuation_guard.xlsx"
    temporary = output / "ndx_v11_current_valuation_guard.tmp.xlsx"
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            pd.DataFrame([
                {"项目": "状态", "值": "RESEARCH_GUARD_READY_NOT_ADMITTED"},
                {"项目": "候选证券数", "值": len(scores)},
                {"项目": "FCF Yield已观测", "值": int(scores["fcf_yield_observed"].sum())},
                {"项目": "缺失中性50", "值": int(scores["valuation_missing_neutral_applied"].sum())},
                {"项目": "最低30%单边惩罚", "值": True},
                {"项目": "便宜股奖励", "值": False},
                {"项目": "读取收益数据", "值": False},
                {"项目": "实盘准入", "值": False},
            ]).to_excel(writer, sheet_name="摘要", index=False)
            valuation_gate.to_excel(writer, sheet_name="101只估值防过付", index=False)
            score_coverage.to_excel(writer, sheet_name="估值覆盖", index=False)
            values.to_excel(writer, sheet_name="估值原值", index=False)
            gate.to_excel(writer, sheet_name="上游就绪审计", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()
    artifacts["workbook"] = {
        "path": workbook.as_posix(), "rows": None, "sha256": file_sha256(workbook)
    }
    coverage_row = score_coverage.iloc[0]
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_v11_current_valuation_guard",
        "generated_at": utc_now_iso(),
        "status": "RESEARCH_GUARD_READY_NOT_ADMITTED",
        **common,
        "selection_date": args.selection_date,
        "universe_count": len(scores),
        "fcf_yield_observed_count": int(coverage_row["fcf_yield_observed_count"]),
        "fcf_yield_coverage": float(coverage_row["fcf_yield_coverage"]),
        "factor_active": bool(coverage_row["factor_active"]),
        "missing_neutral_count": int(coverage_row["missing_neutral_count"]),
        "inputs": {
            "current_readiness": readiness_version,
            "factor_inputs": factors_version,
            "raw_price_basis_manifest_path": (price_basis_dir / "manifest.json").as_posix(),
            "raw_price_basis_manifest_sha256": file_sha256(price_basis_dir / "manifest.json"),
            "raw_price_coverage": price_version,
        },
        "artifacts": artifacts,
    }
    atomic_write_text(
        output / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11当前FCF Yield单边防过付研究")
    parser.add_argument("--current-readiness", default="data/cache/research/ndx_v11_current_fundamental_evidence_v1/valuation_readiness.csv")
    parser.add_argument("--factors", default="data/cache/research/ndx_v11_current_fundamental_evidence_v1/quality_factor_inputs.csv")
    parser.add_argument("--price-plan", default="data/cache/research/ndx_v11_current_price_plan_v1/plan.csv")
    parser.add_argument("--price-basis-dir", default="data/cache/research/ndx_v11_current_price_basis_v2")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_v11_current_valuation_guard_v1")
    parser.add_argument("--selection-date", default="2026-07-13")
    parser.add_argument("--prepare-price-plan-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.prepare_price_plan_only:
            artifact = prepare_price_plan(_resolve(args.factors), _resolve(args.price_plan))
            print(f"当前估值原始价格计划已锁定 | rows={artifact['rows']} | {artifact['path']}")
            return 0
        manifest = build_bundle(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NDX当前估值防过付失败: {exc}", file=sys.stderr)
        return 2
    print(
        "NDX当前估值防过付完成 | "
        f"observed={manifest['fcf_yield_observed_count']}/{manifest['universe_count']} | "
        f"missing_neutral={manifest['missing_neutral_count']} | admitted=0"
    )
    print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
