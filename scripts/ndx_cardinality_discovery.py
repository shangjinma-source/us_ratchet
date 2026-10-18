r"""Build the point-in-time preflight for the variable-cardinality runner.

PowerShell/PyCharm:
    python -B scripts\ndx_cardinality_discovery.py --plan-only
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

from backtest.ndx_cardinality_discovery import (
    NdxCardinalityDiscoveryError,
    build_point_in_time_taxonomy_panel,
    build_training_job_plan,
    load_discovery_spec,
    monthly_selection_dates,
    point_in_time_cardinality_readiness,
    point_in_time_track_memberships,
    read_synthetic_cardinality_shard,
    read_synthetic_checkpoint,
    search_synthetic_cardinality,
    synthetic_fixture,
    synthetic_run_fingerprint,
    validate_discovery_spec,
    verify_plan_bundle,
    write_synthetic_cardinality_shard,
    write_synthetic_checkpoint,
)
from core.helpers import atomic_write_text
from data.versioning import file_sha256


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _load_event_gap_scope(manifest_path: Path) -> tuple[pd.DataFrame, Path, dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_key") != "ndx_event_gap_disposition_v1":
        raise NdxCardinalityDiscoveryError("event gap disposition dataset changed")
    if manifest.get("historical_backtest_allowed") is not False:
        raise NdxCardinalityDiscoveryError("event gap disposition unexpectedly allows backtest")
    if manifest.get("scope_lock_complete") is not True:
        raise NdxCardinalityDiscoveryError("event gap disposition scope is not locked")
    artifact = (manifest.get("artifacts") or {}).get("blocking_scope") or {}
    filename = str(artifact.get("filename") or "")
    if not filename or Path(filename).name != filename:
        raise NdxCardinalityDiscoveryError("event gap blocking scope filename is invalid")
    scope_path = manifest_path.parent / filename
    if file_sha256(scope_path) != str(artifact.get("sha256") or ""):
        raise NdxCardinalityDiscoveryError("event gap blocking scope hash mismatch")
    scope = pd.read_csv(scope_path, low_memory=False)
    if len(scope) != int(artifact.get("rows") or -1):
        raise NdxCardinalityDiscoveryError("event gap blocking scope row count changed")
    return scope, scope_path, manifest


def _load_historical_taxonomy_panel(
    taxonomy_manifest_path: Path,
    taxonomy_records_path: Path,
    plan_bundle: dict,
) -> tuple[pd.DataFrame, Path, Path, Path, dict, dict]:
    taxonomy_manifest = json.loads(taxonomy_manifest_path.read_text(encoding="utf-8"))
    if taxonomy_manifest.get("manifest_type") != "ndx_taxonomy_v2_bundle":
        raise NdxCardinalityDiscoveryError("unexpected taxonomy bundle manifest type")
    if taxonomy_manifest.get("historical_backfill_allowed") is not False:
        raise NdxCardinalityDiscoveryError("taxonomy bundle unexpectedly allows historical backfill")
    if (taxonomy_manifest.get("future_data_guard") or {}).get("passed") is not True:
        raise NdxCardinalityDiscoveryError("taxonomy future-data guard is not complete")
    artifact = (taxonomy_manifest.get("artifacts") or {}).get("records") or {}
    if artifact.get("filename") != taxonomy_records_path.name:
        raise NdxCardinalityDiscoveryError("taxonomy record filename changed")
    if taxonomy_records_path.parent != taxonomy_manifest_path.parent:
        raise NdxCardinalityDiscoveryError("taxonomy records must share the bundle directory")
    if file_sha256(taxonomy_records_path) != str(artifact.get("sha256") or ""):
        raise NdxCardinalityDiscoveryError("taxonomy record hash mismatch")
    records = pd.read_csv(taxonomy_records_path, low_memory=False)
    if len(records) != int(artifact.get("rows") or -1):
        raise NdxCardinalityDiscoveryError("taxonomy record row count changed")

    plan_input = (plan_bundle.get("input_files") or {}).get("spec") or {}
    plan_spec_path = Path(str(plan_input.get("path") or ""))
    if not plan_spec_path.is_absolute():
        raise NdxCardinalityDiscoveryError("base search-plan spec path is not absolute")
    if file_sha256(plan_spec_path) != str(plan_input.get("sha256") or ""):
        raise NdxCardinalityDiscoveryError("base search-plan spec hash mismatch")
    membership_input = next((
        item for item in (taxonomy_manifest.get("input_versions") or [])
        if item.get("source_name") == "ndx_point_in_time_constituents"
    ), None)
    if not membership_input or membership_input.get("manifest_verified") is not True:
        raise NdxCardinalityDiscoveryError("taxonomy membership source is not manifest verified")
    membership_path = Path(str(membership_input.get("path") or ""))
    if not membership_path.is_absolute():
        raise NdxCardinalityDiscoveryError("taxonomy membership source path is not absolute")
    if file_sha256(membership_path) != str(membership_input.get("content_sha256") or ""):
        raise NdxCardinalityDiscoveryError("taxonomy membership source hash mismatch")
    membership = pd.read_csv(membership_path, low_memory=False)
    if len(membership) != int(membership_input.get("row_count") or -1):
        raise NdxCardinalityDiscoveryError("taxonomy membership source row count changed")
    panel = build_point_in_time_taxonomy_panel(
        records, load_discovery_spec(plan_spec_path), membership
    )
    lifecycle_input = next((
        item for item in (taxonomy_manifest.get("input_versions") or [])
        if item.get("source_name") == "ndx_security_lifecycle_v1"
    ), None)
    if not lifecycle_input:
        raise NdxCardinalityDiscoveryError("taxonomy ticker lifecycle input is missing")
    lifecycle_path = Path(str(lifecycle_input.get("path") or ""))
    if not lifecycle_path.is_absolute():
        raise NdxCardinalityDiscoveryError("ticker lifecycle path is not absolute")
    if file_sha256(lifecycle_path) != str(lifecycle_input.get("content_sha256") or ""):
        raise NdxCardinalityDiscoveryError("ticker lifecycle hash mismatch")
    lifecycle = load_discovery_spec(lifecycle_path)
    return panel, plan_spec_path, membership_path, lifecycle_path, taxonomy_manifest, lifecycle


def _synthetic_checkpoint_coordinate(holding_count: int) -> dict:
    return {
        "universe_track": "synthetic_fixture",
        "selection_date": "SYNTHETIC_ALL_WINDOWS",
        "holding_count": int(holding_count),
        "shard_id": "0000",
    }


def _checkpoint_shard_path(output: Path, fingerprint: str, coordinate: dict) -> Path:
    return (
        output / "checkpoint_shards" / fingerprint[:16]
        / coordinate["universe_track"] / coordinate["selection_date"]
        / f"holding_count_{int(coordinate['holding_count']):04d}"
        / f"shard_{coordinate['shard_id']}.json"
    )


def build_preflight(args) -> dict:
    spec_path = _resolve(args.spec)
    manifest_path = _resolve(args.plan_manifest)
    universe_path = _resolve(args.universe)
    taxonomy_records_path = _resolve(args.taxonomy_records)
    taxonomy_manifest_path = _resolve(args.taxonomy_manifest)
    calendar_path = _resolve(args.calendar)
    output = _resolve(args.output_dir)
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    event_gap_manifest_path = _resolve(args.event_gap_manifest)
    protected_before = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }
    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    plan_bundle = verify_plan_bundle(manifest_path, universe_path, str(spec["base_plan_id"]))
    (
        universe, plan_spec_path, membership_path, lifecycle_path,
        taxonomy_manifest, ticker_lifecycle,
    ) = _load_historical_taxonomy_panel(
        taxonomy_manifest_path, taxonomy_records_path, plan_bundle
    )
    event_gap_scope, event_gap_scope_path, event_gap_manifest = _load_event_gap_scope(
        event_gap_manifest_path
    )
    calendar_frame = pd.read_csv(calendar_path, usecols=["Date"])
    history = spec["history_contract"]
    calendar = pd.DatetimeIndex(pd.to_datetime(calendar_frame["Date"])).normalize().unique().sort_values()
    selections = monthly_selection_dates(calendar, history["start_date"], history["end_date"])
    frames = [
        point_in_time_cardinality_readiness(
            universe, selections, calendar, track=track,
            horizon_days=int(history["primary_horizon_trading_days"]),
            minimum_windows=int(history["minimum_mature_windows_per_cardinality"]),
            event_gap_scope=event_gap_scope,
        )
        for track in spec["search_contract"]["tracks"]
    ]
    windows = pd.concat([item[0] for item in frames], ignore_index=True)
    coverage = pd.concat([item[1] for item in frames], ignore_index=True)
    memberships = pd.concat([
        point_in_time_track_memberships(
            universe, selections, track=track, ticker_lifecycle=ticker_lifecycle
        )
        for track in spec["search_contract"]["tracks"]
    ], ignore_index=True)
    memberships = memberships.merge(
        windows[[
            "universe_track", "selection_date", "membership_window_eligible",
            "event_gap_blocked", "event_gap_case_ids", "maturity_date",
        ]],
        on=["universe_track", "selection_date"],
        how="left",
        validate="many_to_one",
    )
    jobs = build_training_job_plan(
        memberships, windows, coverage,
        exact_limit=int(spec["search_contract"]["exact_enumeration_max_feasible_combinations"]),
    )
    output.mkdir(parents=True, exist_ok=True)
    window_path = output / "point_in_time_windows.csv"
    coverage_path = output / "cardinality_training_readiness.csv"
    membership_path_out = output / "point_in_time_eligible_securities.csv"
    job_plan_path = output / "training_job_plan.csv"
    workbook_path = output / "ndx_variable_cardinality_discovery_preflight.xlsx"
    windows.to_csv(window_path, index=False, encoding="utf-8-sig")
    coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")
    memberships.to_csv(membership_path_out, index=False, encoding="utf-8-sig")
    jobs.to_csv(job_plan_path, index=False, encoding="utf-8-sig")
    variable_ready = bool(
        coverage.loc[coverage["holding_count"].ge(2), "training_evaluation_ready"].any()
    )
    window_count_status = (
        "VARIABLE_CARDINALITY_WINDOW_COUNT_READY" if variable_ready
        else "INSUFFICIENT_POINT_IN_TIME_WINDOWS"
    )
    readiness_status = (
        "BLOCKED_HISTORICAL_MEMBERSHIP_EVENT_GAPS" if variable_ready
        else "BLOCKED_REAL_HISTORY_INSUFFICIENT_POINT_IN_TIME_WINDOWS"
    )
    summary = pd.DataFrame([
        {"项目": "运行角色", "值": spec["status"]},
        {"项目": "真实历史运行状态", "值": readiness_status},
        {"项目": "窗口数量状态", "值": window_count_status},
        {"项目": "持仓数>=2且满足窗口门的行", "值": int(coverage.loc[coverage["holding_count"].ge(2), "training_evaluation_ready"].sum())},
        {"项目": "组合计算范围", "值": "汇丰100%美股股票风险仓"},
        {"项目": "SGOV处理", "值": "排除出目标函数、候选权重和绩效比较"},
        {"项目": "外部指数底仓", "值": "约占全资产一半，仅作架构背景，不并入回测"},
        {"项目": "收益数据读取", "值": False},
        {"项目": "当前taxonomy回填历史", "值": False},
        {"项目": "精确NDX历史成员有效", "值": False},
        {"项目": "fresh OOS消费", "值": False},
        {"项目": "实盘晋级", "值": False},
        {"项目": "下一步", "值": "先开发synthetic smoke与可恢复搜索核心；真实前沿等待点时窗口/事件证据"},
    ])
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            memberships.to_excel(writer, sheet_name="point_in_time_members", index=False)
            jobs.to_excel(writer, sheet_name="training_job_dry_run", index=False)
            summary.to_excel(writer, sheet_name="摘要", index=False)
            coverage.to_excel(writer, sheet_name="逐持仓数训练就绪", index=False)
            windows.to_excel(writer, sheet_name="逐月点时可用窗口", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    protected_after = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }
    if protected_after != protected_before:
        raise NdxCardinalityDiscoveryError("protected config/state hash changed")
    payload = {
        "schema_version": 1,
        "manifest_type": "ndx_variable_cardinality_discovery_preflight",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": spec["status"],
        "readiness_status": readiness_status,
        "window_count_status": window_count_status,
        "return_data_read": False,
        "price_values_read": False,
        "calendar_dates_read": True,
        "historical_discovery_executed": False,
        "fresh_oos_consumed": False,
        "exact_ndx_membership_valid": False,
        "historical_backtest_allowed": False,
        "portfolio_scope": spec["result_contract"]["portfolio_scope"],
        "safe_leg_role": spec["result_contract"]["safe_leg_role"],
        "external_index_context": spec["result_contract"]["external_index_context"],
        "incumbent_role": spec["result_contract"]["incumbent_role"],
        "candidate_promotion_count": 0,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "protected_hashes_unchanged": True,
        "taxonomy_backfill_allowed": False,
        "taxonomy_membership_mode": "LATEST_MANIFEST_VERIFIED_NPORT_SNAPSHOT_AS_OF_SELECTION_DATE",
        "taxonomy_version": taxonomy_manifest.get("taxonomy_version"),
        "taxonomy_classified_panel_rows": int(
            universe["status"].astype(str).str.lower().eq("accepted").sum()
        ),
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": file_sha256(spec_path)},
            "plan_manifest": {"path": manifest_path.as_posix(), "sha256": file_sha256(manifest_path)},
            "base_current_universe": {"path": universe_path.as_posix(), "sha256": file_sha256(universe_path), "read_for_historical_membership": False},
            "base_search_plan_spec": {"path": plan_spec_path.as_posix(), "sha256": file_sha256(plan_spec_path)},
            "taxonomy_manifest": {"path": taxonomy_manifest_path.as_posix(), "sha256": file_sha256(taxonomy_manifest_path)},
            "taxonomy_records": {"path": taxonomy_records_path.as_posix(), "sha256": file_sha256(taxonomy_records_path), "panel_rows": len(universe)},
            "membership_observations": {"path": membership_path.as_posix(), "sha256": file_sha256(membership_path)},
            "ticker_lifecycle": {"path": lifecycle_path.as_posix(), "sha256": file_sha256(lifecycle_path)},
            "calendar": {"path": calendar_path.as_posix(), "sha256": file_sha256(calendar_path), "columns_read": ["Date"]},
            "event_gap_manifest": {"path": event_gap_manifest_path.as_posix(), "sha256": file_sha256(event_gap_manifest_path)},
            "event_gap_scope": {"path": event_gap_scope_path.as_posix(), "sha256": file_sha256(event_gap_scope_path), "rows": len(event_gap_scope)},
            "config": {"path": config_path.as_posix(), "sha256": protected_before["config"]},
            "state": {"path": state_path.as_posix(), "sha256": protected_before["state"]},
        },
        "artifacts": {
            "windows": {"path": window_path.as_posix(), "rows": len(windows), "sha256": file_sha256(window_path)},
            "readiness": {"path": coverage_path.as_posix(), "rows": len(coverage), "sha256": file_sha256(coverage_path)},
            "eligible_securities": {"path": membership_path_out.as_posix(), "rows": len(memberships), "sha256": file_sha256(membership_path_out)},
            "training_job_plan": {"path": job_plan_path.as_posix(), "rows": len(jobs), "sha256": file_sha256(job_plan_path)},
            "workbook": {"path": workbook_path.as_posix(), "rows": None, "sha256": file_sha256(workbook_path)},
        },
        "ready_cardinality_rows": int(coverage["training_evaluation_ready"].sum()),
        "blocked_cardinality_rows": int((~coverage["training_evaluation_ready"]).sum()),
        "variable_cardinality_training_ready": variable_ready,
        "event_gap_scope_lock_complete": bool(event_gap_manifest["scope_lock_complete"]),
        "event_gap_blocked_window_rows": int(windows["event_gap_blocked"].sum()),
        "event_gap_blocked_mature_window_rows": int(
            (windows["event_gap_blocked"] & windows["matured_horizon"]).sum()
        ),
        "real_history_execution_allowed": False,
        "training_job_count": len(jobs),
        "training_job_exact_count": int(jobs["planned_search_method"].eq("EXACT_ENUMERATION").sum()),
        "training_job_bounded_count": int(jobs["planned_search_method"].eq("MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND").sum()),
        "limitation": spec["point_in_time_contract"]["limitation"],
    }
    atomic_write_text(output / "manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def build_synthetic_smoke(args) -> dict:
    spec_path = _resolve(args.spec)
    output = _resolve(args.smoke_output_dir)
    config_path = _resolve(args.config)
    state_path = _resolve(args.state)
    protected_before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    spec = load_discovery_spec(spec_path)
    validate_discovery_spec(spec)
    contract = spec["synthetic_smoke_contract"]
    spec_hash = file_sha256(spec_path)
    fingerprint = synthetic_run_fingerprint(spec_hash, contract)
    universe, returns, target, incumbent = synthetic_fixture(
        seed=int(contract["seed"]), business_days=int(contract["business_days"])
    )
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output / "checkpoint.json"
    if args.resume and checkpoint_path.exists():
        checkpoint = read_synthetic_checkpoint(checkpoint_path, fingerprint)
    else:
        checkpoint = {
            "schema_version": 1,
            "status": "SYNTHETIC_ENGINE_VALIDATION_ONLY",
            "run_fingerprint": fingerprint,
            "spec_sha256": spec_hash,
            "completed_cardinalities": {},
            "complete": False,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "checkpoint_layout": "IMMUTABLE_CARDINALITY_SHARDS",
        }
    completed = checkpoint["completed_cardinalities"]
    max_k = int(universe["issuer_id"].nunique())
    migrated_legacy = False
    for key in sorted(list(completed), key=int):
        block = completed[key]
        if "shard_path" in block:
            continue
        holding_count = int(key)
        coordinate = _synthetic_checkpoint_coordinate(holding_count)
        shard_path = _checkpoint_shard_path(output, fingerprint, coordinate)
        shard_payload = {
            "schema_version": 1,
            "status": "SYNTHETIC_CARDINALITY_SHARD_ONLY",
            "run_fingerprint": fingerprint,
            "holding_count": holding_count,
            "checkpoint_coordinate": coordinate,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "audit": block["audit"],
            "rows": block["rows"],
        }
        write_synthetic_cardinality_shard(shard_path, shard_payload)
        completed[key] = {
            "holding_count": holding_count,
            "shard_path": shard_path.relative_to(output).as_posix(),
            "shard_sha256": file_sha256(shard_path),
            "evaluation_rows": len(block["rows"]),
            "checkpoint_coordinate": coordinate,
        }
        migrated_legacy = True
    if migrated_legacy:
        checkpoint["completed_cardinalities"] = completed
        checkpoint["checkpoint_layout"] = "IMMUTABLE_CARDINALITY_SHARDS"
        write_synthetic_checkpoint(checkpoint_path, checkpoint)
    processed_this_call = 0
    for holding_count in range(1, max_k + 1):
        key = str(holding_count)
        if key in completed:
            continue
        frame, audit = search_synthetic_cardinality(
            universe, returns, target, incumbent,
            holding_count=holding_count,
            exact_limit=int(contract["exact_enumeration_max_feasible_combinations"]),
            beam_width=int(contract["beam_width"]),
            window_days=int(contract["rolling_window_days"]),
            step_days=int(contract["rolling_step_days"]),
            transaction_cost_bps=float(contract["transaction_cost_bps"]),
            weight_specs=tuple(contract["weight_specifications"]),
            fit_days=int(contract["covariance_fit_days"]),
            shrinkage_intensity=float(contract["fixed_shrinkage_intensity"]),
            max_single_weight=float(contract["max_single_weight"]),
            min_single_weight=float(contract["min_single_weight"]),
            top_weight_cap=float(contract["top_weight_cap"]),
            minimum_effective_n_ratio=float(contract["minimum_effective_n_ratio"]),
            risk_chain_top1_cap=float(contract["risk_chain_top1_cap"]),
            turnover_anchor_strength=float(contract["turnover_anchor_strength"]),
            portfolio_cash_usd=float(contract["portfolio_cash_usd"]),
            minimum_cash_buffer_usd=float(contract["minimum_cash_buffer_usd"]),
            minimum_median_dollar_volume_usd=float(contract["minimum_median_dollar_volume_usd"]),
        )
        coordinate = _synthetic_checkpoint_coordinate(holding_count)
        shard_path = _checkpoint_shard_path(output, fingerprint, coordinate)
        shard_payload = {
            "schema_version": 1,
            "status": "SYNTHETIC_CARDINALITY_SHARD_ONLY",
            "run_fingerprint": fingerprint,
            "holding_count": holding_count,
            "checkpoint_coordinate": coordinate,
            "fresh_oos_consumed": False,
            "promotion_allowed": False,
            "audit": audit,
            "rows": frame.to_dict("records"),
        }
        write_synthetic_cardinality_shard(shard_path, shard_payload)
        completed[key] = {
            "holding_count": holding_count,
            "shard_path": shard_path.relative_to(output).as_posix(),
            "shard_sha256": file_sha256(shard_path),
            "evaluation_rows": len(frame),
            "checkpoint_coordinate": coordinate,
        }
        checkpoint["completed_cardinalities"] = completed
        checkpoint["complete"] = len(completed) == max_k
        write_synthetic_checkpoint(checkpoint_path, checkpoint)
        processed_this_call += 1
        if int(args.max_cardinalities or 0) > 0 and processed_this_call >= int(args.max_cardinalities):
            break

    candidate_rows = []
    audit_rows = []
    shard_artifacts = []
    for key in sorted(completed, key=int):
        block = completed[key]
        if "shard_path" in block:
            shard_path = output / str(block["shard_path"])
            shard = read_synthetic_cardinality_shard(
                shard_path, fingerprint, int(key), block.get("checkpoint_coordinate")
            )
            candidate_rows.extend(shard["rows"])
            audit_rows.append(shard["audit"])
            shard_artifacts.append({
                "holding_count": int(key),
                "path": shard_path.as_posix(),
                "rows": len(shard["rows"]),
                "sha256": file_sha256(shard_path),
                "checkpoint_coordinate": shard.get("checkpoint_coordinate"),
            })
        else:  # Legacy schema-1 checkpoint hydration for one-way migration.
            candidate_rows.extend(block["rows"])
            audit_rows.append(block["audit"])
    candidates = pd.DataFrame(candidate_rows)
    audits = pd.DataFrame(audit_rows)
    candidate_path = output / "synthetic_candidates.csv"
    audit_path = output / "synthetic_search_coverage.csv"
    workbook_path = output / "ndx_variable_cardinality_synthetic_smoke.xlsx"
    candidates.to_csv(candidate_path, index=False, encoding="utf-8-sig")
    audits.to_csv(audit_path, index=False, encoding="utf-8-sig")
    run_complete = len(completed) == max_k
    summary = pd.DataFrame([
        {"项目": "状态", "值": "SYNTHETIC_ENGINE_VALIDATION_COMPLETE" if run_complete else "SYNTHETIC_ENGINE_VALIDATION_PARTIAL"},
        {"项目": "合成证券/发行人数", "值": f"{len(universe)}/{max_k}"},
        {"项目": "已完成持仓数", "值": ";".join(sorted(completed, key=int))},
        {"项目": "组合计算范围", "值": "汇丰100%美股股票风险仓"},
        {"项目": "SGOV处理", "值": "排除出目标函数、候选权重和绩效比较"},
        {"项目": "外部指数底仓", "值": "约占全资产一半，仅作架构背景，不并入回测"},
        {"项目": "真实收益读取", "值": False},
        {"项目": "合成数据", "值": True},
        {"项目": "fresh OOS消费", "值": False},
        {"项目": "实盘晋级", "值": False},
        {"项目": "最优性用语", "值": "仅穷尽基数可称synthetic exact；beam只称当前已搜索前沿"},
    ])
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="摘要", index=False)
            audits.to_excel(writer, sheet_name="逐持仓数搜索覆盖", index=False)
            candidates.to_excel(writer, sheet_name="合成候选与前沿", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    protected_after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if protected_after != protected_before:
        raise NdxCardinalityDiscoveryError("protected config/state hash changed during synthetic smoke")
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_variable_cardinality_synthetic_smoke",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "SYNTHETIC_ENGINE_VALIDATION_COMPLETE" if run_complete else "SYNTHETIC_ENGINE_VALIDATION_PARTIAL",
        "run_fingerprint": fingerprint,
        "synthetic_data_only": True,
        "return_data_read": False,
        "real_return_data_read": False,
        "historical_discovery_executed": False,
        "fresh_oos_consumed": False,
        "candidate_promotion_count": 0,
        "promotion_allowed": False,
        "live_config_changed": False,
        "state_changed": False,
        "today_advice_changed": False,
        "protected_hashes_unchanged": True,
        "holding_count_fixed": False,
        "holding_count_range": f"1..{max_k}",
        "portfolio_scope": spec["result_contract"]["portfolio_scope"],
        "safe_leg_role": spec["result_contract"]["safe_leg_role"],
        "external_index_context": spec["result_contract"]["external_index_context"],
        "incumbent_role": spec["result_contract"]["incumbent_role"],
        "completed_cardinalities": sorted(int(key) for key in completed),
        "all_cardinalities_complete": run_complete,
        "checkpoint_layout": "IMMUTABLE_CARDINALITY_SHARDS",
        "checkpoint_shard_count": len(shard_artifacts),
        "search_modes": sorted(audits["search_mode"].unique().tolist()) if not audits.empty else [],
        "approximate_results_use_optimal_language": False,
        "inputs": {
            "spec": {"path": spec_path.as_posix(), "sha256": spec_hash},
            "engine": {"path": (ROOT / "backtest/ndx_cardinality_discovery.py").as_posix(), "sha256": file_sha256(ROOT / "backtest/ndx_cardinality_discovery.py")},
            "config": {"path": config_path.as_posix(), "sha256": protected_before["config"]},
            "state": {"path": state_path.as_posix(), "sha256": protected_before["state"]},
        },
        "artifacts": {
            "checkpoint": {"path": checkpoint_path.as_posix(), "sha256": file_sha256(checkpoint_path)},
            "checkpoint_shards": shard_artifacts,
            "candidates": {"path": candidate_path.as_posix(), "rows": len(candidates), "sha256": file_sha256(candidate_path)},
            "coverage": {"path": audit_path.as_posix(), "rows": len(audits), "sha256": file_sha256(audit_path)},
            "workbook": {"path": workbook_path.as_posix(), "rows": None, "sha256": file_sha256(workbook_path)},
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="NDX不固定持仓数训练发现运行器：点时窗口preflight")
    parser.add_argument("--spec", default="config/ndx_cardinality_discovery_v1.yaml")
    parser.add_argument("--plan-manifest", default="data/cache/research/ndx_variable_cardinality_search_plan_v1/manifest.json")
    parser.add_argument("--universe", default="data/cache/research/ndx_variable_cardinality_search_plan_v1/technology_search_universe.csv")
    parser.add_argument("--taxonomy-records", default="data/cache/candidate_pools/ndx_taxonomy_v2/taxonomy_records.csv")
    parser.add_argument("--taxonomy-manifest", default="data/cache/candidate_pools/ndx_taxonomy_v2/manifest.json")
    parser.add_argument("--calendar", default="data/cache/QQQ.csv")
    parser.add_argument("--event-gap-manifest", default="data/cache/candidate_pools/ndx_history/event_gap_disposition/manifest.json")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_variable_cardinality_discovery_v1")
    parser.add_argument("--smoke-output-dir", default="data/cache/research/ndx_variable_cardinality_discovery_synthetic_smoke_v1")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-cardinalities", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = build_preflight(args) if args.plan_only else build_synthetic_smoke(args)
    except (NdxCardinalityDiscoveryError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"不固定持仓数训练发现preflight失败: {exc}", file=sys.stderr)
        return 2
    if args.plan_only:
        print(
            "不固定持仓数训练发现preflight完成 | "
            f"ready={result['ready_cardinality_rows']} | blocked={result['blocked_cardinality_rows']} | "
            f"status={result['readiness_status']} | return_data_read=False | promotion_allowed=False"
        )
        print(f"Manifest: {_resolve(args.output_dir) / 'manifest.json'}")
    else:
        print(
            "不固定持仓数synthetic smoke完成 | "
            f"complete={result['all_cardinalities_complete']} | "
            f"holding_count={result['holding_count_range']} | promotion_allowed=False"
        )
        print(f"Manifest: {_resolve(args.smoke_output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
