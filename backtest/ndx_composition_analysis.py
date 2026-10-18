"""Analyze v8e single-stock ablations and generate a bounded pair search."""
from __future__ import annotations

import hashlib
import itertools
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


class NdxCompositionAnalysisError(ValueError):
    """Raised when composition evidence cannot support the next beam step."""


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


def ablation_effects(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    baseline_profile_id: str,
    shortlist: pd.DataFrame,
) -> pd.DataFrame:
    """Pair every single-name ablation with the unchanged pool24 baseline."""
    metadata = shortlist.set_index(shortlist["ticker"].astype(str).str.upper())
    rows = []
    ablations = candidates[
        ~candidates["profile_id"].astype(str).eq(baseline_profile_id)
    ]
    for profile_id in sorted(ablations["profile_id"].astype(str).unique()):
        marker = "__without_"
        if marker not in profile_id:
            raise NdxCompositionAnalysisError(
                f"ablation profile does not identify its omitted ticker: {profile_id}"
            )
        omitted = profile_id.split(marker, 1)[1].upper()
        if omitted not in metadata.index:
            raise NdxCompositionAnalysisError(
                f"omitted ticker is not in frozen pool24: {omitted}"
            )
        candidate_pairs, window_pairs, summary = paired_profile_effects(
            candidates,
            windows,
            challenger_id=profile_id,
            baseline_id=baseline_profile_id,
        )
        if len(candidate_pairs) != 1:
            raise NdxCompositionAnalysisError(
                "single-ablation stage must have one candidate pair per profile"
            )
        candidate = candidates[
            candidates["profile_id"].astype(str).eq(profile_id)
        ].iloc[0]
        changed = (
            window_pairs["incumbent_xirr_margin_delta"].abs() > 1e-12
        ) | (window_pairs["incumbent_dd_relief_delta"].abs() > 1e-12)
        evidence = metadata.loc[omitted]
        if isinstance(evidence, pd.DataFrame):
            raise NdxCompositionAnalysisError(
                f"frozen pool24 contains duplicate ticker {omitted}"
            )
        row = {
            "profile_id": profile_id,
            "omitted_ticker": omitted,
            "pool_rank": evidence.get("rank"),
            "sic2": evidence.get("sic2"),
            "sic4": evidence.get("sic4"),
            "sic_description": evidence.get("sic_description"),
            "sic_division": evidence.get("sic_division"),
            "evidence_score": evidence.get("evidence_score"),
            "current_strategy_member": evidence.get("current_strategy_member"),
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
            "changed_window_rate": float(changed.mean()),
            **summary,
        }
        row["pair_search_eligible"] = bool(
            row["concentration_guard_passed"]
            and row["candidate_p50_return_delta_median"] > 0.0
            and row["candidate_p10_return_delta_median"] > 0.0
            and row["window_return_improvement_rate"] > 0.50
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        [
            "pair_search_eligible",
            "candidate_p50_return_delta_median",
            "candidate_p10_return_delta_median",
            "window_return_improvement_rate",
        ],
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)


def stage6_pair_search_spec(
    *,
    source_manifest_path: Path,
    shortlist_path: Path,
    pool24: pd.DataFrame,
    contract: dict,
    selected_tickers: list[str],
) -> dict[str, Any]:
    ordered = pool24.sort_values("rank", kind="stable")
    tickers = ordered["ticker"].astype(str).str.upper().tolist()
    rank = {ticker: index for index, ticker in enumerate(tickers)}
    selected = sorted({str(ticker).upper() for ticker in selected_tickers}, key=rank.get)
    if len(selected) < 2 or any(ticker not in rank for ticker in selected):
        raise NdxCompositionAnalysisError("pair-search seed tickers are invalid")
    top1 = float(contract["incumbent_top1"])
    top3 = float(contract["incumbent_top3"])

    def profile(profile_id: str, omitted: tuple[str, ...]) -> dict[str, Any]:
        candidates = [ticker for ticker in tickers if ticker not in set(omitted)]
        return {
            "id": profile_id,
            "candidate_tickers": candidates,
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
    profiles = [profile(baseline_id, ())]
    profiles.extend(
        profile(f"pool23__without_{ticker.lower()}", (ticker,))
        for ticker in selected
    )
    pairs = list(itertools.combinations(selected, 2))
    profiles.extend(
        profile(
            "pool22__without_" + "_".join(ticker.lower() for ticker in pair),
            pair,
        )
        for pair in pairs
    )
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_composition_pairs_v8f",
        "research_question": (
            "Do pair exclusions among robust single-ablation seeds improve the "
            "exact-Top3 pool24 challenger beyond each single exclusion?"
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
            "component_family": "incumbent_composition_pair_search",
            "research_stage": "pair_candidate_pool_ablation",
            "baseline_profile_id": baseline_id,
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_v8e_manifest_sha256": _content_hash(source_manifest_path),
            "source_stage1_shortlists_sha256": _content_hash(shortlist_path),
            "source_pool_id": "pool24",
            "single_seed_rule": (
                "p50_delta>0 and p10_delta>0 and paired_window_return_win_rate>0.5"
            ),
            "single_seed_tickers": selected,
            "single_seed_count": len(selected),
            "pair_count": len(pairs),
            "search_policy": "baseline_plus_selected_singles_plus_all_seed_pairs",
            "multiple_testing_policy": "beam_search_training_only_no_promotion",
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
                "phase_id": "pair_ablation_training",
                "enabled": True,
                "role": "exploratory_training",
                "rationale": (
                    "Re-run the unchanged baseline and every selected single beside "
                    "all seed pairs so pair interaction is measured in one engine version."
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
                "sweep": {"lookback_years": [3], "trade_cost_bps": [10]},
            },
            {
                "phase_id": "future_sensitivity",
                "enabled": False,
                "role": "sensitivity",
                "rationale": (
                    "Only pair finalists supported by interaction evidence are swept "
                    "across lookbacks and costs."
                ),
                "start": None,
                "end": None,
                "target": "012922",
                "shared_grid": {
                    "top_ns": [12],
                    "weight_modes": ["source_weight"],
                    "safe_weights": [0.26],
                    "rebalance_months": [6],
                    "max_weights": [top1],
                },
                "construction_profiles": [profiles[0]],
                "sweep": {"lookback_years": [3], "trade_cost_bps": [10]},
            },
            {
                "phase_id": "future_validation",
                "enabled": False,
                "role": "locked_validation",
                "rationale": "Validation remains closed during beam search.",
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


def _curve_candidates(candidates: pd.DataFrame, effects: pd.DataFrame) -> pd.DataFrame:
    seeds = effects[effects["pair_search_eligible"]].sort_values(
        ["candidate_p50_return_delta_median", "candidate_p10_return_delta_median"],
        ascending=False,
        kind="stable",
    )
    profile_ids = [
        "pool24__q25__top12__source_top3_envelope_baseline",
        *seeds["profile_id"].astype(str).tolist(),
    ]
    selected = candidates[candidates["profile_id"].astype(str).isin(profile_ids)].copy()
    if len(selected) != len(profile_ids):
        raise NdxCompositionAnalysisError("key ablation curve evidence is incomplete")
    order = {profile_id: index for index, profile_id in enumerate(profile_ids)}
    selected["analysis_role"] = selected["profile_id"].map(
        lambda value: "composition_baseline"
        if value == profile_ids[0]
        else f"omit_{str(value).split('__without_', 1)[1]}"
    )
    selected["analysis_role_cn"] = selected["profile_id"].map(
        lambda value: "精确Top3候选池基线"
        if value == profile_ids[0]
        else f"剔除 {str(value).split('__without_', 1)[1].upper()}"
    )
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


def build_composition_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    source_v8d_manifest_path: str | Path,
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
    if contract.get("research_stage") != "single_stock_candidate_pool_ablation":
        raise NdxCompositionAnalysisError("experiment is not v8e single ablation")
    if contract.get("decision_priority") != "incumbent_first":
        raise NdxCompositionAnalysisError("v8e is not incumbent-first")
    v8d_manifest_path = Path(source_v8d_manifest_path)
    shortlist_path = Path(shortlists_path)
    if _content_hash(v8d_manifest_path) != contract.get(
        "source_v8d_manifest_sha256"
    ):
        raise NdxCompositionAnalysisError("source v8d manifest hash changed")
    if _content_hash(shortlist_path) != contract.get(
        "source_stage1_shortlists_sha256"
    ):
        raise NdxCompositionAnalysisError("stage1 shortlist hash changed")

    analysis_frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=10.0,
        strategy_config_path=strategy_config_path,
    )
    candidates = analysis_frames["concentration"].copy()
    shortlist = pd.read_csv(shortlist_path)
    pool24 = shortlist[shortlist["shortlist_id"].astype(str).eq("pool24")]
    baseline_id = str(contract["baseline_profile_id"])
    effects = ablation_effects(
        candidates,
        raw["windows"],
        baseline_profile_id=baseline_id,
        shortlist=pool24,
    )
    seeds = effects[effects["pair_search_eligible"]].copy()
    if len(seeds) < 2:
        raise NdxCompositionAnalysisError(
            "fewer than two single ablations support a pair search"
        )
    selected_tickers = seeds.sort_values("pool_rank")["omitted_ticker"].tolist()
    stage6 = stage6_pair_search_spec(
        source_manifest_path=root / "manifest.json",
        shortlist_path=shortlist_path,
        pool24=pool24,
        contract=contract,
        selected_tickers=selected_tickers,
    )
    selected = _curve_candidates(candidates, effects)
    selected_keys = selected[["profile_id", "lookback_years", "trade_cost_bps"]]
    selected_windows = raw["windows"].merge(
        selected_keys,
        on=["profile_id", "lookback_years", "trade_cost_bps"],
        how="inner",
        validate="many_to_one",
    )

    output = Path(output_dir) if output_dir else root / "analysis" / "composition"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "effects": output / "single_ablation_effects.csv",
        "selected": output / "pair_search_seeds.csv",
        "windows": output / "seed_windows.csv",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "stage6": output / "stage6_pair_search_spec.yaml",
        "workbook": output / "v8e_single_ablation_analysis.xlsx",
    }
    _atomic_csv(effects, paths["effects"])
    _atomic_csv(seeds, paths["selected"])
    _atomic_csv(selected_windows, paths["windows"])
    atomic_write_text(
        paths["stage6"],
        yaml.safe_dump(stage6, allow_unicode=True, sort_keys=False),
    )

    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=10.0,
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_payload["research_stage"] = "v8e_single_stock_ablation"
    curve_payload["frontier_conclusion"] = {
        "decision": "RUN_BOUNDED_PAIR_COMPOSITION_SEARCH",
        "pair_search_seed_rule": (
            "p50_delta>0 and p10_delta>0 and paired_window_return_win_rate>0.5"
        ),
        "pair_search_seed_tickers": selected_tickers,
        "pair_search_seed_count": len(selected_tickers),
        "pair_count": int(len(selected_tickers) * (len(selected_tickers) - 1) / 2),
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

    best = effects.iloc[0]
    summary_frame = pd.DataFrame([
        {"项目": "主竞争基准", "内容": "当前8只配置"},
        {"项目": "第二层参照", "内容": "012922"},
        {"项目": "单股剔除方案数", "内容": len(effects)},
        {"项目": "全部集中度合规", "内容": bool(effects["concentration_guard_passed"].all())},
        {"项目": "二元搜索种子数", "内容": len(seeds)},
        {"项目": "二元组合数", "内容": int(len(seeds) * (len(seeds) - 1) / 2)},
        {"项目": "当前8只口径最佳单股剔除", "内容": best["omitted_ticker"]},
        {"项目": "最佳单股剔除XIRR中位改善", "内容": best["candidate_p50_return_delta_median"]},
        {"项目": "最佳单股剔除XIRR尾部改善", "内容": best["candidate_p10_return_delta_median"]},
        {"项目": "最佳单股剔除逐窗口收益改善率", "内容": best["window_return_improvement_rate"]},
        {"项目": "同时改善全部收益与回撤指标方案", "内容": 0},
        {"项目": "结论", "内容": "单股剔除仅作为组成搜索种子，不直接删除任何股票"},
        {"项目": "下一步", "内容": "同批复跑基线、6个单股种子和15个二元组合，测量交互效应"},
    ])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary_frame.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(effects)[0].to_excel(
                writer, sheet_name="全部单股剔除", index=False
            )
            _localized_excel_frame(seeds)[0].to_excel(
                writer, sheet_name="二元搜索种子", index=False
            )
            _localized_excel_frame(selected_windows)[0].to_excel(
                writer, sheet_name="种子逐窗口", index=False
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
        "pair_search_seed_count": len(seeds),
        "pair_search_seed_tickers": selected_tickers,
        "best_single_ablation": {
            key: _json_scalar(best.get(key))
            for key in (
                "omitted_ticker",
                "incumbent_win_rate",
                "incumbent_xirr_p50_margin",
                "incumbent_xirr_p10_margin",
                "candidate_p50_return_delta_median",
                "candidate_p10_return_delta_median",
                "candidate_dd_p50_delta_median",
                "candidate_dd_p90_delta_median",
                "window_return_improvement_rate",
                "window_dd_improvement_rate",
            )
        },
        "decision": "RUN_BOUNDED_PAIR_COMPOSITION_SEARCH",
        "stage6_profile_count": len(stage6["phases"][0]["construction_profiles"]),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
