"""Paired analysis of v8d exact incumbent-concentration envelope evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_cap_frontier_analysis import attach_cost_invariant_concentration
from backtest.ndx_experiment_analysis import (
    _read_verified_bundle,
    analyze_ndx_experiment,
)
from backtest.ndx_experiment_lab import _format_workbook, _localized_excel_frame
from backtest.ndx_incumbent_frontier import build_incumbent_frontier_bundle
from core.helpers import atomic_write_text


class NdxEnvelopeAnalysisError(ValueError):
    """Raised when v8d evidence cannot support a composition-search decision."""


CANDIDATE_PAIR_KEYS = ("lookback_years", "trade_cost_bps")
WINDOW_PAIR_KEYS = ("lookback_years", "trade_cost_bps", "start")
CANDIDATE_METRICS = (
    "incumbent_win_rate",
    "incumbent_xirr_p50_margin",
    "incumbent_xirr_p10_margin",
    "incumbent_dd_relief_p50",
    "incumbent_dd_relief_p90",
    "turnover_x_p50",
)
WINDOW_METRICS = (
    "incumbent_xirr_margin",
    "incumbent_dd_relief",
    "strategy_xirr",
    "strategy_maxdd",
    "turnover_x",
)


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


def paired_profile_effects(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    *,
    challenger_id: str,
    baseline_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return paired candidate and rolling-window deltas for two profiles."""
    candidate_challenger = candidates[
        candidates["profile_id"].astype(str).eq(challenger_id)
    ]
    candidate_baseline = candidates[
        candidates["profile_id"].astype(str).eq(baseline_id)
    ]
    if candidate_challenger.empty or candidate_baseline.empty:
        raise NdxEnvelopeAnalysisError(
            f"paired candidate evidence missing: {challenger_id} vs {baseline_id}"
        )
    candidate_pairs = candidate_challenger.merge(
        candidate_baseline,
        on=list(CANDIDATE_PAIR_KEYS),
        suffixes=("_challenger", "_baseline"),
        validate="one_to_one",
    )
    if len(candidate_pairs) != len(candidate_challenger) or len(candidate_pairs) != len(
        candidate_baseline
    ):
        raise NdxEnvelopeAnalysisError("candidate pairs are incomplete")
    candidate_effects = candidate_pairs[list(CANDIDATE_PAIR_KEYS)].copy()
    candidate_effects["challenger_profile_id"] = challenger_id
    candidate_effects["baseline_profile_id"] = baseline_id
    for metric in CANDIDATE_METRICS:
        candidate_effects[f"{metric}_challenger"] = candidate_pairs[
            f"{metric}_challenger"
        ]
        candidate_effects[f"{metric}_baseline"] = candidate_pairs[
            f"{metric}_baseline"
        ]
        candidate_effects[f"{metric}_delta"] = (
            candidate_pairs[f"{metric}_challenger"]
            - candidate_pairs[f"{metric}_baseline"]
        )

    window_challenger = windows[
        windows["profile_id"].astype(str).eq(challenger_id)
    ]
    window_baseline = windows[
        windows["profile_id"].astype(str).eq(baseline_id)
    ]
    window_pairs = window_challenger.merge(
        window_baseline,
        on=list(WINDOW_PAIR_KEYS),
        suffixes=("_challenger", "_baseline"),
        validate="one_to_one",
    )
    if len(window_pairs) != len(window_challenger) or len(window_pairs) != len(
        window_baseline
    ):
        raise NdxEnvelopeAnalysisError("rolling-window pairs are incomplete")
    window_effects = window_pairs[list(WINDOW_PAIR_KEYS)].copy()
    window_effects["challenger_profile_id"] = challenger_id
    window_effects["baseline_profile_id"] = baseline_id
    for metric in WINDOW_METRICS:
        window_effects[f"{metric}_challenger"] = window_pairs[
            f"{metric}_challenger"
        ]
        window_effects[f"{metric}_baseline"] = window_pairs[
            f"{metric}_baseline"
        ]
        window_effects[f"{metric}_delta"] = (
            window_pairs[f"{metric}_challenger"]
            - window_pairs[f"{metric}_baseline"]
        )

    candidate_return = candidate_effects["incumbent_xirr_p50_margin_delta"]
    candidate_tail = candidate_effects["incumbent_xirr_p10_margin_delta"]
    candidate_dd50 = candidate_effects["incumbent_dd_relief_p50_delta"]
    candidate_dd90 = candidate_effects["incumbent_dd_relief_p90_delta"]
    window_return = window_effects["incumbent_xirr_margin_delta"]
    window_dd = window_effects["incumbent_dd_relief_delta"]
    summary = {
        "challenger_profile_id": challenger_id,
        "baseline_profile_id": baseline_id,
        "candidate_pairs": len(candidate_effects),
        "window_pairs": len(window_effects),
        "candidate_p50_return_improvement_count": int((candidate_return > 0).sum()),
        "candidate_p10_return_improvement_count": int((candidate_tail > 0).sum()),
        "candidate_dd_p50_improvement_count": int((candidate_dd50 > 0).sum()),
        "candidate_dd_p90_improvement_count": int((candidate_dd90 > 0).sum()),
        "candidate_p50_return_delta_median": float(candidate_return.median()),
        "candidate_p10_return_delta_median": float(candidate_tail.median()),
        "candidate_dd_p50_delta_median": float(candidate_dd50.median()),
        "candidate_dd_p90_delta_median": float(candidate_dd90.median()),
        "window_return_improvement_rate": float((window_return > 0).mean()),
        "window_dd_improvement_rate": float((window_dd > 0).mean()),
        "window_return_delta_p10": float(window_return.quantile(0.10)),
        "window_return_delta_p50": float(window_return.quantile(0.50)),
        "window_return_delta_p90": float(window_return.quantile(0.90)),
        "window_dd_delta_p10": float(window_dd.quantile(0.10)),
        "window_dd_delta_p50": float(window_dd.quantile(0.50)),
        "window_dd_delta_p90": float(window_dd.quantile(0.90)),
    }
    return candidate_effects, window_effects, summary


def profile_equivalence_audit(
    candidates: pd.DataFrame,
    windows: pd.DataFrame,
    selections: pd.DataFrame,
    *,
    left_id: str,
    right_id: str,
    tolerance: float = 1e-8,
) -> dict[str, Any]:
    """Determine whether two declared profiles are economically redundant."""
    checks: dict[str, float | int] = {}
    for name, frame, keys, metrics in (
        (
            "candidate",
            candidates,
            list(CANDIDATE_PAIR_KEYS),
            list(CANDIDATE_METRICS),
        ),
        (
            "window",
            windows,
            list(WINDOW_PAIR_KEYS),
            list(WINDOW_METRICS),
        ),
        (
            "selection",
            selections,
            [
                "lookback_years",
                "trade_cost_bps",
                "window_start",
                "selection_date",
                "trigger",
            ],
            ["observed_max_weight", "observed_top_weight", "observed_effective_n"],
        ),
    ):
        left = frame[frame["profile_id"].astype(str).eq(left_id)]
        right = frame[frame["profile_id"].astype(str).eq(right_id)]
        merged = left.merge(
            right,
            on=keys,
            suffixes=("_left", "_right"),
            validate="one_to_one",
        )
        if len(merged) != len(left) or len(merged) != len(right):
            raise NdxEnvelopeAnalysisError(
                f"{name} equivalence evidence is not fully paired"
            )
        max_difference = 0.0
        for metric in metrics:
            left_values = pd.to_numeric(merged[f"{metric}_left"], errors="coerce")
            right_values = pd.to_numeric(merged[f"{metric}_right"], errors="coerce")
            difference = (left_values - right_values).abs().max()
            if pd.notna(difference):
                max_difference = max(max_difference, float(difference))
        checks[f"{name}_pairs"] = len(merged)
        checks[f"{name}_max_abs_difference"] = max_difference
    return {
        "left_profile_id": left_id,
        "right_profile_id": right_id,
        "tolerance": float(tolerance),
        **checks,
        "economically_equivalent": bool(
            all(
                float(checks[key]) <= float(tolerance)
                for key in checks
                if key.endswith("_max_abs_difference")
            )
        ),
    }


def _curve_candidates(candidates: pd.DataFrame, profile_ids: list[str]) -> pd.DataFrame:
    selected = candidates[
        candidates["profile_id"].astype(str).isin(profile_ids)
        & np.isclose(candidates["lookback_years"], 3.0)
        & np.isclose(candidates["trade_cost_bps"], 10.0)
    ].copy()
    if len(selected) != len(profile_ids):
        raise NdxEnvelopeAnalysisError("one or more key curve profiles are missing")
    labels = {
        profile_ids[0]: "20%统一上限（收益端点）",
        profile_ids[1]: "精确Top3边界（合规折中）",
        profile_ids[2]: "13.63%统一上限（保守端点）",
    }
    order = {profile_id: index for index, profile_id in enumerate(profile_ids)}
    selected["analysis_role"] = selected["profile_id"].map({
        profile_ids[0]: "cap20_return_endpoint",
        profile_ids[1]: "exact_top3_envelope",
        profile_ids[2]: "cap1363_conservative_endpoint",
    })
    selected["analysis_role_cn"] = selected["profile_id"].map(labels)
    selected["_display_order"] = selected["profile_id"].map(order)
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
            raise NdxEnvelopeAnalysisError(
                f"latest selection evidence disagrees for {row.profile_id}"
            )
        evidence = latest.iloc[0]
        weights = _parse_mapping(evidence["weights"], numeric=True)
        sic2 = _parse_mapping(evidence.get("sic2_by_ticker"))
        safe_weight = float(row.safe_weight)
        sector_weights: dict[str, float] = {}
        for ticker, weight in sorted(
            weights.items(), key=lambda item: item[1], reverse=True
        ):
            sector = str(sic2.get(ticker) or "unclassified")
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
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
        for sector, weight in sorted(sector_weights.items()):
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


def stage5_composition_ablation_spec(
    *,
    source_manifest_path: Path,
    shortlist_path: Path,
    pool24: pd.DataFrame,
    contract: dict,
    baseline_profile_id: str,
) -> dict:
    ordered = pool24.sort_values("rank", kind="stable")
    tickers = ordered["ticker"].astype(str).str.upper().tolist()
    if len(tickers) != 24 or len(set(tickers)) != 24:
        raise NdxEnvelopeAnalysisError("composition ablation requires exact pool24")
    if "sic2" not in ordered:
        raise NdxEnvelopeAnalysisError("pool24 has no SEC SIC2 evidence")
    max_per_sic2 = int(ordered.groupby("sic2")["ticker"].size().max())
    if max_per_sic2 > 2:
        raise NdxEnvelopeAnalysisError("pool24 no longer satisfies its SIC2 name cap")
    top1 = float(contract["incumbent_top1"])
    top3 = float(contract["incumbent_top3"])

    def profile(profile_id: str, candidates: list[str]) -> dict[str, Any]:
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

    profiles = [profile(baseline_profile_id, tickers)]
    profiles.extend(
        profile(
            f"pool23__without_{ticker.lower()}",
            [candidate for candidate in tickers if candidate != ticker],
        )
        for ticker in tickers
    )
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_composition_ablation_v8e",
        "research_question": (
            "Which individual pool24 exclusions improve the exact-Top3 challenger "
            "on paired windows before any multi-stock combination search?"
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
            "component_family": "incumbent_composition_ablation",
            "research_stage": "single_stock_candidate_pool_ablation",
            "baseline_profile_id": baseline_profile_id,
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_v8d_manifest_sha256": _content_hash(source_manifest_path),
            "source_stage1_shortlists_sha256": _content_hash(shortlist_path),
            "source_pool_id": "pool24",
            "source_pool_size": 24,
            "source_pool_max_names_per_sic2": max_per_sic2,
            "ablation_count": 24,
            "search_policy": "baseline_plus_every_single_ticker_exclusion",
            "multiple_testing_policy": "screen_only_no_promotion",
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
                "phase_id": "single_stock_ablation_training",
                "enabled": True,
                "role": "exploratory_training",
                "rationale": (
                    "Hold selection, allocation and risk envelope fixed; remove one "
                    "pool24 name at a time to identify composition sensitivity before "
                    "testing pairs or larger combinations."
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
                    "lookback_years": [3],
                    "trade_cost_bps": [10],
                },
            },
            {
                "phase_id": "future_pair_search",
                "enabled": False,
                "role": "exploratory_training",
                "rationale": (
                    "Pair exclusions are generated only from measured single-stock "
                    "ablation evidence; no pair is guessed in advance."
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
                "rationale": "Validation remains closed during composition search.",
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


def build_envelope_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    source_v8c_manifest_path: str | Path,
    shortlists_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    strategy_config_path: str | Path | None = None,
    canonical_cost_bps: float = 10.0,
) -> dict[str, Any]:
    root = Path(experiment_dir)
    manifest, raw = _read_verified_bundle(
        root, strategy_config_path=strategy_config_path
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("research_stage") != "allocation_envelope_projection":
        raise NdxEnvelopeAnalysisError("experiment is not v8d envelope projection")
    if contract.get("decision_priority") != "incumbent_first":
        raise NdxEnvelopeAnalysisError("v8d is not incumbent-first")
    v8c_manifest_path = Path(source_v8c_manifest_path)
    shortlist_path = Path(shortlists_path)
    if not v8c_manifest_path.exists() or not shortlist_path.exists():
        raise NdxEnvelopeAnalysisError("upstream v8c or shortlist evidence is missing")
    if _content_hash(v8c_manifest_path) != contract.get(
        "source_v8c_manifest_sha256"
    ):
        raise NdxEnvelopeAnalysisError("source v8c manifest hash changed")
    if _content_hash(shortlist_path) != contract.get(
        "source_stage1_shortlists_sha256"
    ):
        raise NdxEnvelopeAnalysisError("stage1 shortlist hash changed")

    analysis_frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=float(canonical_cost_bps),
        strategy_config_path=strategy_config_path,
    )
    candidates = attach_cost_invariant_concentration(
        raw["candidates"], analysis_frames["concentration"]
    )
    baseline_ids = list(contract.get("baseline_profile_ids") or [])
    challenger_ids = list(contract.get("challenger_profile_ids") or [])
    if len(baseline_ids) != 2 or len(challenger_ids) != 2:
        raise NdxEnvelopeAnalysisError("v8d declared profile roles changed")
    cap20_id, cap1363_id = baseline_ids
    top3_id, full_id = challenger_ids

    all_candidate_effects = []
    all_window_effects = []
    pair_summaries = []
    for challenger_id, baseline_id in (
        (top3_id, cap1363_id),
        (top3_id, cap20_id),
    ):
        candidate_effects, window_effects, pair_summary = paired_profile_effects(
            candidates,
            raw["windows"],
            challenger_id=challenger_id,
            baseline_id=baseline_id,
        )
        all_candidate_effects.append(candidate_effects)
        all_window_effects.append(window_effects)
        pair_summaries.append(pair_summary)
    candidate_effects = pd.concat(all_candidate_effects, ignore_index=True)
    window_effects = pd.concat(all_window_effects, ignore_index=True)
    equivalence = profile_equivalence_audit(
        candidates,
        raw["windows"],
        raw["selections"],
        left_id=top3_id,
        right_id=full_id,
    )

    vs_conservative = pair_summaries[0]
    canonical_top3 = candidates[
        candidates["profile_id"].astype(str).eq(top3_id)
        & np.isclose(candidates["trade_cost_bps"], float(canonical_cost_bps))
    ]
    if len(canonical_top3) != 3 or not canonical_top3[
        "concentration_guard_passed"
    ].fillna(False).all():
        raise NdxEnvelopeAnalysisError(
            "exact Top3 profile is not concentration-compliant across lookbacks"
        )
    if not (
        vs_conservative["candidate_p50_return_improvement_count"]
        == vs_conservative["candidate_pairs"]
        and vs_conservative["candidate_p10_return_improvement_count"]
        == vs_conservative["candidate_pairs"]
        and np.isclose(vs_conservative["window_return_improvement_rate"], 1.0)
        and equivalence["economically_equivalent"]
    ):
        raise NdxEnvelopeAnalysisError(
            "v8d does not support retaining Top3 for composition search"
        )

    profile_order = [cap20_id, top3_id, cap1363_id]
    selected = _curve_candidates(candidates, profile_order)
    holdings, sector_exposure = _latest_portfolios(raw["selections"], selected)
    selected_keys = selected[["profile_id", "lookback_years", "trade_cost_bps"]]
    selected_windows = raw["windows"].merge(
        selected_keys,
        on=["profile_id", "lookback_years", "trade_cost_bps"],
        how="inner",
        validate="many_to_one",
    )

    shortlists = pd.read_csv(shortlist_path)
    pool24 = shortlists[shortlists["shortlist_id"].astype(str).eq("pool24")]
    stage5_baseline_id = "pool24__q25__top12__source_top3_envelope_baseline"
    stage5 = stage5_composition_ablation_spec(
        source_manifest_path=root / "manifest.json",
        shortlist_path=shortlist_path,
        pool24=pool24,
        contract=contract,
        baseline_profile_id=stage5_baseline_id,
    )

    output = Path(output_dir) if output_dir else root / "analysis" / "envelope"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "ranked_candidates": output / "ranked_candidates.csv",
        "candidate_effects": output / "paired_candidate_effects.csv",
        "window_effects": output / "paired_window_effects.csv",
        "selected": output / "key_candidates.csv",
        "windows": output / "key_candidate_windows.csv",
        "holdings": output / "latest_holdings.csv",
        "sectors": output / "latest_sic2_exposure.csv",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "stage5": output / "stage5_composition_ablation_spec.yaml",
        "workbook": output / "v8d_envelope_analysis.xlsx",
    }
    ranked = candidates.sort_values(
        [
            "concentration_guard_passed",
            "incumbent_xirr_p50_margin",
            "incumbent_xirr_p10_margin",
        ],
        ascending=False,
        kind="stable",
    )
    for frame, key in (
        (ranked, "ranked_candidates"),
        (candidate_effects, "candidate_effects"),
        (window_effects, "window_effects"),
        (selected, "selected"),
        (selected_windows, "windows"),
        (holdings, "holdings"),
        (sector_exposure, "sectors"),
    ):
        _atomic_csv(frame, paths[key])
    atomic_write_text(
        paths["stage5"],
        yaml.safe_dump(stage5, allow_unicode=True, sort_keys=False),
    )

    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=float(canonical_cost_bps),
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_payload["research_stage"] = "v8d_exact_top3_envelope"
    curve_payload["frontier_conclusion"] = {
        "decision": "RETAIN_EXACT_TOP3_ENVELOPE_FOR_COMPOSITION_SEARCH",
        "vs_cap1363": vs_conservative,
        "vs_cap20": pair_summaries[1],
        "full_envelope_redundancy": equivalence,
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
        {"项目": "候选方案数", "内容": len(candidates)},
        {"项目": "逐窗口审计记录", "内容": int(manifest["selection_rows"])},
        {"项目": "Top3约束失败", "内容": int(manifest["selection_constraint_audit"]["top_weight_cap_failures"])},
        {"项目": "有效持仓数约束失败", "内容": int(manifest["selection_constraint_audit"]["effective_n_floor_failures"])},
        {"项目": "相对13.63%上限收益中位全组改善", "内容": vs_conservative["candidate_p50_return_improvement_count"]},
        {"项目": "相对13.63%上限收益尾部全组改善", "内容": vs_conservative["candidate_p10_return_improvement_count"]},
        {"项目": "相对13.63%上限逐窗口收益改善率", "内容": vs_conservative["window_return_improvement_rate"]},
        {"项目": "相对13.63%上限逐窗口回撤改善率", "内容": vs_conservative["window_dd_improvement_rate"]},
        {"项目": "有效持仓数下限是否产生独立结果", "内容": "否，Top3-only与完整边界在1e-8内等价"},
        {"项目": "结论", "内容": "保留精确Top3投影作为更强合规挑战结构，不替换当前8只"},
        {"项目": "下一步", "内容": "固定权重与风险边界，对pool24逐只剔除，先测股票组成敏感度"},
    ])
    pair_summary_frame = pd.DataFrame(pair_summaries)
    equivalence_frame = pd.DataFrame([equivalence])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary_frame.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(pair_summary_frame)[0].to_excel(
                writer, sheet_name="配对汇总", index=False
            )
            _localized_excel_frame(candidate_effects)[0].to_excel(
                writer, sheet_name="候选层配对", index=False
            )
            _localized_excel_frame(window_effects)[0].to_excel(
                writer, sheet_name="逐窗口配对", index=False
            )
            _localized_excel_frame(equivalence_frame)[0].to_excel(
                writer, sheet_name="冗余约束审计", index=False
            )
            _localized_excel_frame(selected)[0].to_excel(
                writer, sheet_name="关键曲线方案", index=False
            )
            _localized_excel_frame(ranked)[0].to_excel(
                writer, sheet_name="全部方案", index=False
            )
            _localized_excel_frame(selected_windows)[0].to_excel(
                writer, sheet_name="关键方案窗口", index=False
            )
            _localized_excel_frame(holdings)[0].to_excel(
                writer, sheet_name="最新持仓", index=False
            )
            _localized_excel_frame(sector_exposure)[0].to_excel(
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

    incumbent_gate_rows = int(
        candidates["incumbent_gate_passed"].fillna(False).astype(bool).sum()
    )
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
        "pair_summaries": pair_summaries,
        "full_envelope_redundancy": equivalence,
        "decision": "RETAIN_EXACT_TOP3_ENVELOPE_FOR_COMPOSITION_SEARCH",
        "stage5_profile_count": len(stage5["phases"][0]["construction_profiles"]),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
