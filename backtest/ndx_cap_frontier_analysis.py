"""Incumbent-first analysis of the completed NDX v8c source-cap frontier."""
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


class NdxCapFrontierAnalysisError(ValueError):
    """Raised when v8c evidence cannot support a deterministic next stage."""


CONCENTRATION_KEYS = (
    "selection_rows",
    "window_conditioned_rows",
    "duplicate_window_rows",
    "effective_n_p10",
    "effective_n_p50",
    "top1_p50",
    "top1_p90",
    "top3_p50",
    "top3_p90",
    "window_conditioned_churn_p50",
    "concentration_guard_passed",
    "concentration_effective_n_margin",
    "concentration_top1_margin",
    "concentration_top3_margin",
)
ADJACENT_GROUP_KEYS = (
    "profile_pool",
    "top_n",
    "lookback_years",
    "trade_cost_bps",
)
RETURN_FIELDS = (
    "incumbent_xirr_p50_margin",
    "incumbent_xirr_p10_margin",
)
DRAWDOWN_FIELDS = (
    "incumbent_dd_relief_p50",
    "incumbent_dd_relief_p90",
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


def _parse_mapping(value: Any, *, numeric: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in str(value or "").split(";"):
        if ":" not in item:
            continue
        key, raw = item.split(":", 1)
        result[str(key)] = float(raw) if numeric else str(raw)
    return result


def attach_cost_invariant_concentration(
    candidates: pd.DataFrame,
    canonical_concentration: pd.DataFrame,
) -> pd.DataFrame:
    """Attach canonical selection concentration to every transaction-cost row."""
    keys = ["profile_id", "lookback_years"]
    required = set(keys) | set(CONCENTRATION_KEYS)
    missing = sorted(required - set(canonical_concentration.columns))
    if missing:
        raise NdxCapFrontierAnalysisError(
            f"canonical concentration is missing columns: {missing}"
        )
    concentration = canonical_concentration[keys + list(CONCENTRATION_KEYS)].copy()
    if concentration.duplicated(keys).any():
        raise NdxCapFrontierAnalysisError(
            "canonical concentration contains duplicate profile/lookback rows"
        )
    base = candidates.drop(
        columns=[key for key in CONCENTRATION_KEYS if key in candidates],
        errors="ignore",
    )
    merged = base.merge(
        concentration,
        on=keys,
        how="left",
        validate="many_to_one",
    )
    if len(merged) != len(candidates):
        raise NdxCapFrontierAnalysisError("concentration merge changed row count")
    if merged[list(CONCENTRATION_KEYS)].isna().all(axis=1).any():
        raise NdxCapFrontierAnalysisError(
            "one or more candidates have no canonical concentration evidence"
        )
    merged["profile_pool"] = merged["profile_id"].astype(str).str.extract(
        r"^(pool\d+)"
    )[0]
    if merged["profile_pool"].isna().any():
        raise NdxCapFrontierAnalysisError("profile id does not declare its pool")
    return merged


def cap_cost_summary(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    grouped = candidates.groupby(["max_weight", "trade_cost_bps"], sort=True)
    for (cap, cost), frame in grouped:
        compliant = frame["concentration_guard_passed"].fillna(False).astype(bool)
        rows.append({
            "cap": float(cap),
            "trade_cost_bps": float(cost),
            "candidate_rows": len(frame),
            "concentration_compliant_rows": int(compliant.sum()),
            "incumbent_gate_passed_rows": int(
                frame["incumbent_gate_passed"].fillna(False).astype(bool).sum()
            ),
            "incumbent_win_rate_best": frame["incumbent_win_rate"].max(),
            "incumbent_xirr_p50_margin_best": frame[
                "incumbent_xirr_p50_margin"
            ].max(),
            "incumbent_xirr_p10_margin_best": frame[
                "incumbent_xirr_p10_margin"
            ].max(),
            "incumbent_dd_relief_p50_median": frame[
                "incumbent_dd_relief_p50"
            ].median(),
            "incumbent_dd_relief_p90_median": frame[
                "incumbent_dd_relief_p90"
            ].median(),
            "effective_n_p10_min": frame["effective_n_p10"].min(),
            "top1_p90_max": frame["top1_p90"].max(),
            "top3_p90_max": frame["top3_p90"].max(),
        })
    return pd.DataFrame(rows).sort_values(
        ["trade_cost_bps", "cap"], kind="stable"
    ).reset_index(drop=True)


def adjacent_cap_pairs(
    candidates: pd.DataFrame,
    *,
    tolerance: float = 1e-12,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Compare every adjacent cap while holding all other dimensions fixed."""
    required = {
        *ADJACENT_GROUP_KEYS,
        "max_weight",
        *RETURN_FIELDS,
        *DRAWDOWN_FIELDS,
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise NdxCapFrontierAnalysisError(
            f"adjacent-cap evidence is missing columns: {missing}"
        )
    rows = []
    for identity, frame in candidates.groupby(
        list(ADJACENT_GROUP_KEYS), sort=True, dropna=False
    ):
        ordered = frame.sort_values("max_weight", kind="stable")
        caps = ordered["max_weight"].astype(float).tolist()
        if len(caps) != len(set(caps)):
            raise NdxCapFrontierAnalysisError(
                f"duplicate cap inside fixed family {identity}"
            )
        for index in range(1, len(ordered)):
            lower = ordered.iloc[index - 1]
            upper = ordered.iloc[index]
            row = {
                key: value for key, value in zip(ADJACENT_GROUP_KEYS, identity)
            }
            row.update({
                "lower_cap": float(lower["max_weight"]),
                "upper_cap": float(upper["max_weight"]),
            })
            for field in (*RETURN_FIELDS, *DRAWDOWN_FIELDS):
                row[f"{field}_lower"] = float(lower[field])
                row[f"{field}_upper"] = float(upper[field])
                row[f"{field}_delta"] = float(upper[field] - lower[field])
            row["return_p50_improved"] = bool(
                row["incumbent_xirr_p50_margin_delta"] > tolerance
            )
            row["return_p10_improved"] = bool(
                row["incumbent_xirr_p10_margin_delta"] > tolerance
            )
            row["drawdown_p50_worsened"] = bool(
                row["incumbent_dd_relief_p50_delta"] < -tolerance
            )
            row["drawdown_p90_worsened"] = bool(
                row["incumbent_dd_relief_p90_delta"] < -tolerance
            )
            row["higher_cap_dominates"] = bool(
                row["incumbent_xirr_p50_margin_delta"] >= -tolerance
                and row["incumbent_xirr_p10_margin_delta"] >= -tolerance
                and row["incumbent_dd_relief_p50_delta"] >= -tolerance
                and row["incumbent_dd_relief_p90_delta"] >= -tolerance
                and any(
                    row[f"{field}_delta"] > tolerance
                    for field in (*RETURN_FIELDS, *DRAWDOWN_FIELDS)
                )
            )
            rows.append(row)
    pairs = pd.DataFrame(rows)
    summary = {
        "family_paths": int(
            candidates.groupby(list(ADJACENT_GROUP_KEYS), dropna=False).ngroups
        ),
        "adjacent_comparisons": len(pairs),
        "return_p50_improved": int(pairs["return_p50_improved"].sum()),
        "return_p10_improved": int(pairs["return_p10_improved"].sum()),
        "drawdown_p50_worsened": int(pairs["drawdown_p50_worsened"].sum()),
        "drawdown_p90_worsened": int(pairs["drawdown_p90_worsened"].sum()),
        "higher_cap_dominates": int(pairs["higher_cap_dominates"].sum()),
    }
    return pairs, summary


def dimension_effects(candidates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dimension in (
        "profile_pool",
        "top_n",
        "lookback_years",
        "trade_cost_bps",
        "max_weight",
    ):
        for value, frame in candidates.groupby(dimension, sort=True, dropna=False):
            rows.append({
                "dimension": dimension,
                "value": value,
                "candidate_rows": len(frame),
                "incumbent_win_rate_median": frame["incumbent_win_rate"].median(),
                "incumbent_win_rate_best": frame["incumbent_win_rate"].max(),
                "incumbent_xirr_p50_margin_median": frame[
                    "incumbent_xirr_p50_margin"
                ].median(),
                "incumbent_xirr_p50_margin_best": frame[
                    "incumbent_xirr_p50_margin"
                ].max(),
                "incumbent_xirr_p10_margin_median": frame[
                    "incumbent_xirr_p10_margin"
                ].median(),
                "incumbent_xirr_p10_margin_best": frame[
                    "incumbent_xirr_p10_margin"
                ].max(),
                "incumbent_dd_relief_p50_median": frame[
                    "incumbent_dd_relief_p50"
                ].median(),
                "incumbent_dd_relief_p90_median": frame[
                    "incumbent_dd_relief_p90"
                ].median(),
                "concentration_pass_rate": frame[
                    "concentration_guard_passed"
                ].fillna(False).mean(),
            })
    return pd.DataFrame(rows)


def select_cap_curve_candidates(
    candidates: pd.DataFrame,
    *,
    canonical_cost_bps: float,
    envelope: dict,
) -> pd.DataFrame:
    canonical = candidates[
        np.isclose(candidates["trade_cost_bps"], float(canonical_cost_bps))
    ].copy()
    if canonical.empty:
        raise NdxCapFrontierAnalysisError("canonical-cost candidates are missing")
    upper_cap = float(canonical["max_weight"].max())
    upper = canonical[np.isclose(canonical["max_weight"], upper_cap)].sort_values(
        [
            "incumbent_xirr_p50_margin",
            "incumbent_xirr_p10_margin",
            "incumbent_win_rate",
        ],
        ascending=False,
        kind="stable",
    )
    anchor = upper.iloc[0]
    selected = canonical[
        canonical["profile_pool"].astype(str).eq(str(anchor["profile_pool"]))
        & canonical["top_n"].eq(anchor["top_n"])
        & np.isclose(canonical["lookback_years"], float(anchor["lookback_years"]))
    ].sort_values("max_weight", kind="stable")
    expected_caps = sorted(canonical["max_weight"].astype(float).unique())
    observed_caps = selected["max_weight"].astype(float).tolist()
    if observed_caps != expected_caps or selected["max_weight"].duplicated().any():
        raise NdxCapFrontierAnalysisError(
            "best-return family does not contain exactly one row for every cap"
        )

    labels = []
    roles = []
    top3_equal = float(envelope["top3"]) / 3.0
    top1 = float(envelope["top1"])
    for cap in observed_caps:
        role = f"source_cap_{cap:.4f}".replace(".", "p")
        if np.isclose(cap, min(expected_caps)):
            label = f"单股上限{cap:.2%}（低集中端点）"
        elif np.isclose(cap, top3_equal, atol=5e-5):
            label = f"单股上限{cap:.2%}（Top3等分边界）"
        elif np.isclose(cap, top1, atol=5e-5):
            label = f"单股上限{cap:.2%}（当前8只Top1锚点）"
        elif np.isclose(cap, max(expected_caps)):
            label = f"单股上限{cap:.2%}（v8b收益端点）"
        else:
            label = f"单股上限{cap:.2%}"
        roles.append(role)
        labels.append(label)
    selected = selected.copy()
    selected["analysis_role"] = roles
    selected["analysis_role_cn"] = labels
    return selected


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
            raise NdxCapFrontierAnalysisError(
                f"selection evidence is missing for {row.profile_id}"
            )
        latest_date = str(subset["selection_date"].max())[:10]
        latest = subset[
            subset["selection_date"].astype(str).str[:10].eq(latest_date)
        ]
        if len(set(latest["weights"].astype(str))) != 1:
            raise NdxCapFrontierAnalysisError(
                f"latest weights disagree across windows for {row.profile_id}"
            )
        evidence = latest.iloc[0]
        weights = _parse_mapping(evidence["weights"], numeric=True)
        sic2 = _parse_mapping(evidence.get("sic2_by_ticker"))
        safe_weight = float(row.safe_weight)
        for ticker, weight in sorted(
            weights.items(), key=lambda item: item[1], reverse=True
        ):
            holdings_rows.append({
                "analysis_role": row.analysis_role,
                "analysis_role_cn": row.analysis_role_cn,
                "profile_id": row.profile_id,
                "selection_date": latest_date,
                "ticker": ticker,
                "sic2": sic2.get(ticker),
                "risk_sleeve_weight": weight,
                "portfolio_weight": weight * (1.0 - safe_weight),
            })
        sector_weights: dict[str, float] = {}
        for ticker, weight in weights.items():
            sector = str(sic2.get(ticker) or "unclassified")
            sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
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


def stage4_envelope_spec(
    *,
    source_manifest_path: Path,
    shortlist_path: Path,
    pool24_tickers: list[str],
    contract: dict,
    evidence_summary: dict,
) -> dict:
    top1 = float(contract["incumbent_top1"])
    top3 = float(contract["incumbent_top3"])
    effective_n = float(contract["incumbent_effective_n"])
    common = {
        "candidate_tickers": pool24_tickers,
        "top_n": 12,
        "weight_mode": "source_weight",
        "rebalance_months": 6,
        "safe_weight": 0.26,
        "challenger_sleeve_weight": 1.0,
        "min_weight": 0.02,
        "selection_mode": "rank",
        "fundamental_score_weight": 0.25,
        "quality_policy_id": "ndx_sec_quality_three_sleeve_v1",
        "defense_mode": "static",
    }
    profiles = [
        {
            "id": "pool24__q25__top12__source_cap20_baseline",
            **common,
            "max_weight": 0.20,
        },
        {
            "id": "pool24__q25__top12__source_cap1363_baseline",
            **common,
            "max_weight": 0.1363,
        },
        {
            "id": "pool24__q25__top12__source_top3_envelope",
            **common,
            "max_weight": top1,
            "top_weight_count": 3,
            "top_weight_cap": top3,
        },
        {
            "id": "pool24__q25__top12__source_full_envelope",
            **common,
            "max_weight": top1,
            "top_weight_count": 3,
            "top_weight_cap": top3,
            "min_effective_n": effective_n,
        },
    ]
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_envelope_projection_v8d",
        "research_question": (
            "Can minimum-tracking-error source weights constrained by the exact "
            "current-eight Top1, Top3 and effective-name envelope improve on "
            "uniform single-name caps?"
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
            "component_family": "incumbent_exact_concentration_envelope",
            "research_stage": "allocation_envelope_projection",
            "baseline_profile_id": profiles[0]["id"],
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_v8c_manifest_sha256": _content_hash(source_manifest_path),
            "source_stage1_shortlists_sha256": _content_hash(shortlist_path),
            "projection_objective": "minimum_l2_source_weight_tracking_error",
            "incumbent_top1": top1,
            "incumbent_top3": top3,
            "incumbent_effective_n": effective_n,
            "v8c_adjacent_comparisons": int(
                evidence_summary["adjacent_comparisons"]
            ),
            "v8c_higher_cap_return_p50_improvements": int(
                evidence_summary["return_p50_improved"]
            ),
            "v8c_higher_cap_drawdown_p90_worsenings": int(
                evidence_summary["drawdown_p90_worsened"]
            ),
            "baseline_profile_ids": [profiles[0]["id"], profiles[1]["id"]],
            "challenger_profile_ids": [profiles[2]["id"], profiles[3]["id"]],
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
                "phase_id": "envelope_projection_training",
                "enabled": True,
                "role": "exploratory_training",
                "rationale": (
                    "v8c showed a strict return-versus-drawdown tradeoff at every "
                    "adjacent uniform cap. Re-run both cap baselines beside exact "
                    "asymmetric incumbent-envelope projections for paired attribution."
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
                    "Validation remains closed until one projection improves its "
                    "paired cap baseline across costs and training windows."
                ),
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


def build_cap_frontier_analysis_bundle(
    cfg,
    experiment_dir: str | Path,
    source_v8b_manifest_path: str | Path,
    shortlists_path: str | Path,
    *,
    output_dir: str | Path | None = None,
    strategy_config_path: str | Path | None = None,
    canonical_cost_bps: float = 10.0,
) -> dict:
    root = Path(experiment_dir)
    manifest, raw = _read_verified_bundle(
        root, strategy_config_path=strategy_config_path
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("research_stage") != "allocation_cap_frontier":
        raise NdxCapFrontierAnalysisError("experiment is not the v8c cap frontier")
    if contract.get("decision_priority") != "incumbent_first":
        raise NdxCapFrontierAnalysisError("v8c is not incumbent-first")
    v8b_manifest_path = Path(source_v8b_manifest_path)
    shortlist_path = Path(shortlists_path)
    if not v8b_manifest_path.exists() or not shortlist_path.exists():
        raise NdxCapFrontierAnalysisError("upstream v8b or shortlist evidence is missing")
    if _content_hash(v8b_manifest_path) != contract.get(
        "source_v8b_manifest_sha256"
    ):
        raise NdxCapFrontierAnalysisError("source v8b manifest hash changed")
    if _content_hash(shortlist_path) != contract.get(
        "source_stage1_shortlists_sha256"
    ):
        raise NdxCapFrontierAnalysisError("stage1 shortlist hash changed")

    analysis_frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=float(canonical_cost_bps),
        strategy_config_path=strategy_config_path,
    )
    candidates = attach_cost_invariant_concentration(
        raw["candidates"], analysis_frames["concentration"]
    )
    declared_caps = sorted(float(value) for value in contract.get("cap_grid") or [])
    observed_caps = sorted(candidates["max_weight"].astype(float).unique())
    if len(declared_caps) != len(observed_caps) or not np.allclose(
        declared_caps, observed_caps, rtol=0.0, atol=1e-12
    ):
        raise NdxCapFrontierAnalysisError("observed cap grid changed from registration")

    cap_summary = cap_cost_summary(candidates)
    adjacent, adjacent_summary = adjacent_cap_pairs(candidates)
    dimensions = dimension_effects(candidates)
    envelope = analysis["incumbent_concentration_envelope"]
    for key, contract_key in (
        ("top1", "incumbent_top1"),
        ("top3", "incumbent_top3"),
        ("effective_n", "incumbent_effective_n"),
    ):
        if not np.isclose(
            float(envelope[key]), float(contract[contract_key]), atol=1e-12, rtol=0.0
        ):
            raise NdxCapFrontierAnalysisError(
                f"incumbent concentration envelope changed: {key}"
            )

    selected = select_cap_curve_candidates(
        candidates,
        canonical_cost_bps=float(canonical_cost_bps),
        envelope=envelope,
    )
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
    if pool24.empty:
        raise NdxCapFrontierAnalysisError("stage1 shortlist has no pool24")
    pool24_tickers = pool24.sort_values("rank", kind="stable")["ticker"].tolist()

    incumbent_gate_rows = int(
        candidates["incumbent_gate_passed"].fillna(False).astype(bool).sum()
    )
    p50_nonnegative_rows = int(
        (candidates["incumbent_xirr_p50_margin"] >= 0.0).sum()
    )
    p10_nonnegative_rows = int(
        (candidates["incumbent_xirr_p10_margin"] >= 0.0).sum()
    )
    majority_win_rows = int((candidates["incumbent_win_rate"] >= 0.50).sum())
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
    compliant = ordered[
        ordered["concentration_guard_passed"].fillna(False).astype(bool)
    ]
    if compliant.empty:
        raise NdxCapFrontierAnalysisError("v8c has no concentration-compliant row")
    best_compliant = compliant.iloc[0]

    if not (
        adjacent_summary["return_p50_improved"]
        == adjacent_summary["adjacent_comparisons"]
        and adjacent_summary["return_p10_improved"]
        == adjacent_summary["adjacent_comparisons"]
        and adjacent_summary["drawdown_p90_worsened"]
        == adjacent_summary["adjacent_comparisons"]
        and adjacent_summary["higher_cap_dominates"] == 0
    ):
        raise NdxCapFrontierAnalysisError(
            "v8c no longer supports the pre-registered exact-envelope next step"
        )

    output = Path(output_dir) if output_dir else root / "analysis" / "cap_frontier"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "ranked_candidates": output / "ranked_candidates.csv",
        "cap_summary": output / "cap_cost_summary.csv",
        "adjacent_pairs": output / "adjacent_cap_pairs.csv",
        "dimensions": output / "dimension_effects.csv",
        "selected": output / "key_cap_candidates.csv",
        "windows": output / "key_cap_windows.csv",
        "holdings": output / "latest_holdings.csv",
        "sectors": output / "latest_sic2_exposure.csv",
        "curves": output / "portfolio_curves.json",
        "curve_daily": output / "portfolio_curves_daily.csv",
        "stage4": output / "stage4_envelope_projection_spec.yaml",
        "workbook": output / "v8c_cap_frontier_analysis.xlsx",
    }
    for frame, key in (
        (ordered, "ranked_candidates"),
        (cap_summary, "cap_summary"),
        (adjacent, "adjacent_pairs"),
        (dimensions, "dimensions"),
        (selected, "selected"),
        (selected_windows, "windows"),
        (holdings, "holdings"),
        (sector_exposure, "sectors"),
    ):
        _atomic_csv(frame, paths[key])

    stage4 = stage4_envelope_spec(
        source_manifest_path=root / "manifest.json",
        shortlist_path=shortlist_path,
        pool24_tickers=pool24_tickers,
        contract=contract,
        evidence_summary=adjacent_summary,
    )
    atomic_write_text(
        paths["stage4"],
        yaml.safe_dump(stage4, allow_unicode=True, sort_keys=False),
    )

    curve_payload, _, _, curve_daily = build_incumbent_frontier_bundle(
        root,
        cfg,
        canonical_cost_bps=float(canonical_cost_bps),
        max_solutions=len(selected),
        strategy_config_path=strategy_config_path,
        selected_candidates=selected,
    )
    curve_payload["research_stage"] = "v8c_source_cap_frontier"
    curve_payload["frontier_conclusion"] = {
        "decision": "STOP_SINGLE_CAP_FRONTIER_RUN_EXACT_INCUMBENT_ENVELOPE",
        **adjacent_summary,
        "incumbent_gate_passed_rows": incumbent_gate_rows,
        "incumbent_xirr_p50_nonnegative_rows": p50_nonnegative_rows,
        "incumbent_xirr_p10_nonnegative_rows": p10_nonnegative_rows,
        "incumbent_majority_win_rows": majority_win_rows,
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

    conclusion = pd.DataFrame([
        {"项目": "主竞争基准", "内容": "当前8只配置"},
        {"项目": "第二层参照", "内容": "012922"},
        {"项目": "候选方案数", "内容": len(candidates)},
        {"项目": "相邻上限比较数", "内容": adjacent_summary["adjacent_comparisons"]},
        {"项目": "上限放宽后XIRR中位改善", "内容": adjacent_summary["return_p50_improved"]},
        {"项目": "上限放宽后XIRR尾部改善", "内容": adjacent_summary["return_p10_improved"]},
        {"项目": "上限放宽后回撤压力恶化", "内容": adjacent_summary["drawdown_p90_worsened"]},
        {"项目": "完全支配的相邻放宽", "内容": adjacent_summary["higher_cap_dominates"]},
        {"项目": "通过当前8只收益守门方案", "内容": incumbent_gate_rows},
        {"项目": "收益最接近方案", "内容": best["profile_id"]},
        {"项目": "收益最接近方案XIRR中位差", "内容": best["incumbent_xirr_p50_margin"]},
        {"项目": "集中度合规最佳方案", "内容": best_compliant["profile_id"]},
        {"项目": "集中度合规最佳XIRR中位差", "内容": best_compliant["incumbent_xirr_p50_margin"]},
        {"项目": "结论", "内容": "单一上限没有无代价平台，停止继续细调该参数"},
        {"项目": "下一步", "内容": "测试当前8只精确Top1、Top3及有效持仓数边界下的非对称权重投影"},
    ])
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            conclusion.to_excel(writer, sheet_name="结论", index=False)
            _localized_excel_frame(cap_summary)[0].to_excel(
                writer, sheet_name="上限成本汇总", index=False
            )
            _localized_excel_frame(adjacent)[0].to_excel(
                writer, sheet_name="相邻上限比较", index=False
            )
            _localized_excel_frame(selected)[0].to_excel(
                writer, sheet_name="关键曲线方案", index=False
            )
            _localized_excel_frame(ordered)[0].to_excel(
                writer, sheet_name="全部方案", index=False
            )
            _localized_excel_frame(dimensions)[0].to_excel(
                writer, sheet_name="维度效果", index=False
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
        "incumbent_xirr_p50_nonnegative_rows": p50_nonnegative_rows,
        "incumbent_xirr_p10_nonnegative_rows": p10_nonnegative_rows,
        "incumbent_majority_win_rows": majority_win_rows,
        "adjacent_cap_evidence": adjacent_summary,
        "best_unconstrained": {
            key: _json_scalar(best.get(key))
            for key in (
                "profile_id",
                "lookback_years",
                "trade_cost_bps",
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
            key: _json_scalar(best_compliant.get(key))
            for key in (
                "profile_id",
                "lookback_years",
                "trade_cost_bps",
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
        "incumbent_concentration_envelope": envelope,
        "decision": "STOP_SINGLE_CAP_FRONTIER_RUN_EXACT_INCUMBENT_ENVELOPE",
        "stage4_profile_count": len(stage4["phases"][0]["construction_profiles"]),
        "files": {key: path.name for key, path in paths.items()},
    }
    atomic_write_text(
        output / "summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
