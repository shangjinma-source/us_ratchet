"""Register or evaluate immutable v11 stage-1 forward cohorts."""
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

from backtest.ndx_marginal_forward import (  # noqa: E402
    NdxMarginalForwardError,
    append_cohort_index,
    build_cohort,
    build_cohort_curve_points,
    build_maturity_summary,
    evaluate_cohort,
    load_forward_spec,
    read_cohort_index,
)
from core.helpers import atomic_write_text  # noqa: E402
from data.versioning import file_sha256, utc_now_iso, write_dataset_manifest  # noqa: E402


def _resolve(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _artifact(path: Path, rows: int | None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "sha256": file_sha256(path), "bytes": path.stat().st_size}


def register(args) -> dict:
    output = _resolve(args.output_dir)
    existing_index = read_cohort_index(output / "cohort_index.jsonl")
    if existing_index and not any(
        row.get("observation_date") == args.observation_date for row in existing_index
    ):
        previous = pd.Timestamp(existing_index[-1]["observation_date"])
        observed = pd.Timestamp(args.observation_date)
        minimum = previous + pd.DateOffset(months=6)
        if observed < minimum:
            raise NdxMarginalForwardError(
                f"observation interval is below six months: previous={previous.date()} minimum={minimum.date()}"
            )
    cohort, manifest = build_cohort(
        observation_date=args.observation_date,
        shortlist_path=_resolve(args.shortlist),
        actions_path=_resolve(args.actions),
        config_path=_resolve(args.config),
        spec_path=_resolve(args.spec),
        imported_seed=bool(args.import_existing_seed),
    )
    cohort_dir = output / "observations" / args.observation_date
    cohort_dir.mkdir(parents=True, exist_ok=True)
    cohort_path = cohort_dir / "cohort_actions.csv"
    manifest_path = cohort_dir / "manifest.json"
    if cohort_path.exists() or manifest_path.exists():
        if not cohort_path.exists() or not manifest_path.exists():
            raise NdxMarginalForwardError("partial cohort directory already exists")
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("cohort_content_sha256") != manifest["cohort_content_sha256"]:
            raise NdxMarginalForwardError("immutable cohort already exists with different content")
    else:
        cohort.to_csv(cohort_path, index=False, encoding="utf-8-sig")
        manifest["cohort_csv_sha256"] = file_sha256(cohort_path)
        atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        write_dataset_manifest(
            cohort_path,
            dataset_type="ndx_marginal_forward",
            dataset_key=f"cohort_actions_{args.observation_date}",
            source="frozen_stage1_actions",
            fetched_at_evidence="registration_utc",
            row_count=len(cohort),
            data_start=args.observation_date,
            data_end=args.observation_date,
            extra={
                "return_data_read": False,
                "fresh_oos_eligible": manifest["fresh_oos_eligible"],
                "live_config_changed": False,
                "state_changed": False,
                "today_advice_changed": False,
            },
        )
    record = append_cohort_index(output / "cohort_index.jsonl", {
        "schema_version": 1,
        "observation_date": args.observation_date,
        "cohort_origin": manifest["cohort_origin"],
        "fresh_oos_eligible": manifest["fresh_oos_eligible"],
        "cohort_manifest_path": manifest_path.resolve().as_posix(),
        "cohort_manifest_sha256": file_sha256(manifest_path),
        "cohort_csv_sha256": file_sha256(cohort_path),
        "action_count": len(cohort),
    })
    return {"manifest": manifest, "index_record": record, "cohort_path": cohort_path.as_posix()}


def evaluate(args) -> dict:
    output = _resolve(args.output_dir)
    spec = load_forward_spec(_resolve(args.spec))
    evaluation_contract = spec["evaluation_contract"]
    horizons = list(evaluation_contract["diagnostic_horizons_trading_days"]) + [
        int(evaluation_contract["primary_horizon_trading_days"])
    ]
    evaluations = []
    curve_frames = []
    input_rows = []
    price_tickers: set[str] = set()
    target_path = _resolve(args.target_nav)
    target_sidecar = target_path.with_name(target_path.name + ".manifest.json")
    if not target_path.exists() or not target_sidecar.exists():
        raise NdxMarginalForwardError("012922 target NAV or sidecar is missing")
    target_manifest = json.loads(target_sidecar.read_text(encoding="utf-8"))
    if target_manifest.get("content_sha256") != file_sha256(target_path):
        raise NdxMarginalForwardError("012922 target NAV hash mismatch")
    target_nav = pd.read_csv(target_path)
    if not {"Date", "Close"}.issubset(target_nav.columns):
        raise NdxMarginalForwardError("012922 target NAV columns missing")
    target_nav["Date"] = pd.to_datetime(target_nav["Date"], errors="coerce")
    target_nav["Close"] = pd.to_numeric(target_nav["Close"], errors="coerce")
    target_nav = target_nav.dropna(subset=["Date", "Close"]).drop_duplicates("Date").sort_values("Date").set_index("Date")
    for record in read_cohort_index(output / "cohort_index.jsonl"):
        manifest_path = Path(record["cohort_manifest_path"])
        cohort_path = manifest_path.parent / "cohort_actions.csv"
        if file_sha256(manifest_path) != record["cohort_manifest_sha256"]:
            raise NdxMarginalForwardError(f"cohort manifest changed: {manifest_path}")
        if file_sha256(cohort_path) != record["cohort_csv_sha256"]:
            raise NdxMarginalForwardError(f"cohort actions changed: {cohort_path}")
        cohort_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (cohort_manifest.get("spec") or {}).get("sha256") != spec["sha256"]:
            raise NdxMarginalForwardError(
                f"cohort evaluation spec identity changed: {manifest_path}"
            )
        cohort = pd.read_csv(cohort_path, low_memory=False, keep_default_na=False)
        if not cohort.empty:
            price_tickers.update(json.loads(str(cohort.iloc[0]["incumbent_weights_json"])))
            price_tickers.update(str(value) for value in cohort["ticker"] if str(value).strip())
        frame = evaluate_cohort(
            cohort,
            price_cache_dir=_resolve(args.price_cache_dir),
            horizons=horizons,
            transaction_cost_bps=float(evaluation_contract["modeled_transaction_cost_bps"]),
            target_nav=target_nav,
            start_offsets_months=list(evaluation_contract["contribution_start_offsets_months"]),
        )
        evaluations.append(frame)
        curve_frames.append(build_cohort_curve_points(
            cohort,
            price_cache_dir=_resolve(args.price_cache_dir),
            transaction_cost_bps=float(
                evaluation_contract["modeled_transaction_cost_bps"]
            ),
            target_nav=target_nav,
            start_offset_months=0,
            primary_horizon=int(
                evaluation_contract["primary_horizon_trading_days"]
            ),
        ))
        input_rows.append({
            "observation_date": record["observation_date"],
            "fresh_oos_eligible": record["fresh_oos_eligible"],
            "cohort_manifest_sha256": record["cohort_manifest_sha256"],
            "cohort_csv_sha256": record["cohort_csv_sha256"],
        })
    all_evaluations = pd.concat(evaluations, ignore_index=True) if evaluations else pd.DataFrame()
    curve_points = (
        pd.concat(curve_frames, ignore_index=True)
        if curve_frames else pd.DataFrame()
    )
    summary = build_maturity_summary(
        all_evaluations,
        primary_horizon=int(evaluation_contract["primary_horizon_trading_days"]),
        minimum_windows=int(evaluation_contract["minimum_paired_primary_windows"]),
    )
    report_dir = output / "latest_evaluation"
    report_dir.mkdir(parents=True, exist_ok=True)
    first_horizon = min(horizons)
    interim_snapshot = all_evaluations.loc[
        all_evaluations["window_start_offset_months"].eq(0)
        & all_evaluations["horizon_trading_days"].eq(first_horizon)
    ].copy() if not all_evaluations.empty else pd.DataFrame()
    if not interim_snapshot.empty:
        interim_snapshot["evidence_role"] = "INTERIM_MONITORING_ONLY_NOT_ADMISSION_EVIDENCE"
        interim_snapshot["display_return_delta_vs_incumbent"] = interim_snapshot[
            "return_delta_vs_incumbent"
        ].where(
            interim_snapshot["mature"], interim_snapshot["interim_return_delta_vs_incumbent"]
        )
        interim_snapshot["display_dd_cost_vs_incumbent"] = interim_snapshot[
            "dd_cost_vs_incumbent"
        ].where(
            interim_snapshot["mature"], interim_snapshot["interim_dd_cost_vs_incumbent"]
        )
        interim_snapshot = interim_snapshot.sort_values(
            ["display_return_delta_vs_incumbent", "target_candidate_share", "ticker"],
            ascending=[False, False, True],
            na_position="last",
        )
    evaluation_path = report_dir / "cohort_evaluations.csv"
    summary_path = report_dir / "maturity_summary.csv"
    inputs_path = report_dir / "cohort_inputs.csv"
    price_inputs_path = report_dir / "price_inputs.csv"
    interim_path = report_dir / "interim_snapshot.csv"
    curves_path = report_dir / "curve_points.csv"
    all_evaluations.to_csv(evaluation_path, index=False, encoding="utf-8-sig")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(input_rows).to_csv(inputs_path, index=False, encoding="utf-8-sig")
    price_input_rows = []
    for ticker in sorted(price_tickers):
        path = _resolve(args.price_cache_dir) / f"{ticker}.csv"
        frame = pd.read_csv(path, usecols=["Date"])
        dates = pd.to_datetime(frame["Date"], errors="coerce").dropna()
        price_input_rows.append({
            "ticker": ticker,
            "path": path.resolve().as_posix(),
            "sha256": file_sha256(path),
            "rows": len(frame),
            "data_start": dates.min().strftime("%Y-%m-%d") if not dates.empty else None,
            "data_end": dates.max().strftime("%Y-%m-%d") if not dates.empty else None,
        })
    price_inputs = pd.DataFrame(price_input_rows)
    price_inputs.to_csv(price_inputs_path, index=False, encoding="utf-8-sig")
    interim_snapshot.to_csv(interim_path, index=False, encoding="utf-8-sig")
    curve_points.to_csv(curves_path, index=False, encoding="utf-8-sig")
    workbook = report_dir / "ndx_marginal_forward_evaluation.xlsx"
    temporary = report_dir / "ndx_marginal_forward_evaluation.tmp.xlsx"
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            pd.DataFrame([
                {"项目": "状态", "值": "WAITING_FOR_FRESH_PRIMARY_COHORTS"},
                {"项目": "已登记批次", "值": len(input_rows)},
                {"项目": "fresh OOS批次", "值": sum(bool(row["fresh_oos_eligible"]) for row in input_rows)},
                {"项目": "主观察期交易日", "值": evaluation_contract["primary_horizon_trading_days"]},
                {"项目": "最低成熟fresh配对窗口", "值": evaluation_contract["minimum_paired_primary_windows"]},
                {"项目": "阶段2解锁", "值": False},
                {"项目": "配置/state/今日建议改变", "值": False},
            ]).to_excel(writer, sheet_name="摘要", index=False)
            summary.to_excel(writer, sheet_name="成熟度与准入", index=False)
            all_evaluations.to_excel(writer, sheet_name="各批次配对结果", index=False)
            pd.DataFrame(input_rows).to_excel(writer, sheet_name="批次输入哈希", index=False)
            price_inputs.to_excel(writer, sheet_name="价格输入哈希", index=False)
            interim_snapshot.to_excel(writer, sheet_name="期中观察非准入证据", index=False)
            curve_points.to_excel(writer, sheet_name="前向曲线非准入证据", index=False)
        os.replace(temporary, workbook)
    finally:
        if temporary.exists():
            temporary.unlink()
    common_extra = {
        "return_data_read": True,
        "return_data_role": "forward_outcome_maturity_check",
        "candidate_admission_count": 0,
        "stage_2_unlocked": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
    }
    for key, path, rows in (
        ("cohort_evaluations", evaluation_path, len(all_evaluations)),
        ("maturity_summary", summary_path, len(summary)),
        ("cohort_inputs", inputs_path, len(input_rows)),
        ("price_inputs", price_inputs_path, len(price_inputs)),
        ("interim_snapshot", interim_path, len(interim_snapshot)),
        ("curve_points", curves_path, len(curve_points)),
    ):
        write_dataset_manifest(
            path,
            dataset_type="ndx_marginal_forward_evaluation",
            dataset_key=key,
            source="immutable_forward_cohorts_and_versioned_price_caches",
            fetched_at_evidence="evaluation_utc",
            row_count=rows,
            extra=common_extra,
        )
    write_dataset_manifest(
        workbook,
        dataset_type="ndx_marginal_forward_evaluation_workbook",
        dataset_key="latest_evaluation",
        source="immutable_forward_cohorts_and_versioned_price_caches",
        fetched_at_evidence="evaluation_utc",
        row_count=len(all_evaluations),
        extra=common_extra,
    )
    fresh_primary_mature = 0
    if not all_evaluations.empty:
        mature_primary = all_evaluations.loc[
            all_evaluations["fresh_oos_eligible"]
            & all_evaluations["mature"]
            & all_evaluations["horizon_trading_days"].eq(
                int(evaluation_contract["primary_horizon_trading_days"])
            )
        ]
        if not mature_primary.empty:
            fresh_primary_mature = int(mature_primary.groupby("action_id").size().max())
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_marginal_forward_evaluation",
        "generated_at": utc_now_iso(),
        "status": "WAITING_FOR_FRESH_PRIMARY_COHORTS",
        "registered_cohorts": len(input_rows),
        "fresh_oos_cohorts": sum(bool(row["fresh_oos_eligible"]) for row in input_rows),
        "fresh_primary_mature_windows_max_per_action": fresh_primary_mature,
        "minimum_required_fresh_primary_windows": evaluation_contract["minimum_paired_primary_windows"],
        "primary_horizon_trading_days": evaluation_contract["primary_horizon_trading_days"],
        "modeled_transaction_cost_bps": evaluation_contract["modeled_transaction_cost_bps"],
        "candidate_admission_count": 0,
        "incumbent_gate_evaluated": False,
        "target_012922_gate_evaluated": False,
        "stage_2_unlocked": False,
        "return_data_read": True,
        "return_data_role": "forward_outcome_maturity_check",
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "spec_sha256": spec["sha256"],
        "target_012922_version": {
            "path": target_path.as_posix(),
            "sha256": file_sha256(target_path),
            "version_id": target_manifest.get("version_id"),
            "data_end": target_manifest.get("data_end"),
        },
        "artifacts": {
            "evaluations": _artifact(evaluation_path, len(all_evaluations)),
            "summary": _artifact(summary_path, len(summary)),
            "inputs": _artifact(inputs_path, len(input_rows)),
            "price_inputs": _artifact(price_inputs_path, len(price_inputs)),
            "interim_snapshot": _artifact(interim_path, len(interim_snapshot)),
            "curve_points": _artifact(curves_path, len(curve_points)),
            "workbook": _artifact(workbook, None),
        },
    }
    atomic_write_text(report_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX v11阶段1不可回填前向观察")
    sub = parser.add_subparsers(dest="command", required=True)
    register_parser = sub.add_parser("register", help="冻结一个观察批次")
    register_parser.add_argument("--observation-date", required=True)
    register_parser.add_argument("--import-existing-seed", action="store_true")
    evaluate_parser = sub.add_parser("evaluate", help="评估所有已登记批次成熟度")
    for child in (register_parser, evaluate_parser):
        child.add_argument("--spec", default="config/ndx_marginal_forward_v1.yaml")
        child.add_argument("--output-dir", default="data/cache/research/ndx_marginal_forward_v1")
    register_parser.add_argument("--shortlist", default="data/cache/research/ndx_v11_current_competition_v1/risk_chain_shortlist.csv")
    register_parser.add_argument("--actions", default="data/cache/research/ndx_marginal_stage1_v1/allocation_actions.csv")
    register_parser.add_argument("--config", default="config/config.yaml")
    evaluate_parser.add_argument("--price-cache-dir", default="data/cache")
    evaluate_parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    args = parser.parse_args()
    try:
        result = register(args) if args.command == "register" else evaluate(args)
    except (NdxMarginalForwardError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"NDX阶段1前向观察失败: {exc}", file=sys.stderr)
        return 2
    if args.command == "register":
        manifest = result["manifest"]
        print(
            f"前向批次已冻结 | date={manifest['observation_date']} | "
            f"origin={manifest['cohort_origin']} | fresh={manifest['fresh_oos_eligible']} | "
            "admitted=0"
        )
    else:
        print(
            f"前向成熟度完成 | cohorts={result['registered_cohorts']} | "
            f"fresh_mature_windows={result['fresh_primary_mature_windows_max_per_action']} | "
            "stage2_unlocked=False"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
