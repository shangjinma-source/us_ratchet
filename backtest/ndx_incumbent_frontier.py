"""Incumbent-first Pareto analysis and chart evidence for NDX lab results."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from backtest.ndx_competition import run_ndx_profile_trace
from backtest.ndx_experiment_analysis import analyze_ndx_experiment
from backtest.ndx_experiment_lab import CONSTRUCTION_EXPORT_KEYS


FRONTIER_METRICS = (
    "incumbent_win_rate",
    "incumbent_xirr_p10_margin",
    "incumbent_xirr_p50_margin",
    "incumbent_dd_relief_p50",
    "incumbent_dd_relief_p90",
    "effective_n_p10",
)


class NdxIncumbentFrontierError(ValueError):
    """Raised when incumbent-first evidence is incomplete or inconsistent."""


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _json_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _pareto_mask(
    frame: pd.DataFrame,
    *,
    maximize: Iterable[str] = FRONTIER_METRICS,
    minimize: Iterable[str] = ("turnover_x_p50",),
) -> pd.Series:
    """Return non-dominated rows; missing metrics fail closed."""
    max_fields = list(maximize)
    min_fields = list(minimize)
    fields = max_fields + min_fields
    numeric = frame[fields].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().all(axis=1)
    transformed = numeric.copy()
    transformed[min_fields] *= -1.0
    values = transformed.to_numpy(dtype=float)
    result = np.zeros(len(frame), dtype=bool)
    for index in range(len(frame)):
        if not bool(valid.iloc[index]):
            continue
        candidate = values[index]
        dominated = False
        for peer_index in range(len(frame)):
            if peer_index == index or not bool(valid.iloc[peer_index]):
                continue
            peer = values[peer_index]
            if np.all(peer >= candidate) and np.any(peer > candidate):
                dominated = True
                break
        result[index] = not dominated
    return pd.Series(result, index=frame.index, dtype=bool)


def _balanced_score(frame: pd.DataFrame) -> pd.Series:
    components = []
    for field in FRONTIER_METRICS:
        values = pd.to_numeric(frame[field], errors="coerce")
        components.append(values.rank(method="average", pct=True))
    turnover = pd.to_numeric(frame["turnover_x_p50"], errors="coerce")
    components.append((-turnover).rank(method="average", pct=True))
    return pd.concat(components, axis=1).mean(axis=1, skipna=False)


def select_incumbent_frontier(
    candidates: pd.DataFrame,
    *,
    max_solutions: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select distinct, concentration-compliant solutions for chart replay."""
    required = {
        "profile_id",
        "windows",
        "concentration_guard_passed",
        "turnover_x_p50",
        *FRONTIER_METRICS,
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise NdxIncumbentFrontierError(
            f"incumbent frontier evidence is missing columns: {missing}"
        )
    work = candidates.copy()
    work["balanced_score"] = _balanced_score(work)
    work["pareto_optimal"] = _pareto_mask(work)
    work["beats_incumbent_return"] = (
        (pd.to_numeric(work["incumbent_win_rate"], errors="coerce") >= 0.50)
        & (pd.to_numeric(work["incumbent_xirr_p50_margin"], errors="coerce") >= 0.0)
    )
    eligible = work[
        work["concentration_guard_passed"].fillna(False).astype(bool)
        & (pd.to_numeric(work["windows"], errors="coerce") >= 12)
    ].copy()
    if eligible.empty:
        raise NdxIncumbentFrontierError(
            "no candidate has sufficient windows and incumbent concentration compliance"
        )
    frontier = eligible[eligible["pareto_optimal"]].copy()
    if frontier.empty:
        raise NdxIncumbentFrontierError("incumbent Pareto frontier is empty")

    role_specs = [
        (
            "highest_win_rate",
            ["incumbent_win_rate", "incumbent_xirr_p10_margin", "incumbent_xirr_p50_margin"],
        ),
        (
            "best_tail_return",
            ["incumbent_xirr_p10_margin", "incumbent_win_rate", "incumbent_xirr_p50_margin"],
        ),
        (
            "best_median_return",
            ["incumbent_xirr_p50_margin", "incumbent_xirr_p10_margin", "incumbent_win_rate"],
        ),
        (
            "best_drawdown",
            ["incumbent_dd_relief_p90", "incumbent_dd_relief_p50", "incumbent_win_rate"],
        ),
        (
            "best_diversification",
            ["effective_n_p10", "incumbent_xirr_p10_margin", "incumbent_win_rate"],
        ),
        (
            "balanced_pareto",
            ["balanced_score", "incumbent_win_rate", "incumbent_xirr_p10_margin"],
        ),
    ]
    selected_rows = []
    selected_profiles = set()
    for role, fields in role_specs:
        ordered = frontier.sort_values(fields, ascending=False, kind="stable")
        row = next(
            (
                item for _, item in ordered.iterrows()
                if str(item["profile_id"]) not in selected_profiles
            ),
            None,
        )
        if row is None:
            continue
        selected_profiles.add(str(row["profile_id"]))
        payload = row.to_dict()
        payload["frontier_role"] = role
        selected_rows.append(payload)
        if len(selected_rows) >= int(max_solutions):
            break
    if len(selected_rows) < int(max_solutions):
        ordered = frontier.sort_values(
            ["balanced_score", "incumbent_win_rate", "incumbent_xirr_p10_margin"],
            ascending=False,
            kind="stable",
        )
        for _, row in ordered.iterrows():
            profile_id = str(row["profile_id"])
            if profile_id in selected_profiles:
                continue
            selected_profiles.add(profile_id)
            payload = row.to_dict()
            payload["frontier_role"] = "additional_pareto"
            selected_rows.append(payload)
            if len(selected_rows) >= int(max_solutions):
                break
    return work, pd.DataFrame(selected_rows)


def _profile_from_candidate(row: pd.Series) -> dict:
    keys = [
        *CONSTRUCTION_EXPORT_KEYS,
        "top_n",
        "weight_mode",
        "rebalance_months",
        "safe_weight",
        "max_weight",
        "min_weight",
    ]
    profile = {}
    for key in dict.fromkeys(keys):
        if key not in row.index or pd.isna(row[key]):
            continue
        profile[key] = _json_scalar(row[key])
    profile["id"] = str(row["profile_id"])
    profile.pop("profile_id", None)
    return profile


def _parse_mapping(value: Any, *, numeric: bool = False) -> dict:
    result = {}
    for item in str(value or "").split(";"):
        if ":" not in item:
            continue
        key, raw = item.split(":", 1)
        result[str(key)] = float(raw) if numeric else str(raw)
    return result


def _latest_portfolio(
    selections: pd.DataFrame,
    row: pd.Series,
) -> dict:
    subset = selections[
        selections["profile_id"].astype(str).eq(str(row["profile_id"]))
        & np.isclose(selections["lookback_years"], float(row["lookback_years"]))
        & np.isclose(selections["trade_cost_bps"], float(row["trade_cost_bps"]))
    ].copy()
    if "phase_id" in row.index and "phase_id" in subset:
        subset = subset[subset["phase_id"].astype(str).eq(str(row["phase_id"]))]
    if subset.empty:
        raise NdxIncumbentFrontierError(
            f"selection evidence missing for {row['profile_id']}"
        )
    subset = subset.sort_values("selection_date", kind="stable")
    latest = subset.iloc[-1]
    weights = _parse_mapping(latest["weights"], numeric=True)
    sic2 = _parse_mapping(latest.get("sic2_by_ticker"))
    sic4 = _parse_mapping(latest.get("sic4_by_ticker"))
    holdings = [
        {
            "ticker": ticker,
            "risk_sleeve_weight": weight,
            "portfolio_weight": weight * (1.0 - float(row["safe_weight"])),
            "sic2": sic2.get(ticker),
            "sic4": sic4.get(ticker),
        }
        for ticker, weight in sorted(weights.items(), key=lambda item: item[1], reverse=True)
    ]
    sector_weights = {}
    for holding in holdings:
        sector = holding["sic2"] or "unclassified"
        sector_weights[sector] = sector_weights.get(sector, 0.0) + float(
            holding["portfolio_weight"]
        )
    return {
        "selection_date": str(latest["selection_date"])[:10],
        "holdings": holdings,
        "sector_weights": sector_weights,
    }


def _manifest_sha256(experiment_dir: Path) -> str:
    return hashlib.sha256((experiment_dir / "manifest.json").read_bytes()).hexdigest()


def read_verified_incumbent_curve_bundle(
    curves_path: str | Path,
    manifest_path: str | Path,
) -> dict:
    """Read a static curve bundle only when it still matches its source manifest."""
    curve_file = Path(curves_path)
    manifest_file = Path(manifest_path)
    if not curve_file.exists():
        raise NdxIncumbentFrontierError(f"curve evidence is missing: {curve_file}")
    if not manifest_file.exists():
        raise NdxIncumbentFrontierError(
            f"source experiment manifest is missing: {manifest_file}"
        )
    try:
        payload = json.loads(curve_file.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxIncumbentFrontierError(
            f"curve evidence is not valid JSON: {exc}"
        ) from exc

    expected_hash = hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    if payload.get("source_manifest_sha256") != expected_hash:
        raise NdxIncumbentFrontierError(
            "curve evidence is stale because the source manifest changed"
        )
    if payload.get("source_experiment_id") != manifest.get("experiment_id"):
        raise NdxIncumbentFrontierError(
            "curve evidence experiment id does not match its source manifest"
        )
    if (
        int(manifest.get("completed_jobs") or 0)
        != int(manifest.get("planned_jobs") or 0)
        or int(manifest.get("failed_jobs") or 0) != 0
    ):
        raise NdxIncumbentFrontierError(
            "source experiment is incomplete or contains failed jobs"
        )
    if not payload.get("available") or not payload.get("research_only"):
        raise NdxIncumbentFrontierError(
            "curve evidence is not a complete research-only bundle"
        )

    dates = payload.get("dates") or []
    if not dates:
        raise NdxIncumbentFrontierError("curve evidence has no dates")
    if (
        any(not isinstance(value, str) or len(value) != 10 for value in dates)
        or dates != sorted(dates)
        or len(set(dates)) != len(dates)
    ):
        raise NdxIncumbentFrontierError(
            "curve evidence dates are not unique ordered ISO dates"
        )
    secondary_reference = str(payload.get("secondary_reference") or "").strip()
    if not secondary_reference:
        raise NdxIncumbentFrontierError(
            "curve evidence has no declared secondary reference"
        )
    for family in ("nav_series", "drawdown_series"):
        series = payload.get(family) or {}
        required = {
            "current_config",
            secondary_reference,
        }
        if not required.issubset(series):
            raise NdxIncumbentFrontierError(
                f"curve evidence {family} is missing a benchmark series"
            )
        for values in series.values():
            if not isinstance(values, list) or len(values) != len(dates):
                raise NdxIncumbentFrontierError(
                    f"curve evidence {family} does not align with dates"
                )
            try:
                numeric = np.asarray(values, dtype=float)
            except (TypeError, ValueError) as exc:
                raise NdxIncumbentFrontierError(
                    f"curve evidence {family} contains non-numeric values"
                ) from exc
            if not np.isfinite(numeric).all():
                raise NdxIncumbentFrontierError(
                    f"curve evidence {family} contains non-finite values"
                )
    solution_rows = payload.get("solutions") or []
    solution_ids = [str(row.get("solution_id") or "") for row in solution_rows]
    if not solution_ids or any(not value for value in solution_ids):
        raise NdxIncumbentFrontierError("curve evidence has no displayed solutions")
    if len(set(solution_ids)) != len(solution_ids):
        raise NdxIncumbentFrontierError(
            "curve evidence contains duplicate solution ids"
        )
    solution_id_set = set(solution_ids)
    if not solution_id_set.issubset(payload["nav_series"]):
        raise NdxIncumbentFrontierError(
            "curve evidence is missing one or more solution NAV series"
        )
    if not solution_id_set.issubset(payload["drawdown_series"]):
        raise NdxIncumbentFrontierError(
            "curve evidence is missing one or more solution drawdown series"
        )
    return payload


def build_incumbent_frontier_bundle(
    experiment_dir: str | Path,
    cfg,
    *,
    canonical_cost_bps: float = 10.0,
    max_solutions: int = 6,
    strategy_config_path: str | Path | None = None,
    selected_candidates: pd.DataFrame | None = None,
) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    root = Path(experiment_dir)
    frames, analysis = analyze_ndx_experiment(
        root,
        cfg,
        canonical_cost_bps=float(canonical_cost_bps),
        strategy_config_path=strategy_config_path,
    )
    contract = analysis.get("analysis_contract") or {}
    if contract.get("decision_priority") != "incumbent_first":
        raise NdxIncumbentFrontierError(
            "experiment did not pre-register incumbent_first decision priority"
        )
    canonical = frames["concentration"].copy()
    ranked, frontier_selected = select_incumbent_frontier(
        canonical,
        max_solutions=int(max_solutions),
    )
    if selected_candidates is not None:
        declared = selected_candidates.copy()
        identity_fields = ["profile_id", "lookback_years", "trade_cost_bps"]
        if "phase_id" in declared and "phase_id" in ranked:
            identity_fields.insert(0, "phase_id")
        role_fields = [
            field for field in ("analysis_role", "analysis_role_cn")
            if field in declared
        ]
        declared = declared[identity_fields + role_fields].copy()
        declared["_display_order"] = np.arange(len(declared), dtype=int)
        selected = ranked.merge(
            declared,
            on=identity_fields,
            how="inner",
            validate="one_to_one",
        )
        if len(selected) != len(declared):
            raise NdxIncumbentFrontierError(
                "one or more selected curve candidates are not in canonical evidence"
            )
        selected = selected.sort_values("_display_order", kind="stable").drop(
            columns="_display_order"
        )
    else:
        selected = frontier_selected
    if selected.empty:
        raise NdxIncumbentFrontierError("no distinct incumbent frontier solutions")
    required_selected = {
        "profile_id",
        "lookback_years",
        "trade_cost_bps",
        "research_start",
        "research_end",
    }
    missing_selected = sorted(required_selected - set(selected.columns))
    if missing_selected:
        raise NdxIncumbentFrontierError(
            f"selected curve candidates are missing columns: {missing_selected}"
        )
    identities = selected[
        ["profile_id", "lookback_years", "trade_cost_bps"]
    ].astype({"profile_id": str})
    if identities.duplicated().any():
        raise NdxIncumbentFrontierError(
            "selected curve candidates contain duplicate experiment identities"
        )
    if "frontier_role" not in selected:
        selected["frontier_role"] = selected.get(
            "analysis_role", "key_evidence"
        )
    selections = pd.read_csv(root / "selections.csv", low_memory=False)
    research_starts = selected["research_start"].dropna().astype(str).str[:10].unique()
    research_ends = selected["research_end"].dropna().astype(str).str[:10].unique()
    if len(research_starts) != 1 or len(research_ends) != 1:
        raise NdxIncumbentFrontierError("frontier candidates do not share one training period")
    window_start = str(research_starts[0])
    research_end = str(research_ends[0])
    target = str(analysis["primary_target"])

    original_start = cfg.data.start_date
    original_end = cfg.data.end_date
    cfg.data.start_date = window_start
    cfg.data.end_date = research_end
    dates = None
    incumbent_nav = None
    target_nav = None
    incumbent_drawdown = None
    target_drawdown = None
    nav_series = {}
    drawdown_series = {}
    solution_rows = []
    daily_columns = {}
    try:
        for solution_index, (_, row) in enumerate(selected.iterrows(), start=1):
            profile = _profile_from_candidate(row)
            trace = run_ndx_profile_trace(
                cfg,
                profile,
                window_start=window_start,
                target_benchmark=target,
                lookback_years=float(row["lookback_years"]),
                trade_cost_bps=float(row["trade_cost_bps"]),
                local_only=True,
            )
            daily = trace["daily"]
            observed_dates = daily["date"].dt.strftime("%Y-%m-%d").tolist()
            if dates is None:
                dates = observed_dates
                incumbent_nav = daily["incumbent_nav"].to_numpy(dtype=float)
                target_nav = daily["target_nav"].to_numpy(dtype=float)
                incumbent_drawdown = daily["incumbent_drawdown"].to_numpy(dtype=float)
                target_drawdown = daily["target_drawdown"].to_numpy(dtype=float)
            elif observed_dates != dates:
                raise NdxIncumbentFrontierError("frontier trace dates do not align")
            elif not (
                np.allclose(incumbent_nav, daily["incumbent_nav"], rtol=0.0, atol=1e-10)
                and np.allclose(target_nav, daily["target_nav"], rtol=0.0, atol=1e-10)
            ):
                raise NdxIncumbentFrontierError(
                    "incumbent or target trace changed across candidate replay"
                )
            solution_id = f"solution_{solution_index}"
            nav = daily["strategy_nav"].to_numpy(dtype=float)
            drawdown = daily["strategy_drawdown"].to_numpy(dtype=float)
            nav_series[solution_id] = nav.tolist()
            drawdown_series[solution_id] = (-drawdown).tolist()
            daily_columns[f"{solution_id}_nav"] = nav
            daily_columns[f"{solution_id}_drawdown"] = -drawdown
            portfolio = _latest_portfolio(selections, row)
            metrics = {
                key: _json_scalar(row[key])
                for key in [
                    "profile_id",
                    "frontier_role",
                    "analysis_role",
                    "analysis_role_cn",
                    "lookback_years",
                    "trade_cost_bps",
                    "top_n",
                    "weight_mode",
                    "rebalance_months",
                    "safe_weight",
                    "max_weight",
                    "top_weight_count",
                    "top_weight_cap",
                    "min_effective_n",
                    "fundamental_score_weight",
                    "max_names_per_sic4",
                    "max_names_per_sic2",
                    "windows",
                    "incumbent_win_rate",
                    "incumbent_dd_win_rate",
                    "incumbent_xirr_p50_margin",
                    "incumbent_xirr_p10_margin",
                    "incumbent_dd_relief_p50",
                    "incumbent_dd_relief_p90",
                    "effective_n_p10",
                    "top1_p90",
                    "top3_p90",
                    "max_top_weight_p90",
                    "observed_min_effective_n",
                    "turnover_x_p50",
                    "balanced_score",
                    "pareto_optimal",
                    "beats_incumbent_return",
                    "concentration_guard_passed",
                    "incumbent_gate_passed",
                    "target_gate_passed",
                ]
                if key in row.index
            }
            solution_rows.append({
                "solution_id": solution_id,
                "label": str(
                    row.get("analysis_role_cn")
                    or row.get("frontier_role")
                    or f"方案{solution_index}"
                ),
                "metrics": metrics,
                "path_metrics": {
                    "strategy": trace["strategy"],
                    "incumbent": trace["incumbent"],
                    "target": trace["target"],
                },
                **portfolio,
            })
    finally:
        cfg.data.start_date = original_start
        cfg.data.end_date = original_end

    assert dates is not None
    nav_series = {
        "current_config": incumbent_nav.tolist(),
        **nav_series,
        target: target_nav.tolist(),
    }
    drawdown_series = {
        "current_config": (-incumbent_drawdown).tolist(),
        **drawdown_series,
        target: (-target_drawdown).tolist(),
    }
    daily_frame = pd.DataFrame({
        "date": dates,
        "current_config_nav": incumbent_nav,
        "current_config_drawdown": -incumbent_drawdown,
        **daily_columns,
        f"{target}_nav": target_nav,
        f"{target}_drawdown": -target_drawdown,
    })
    incumbent_weights = {
        symbol.ticker: float(symbol.cap_total)
        for symbol in cfg.symbols
        if float(symbol.cap_total) > 0
    }
    total = sum(incumbent_weights.values())
    incumbent_weights = {
        ticker: value / total for ticker, value in incumbent_weights.items()
    }
    top_ns = sorted({int(value) for value in ranked["top_n"].dropna().unique()})
    incumbent_beating_rows = int((
        (pd.to_numeric(ranked["incumbent_win_rate"], errors="coerce") >= 0.50)
        & (pd.to_numeric(
            ranked["incumbent_xirr_p50_margin"], errors="coerce"
        ) >= 0.0)
        & (pd.to_numeric(
            ranked["incumbent_xirr_p10_margin"], errors="coerce"
        ) >= 0.0)
    ).sum())
    payload = {
        "schema_version": 2,
        "available": True,
        "research_only": True,
        "source_experiment_id": analysis["source_experiment_id"],
        "source_manifest_sha256": _manifest_sha256(root),
        "decision_priority": "incumbent_first",
        "primary_competition_benchmark": "current_config",
        "secondary_reference": target,
        "training_period": [window_start, research_end],
        "held_out_validation_used": False,
        "canonical_cost_bps": float(canonical_cost_bps),
        "search_summary": {
            "evaluated_candidate_rows": int(analysis["training_candidate_rows"]),
            "canonical_candidate_rows": int(len(ranked)),
            "concentration_compliant_rows": int(
                ranked["concentration_guard_passed"].fillna(False).sum()
            ),
            "incumbent_beating_rows": incumbent_beating_rows,
            "pareto_rows": int(ranked["pareto_optimal"].sum()),
            "displayed_solutions": len(solution_rows),
            "display_selection": (
                "declared_key_evidence_roles"
                if selected_candidates is not None
                else "concentration_compliant_pareto_frontier"
            ),
            "top_ns": top_ns,
            "theoretical_equal_weight_combinations": {
                str(top_n): str(math.comb(100, top_n)) for top_n in top_ns
            },
            "search_scope_note": (
                "Exhaustive over the pre-registered rule matrix, not over every "
                "possible C(100,n) security set or continuous weight vector."
            ),
        },
        "incumbent": {
            "safe_weight": float(cfg.safe_leg.target_weight) if cfg.safe_leg else 0.0,
            "risk_sleeve_weights": incumbent_weights,
        },
        "solutions": solution_rows,
        "dates": dates,
        "nav_series": nav_series,
        "drawdown_series": drawdown_series,
        "evidence": {
            "input_version_bundle_ids": analysis["input_version_bundle_ids"],
            "constraint_audit_passed": analysis["constraint_audit_passed"],
            "concentration_event_policy": analysis["concentration_event_policy"],
            "sector_classification": "point_in_time_sec_sic_not_gics",
        },
    }
    return payload, ranked, selected, daily_frame
