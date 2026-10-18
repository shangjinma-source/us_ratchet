"""Final training-evidence report for v8g composition sensitivity."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.ndx_cap_frontier_analysis import attach_cost_invariant_concentration
from backtest.ndx_envelope_analysis import paired_profile_effects
from backtest.ndx_experiment_analysis import (
    _read_verified_bundle,
    analyze_ndx_experiment,
)
from backtest.ndx_experiment_lab import _format_workbook, _localized_excel_frame
from backtest.ndx_incumbent_frontier import build_incumbent_frontier_bundle
from core.helpers import atomic_write_text


class NdxSensitivityAnalysisError(ValueError):
    """Raised when v8g sensitivity evidence is incomplete or inconsistent."""


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


def sensitivity_effects(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    baseline_profile_id: str,
    profile_roles: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candidate_frames = []
    window_frames = []
    summaries = []
    for profile_id, role in profile_roles.items():
        if profile_id == baseline_profile_id:
            continue
        candidate_effect, window_effect, summary = paired_profile_effects(
            candidates,
            windows,
            challenger_id=profile_id,
            baseline_id=baseline_profile_id,
        )
        candidate_effect["profile_role"] = role
        window_effect["profile_role"] = role
        summary["profile_role"] = role
        candidate_frames.append(candidate_effect)
        window_frames.append(window_effect)
        summaries.append(summary)
    return (
        pd.concat(candidate_frames, ignore_index=True),
        pd.concat(window_frames, ignore_index=True),
        pd.DataFrame(summaries),
    )


def _key_candidates(
    candidates: pd.DataFrame,
    *,
    profile_roles: dict[str, str],
) -> pd.DataFrame:
    selected = candidates[
        candidates["profile_id"].astype(str).isin(profile_roles)
        & np.isclose(candidates["lookback_years"], 3.0)
        & np.isclose(candidates["trade_cost_bps"], 10.0)
    ].copy()
    if len(selected) != len(profile_roles):
        raise NdxSensitivityAnalysisError("key sensitivity candidates are incomplete")
    labels = {
        "baseline": "精确Top3候选池基线",
        "best_single": "最佳单股剔除（TMUS）",
        "best_median_return": "收益中位前沿（剔除 TMUS+MNST）",
        "best_tail_return": "收益尾部前沿（剔除 ODFL+TMUS）",
        "best_drawdown_pressure": "回撤压力前沿（剔除 ODFL+ORLY）",
    }
    order = {role: index for index, role in enumerate(labels)}
    selected["analysis_role"] = selected["profile_id"].map(profile_roles)
    selected["analysis_role_cn"] = selected["analysis_role"].map(labels)
    selected["_display_order"] = selected["analysis_role"].map(order)
    return selected.sort_values("_display_order", kind="stable").drop(
        columns="_display_order"
    )


def _parse_mapping(value: Any, *, numeric: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in str(value or "").split(";"):
        if ":" not in item:
            continue
        key, raw = item.split(":", 1)
        result[str(key)] = float(raw) if numeric else str(raw)
    return result


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
        latest_date = str(subset["selection_date"].max())[:10]
        latest = subset[
            subset["selection_date"].astype(str).str[:10].eq(latest_date)
        ]
        if latest.empty or len(set(latest["weights"].astype(str))) != 1:
            raise NdxSensitivityAnalysisError(
                f"latest weights disagree for {row.profile_id}"
            )
        evidence = latest.iloc[0]
        weights = _parse_mapping(evidence["weights"], numeric=True)
        sic2 = _parse_mapping(evidence.get("sic2_by_ticker"))
        safe_weight = float(row.safe_weight)
        sectors: dict[str, float] = {}
        for ticker, weight in sorted(
            weights.items(), key=lambda item: item[1], reverse=True
        ):
            sector = str(sic2.get(ticker) or "unclassified")
            sectors[sector] = sectors.get(sector, 0.0) + weight
            holdings_rows.append({
                "analysis_role": row.analysis_role,
                "analysis_role_cn": row.analysis_role_cn,
                "profile_id": row.profile_id,
                "selection_date": latest_date,
                "ticker": ticker,
                "sic2": sector,
                "risk_sleeve_weight": weight,
                "portfolio_weight": weight * (1.0 - safe_weight),
            })
        for sector, weight in sorted(sectors.items()):
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


def apply_sensitivity_search_summary(
    curve_payload: dict[str, Any],
    candidates: pd.DataFrame,
) -> dict[str, Any]:
    """Align headline counts to the full sensitivity matrix, not its 10bp slice."""
    required = {
        "concentration_guard_passed",
        "incumbent_win_rate",
        "incumbent_xirr_p50_margin",
        "incumbent_xirr_p10_margin",
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise NdxSensitivityAnalysisError(
            f"sensitivity summary candidates are missing columns: {missing}"
        )
    summary = curve_payload.setdefault("search_summary", {})
    summary["canonical_concentration_compliant_rows"] = int(
        summary.get("concentration_compliant_rows") or 0
    )
    summary["canonical_incumbent_beating_rows"] = int(
        summary.get("incumbent_beating_rows") or 0
    )
    concentration = candidates["concentration_guard_passed"].fillna(False).astype(bool)
    win_rate = pd.to_numeric(candidates["incumbent_win_rate"], errors="coerce")
    p50 = pd.to_numeric(candidates["incumbent_xirr_p50_margin"], errors="coerce")
    p10 = pd.to_numeric(candidates["incumbent_xirr_p10_margin"], errors="coerce")
    summary["concentration_compliant_rows"] = int(concentration.sum())
    summary["incumbent_beating_rows"] = int(
        ((win_rate >= 0.50) & (p50 >= 0.0) & (p10 >= 0.0)).sum()
    )
    summary["headline_count_scope"] = "all_sensitivity_candidate_rows"
    return curve_payload


def build_sensitivity_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    source_v8f_manifest_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    strategy_config_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(experiment_dir)
    manifest, raw = _read_verified_bundle(
        root, strategy_config_path=strategy_config_path
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("research_stage") != "pair_finalist_sensitivity":
        raise NdxSensitivityAnalysisError("experiment is not v8g sensitivity")
    v8f_manifest_path = Path(source_v8f_manifest_path)
    if _content_hash(v8f_manifest_path) != contract.get(
        "source_v8f_manifest_sha256"
    ):
        raise NdxSensitivityAnalysisError("source v8f manifest hash changed")

    analysis_frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=10.0,
        strategy_config_path=strategy_config_path,
    )
    candidates = attach_cost_invariant_concentration(
        raw["candidates"], analysis_frames["concentration"]
    )
    baseline_id = str(contract["baseline_profile_id"])
    profile_roles = {
        str(key): str(value)
        for key, value in (contract.get("profile_roles") or {}).items()
    }
    candidate_effects, window_effects, summaries = sensitivity_effects(
        candidates,
        raw["windows"],
        baseline_profile_id=baseline_id,
        profile_roles=profile_roles,
    )
    pair_roles = {
        "best_median_return",
        "best_tail_return",
        "best_drawdown_pressure",
    }
    pair_summaries = summaries[summaries["profile_role"].isin(pair_roles)]
    if len(pair_summaries) != 3:
        raise NdxSensitivityAnalysisError("three pair sensitivity roles are required")
    if not (
        (pair_summaries["candidate_p50_return_improvement_count"] == 9).all()
        and (pair_summaries["candidate_p10_return_improvement_count"] == 9).all()
    ):
        raise NdxSensitivityAnalysisError(
            "one or more pair finalists failed return sensitivity"
        )

    selected = _key_candidates(candidates, profile_roles=profile_roles)
    holdings, sectors = _latest_portfolios(raw["selections"], selected)
    selected_keys = selected[["profile_id", "lookback_years", "trade_cost_bps"]]
    selected_windows = raw["windows"].merge(
        selected_keys,
        on=["profile_id", "lookback_years", "trade_cost_bps"],
        how="inner",
        validate="many_to_one",
    )

    output = Path(output_dir) if output_dir else root / "analysis" / "sensitivity"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_table": output / "sensitivity_summary.csv",
        "candidate_effects": output / "paired_candidate_effects.csv",
        "window_effects": output / "paired_window_effects.csv",
        "selected": output / "key_candidates.csv",
        "windows": output / "key_candidate_windows.csv",
        "holdings": output / "latest_holdings.csv",
        "sectors": output / "latest_sic2_exposure.csv",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "workbook": output / "v8g_composition_sensitivity_analysis.xlsx",
    }
    for frame, key in (
        (summaries, "summary_table"),
        (candidate_effects, "candidate_effects"),
        (window_effects, "window_effects"),
        (selected, "selected"),
        (selected_windows, "windows"),
        (holdings, "holdings"),
        (sectors, "sectors"),
    ):
        _atomic_csv(frame, paths[key])

    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=10.0,
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_payload["research_stage"] = "v8g_composition_sensitivity"
    curve_payload["frontier_conclusion"] = {
        "decision": "KEEP_THREE_TRAINING_FRONTIERS_NO_PROMOTION",
        "all_pair_finalists_return_improved_across_9_sensitivities": True,
        "locked_validation_executed": False,
        "post_2024_evidence_may_not_be_reused_as_new_holdout": True,
    }
    apply_sensitivity_search_summary(curve_payload, candidates)
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

    best_absolute = candidates.sort_values(
        ["incumbent_xirr_p50_margin", "incumbent_xirr_p10_margin"],
        ascending=False,
        kind="stable",
    ).iloc[0]
    incumbent_gate_rows = int(
        candidates["incumbent_gate_passed"].fillna(False).astype(bool).sum()
    )
    summary_frame = pd.DataFrame([
        {"项目": "主竞争基准", "内容": "当前8只配置"},
        {"项目": "第二层参照", "内容": "012922"},
        {"项目": "敏感性候选行", "内容": len(candidates)},
        {"项目": "集中度合规候选行", "内容": int(candidates["concentration_guard_passed"].sum())},
        {"项目": "通过当前8只收益守门候选行", "内容": incumbent_gate_rows},
        {"项目": "三条二元前沿P50改善组数", "内容": "9/9、9/9、9/9"},
        {"项目": "三条二元前沿P10改善组数", "内容": "9/9、9/9、9/9"},
        {"项目": "最接近当前8只方案", "内容": best_absolute["profile_id"]},
        {"项目": "最接近方案XIRR中位差", "内容": best_absolute["incumbent_xirr_p50_margin"]},
        {"项目": "最接近方案XIRR尾部差", "内容": best_absolute["incumbent_xirr_p10_margin"]},
        {"项目": "锁定验证", "内容": "未执行"},
        {"项目": "样本独立性说明", "内容": "每组18个滚动起点高度重叠，不按162个独立样本解释"},
        {"项目": "验证纪律", "内容": "2024-07之后证据已被既往研究消费，不复用为新锁定验证"},
        {"项目": "结论", "内容": "保留三条训练前沿，不替换当前8只，不继续扩大组合搜索"},
    ])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary_frame.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(summaries)[0].to_excel(
                writer, sheet_name="敏感性汇总", index=False
            )
            _localized_excel_frame(candidate_effects)[0].to_excel(
                writer, sheet_name="候选层配对", index=False
            )
            _localized_excel_frame(window_effects)[0].to_excel(
                writer, sheet_name="逐窗口配对", index=False
            )
            _localized_excel_frame(selected)[0].to_excel(
                writer, sheet_name="关键曲线方案", index=False
            )
            _localized_excel_frame(selected_windows)[0].to_excel(
                writer, sheet_name="关键方案窗口", index=False
            )
            _localized_excel_frame(holdings)[0].to_excel(
                writer, sheet_name="最新持仓", index=False
            )
            _localized_excel_frame(sectors)[0].to_excel(
                writer, sheet_name="SIC二位暴露", index=False
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
        "incumbent_gate_passed_rows": incumbent_gate_rows,
        "sensitivity_summaries": [
            {key: _json_scalar(value) for key, value in row.items()}
            for row in summaries.to_dict(orient="records")
        ],
        "best_absolute": {
            key: _json_scalar(best_absolute.get(key))
            for key in (
                "profile_id",
                "lookback_years",
                "trade_cost_bps",
                "incumbent_win_rate",
                "incumbent_xirr_p50_margin",
                "incumbent_xirr_p10_margin",
                "incumbent_dd_relief_p50",
                "incumbent_dd_relief_p90",
            )
        },
        "locked_validation_executed": False,
        "decision": "KEEP_THREE_TRAINING_FRONTIERS_NO_PROMOTION",
        "next_evidence_requirement": (
            "new unconsumed point-in-time period or independent pre-registered data"
        ),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
