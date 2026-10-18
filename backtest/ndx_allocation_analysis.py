"""Incumbent-first analysis and narrow cap-frontier generation for NDX v8b."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_experiment_analysis import (
    _read_verified_bundle,
    analyze_ndx_experiment,
)
from backtest.ndx_experiment_lab import _format_workbook, _localized_excel_frame
from backtest.ndx_incumbent_frontier import build_incumbent_frontier_bundle
from core.helpers import atomic_write_text


class NdxAllocationAnalysisError(ValueError):
    """Raised when allocation evidence cannot support a staged decision."""


ROLE_LABELS_CN = {
    "best_unconstrained_return": "收益最接近当前8只（未通过集中度）",
    "best_unconstrained_tail": "尾部收益最接近当前8只（未通过集中度）",
    "best_unconstrained_win_rate": "窗口胜率最高（未通过集中度）",
    "best_compliant_return": "集中度合规收益最佳",
    "best_compliant_tail": "集中度合规尾部收益最佳",
    "best_compliant_drawdown": "集中度合规回撤最佳",
    "best_compliant_diversification": "集中度合规分散度最佳",
}


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


def _parse_mapping(value: Any, *, numeric: bool = False) -> dict:
    result = {}
    for item in str(value or "").split(";"):
        if ":" not in item:
            continue
        key, raw = item.split(":", 1)
        result[str(key)] = float(raw) if numeric else str(raw)
    return result


def _candidate_identity(row: pd.Series) -> tuple[str, float, float]:
    return (
        str(row["profile_id"]),
        float(row["lookback_years"]),
        float(row["trade_cost_bps"]),
    )


def _pick_distinct(
    frame: pd.DataFrame,
    role_specs: list[tuple[str, list[str]]],
    *,
    used: set[tuple[str, float, float]] | None = None,
) -> list[dict]:
    selected = []
    seen = used if used is not None else set()
    for role, sort_fields in role_specs:
        ordered = frame.sort_values(sort_fields, ascending=False, kind="stable")
        chosen = None
        for _, row in ordered.iterrows():
            identity = _candidate_identity(row)
            if identity not in seen:
                chosen = row
                seen.add(identity)
                break
        if chosen is None:
            continue
        payload = chosen.to_dict()
        payload["analysis_role"] = role
        payload["analysis_role_cn"] = ROLE_LABELS_CN[role]
        selected.append(payload)
    return selected


def select_key_allocation_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    required = {
        "profile_id",
        "lookback_years",
        "trade_cost_bps",
        "concentration_guard_passed",
        "incumbent_win_rate",
        "incumbent_xirr_p50_margin",
        "incumbent_xirr_p10_margin",
        "incumbent_dd_relief_p50",
        "incumbent_dd_relief_p90",
        "effective_n_p10",
        "turnover_x_p50",
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise NdxAllocationAnalysisError(
            f"allocation candidates are missing columns: {missing}"
        )
    used: set[tuple[str, float, float]] = set()
    rows = _pick_distinct(
        candidates,
        [
            (
                "best_unconstrained_return",
                [
                    "incumbent_xirr_p50_margin",
                    "incumbent_xirr_p10_margin",
                    "incumbent_win_rate",
                ],
            ),
            (
                "best_unconstrained_tail",
                [
                    "incumbent_xirr_p10_margin",
                    "incumbent_xirr_p50_margin",
                    "incumbent_win_rate",
                ],
            ),
            (
                "best_unconstrained_win_rate",
                [
                    "incumbent_win_rate",
                    "incumbent_xirr_p10_margin",
                    "incumbent_xirr_p50_margin",
                ],
            ),
        ],
        used=used,
    )
    compliant = candidates[
        candidates["concentration_guard_passed"].fillna(False).astype(bool)
    ]
    if compliant.empty:
        raise NdxAllocationAnalysisError("no concentration-compliant candidate exists")
    rows.extend(_pick_distinct(
        compliant,
        [
            (
                "best_compliant_return",
                [
                    "incumbent_xirr_p50_margin",
                    "incumbent_xirr_p10_margin",
                    "incumbent_win_rate",
                ],
            ),
            (
                "best_compliant_tail",
                [
                    "incumbent_xirr_p10_margin",
                    "incumbent_xirr_p50_margin",
                    "incumbent_win_rate",
                ],
            ),
            (
                "best_compliant_drawdown",
                [
                    "incumbent_dd_relief_p90",
                    "incumbent_dd_relief_p50",
                    "incumbent_xirr_p10_margin",
                ],
            ),
            (
                "best_compliant_diversification",
                [
                    "effective_n_p10",
                    "incumbent_xirr_p10_margin",
                    "incumbent_xirr_p50_margin",
                ],
            ),
        ],
        used=used,
    ))
    return pd.DataFrame(rows)


def _dimension_effects(candidates: pd.DataFrame) -> pd.DataFrame:
    work = candidates.copy()
    work["pool_id"] = work["profile_id"].astype(str).str.extract(r"^(pool\d+)")
    work["sector_policy"] = np.where(
        work["profile_id"].astype(str).str.contains("sic_cap2"),
        "sic_cap2",
        "uncapped",
    )
    work["quality_blend"] = np.where(
        work["profile_id"].astype(str).str.contains("q25"), "q25", "q00"
    )
    rows = []
    for dimension in (
        "pool_id",
        "sector_policy",
        "quality_blend",
        "top_n",
        "weight_mode",
        "lookback_years",
    ):
        for value, group in work.groupby(dimension, dropna=False, sort=True):
            rows.append({
                "dimension": dimension,
                "value": value,
                "candidate_rows": len(group),
                "incumbent_win_rate_median": group["incumbent_win_rate"].median(),
                "incumbent_win_rate_best": group["incumbent_win_rate"].max(),
                "incumbent_xirr_p50_margin_median": group[
                    "incumbent_xirr_p50_margin"
                ].median(),
                "incumbent_xirr_p50_margin_best": group[
                    "incumbent_xirr_p50_margin"
                ].max(),
                "incumbent_xirr_p10_margin_median": group[
                    "incumbent_xirr_p10_margin"
                ].median(),
                "incumbent_xirr_p10_margin_best": group[
                    "incumbent_xirr_p10_margin"
                ].max(),
                "incumbent_dd_relief_p50_median": group[
                    "incumbent_dd_relief_p50"
                ].median(),
                "incumbent_dd_relief_p90_median": group[
                    "incumbent_dd_relief_p90"
                ].median(),
                "concentration_pass_rate": group[
                    "concentration_guard_passed"
                ].fillna(False).mean(),
                "turnover_x_p50_median": group["turnover_x_p50"].median(),
            })
    return pd.DataFrame(rows)


def _latest_portfolios(
    selections: pd.DataFrame,
    selected: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    holdings_rows = []
    sector_rows = []
    for row in selected.itertuples(index=False):
        subset = selections[
            selections["profile_id"].astype(str).eq(str(row.profile_id))
            & np.isclose(selections["lookback_years"], float(row.lookback_years))
            & np.isclose(selections["trade_cost_bps"], float(row.trade_cost_bps))
        ].copy()
        if subset.empty:
            raise NdxAllocationAnalysisError(
                f"selection evidence is missing for {row.profile_id}"
            )
        latest_date = str(subset["selection_date"].max())[:10]
        latest = subset[subset["selection_date"].astype(str).str[:10].eq(latest_date)]
        signatures = set(latest["weights"].astype(str))
        if len(signatures) != 1:
            raise NdxAllocationAnalysisError(
                f"latest weights disagree across windows for {row.profile_id}"
            )
        observed = latest.iloc[0]
        weights = _parse_mapping(observed["weights"], numeric=True)
        sic2 = _parse_mapping(observed.get("sic2_by_ticker"))
        safe_weight = float(row.safe_weight)
        for ticker, weight in sorted(
            weights.items(), key=lambda item: item[1], reverse=True
        ):
            holdings_rows.append({
                "analysis_role": row.analysis_role,
                "analysis_role_cn": row.analysis_role_cn,
                "profile_id": row.profile_id,
                "lookback_years": row.lookback_years,
                "selection_date": latest_date,
                "ticker": ticker,
                "sic2": sic2.get(ticker),
                "risk_sleeve_weight": weight,
                "portfolio_weight": weight * (1.0 - safe_weight),
            })
        for sector, weight in _parse_mapping(
            observed.get("sic2_weights"), numeric=True
        ).items():
            sector_rows.append({
                "analysis_role": row.analysis_role,
                "analysis_role_cn": row.analysis_role_cn,
                "profile_id": row.profile_id,
                "selection_date": latest_date,
                "sic2": sector,
                "risk_sleeve_weight": weight,
                "portfolio_weight": weight * (1.0 - safe_weight),
            })
        sector_rows.append({
            "analysis_role": row.analysis_role,
            "analysis_role_cn": row.analysis_role_cn,
            "profile_id": row.profile_id,
            "selection_date": latest_date,
            "sic2": "SAFE",
            "risk_sleeve_weight": np.nan,
            "portfolio_weight": safe_weight,
        })
    return pd.DataFrame(holdings_rows), pd.DataFrame(sector_rows)


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


def _cap_profile_id(pool_id: str, top_n: int, cap: float) -> str:
    cap_tag = f"{cap:.4f}".rstrip("0").rstrip(".").replace(".", "p")
    return f"{pool_id}__q25__top{top_n}__source_cap-{cap_tag}"


def _risk_derived_cap_grid(envelope: dict, baseline_cap: float) -> list[float]:
    equal_weight_8 = 1.0 / 8.0
    top3_equal_share = float(envelope["top3"]) / 3.0
    incumbent_top1 = float(envelope["top1"])
    upper_endpoint = float(baseline_cap)
    if not (
        equal_weight_8 < top3_equal_share
        <= incumbent_top1 < upper_endpoint
    ):
        raise NdxAllocationAnalysisError(
            "incumbent concentration evidence cannot define an ordered cap frontier"
        )
    lower_midpoint = (equal_weight_8 + top3_equal_share) / 2.0
    upper_midpoint = (incumbent_top1 + upper_endpoint) / 2.0
    caps = [
        equal_weight_8,
        lower_midpoint,
        top3_equal_share,
        incumbent_top1,
        upper_midpoint,
        upper_endpoint,
    ]
    rounded = [float(f"{value:.4f}") for value in caps]
    if len(set(rounded)) != len(rounded):
        raise NdxAllocationAnalysisError(
            "risk-derived cap frontier collapsed after four-decimal registration"
        )
    return rounded


def _stage3_spec(
    manifest_path: Path,
    shortlists_path: Path,
    shortlists: pd.DataFrame,
    envelope: dict,
    *,
    baseline_pool_id: str,
    baseline_top_n: int,
    baseline_cap: float,
) -> dict:
    expected_hash = _content_hash(shortlists_path)
    caps = _risk_derived_cap_grid(envelope, baseline_cap)
    profiles = []
    for pool_id in ("pool24", "pool30"):
        pool = shortlists[shortlists["shortlist_id"].astype(str).eq(pool_id)]
        if pool.empty:
            raise NdxAllocationAnalysisError(f"shortlist is missing {pool_id}")
        tickers = pool.sort_values("rank", kind="stable")["ticker"].tolist()
        for top_n in (10, 12):
            for cap in caps:
                profiles.append({
                    "id": _cap_profile_id(pool_id, top_n, cap),
                    "candidate_tickers": tickers,
                    "top_n": top_n,
                    "weight_mode": "source_weight",
                    "rebalance_months": 6,
                    "safe_weight": 0.26,
                    "challenger_sleeve_weight": 1.0,
                    "max_weight": cap,
                    "min_weight": 0.02,
                    "selection_mode": "rank",
                    "fundamental_score_weight": 0.25,
                    "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
                    "defense_mode": "static",
                })
    baseline_id = _cap_profile_id(
        baseline_pool_id, int(baseline_top_n), float(baseline_cap)
    )
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_source_cap_frontier_v8c",
        "research_question": (
            "Can a risk-budget-derived cap on QQQ source weights preserve the "
            "closest v8b return profile while entering the current eight-name "
            "concentration envelope?"
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
            "component_family": "incumbent_first_source_cap_frontier",
            "research_stage": "allocation_cap_frontier",
            "baseline_profile_id": baseline_id,
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_v8b_manifest_sha256": _content_hash(manifest_path),
            "source_stage1_shortlists_sha256": expected_hash,
            "cap_grid_policy": "incumbent_envelope_interpolation_v1",
            "cap_grid": caps,
            "source_v8b_baseline_profile_id": baseline_id,
            "source_v8b_baseline_max_weight": float(baseline_cap),
            "equal_weight_8_cap": 1.0 / 8.0,
            "incumbent_top1": float(envelope["top1"]),
            "incumbent_top3": float(envelope["top3"]),
            "incumbent_effective_n": float(envelope["effective_n"]),
            "top3_equal_share_cap": float(envelope["top3"]) / 3.0,
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
                "phase_id": "source_cap_training",
                "enabled": True,
                "role": "exploratory_training",
                "rationale": (
                    "v8b source weights were closest on incumbent return but "
                    "failed Top1/Top3 concentration. Caps bracket equal-like "
                    "allocation, incumbent Top3/3, incumbent Top1, and the "
                    "uncapped 20 percent endpoint."
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
                    "max_weights": [0.20],
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
                    "No cap is validated until a broad training plateau is "
                    "frozen and the reused post-2024 diagnostic is labeled as such."
                ),
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


def build_allocation_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    shortlists_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    strategy_config_path: str | Path | None = None,
) -> dict:
    root = Path(experiment_dir)
    manifest, raw = _read_verified_bundle(
        root, strategy_config_path=strategy_config_path
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("research_stage") != "holding_count_and_allocation":
        raise NdxAllocationAnalysisError("experiment is not v8b allocation search")
    if contract.get("decision_priority") != "incumbent_first":
        raise NdxAllocationAnalysisError("allocation search is not incumbent-first")
    shortlist_path = Path(shortlists_path)
    if not shortlist_path.exists():
        raise NdxAllocationAnalysisError(f"shortlist evidence is missing: {shortlist_path}")
    if _content_hash(shortlist_path) != contract.get(
        "source_stage1_shortlists_sha256"
    ):
        raise NdxAllocationAnalysisError("stage1 shortlist hash changed")

    analysis_frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=10.0,
        strategy_config_path=strategy_config_path,
    )
    candidates = analysis_frames["concentration"].copy()
    if len(candidates) != int(manifest["candidate_rows"]):
        raise NdxAllocationAnalysisError("concentration rows do not match candidates")
    selected = select_key_allocation_candidates(candidates)
    dimensions = _dimension_effects(candidates)
    selections = raw["selections"]
    holdings, sector_exposure = _latest_portfolios(selections, selected)
    windows = raw["windows"]
    selected_keys = selected[["profile_id", "lookback_years", "trade_cost_bps"]]
    key_windows = windows.merge(
        selected_keys,
        on=["profile_id", "lookback_years", "trade_cost_bps"],
        how="inner",
        validate="many_to_one",
    )

    ordered = candidates.sort_values(
        [
            "incumbent_xirr_p50_margin",
            "incumbent_xirr_p10_margin",
            "incumbent_win_rate",
        ],
        ascending=False,
        kind="stable",
    )
    best = ordered.iloc[0]
    baseline_pool_id = str(best["profile_id"]).split("__", 1)[0]
    if (
        baseline_pool_id not in {"pool24", "pool30"}
        or str(best["weight_mode"]) != "source_weight"
        or not np.isclose(float(best["fundamental_score_weight"]), 0.25)
    ):
        raise NdxAllocationAnalysisError(
            "v8b best-return evidence does not support the declared v8c family"
        )
    shortlists = pd.read_csv(shortlist_path)
    stage3 = _stage3_spec(
        root / "manifest.json",
        shortlist_path,
        shortlists,
        analysis["incumbent_concentration_envelope"],
        baseline_pool_id=baseline_pool_id,
        baseline_top_n=int(best["top_n"]),
        baseline_cap=float(best["max_weight"]),
    )
    output = Path(output_dir) if output_dir else root / "analysis" / "incumbent_first"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "selected": output / "key_candidates.csv",
        "candidates": output / "ranked_candidates.csv",
        "dimensions": output / "dimension_effects.csv",
        "windows": output / "key_candidate_windows.csv",
        "holdings": output / "latest_holdings.csv",
        "sectors": output / "latest_sic2_exposure.csv",
        "stage3": output / "stage3_source_cap_spec.yaml",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "workbook": output / "v8b_incumbent_first_analysis.xlsx",
    }
    _atomic_csv(selected, paths["selected"])
    _atomic_csv(ordered, paths["candidates"])
    _atomic_csv(dimensions, paths["dimensions"])
    _atomic_csv(key_windows, paths["windows"])
    _atomic_csv(holdings, paths["holdings"])
    _atomic_csv(sector_exposure, paths["sectors"])
    atomic_write_text(
        paths["stage3"],
        yaml.safe_dump(stage3, allow_unicode=True, sort_keys=False),
    )
    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=10.0,
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_daily_cn = _localized_curve_daily(curve_daily, curve_payload)
    _atomic_csv(curve_daily_cn, paths["curve_daily"])
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

    compliant = ordered[
        ordered["concentration_guard_passed"].fillna(False).astype(bool)
    ].iloc[0]
    incumbent_beating_rows = int(
        (
            (candidates["incumbent_win_rate"] >= 0.50)
            & (candidates["incumbent_xirr_p50_margin"] >= 0.0)
            & (candidates["incumbent_xirr_p10_margin"] >= 0.0)
        ).sum()
    )
    conclusion = pd.DataFrame([
        {"项目": "主比较基准", "内容": "当前8只配置"},
        {"项目": "第二层参照", "内容": "012922"},
        {"项目": "候选方案数", "内容": len(candidates)},
        {"项目": "集中度合规方案数", "内容": int(candidates["concentration_guard_passed"].sum())},
        {"项目": "收益战胜当前8只方案数", "内容": incumbent_beating_rows},
        {"项目": "收益最接近方案", "内容": best["profile_id"]},
        {"项目": "收益最接近方案XIRR中位差", "内容": best["incumbent_xirr_p50_margin"]},
        {"项目": "收益最接近方案XIRR尾部差", "内容": best["incumbent_xirr_p10_margin"]},
        {"项目": "收益最接近方案Top3压力值", "内容": best["top3_p90"]},
        {"项目": "合规收益最佳方案", "内容": compliant["profile_id"]},
        {"项目": "合规收益最佳XIRR中位差", "内容": compliant["incumbent_xirr_p50_margin"]},
        {"项目": "前端关键曲线方案数", "内容": len(curve_payload["solutions"])},
        {"项目": "下一步", "内容": "仅测试风险预算推导的源权重封顶前沿，不晋级实盘"},
    ])
    temporary = paths["workbook"].with_name(
        paths["workbook"].stem + ".tmp.xlsx"
    )
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            conclusion.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(selected)[0].to_excel(
                writer, sheet_name="关键方案", index=False
            )
            _localized_excel_frame(ordered)[0].to_excel(
                writer, sheet_name="全部方案", index=False
            )
            _localized_excel_frame(dimensions)[0].to_excel(
                writer, sheet_name="维度效果", index=False
            )
            _localized_excel_frame(key_windows)[0].to_excel(
                writer, sheet_name="关键方案窗口", index=False
            )
            _localized_excel_frame(holdings)[0].to_excel(
                writer, sheet_name="最新持仓", index=False
            )
            _localized_excel_frame(sector_exposure)[0].to_excel(
                writer, sheet_name="SIC二位暴露", index=False
            )
            curve_daily_cn.to_excel(
                writer, sheet_name="逐日曲线", index=False
            )
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
            candidates["concentration_guard_passed"].sum()
        ),
        "incumbent_beating_rows": incumbent_beating_rows,
        "best_unconstrained": {
            key: _json_scalar(best.get(key))
            for key in (
                "profile_id",
                "lookback_years",
                "incumbent_win_rate",
                "incumbent_xirr_p50_margin",
                "incumbent_xirr_p10_margin",
                "incumbent_dd_relief_p50",
                "incumbent_dd_relief_p90",
                "effective_n_p10",
                "top1_p90",
                "top3_p90",
            )
        },
        "best_compliant": {
            key: _json_scalar(compliant.get(key))
            for key in (
                "profile_id",
                "lookback_years",
                "incumbent_win_rate",
                "incumbent_xirr_p50_margin",
                "incumbent_xirr_p10_margin",
                "incumbent_dd_relief_p50",
                "incumbent_dd_relief_p90",
                "effective_n_p10",
                "top1_p90",
                "top3_p90",
            )
        },
        "incumbent_concentration_envelope": analysis[
            "incumbent_concentration_envelope"
        ],
        "decision": "NO_WHOLESALE_REPLACEMENT_RUN_SOURCE_CAP_FRONTIER",
        "stage3_profile_count": len(stage3["phases"][0]["construction_profiles"]),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
