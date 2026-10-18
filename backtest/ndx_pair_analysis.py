"""Analyze v8f composition pairs and pre-register finalist sensitivity."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_envelope_analysis import paired_profile_effects
from backtest.ndx_experiment_analysis import (
    _read_verified_bundle,
    analyze_ndx_experiment,
)
from backtest.ndx_experiment_lab import _format_workbook, _localized_excel_frame
from backtest.ndx_incumbent_frontier import build_incumbent_frontier_bundle
from core.helpers import atomic_write_text


class NdxPairAnalysisError(ValueError):
    """Raised when pair evidence cannot support a sensitivity experiment."""


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def pair_effects(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    baseline_profile_id: str,
) -> pd.DataFrame:
    rows = []
    pairs = candidates[candidates["profile_id"].astype(str).str.startswith("pool22__")]
    for profile_id in sorted(pairs["profile_id"].astype(str).unique()):
        omitted = tuple(
            item.upper()
            for item in profile_id.split("__without_", 1)[1].split("_")
        )
        if len(omitted) != 2:
            raise NdxPairAnalysisError(f"pair profile id is invalid: {profile_id}")
        candidate_pairs, window_pairs, summary = paired_profile_effects(
            candidates,
            windows,
            challenger_id=profile_id,
            baseline_id=baseline_profile_id,
        )
        if len(candidate_pairs) != 1:
            raise NdxPairAnalysisError("pair search must have one rollup per profile")
        candidate = candidates[candidates["profile_id"].astype(str).eq(profile_id)].iloc[0]
        row = {
            "profile_id": profile_id,
            "omitted_ticker_1": omitted[0],
            "omitted_ticker_2": omitted[1],
            "omitted_tickers": ";".join(omitted),
            "concentration_guard_passed": bool(
                candidate.get("concentration_guard_passed")
            ),
            "incumbent_win_rate": candidate.get("incumbent_win_rate"),
            "incumbent_xirr_p50_margin": candidate.get(
                "incumbent_xirr_p50_margin"
            ),
            "incumbent_xirr_p10_margin": candidate.get(
                "incumbent_xirr_p10_margin"
            ),
            "incumbent_dd_relief_p50": candidate.get(
                "incumbent_dd_relief_p50"
            ),
            "incumbent_dd_relief_p90": candidate.get(
                "incumbent_dd_relief_p90"
            ),
            **summary,
        }
        for ticker in omitted:
            single_id = f"pool23__without_{ticker.lower()}"
            _, _, interaction = paired_profile_effects(
                candidates,
                windows,
                challenger_id=profile_id,
                baseline_id=single_id,
            )
            row[f"vs_single_{ticker}_p50_delta"] = interaction[
                "candidate_p50_return_delta_median"
            ]
            row[f"vs_single_{ticker}_p10_delta"] = interaction[
                "candidate_p10_return_delta_median"
            ]
            row[f"vs_single_{ticker}_window_return_rate"] = interaction[
                "window_return_improvement_rate"
            ]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        [
            "candidate_p50_return_delta_median",
            "candidate_p10_return_delta_median",
            "candidate_dd_p90_delta_median",
        ],
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)


def select_pair_finalists(effects: pd.DataFrame) -> pd.DataFrame:
    eligible = effects[
        effects["concentration_guard_passed"]
        & (effects["candidate_p50_return_delta_median"] > 0.0)
        & (effects["candidate_p10_return_delta_median"] > 0.0)
    ].copy()
    if eligible.empty:
        raise NdxPairAnalysisError("no return-improving pair is concentration compliant")
    role_specs = [
        (
            "best_median_return",
            "收益中位改善最大",
            [
                "candidate_p50_return_delta_median",
                "candidate_p10_return_delta_median",
                "candidate_dd_p90_delta_median",
            ],
        ),
        (
            "best_tail_return",
            "收益尾部改善最大",
            [
                "candidate_p10_return_delta_median",
                "candidate_p50_return_delta_median",
                "candidate_dd_p90_delta_median",
            ],
        ),
        (
            "best_drawdown_pressure",
            "回撤压力尾部最优",
            [
                "candidate_dd_p90_delta_median",
                "candidate_p10_return_delta_median",
                "candidate_p50_return_delta_median",
            ],
        ),
    ]
    selected = []
    used = set()
    for role, label, fields in role_specs:
        ordered = eligible.sort_values(fields, ascending=False, kind="stable")
        row = next(
            (
                item for _, item in ordered.iterrows()
                if str(item["profile_id"]) not in used
            ),
            None,
        )
        if row is None:
            raise NdxPairAnalysisError("pair finalist roles are not distinct")
        payload = row.to_dict()
        payload["analysis_role"] = role
        payload["analysis_role_cn"] = label
        used.add(str(row["profile_id"]))
        selected.append(payload)
    return pd.DataFrame(selected)


def stage7_sensitivity_spec(
    *,
    source_manifest_path: Path,
    shortlist_path: Path,
    pool24: pd.DataFrame,
    contract: dict,
    finalist_rows: pd.DataFrame,
    best_single_ticker: str,
) -> dict[str, Any]:
    ordered = pool24.sort_values("rank", kind="stable")
    tickers = ordered["ticker"].astype(str).str.upper().tolist()
    top1 = float(contract["incumbent_top1"])
    top3 = float(contract["incumbent_top3"])

    def profile(profile_id: str, omitted: tuple[str, ...]) -> dict[str, Any]:
        omitted_set = {ticker.upper() for ticker in omitted}
        return {
            "id": profile_id,
            "candidate_tickers": [
                ticker for ticker in tickers if ticker not in omitted_set
            ],
            "top_n": 12,
            "weight_mode": "source_weight",
            "rebalance_months": 6,
            "safe_weight": 0.26,
            "challenger_sleeve_weight": 1.0,
            "max_weight": top1,
            "min_weight": 0.02,
            "top_weight_count": 3,
            "top_weight_cap": top3,
            "selection_mode": "rank",
            "fundamental_score_weight": 0.25,
            "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
            "defense_mode": "static",
        }

    baseline_id = "pool24__q25__top12__source_top3_envelope_baseline"
    single_id = f"pool23__without_{best_single_ticker.lower()}"
    profiles = [profile(baseline_id, ()), profile(single_id, (best_single_ticker,))]
    role_map = {baseline_id: "baseline", single_id: "best_single"}
    for row in finalist_rows.itertuples(index=False):
        omitted = (str(row.omitted_ticker_1), str(row.omitted_ticker_2))
        profiles.append(profile(str(row.profile_id), omitted))
        role_map[str(row.profile_id)] = str(row.analysis_role)
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_composition_sensitivity_v8g",
        "research_question": (
            "Do role-distinct pair finalists retain their composition improvement "
            "across 1/2/3-year lookbacks and 5/10/25bp costs?"
        ),
        "research_only": True,
        "candidate_assets": "nasdaq_100_individual_securities",
        "qqq_role": "benchmark_only_not_candidate",
        "objective_contract": {
            "candidate_universe_source": "qqq_sec_nport_nasdaq100_proxy",
            "primary_target": "012922",
            "qqq_performance_role": "auxiliary_reference_only",
            "incumbent_role": "primary_competition_benchmark",
            "decision_benchmark": "current_config",
            "target_performance_role": "secondary_reference_only",
        },
        "direction_status": "active_iteration",
        "analysis_contract": {
            "component_family": "incumbent_composition_sensitivity",
            "research_stage": "pair_finalist_sensitivity",
            "baseline_profile_id": baseline_id,
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_v8f_manifest_sha256": _content_hash(source_manifest_path),
            "source_stage1_shortlists_sha256": _content_hash(shortlist_path),
            "profile_roles": role_map,
            "best_single_ticker": best_single_ticker.upper(),
            "finalist_profile_ids": finalist_rows["profile_id"].astype(str).tolist(),
            "sensitivity_lookback_years": [1, 2, 3],
            "sensitivity_trade_cost_bps": [5, 10, 25],
            "multiple_testing_policy": "finalists_only_no_locked_validation",
            "incumbent_top1": top1,
            "incumbent_top3": top3,
        },
        "output_dir": "data/cache/research/ndx_lab",
        "defaults": {
            "monthly": 3000,
            "total_cap": 37000,
            "local_only": True,
            "include_samples": True,
            "comparison_priority": "incumbent_first",
            "safe_annual": 0.04,
            "min_history_years": 0.5,
            "max_windows": 0,
        },
        "phases": [
            {
                "phase_id": "composition_sensitivity",
                "enabled": True,
                "role": "sensitivity",
                "rationale": (
                    "Re-run the baseline, best single and three role-distinct pairs "
                    "under every declared lookback/cost combination."
                ),
                "start": "2022-01-11",
                "end": "2024-06-30",
                "target": "012922",
                "min_years": 1.0,
                "step_months": 1,
                "shared_grid": {
                    "top_ns": [12],
                    "weight_modes": ["source_weight"],
                    "safe_weights": [0.26],
                    "rebalance_months": [6],
                    "max_weights": [top1],
                },
                "construction_profiles": profiles,
                "sweep": {
                    "lookback_years": [1, 2, 3],
                    "trade_cost_bps": [5, 10, 25],
                },
            },
            {
                "phase_id": "future_validation",
                "enabled": False,
                "role": "locked_validation",
                "rationale": (
                    "No held-out validation is consumed until sensitivity identifies "
                    "one stable composition rule."
                ),
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


def _curve_candidates(candidates: pd.DataFrame, finalists: pd.DataFrame) -> pd.DataFrame:
    baseline_id = "pool24__q25__top12__source_top3_envelope_baseline"
    single_id = "pool23__without_tmus"
    profile_ids = [baseline_id, single_id, *finalists["profile_id"].astype(str)]
    selected = candidates[candidates["profile_id"].astype(str).isin(profile_ids)].copy()
    if len(selected) != len(profile_ids):
        raise NdxPairAnalysisError("pair curve candidates are incomplete")
    labels = {
        baseline_id: "精确Top3候选池基线",
        single_id: "剔除 TMUS",
        **{
            str(row.profile_id): str(row.analysis_role_cn)
            + "（剔除 "
            + str(row.omitted_tickers).replace(";", "+")
            + "）"
            for row in finalists.itertuples(index=False)
        },
    }
    roles = {
        baseline_id: "composition_baseline",
        single_id: "best_single_ablation",
        **{
            str(row.profile_id): str(row.analysis_role)
            for row in finalists.itertuples(index=False)
        },
    }
    order = {profile_id: index for index, profile_id in enumerate(profile_ids)}
    selected["analysis_role"] = selected["profile_id"].map(roles)
    selected["analysis_role_cn"] = selected["profile_id"].map(labels)
    selected["_display_order"] = selected["profile_id"].map(order)
    return selected.sort_values("_display_order", kind="stable").drop(
        columns="_display_order"
    )


def _localized_curve_daily(frame: pd.DataFrame, payload: dict) -> pd.DataFrame:
    labels = {
        str(row["solution_id"]): str(row["label"])
        for row in payload.get("solutions") or []
    }
    target = str(payload.get("secondary_reference") or "012922")
    columns = {
        "date": "日期",
        "current_config_nav": "当前8只_净值",
        "current_config_drawdown": "当前8只_回撤",
        f"{target}_nav": f"{target}_净值",
        f"{target}_drawdown": f"{target}_回撤",
    }
    for solution_id, label in labels.items():
        columns[f"{solution_id}_nav"] = f"{label}_净值"
        columns[f"{solution_id}_drawdown"] = f"{label}_回撤"
    return frame.rename(columns=columns)


def build_pair_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    source_v8e_manifest_path: str | Path,
    shortlists_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    strategy_config_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(experiment_dir)
    manifest, raw = _read_verified_bundle(
        root, strategy_config_path=strategy_config_path
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("research_stage") != "pair_candidate_pool_ablation":
        raise NdxPairAnalysisError("experiment is not v8f pair search")
    v8e_manifest_path = Path(source_v8e_manifest_path)
    shortlist_path = Path(shortlists_path)
    if _content_hash(v8e_manifest_path) != contract.get(
        "source_v8e_manifest_sha256"
    ):
        raise NdxPairAnalysisError("source v8e manifest hash changed")
    if _content_hash(shortlist_path) != contract.get(
        "source_stage1_shortlists_sha256"
    ):
        raise NdxPairAnalysisError("stage1 shortlist hash changed")

    analysis_frames, _ = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=10.0,
        strategy_config_path=strategy_config_path,
    )
    candidates = analysis_frames["concentration"].copy()
    baseline_id = str(contract["baseline_profile_id"])
    effects = pair_effects(
        candidates,
        raw["windows"],
        baseline_profile_id=baseline_id,
    )
    finalists = select_pair_finalists(effects)
    pool24_all = pd.read_csv(shortlist_path)
    pool24 = pool24_all[pool24_all["shortlist_id"].astype(str).eq("pool24")]
    stage7 = stage7_sensitivity_spec(
        source_manifest_path=root / "manifest.json",
        shortlist_path=shortlist_path,
        pool24=pool24,
        contract=contract,
        finalist_rows=finalists,
        best_single_ticker="TMUS",
    )
    selected = _curve_candidates(candidates, finalists)
    selected_keys = selected[["profile_id", "lookback_years", "trade_cost_bps"]]
    selected_windows = raw["windows"].merge(
        selected_keys,
        on=["profile_id", "lookback_years", "trade_cost_bps"],
        how="inner",
        validate="many_to_one",
    )

    output = Path(output_dir) if output_dir else root / "analysis" / "pairs"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "effects": output / "pair_effects.csv",
        "finalists": output / "pair_finalists.csv",
        "windows": output / "finalist_windows.csv",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "stage7": output / "stage7_sensitivity_spec.yaml",
        "workbook": output / "v8f_pair_analysis.xlsx",
    }
    _atomic_csv(effects, paths["effects"])
    _atomic_csv(finalists, paths["finalists"])
    _atomic_csv(selected_windows, paths["windows"])
    atomic_write_text(
        paths["stage7"],
        yaml.safe_dump(stage7, allow_unicode=True, sort_keys=False),
    )
    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=10.0,
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_payload["research_stage"] = "v8f_pair_composition_search"
    curve_payload["frontier_conclusion"] = {
        "decision": "RUN_PAIR_FINALIST_SENSITIVITY",
        "finalist_roles": {
            str(row.analysis_role): str(row.profile_id)
            for row in finalists.itertuples(index=False)
        },
    }
    atomic_write_text(
        paths["curves"],
        json.dumps(
            curve_payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_scalar,
        ) + "\n",
    )
    curve_daily_cn = _localized_curve_daily(curve_daily, curve_payload)
    _atomic_csv(curve_daily_cn, paths["curve_daily"])

    summary_frame = pd.DataFrame([
        {"项目": "主竞争基准", "内容": "当前8只配置"},
        {"项目": "第二层参照", "内容": "012922"},
        {"项目": "二元组合数", "内容": len(effects)},
        {"项目": "集中度合规二元组合数", "内容": int(effects["concentration_guard_passed"].sum())},
        {"项目": "收益中位角色", "内容": finalists.iloc[0]["omitted_tickers"]},
        {"项目": "收益尾部角色", "内容": finalists.iloc[1]["omitted_tickers"]},
        {"项目": "回撤压力角色", "内容": finalists.iloc[2]["omitted_tickers"]},
        {"项目": "结论", "内容": "三个角色进入回看期与成本敏感性，不在单一切片选冠军"},
        {"项目": "下一步", "内容": "与原始基线和最佳单股TMUS同批完成9组敏感性"},
    ])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary_frame.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(effects)[0].to_excel(
                writer, sheet_name="全部二元组合", index=False
            )
            _localized_excel_frame(finalists)[0].to_excel(
                writer, sheet_name="敏感性入选方案", index=False
            )
            _localized_excel_frame(selected_windows)[0].to_excel(
                writer, sheet_name="入选方案逐窗口", index=False
            )
            curve_daily_cn.to_excel(writer, sheet_name="逐日曲线", index=False)
            _localized_excel_frame(analysis_frames["concentration_baseline"])[0].to_excel(
                writer, sheet_name="当前8只集中度", index=False
            )
            _localized_excel_frame(raw["versions"])[0].to_excel(
                writer, sheet_name="数据版本", index=False
            )
        _format_workbook(temporary)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()

    payload = {
        "schema_version": 1,
        "research_only": True,
        "source_experiment_id": manifest["experiment_id"],
        "source_manifest_sha256": _content_hash(root / "manifest.json"),
        "decision_priority": "incumbent_first",
        "candidate_rows": len(candidates),
        "concentration_compliant_rows": int(
            candidates["concentration_guard_passed"].fillna(False).sum()
        ),
        "finalists": [
            {
                key: _json_scalar(row.get(key))
                for key in (
                    "analysis_role",
                    "analysis_role_cn",
                    "profile_id",
                    "omitted_tickers",
                    "candidate_p50_return_delta_median",
                    "candidate_p10_return_delta_median",
                    "candidate_dd_p50_delta_median",
                    "candidate_dd_p90_delta_median",
                    "window_return_improvement_rate",
                    "window_dd_improvement_rate",
                )
            }
            for _, row in finalists.iterrows()
        ],
        "decision": "RUN_PAIR_FINALIST_SENSITIVITY",
        "stage7_profile_count": len(stage7["phases"][0]["construction_profiles"]),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
