"""Point-in-time correlation-cluster diagnostics for completed NDX labs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from backtest.ndx_competition import _price_universe_version
from backtest.ndx_experiment_analysis import (
    FAMILY_KEYS,
    SHAPE_KEYS,
    NdxExperimentAnalysisError,
    _concentration_baselines,
    _read_verified_bundle,
    _selection_concentration,
)
from backtest.preference_walkforward import _load_series, _research_cfg
from backtest.risk_envelope import resolve_risk_envelope_policy
from core.helpers import atomic_write_text
from data.candidate_pool import get_nasdaq_100_snapshot
from data.ndx_history import get_ndx_point_in_time_history


CORRELATION_SCHEMA_VERSION = 1
DEFAULT_LOOKBACK_DAYS = (126, 252, 504)
DEFAULT_THRESHOLDS = (0.65, 0.75, 0.85)
DEFAULT_MIN_OBSERVATIONS = 60

EVENT_EVIDENCE_KEYS = [
    "selection_date",
    "report_date",
    "available_date",
    "accession_number",
    "tickers",
    "weights",
]
COST_INVARIANCE_KEYS = [
    "experiment_id",
    "phase_id",
    "lookback_years",
    "top_n",
    "weight_mode",
    "rebalance_months",
    "safe_weight",
    "max_weight",
    "window_start",
    "selection_date",
    "trigger",
    "report_date",
    "available_date",
    "accession_number",
]


class NdxCorrelationClusterError(NdxExperimentAnalysisError):
    """Raised when point-in-time cluster evidence cannot be reproduced."""


def parse_positive_ints(
    value: str | Iterable[int],
    *,
    default: Iterable[int] = DEFAULT_LOOKBACK_DAYS,
) -> list[int]:
    parts = value.replace(";", ",").split(",") if isinstance(value, str) else value
    parsed = sorted({int(item) for item in parts if str(item).strip()})
    values = parsed or sorted(set(default))
    if any(item <= 1 for item in values):
        raise NdxCorrelationClusterError("lookback days must be integers above 1")
    return values


def parse_thresholds(
    value: str | Iterable[float],
    *,
    default: Iterable[float] = DEFAULT_THRESHOLDS,
) -> list[float]:
    parts = value.replace(";", ",").split(",") if isinstance(value, str) else value
    parsed = sorted({float(item) for item in parts if str(item).strip()})
    values = parsed or sorted(set(default))
    if any(not np.isfinite(item) or item <= 0 or item >= 1 for item in values):
        raise NdxCorrelationClusterError("correlation thresholds must be in (0, 1)")
    return values


def _stable_id(prefix: str, payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"{prefix}:{hashlib.sha256(encoded).hexdigest()[:16]}"


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ticker_list(text: str) -> list[str]:
    tickers = sorted({item.strip().upper() for item in str(text).split(";") if item.strip()})
    if not tickers or "QQQ" in tickers:
        raise NdxCorrelationClusterError("selection tickers are empty or contain benchmark-only QQQ")
    return tickers


def parse_weight_map(text: str, *, expected_tickers: Iterable[str] | None = None) -> dict[str, float]:
    weights: dict[str, float] = {}
    for item in str(text).split(";"):
        if not item.strip():
            continue
        if ":" not in item:
            raise NdxCorrelationClusterError(f"invalid serialized weight: {item!r}")
        ticker, raw_weight = item.rsplit(":", 1)
        ticker = ticker.strip().upper()
        if not ticker or ticker in weights:
            raise NdxCorrelationClusterError(f"duplicate or empty weight ticker: {ticker!r}")
        weight = float(raw_weight)
        if not np.isfinite(weight) or weight <= 0:
            raise NdxCorrelationClusterError(f"invalid weight for {ticker}: {raw_weight!r}")
        weights[ticker] = weight
    if expected_tickers is not None and set(weights) != set(expected_tickers):
        raise NdxCorrelationClusterError("serialized weights do not match selected tickers")
    if not weights or not np.isclose(sum(weights.values()), 1.0, atol=1e-6):
        raise NdxCorrelationClusterError("serialized weights do not sum to one")
    return weights


def build_selection_plan(
    selections: pd.DataFrame,
    *,
    canonical_cost_bps: float,
) -> dict[str, pd.DataFrame | dict]:
    required = set(SHAPE_KEYS + EVENT_EVIDENCE_KEYS + COST_INVARIANCE_KEYS + ["trade_cost_bps"])
    missing = sorted(required - set(selections.columns))
    if missing:
        raise NdxCorrelationClusterError(f"selection evidence columns are missing: {missing}")

    costs = sorted(float(item) for item in selections["trade_cost_bps"].dropna().unique())
    if not costs or not any(np.isclose(cost, canonical_cost_bps) for cost in costs):
        raise NdxCorrelationClusterError(
            f"canonical trade cost is absent: {canonical_cost_bps:g} bps"
        )
    comparison = selections.groupby(COST_INVARIANCE_KEYS, dropna=False).agg(
        row_count=("trade_cost_bps", "size"),
        cost_count=("trade_cost_bps", "nunique"),
        ticker_variants=("tickers", "nunique"),
        weight_variants=("weights", "nunique"),
    ).reset_index()
    expected_cost_count = len(costs)
    mismatch = comparison[
        (comparison["row_count"] != expected_cost_count)
        | (comparison["cost_count"] != expected_cost_count)
        | (comparison["ticker_variants"] != 1)
        | (comparison["weight_variants"] != 1)
    ]
    if not mismatch.empty:
        raise NdxCorrelationClusterError(
            f"selection or weights vary across transaction costs: {len(mismatch)} keys"
        )

    canonical = selections[np.isclose(selections["trade_cost_bps"], canonical_cost_bps)].copy()
    event_keys = SHAPE_KEYS + EVENT_EVIDENCE_KEYS
    events = canonical.drop_duplicates(event_keys).reset_index(drop=True)
    universes = events[["selection_date", "tickers"]].drop_duplicates().reset_index(drop=True)
    universes["universe_id"] = [
        _stable_id("ndx_corr_universe", {"selection_date": row.selection_date, "tickers": row.tickers})
        for row in universes.itertuples(index=False)
    ]
    scenarios = events[["selection_date", "tickers", "weights"]].drop_duplicates().reset_index(drop=True)
    scenarios = scenarios.merge(
        universes,
        on=["selection_date", "tickers"],
        validate="many_to_one",
    )
    scenarios["scenario_id"] = [
        _stable_id(
            "ndx_corr_scenario",
            {
                "selection_date": row.selection_date,
                "tickers": row.tickers,
                "weights": row.weights,
            },
        )
        for row in scenarios.itertuples(index=False)
    ]
    events = events.merge(
        scenarios,
        on=["selection_date", "tickers", "weights"],
        validate="many_to_one",
    )
    shape_events = events[SHAPE_KEYS + ["scenario_id"]].drop_duplicates().reset_index(drop=True)
    audit = {
        "costs_bps": costs,
        "comparison_keys": len(comparison),
        "cost_invariance_passed": True,
        "canonical_cost_bps": float(canonical_cost_bps),
        "canonical_window_conditioned_rows": len(canonical),
        "unique_shape_events": len(events),
        "duplicate_window_rows": len(canonical) - len(events),
        "unique_date_ticker_universes": len(universes),
        "unique_weight_scenarios": len(scenarios),
        "unique_shapes": events[SHAPE_KEYS].drop_duplicates().shape[0],
    }
    return {
        "audit": audit,
        "events": events,
        "shape_events": shape_events,
        "universes": universes,
        "scenarios": scenarios,
    }


def load_verified_price_panel(cfg, versions: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    expected = versions[versions["source_name"].eq("price_universe")][
        ["version_id", "content_sha256"]
    ].drop_duplicates()
    if len(expected) != 1:
        raise NdxCorrelationClusterError("price-universe version is missing or inconsistent")

    local_cfg = _research_cfg(cfg, True)
    history, _ = get_ndx_point_in_time_history(local_cfg)
    current, _ = get_nasdaq_100_snapshot(local_cfg)
    requested = sorted(
        set(history["ticker"].astype(str).str.upper())
        | set(current["ticker"].astype(str).str.upper())
        | {str(item.ticker).upper() for item in local_cfg.symbols}
    )
    series, _, errors = _load_series(local_cfg, requested)
    if errors or len(series) != len(requested):
        raise NdxCorrelationClusterError(
            f"local price universe is incomplete: {errors or 'unknown missing tickers'}"
        )
    observed = _price_universe_version(series)
    expected_row = expected.iloc[0]
    if (
        observed["version_id"] != expected_row["version_id"]
        or observed["content_sha256"] != expected_row["content_sha256"]
    ):
        raise NdxCorrelationClusterError(
            "local price universe no longer matches the completed experiment"
        )
    close = pd.concat(
        {ticker: frame["Close"].astype(float) for ticker, frame in sorted(series.items())},
        axis=1,
    ).sort_index()
    return close, observed


def correlation_matrix_before(
    close: pd.DataFrame,
    tickers: Iterable[str],
    selection_date: str | pd.Timestamp,
    *,
    lookback_days: int,
    min_observations: int,
) -> tuple[pd.DataFrame, dict]:
    names = sorted({str(item).upper() for item in tickers})
    missing = sorted(set(names) - set(close.columns))
    if missing:
        raise NdxCorrelationClusterError(f"price panel is missing selected tickers: {missing}")
    asof = pd.Timestamp(selection_date)
    prices = close.loc[close.index < asof, names].ffill().dropna(how="any")
    prices = prices.tail(int(lookback_days) + 1)
    returns = prices.pct_change(fill_method=None).dropna(how="any")
    if len(returns) < int(min_observations):
        raise NdxCorrelationClusterError(
            f"only {len(returns)} common observations before {asof.date()}"
        )
    if (returns.std(ddof=1) <= 0).any():
        raise NdxCorrelationClusterError("zero-variance return series cannot be clustered")
    corr = returns.corr()
    if corr.isna().any().any() or not np.isfinite(corr.to_numpy()).all():
        raise NdxCorrelationClusterError("correlation matrix contains non-finite values")
    corr = corr.clip(-1.0, 1.0)
    np.fill_diagonal(corr.values, 1.0)
    meta = {
        "selection_date": asof.strftime("%Y-%m-%d"),
        "requested_lookback_days": int(lookback_days),
        "observations": len(returns),
        "coverage": min(1.0, len(returns) / float(lookback_days)),
        "price_start": prices.index[0].strftime("%Y-%m-%d"),
        "price_end": prices.index[-1].strftime("%Y-%m-%d"),
        "strict_asof_passed": bool(prices.index[-1] < asof),
    }
    return corr, meta


def complete_linkage_clusters(corr: pd.DataFrame, threshold: float) -> dict[str, int]:
    if len(corr) == 1:
        return {str(corr.index[0]): 1}
    if list(corr.index) != list(corr.columns):
        raise NdxCorrelationClusterError("correlation matrix axes do not match")
    distance = np.clip(1.0 - corr.to_numpy(dtype=float), 0.0, 2.0)
    np.fill_diagonal(distance, 0.0)
    condensed = squareform(distance, checks=True)
    raw_labels = fcluster(
        linkage(condensed, method="complete"),
        t=1.0 - float(threshold),
        criterion="distance",
    )
    raw_groups: dict[int, list[str]] = {}
    for ticker, label in zip(corr.index, raw_labels):
        raw_groups.setdefault(int(label), []).append(str(ticker))
    ordered_groups = sorted(tuple(sorted(names)) for names in raw_groups.values())
    normalized = {
        ticker: cluster_id
        for cluster_id, names in enumerate(ordered_groups, start=1)
        for ticker in names
    }
    return normalized


def _pair_rows(
    universe: dict,
    corr: pd.DataFrame,
    meta: dict,
) -> list[dict]:
    rows = []
    names = list(corr.columns)
    for index, ticker_a in enumerate(names):
        for ticker_b in names[index + 1:]:
            rows.append({
                **universe,
                "lookback_days": meta["requested_lookback_days"],
                "observations": meta["observations"],
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "correlation": float(corr.loc[ticker_a, ticker_b]),
            })
    return rows


def _cluster_rows(
    universe: dict,
    corr: pd.DataFrame,
    meta: dict,
    threshold: float,
    labels: dict[str, int],
) -> list[dict]:
    rows = []
    for cluster_id in sorted(set(labels.values())):
        names = sorted(ticker for ticker, label in labels.items() if label == cluster_id)
        pair_values = [
            float(corr.loc[a, b])
            for index, a in enumerate(names)
            for b in names[index + 1:]
        ]
        rows.append({
            **universe,
            "lookback_days": meta["requested_lookback_days"],
            "observations": meta["observations"],
            "threshold": float(threshold),
            "cluster_id": int(cluster_id),
            "cluster_size": len(names),
            "tickers": ";".join(names),
            "within_corr_min": min(pair_values) if pair_values else np.nan,
            "within_corr_p50": float(np.median(pair_values)) if pair_values else np.nan,
            "within_corr_mean": float(np.mean(pair_values)) if pair_values else np.nan,
        })
    return rows


def scenario_cluster_metrics(
    scenario: dict,
    corr: pd.DataFrame,
    meta: dict,
    threshold: float,
    labels: dict[str, int],
) -> dict:
    tickers = _ticker_list(scenario["tickers"])
    weights = parse_weight_map(scenario["weights"], expected_tickers=tickers)
    clusters = []
    for cluster_id in sorted(set(labels.values())):
        names = sorted(ticker for ticker in tickers if labels[ticker] == cluster_id)
        ordered = sorted(names, key=lambda ticker: (-weights[ticker], ticker))
        cluster_weight = float(sum(weights[ticker] for ticker in names))
        clusters.append({
            "cluster_id": cluster_id,
            "tickers": names,
            "ordered": ordered,
            "weight": cluster_weight,
        })
    clusters.sort(key=lambda item: (-item["weight"], ";".join(item["tickers"])))
    largest = clusters[0]
    cluster_weights = np.asarray([item["weight"] for item in clusters], dtype=float)

    pair_mass = 0.0
    weighted_corr = 0.0
    high_corr_mass = 0.0
    high_corr_pairs = 0
    pair_records = []
    for index, ticker_a in enumerate(tickers):
        for ticker_b in tickers[index + 1:]:
            corr_value = float(corr.loc[ticker_a, ticker_b])
            mass = weights[ticker_a] * weights[ticker_b]
            pair_mass += mass
            weighted_corr += mass * corr_value
            if corr_value >= threshold:
                high_corr_mass += mass
                high_corr_pairs += 1
            pair_records.append((corr_value, weights[ticker_a] + weights[ticker_b], ticker_a, ticker_b))
    pair_records.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    max_pair = pair_records[0]
    top_weights = [weights[ticker] for ticker in largest["ordered"]]
    return {
        "scenario_id": scenario["scenario_id"],
        "universe_id": scenario["universe_id"],
        "selection_date": scenario["selection_date"],
        "tickers": scenario["tickers"],
        "weights": scenario["weights"],
        "lookback_days": meta["requested_lookback_days"],
        "observations": meta["observations"],
        "observation_coverage": meta["coverage"],
        "price_start": meta["price_start"],
        "price_end": meta["price_end"],
        "strict_asof_passed": meta["strict_asof_passed"],
        "threshold": float(threshold),
        "cluster_count": len(clusters),
        "effective_cluster_count": 1.0 / float(cluster_weights @ cluster_weights),
        "max_cluster_weight": largest["weight"],
        "largest_cluster_size": len(largest["tickers"]),
        "largest_cluster_tickers": ";".join(largest["ordered"]),
        "largest_cluster_top1_weight": float(sum(top_weights[:1])),
        "largest_cluster_top2_weight": float(sum(top_weights[:2])),
        "largest_cluster_top3_weight": float(sum(top_weights[:3])),
        "weighted_pair_correlation": weighted_corr / pair_mass,
        "high_corr_pair_count": high_corr_pairs,
        "high_corr_pair_mass_share": high_corr_mass / pair_mass,
        "max_pair_correlation": max_pair[0],
        "max_pair_joint_weight": max_pair[1],
        "max_pair_tickers": f"{max_pair[2]};{max_pair[3]}",
    }


def _baseline_inputs(
    cfg,
    selection_dates: Iterable[str],
    latest_price_date: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = {str(item.ticker).upper(): float(item.cap_total) for item in cfg.symbols}
    if not raw or any(not np.isfinite(value) or value <= 0 for value in raw.values()):
        raise NdxCorrelationClusterError("current-config baseline weights are invalid")
    total = sum(raw.values())
    weights = {ticker: value / total for ticker, value in raw.items()}
    tickers_text = ";".join(sorted(weights))
    weights_text = ";".join(f"{ticker}:{weights[ticker]:.8f}" for ticker in sorted(weights))
    dates = [(str(value)[:10], "historical_selection_date") for value in sorted(set(selection_dates))]
    latest_asof = (pd.Timestamp(latest_price_date) + pd.offsets.BDay(1)).strftime("%Y-%m-%d")
    dates.append((latest_asof, "latest_local_data"))
    universes = pd.DataFrame([
        {
            "selection_date": selection_date,
            "tickers": tickers_text,
            "baseline_period": period,
        }
        for selection_date, period in dates
    ])
    universes["universe_id"] = [
        _stable_id("ndx_corr_universe", {"selection_date": row.selection_date, "tickers": row.tickers})
        for row in universes.itertuples(index=False)
    ]
    scenarios = universes.copy()
    scenarios["weights"] = weights_text
    scenarios["scenario_id"] = [
        _stable_id(
            "ndx_corr_scenario",
            {
                "selection_date": row.selection_date,
                "tickers": row.tickers,
                "weights": row.weights,
            },
        )
        for row in scenarios.itertuples(index=False)
    ]
    return universes, scenarios


def _jaccard(left: str | None, right: str | None) -> float:
    a = set(str(left or "").split(";")) - {""}
    b = set(str(right or "").split(";")) - {""}
    return len(a & b) / len(a | b) if a and b else np.nan


def _shape_outputs(
    shape_events: pd.DataFrame,
    scenario_metrics: pd.DataFrame,
    candidates: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    canonical_cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    expanded = shape_events.merge(
        scenario_metrics,
        on="scenario_id",
        how="left",
        validate="many_to_many",
    )
    expanded["max_cluster_portfolio_weight"] = (
        expanded["max_cluster_weight"] * (1.0 - expanded["safe_weight"])
    )
    group_keys = SHAPE_KEYS + ["lookback_days", "threshold"]
    expanded = expanded.sort_values(group_keys + ["selection_date"])
    expanded["dominant_cluster_jaccard"] = np.nan
    for indexes in expanded.groupby(group_keys, dropna=False, sort=False).groups.values():
        previous = None
        values = []
        for index in indexes:
            current = expanded.at[index, "largest_cluster_tickers"]
            values.append(_jaccard(previous, current) if previous is not None else np.nan)
            previous = current
        expanded.loc[list(indexes), "dominant_cluster_jaccard"] = values

    expected = shape_events.groupby(SHAPE_KEYS).agg(
        expected_unique_events=("scenario_id", "nunique")
    ).reset_index()
    summary = expanded.groupby(group_keys, dropna=False).agg(
        analyzed_unique_events=("scenario_id", "nunique"),
        observations_min=("observations", "min"),
        observation_coverage_p10=("observation_coverage", lambda value: value.quantile(0.10)),
        cluster_count_p10=("cluster_count", lambda value: value.quantile(0.10)),
        cluster_count_p50=("cluster_count", "median"),
        effective_cluster_count_p10=(
            "effective_cluster_count", lambda value: value.quantile(0.10)
        ),
        effective_cluster_count_p50=("effective_cluster_count", "median"),
        max_cluster_weight_p50=("max_cluster_weight", "median"),
        max_cluster_weight_p90=("max_cluster_weight", lambda value: value.quantile(0.90)),
        max_cluster_weight_max=("max_cluster_weight", "max"),
        max_cluster_portfolio_weight_p90=(
            "max_cluster_portfolio_weight", lambda value: value.quantile(0.90)
        ),
        largest_cluster_size_p90=(
            "largest_cluster_size", lambda value: value.quantile(0.90)
        ),
        largest_cluster_size_max=("largest_cluster_size", "max"),
        weighted_pair_correlation_p50=("weighted_pair_correlation", "median"),
        weighted_pair_correlation_p90=(
            "weighted_pair_correlation", lambda value: value.quantile(0.90)
        ),
        high_corr_pair_mass_share_p50=("high_corr_pair_mass_share", "median"),
        high_corr_pair_mass_share_p90=(
            "high_corr_pair_mass_share", lambda value: value.quantile(0.90)
        ),
        max_pair_correlation_p90=("max_pair_correlation", lambda value: value.quantile(0.90)),
        max_pair_correlation_max=("max_pair_correlation", "max"),
        dominant_cluster_jaccard_p50=("dominant_cluster_jaccard", "median"),
        dominant_cluster_jaccard_p90=(
            "dominant_cluster_jaccard", lambda value: value.quantile(0.90)
        ),
        dominant_cluster_jaccard_ge_0p5_rate=(
            "dominant_cluster_jaccard",
            lambda value: float((value.dropna() >= 0.5).mean()) if value.notna().any() else np.nan,
        ),
    ).reset_index()
    summary = summary.merge(expected, on=SHAPE_KEYS, validate="many_to_one")
    summary["diagnostic_coverage"] = (
        summary["analyzed_unique_events"] / summary["expected_unique_events"]
    )

    canonical_candidates = candidates[
        np.isclose(candidates["trade_cost_bps"], canonical_cost_bps)
    ]
    summary = canonical_candidates.merge(summary, on=SHAPE_KEYS, validate="one_to_many")

    historical_baseline = baseline[baseline["baseline_period"].eq("historical_selection_date")]
    baseline_summary = historical_baseline.groupby(["lookback_days", "threshold"]).agg(
        incumbent_effective_cluster_count_p10=(
            "effective_cluster_count", lambda value: value.quantile(0.10)
        ),
        incumbent_max_cluster_weight_p90=(
            "max_cluster_weight", lambda value: value.quantile(0.90)
        ),
        incumbent_weighted_pair_correlation_p90=(
            "weighted_pair_correlation", lambda value: value.quantile(0.90)
        ),
    ).reset_index()
    summary = summary.merge(
        baseline_summary,
        on=["lookback_days", "threshold"],
        how="left",
        validate="many_to_one",
    )
    summary["incumbent_cluster_diagnostic_passed"] = (
        np.isclose(summary["diagnostic_coverage"], 1.0)
        & (
            summary["effective_cluster_count_p10"]
            >= summary["incumbent_effective_cluster_count_p10"] - 1e-9
        )
        & (
            summary["max_cluster_weight_p90"]
            <= summary["incumbent_max_cluster_weight_p90"] + 1e-9
        )
        & (
            summary["weighted_pair_correlation_p90"]
            <= summary["incumbent_weighted_pair_correlation_p90"] + 1e-9
        )
    )
    summary["cluster_diagnostic_only"] = True

    stress = expanded.sort_values(
        group_keys + ["max_cluster_weight", "weighted_pair_correlation"],
        ascending=[True] * len(group_keys) + [False, False],
    ).groupby(group_keys, as_index=False, sort=False).head(1)
    stress = canonical_candidates.merge(stress, on=SHAPE_KEYS, validate="one_to_many")

    threshold_summary = summary.groupby(["lookback_days", "threshold"]).agg(
        shapes=("shape_id", "size"),
        incumbent_diagnostic_passes=("incumbent_cluster_diagnostic_passed", "sum"),
        median_max_cluster_weight_p90=("max_cluster_weight_p90", "median"),
        median_effective_cluster_count_p10=("effective_cluster_count_p10", "median"),
        median_weighted_pair_correlation_p90=("weighted_pair_correlation_p90", "median"),
        best_return_p50=("target_excess_p50", "max"),
    ).reset_index()
    return summary, stress, threshold_summary


def _joint_decision_outputs(
    candidates: pd.DataFrame,
    selections: pd.DataFrame,
    shape_summary: pd.DataFrame,
    cfg,
    *,
    canonical_cost_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    concentration = _selection_concentration(
        selections,
        canonical_cost_bps=canonical_cost_bps,
    )
    _, incumbent = _concentration_baselines(cfg)
    canonical = candidates[np.isclose(candidates["trade_cost_bps"], canonical_cost_bps)]
    canonical = canonical.merge(concentration, on=SHAPE_KEYS, validate="one_to_one")
    canonical["concentration_guard_passed"] = (
        (canonical["effective_n_p10"] >= incumbent["effective_n"] - 1e-9)
        & (canonical["top1_p90"] <= incumbent["top1"] + 1e-9)
        & (canonical["top3_p90"] <= incumbent["top3"] + 1e-9)
    )

    cluster = shape_summary.groupby("shape_id").agg(
        cluster_sensitivity_specs=("incumbent_cluster_diagnostic_passed", "size"),
        cluster_sensitivity_passes=("incumbent_cluster_diagnostic_passed", "sum"),
        max_cluster_weight_p90_worst=("max_cluster_weight_p90", "max"),
        effective_cluster_count_p10_worst=("effective_cluster_count_p10", "min"),
        weighted_pair_correlation_p90_worst=("weighted_pair_correlation_p90", "max"),
        dominant_cluster_jaccard_p90_worst=("dominant_cluster_jaccard_p90", "max"),
    ).reset_index()
    cluster["cluster_all_sensitivity_passed"] = (
        cluster["cluster_sensitivity_passes"] == cluster["cluster_sensitivity_specs"]
    )
    joint = canonical.merge(cluster, on="shape_id", validate="one_to_one")

    policy = resolve_risk_envelope_policy(cfg)
    thresholds = {
        "incumbent_xirr_p50_margin": policy.min_incumbent_xirr_margin_p50,
        "incumbent_xirr_p10_margin": policy.min_incumbent_xirr_margin_p10,
        "incumbent_dd_relief_p50": -policy.max_incumbent_dd_cost_p50,
        "incumbent_dd_relief_p90": -policy.max_incumbent_dd_cost_p90,
    }
    violation_columns = []
    for column, threshold in thresholds.items():
        violation = f"{column}_violation"
        joint[violation] = (float(threshold) - joint[column]).clip(lower=0.0)
        violation_columns.append(violation)
    joint["incumbent_failed_checks"] = (
        joint[violation_columns] > 1e-12
    ).sum(axis=1)
    joint["incumbent_max_violation"] = joint[violation_columns].max(axis=1)
    joint["incumbent_sum_violation"] = joint[violation_columns].sum(axis=1)
    joint["target_and_static_structure_passed"] = (
        joint["target_gate_passed"] & joint["concentration_guard_passed"]
    )
    joint["target_and_cluster_sensitivity_passed"] = (
        joint["target_gate_passed"] & joint["cluster_all_sensitivity_passed"]
    )
    joint["target_and_all_structure_passed"] = (
        joint["target_gate_passed"]
        & joint["concentration_guard_passed"]
        & joint["cluster_all_sensitivity_passed"]
    )
    joint["joint_training_status"] = np.select(
        [
            ~joint["target_return_passed"],
            ~joint["target_risk_passed"],
            ~joint["concentration_guard_passed"],
            ~joint["cluster_all_sensitivity_passed"],
            ~joint["incumbent_gate_passed"],
        ],
        [
            "TARGET_RETURN_FAILED",
            "TARGET_DD_TAIL_FAILED",
            "STATIC_CONCENTRATION_FAILED",
            "CORRELATION_SENSITIVITY_FAILED",
            "INCUMBENT_GUARD_FAILED",
        ],
        default="TRAINING_ONLY_REQUIRES_LOCKED_VALIDATION",
    )
    joint["promotion_allowed"] = False
    joint = joint.sort_values(
        [
            "target_and_all_structure_passed",
            "incumbent_failed_checks",
            "incumbent_max_violation",
            "target_excess_p50",
            "target_excess_p10",
        ],
        ascending=[False, True, True, False, False],
    )

    shortlist_rows = []

    def add_shortlist(role: str, frame: pd.DataFrame, sort_by: list[str], ascending: list[bool]) -> None:
        if frame.empty:
            return
        row = frame.sort_values(sort_by, ascending=ascending).iloc[0].to_dict()
        shortlist_rows.append({
            "shortlist_role": role,
            "shortlist_status": "STRUCTURE_ONLY_NOT_VALIDATION",
            "promotion_allowed": False,
            **row,
        })

    add_shortlist(
        "primary_target_return_leader",
        joint,
        ["target_excess_p50", "target_excess_p10"],
        [False, False],
    )
    add_shortlist(
        "closest_incumbent_after_target_gate",
        joint[joint["target_gate_passed"]],
        ["incumbent_failed_checks", "incumbent_max_violation", "incumbent_sum_violation"],
        [True, True, True],
    )
    add_shortlist(
        "best_target_and_static_concentration",
        joint[joint["target_and_static_structure_passed"]],
        ["target_excess_p50", "target_excess_p10"],
        [False, False],
    )
    add_shortlist(
        "best_target_and_all_cluster_sensitivities",
        joint[joint["target_and_all_structure_passed"]],
        ["target_excess_p50", "target_excess_p10"],
        [False, False],
    )
    add_shortlist(
        "low_turnover_target_and_structure",
        joint[
            joint["target_and_all_structure_passed"]
            & (joint["turnover_x_p50"] <= 2.0)
        ],
        ["target_excess_p50", "target_excess_p10"],
        [False, False],
    )
    shortlist = pd.DataFrame(shortlist_rows)

    family = candidates.groupby(FAMILY_KEYS).agg(
        observations=("shape_id", "size"),
        target_gate_passes=("target_gate_passed", "sum"),
        incumbent_gate_passes=("incumbent_gate_passed", "sum"),
        target_excess_p50_worst=("target_excess_p50", "min"),
        target_excess_p50_median=("target_excess_p50", "median"),
        target_excess_p10_worst=("target_excess_p10", "min"),
        target_dd_relief_p10_worst=("target_dd_relief_p10", "min"),
        incumbent_xirr_p50_margin_worst=("incumbent_xirr_p50_margin", "min"),
        incumbent_xirr_p10_margin_worst=("incumbent_xirr_p10_margin", "min"),
        incumbent_dd_relief_p50_worst=("incumbent_dd_relief_p50", "min"),
        incumbent_dd_relief_p90_worst=("incumbent_dd_relief_p90", "min"),
        turnover_median=("turnover_x_p50", "median"),
    ).reset_index()
    structure = joint.groupby(FAMILY_KEYS).agg(
        canonical_lookbacks=("lookback_years", "size"),
        concentration_passes=("concentration_guard_passed", "sum"),
        cluster_all_sensitivity_passes=("cluster_all_sensitivity_passed", "sum"),
        target_and_all_structure_passes=("target_and_all_structure_passed", "sum"),
    ).reset_index()
    family = family.merge(structure, on=FAMILY_KEYS, validate="one_to_one")
    family["target_gate_all_observations"] = (
        family["target_gate_passes"] == family["observations"]
    )
    family["structure_all_lookbacks"] = (
        (family["concentration_passes"] == family["canonical_lookbacks"])
        & (
            family["cluster_all_sensitivity_passes"]
            == family["canonical_lookbacks"]
        )
    )
    family["training_family_passed"] = (
        family["target_gate_all_observations"]
        & family["structure_all_lookbacks"]
        & (family["incumbent_gate_passes"] == family["observations"])
    )
    family["promotion_allowed"] = False
    family = family.sort_values(
        [
            "training_family_passed",
            "target_gate_all_observations",
            "structure_all_lookbacks",
            "target_excess_p50_worst",
            "target_excess_p10_worst",
        ],
        ascending=False,
    )

    counts = {
        "canonical_shapes": len(joint),
        "target_gate_passed": int(joint["target_gate_passed"].sum()),
        "concentration_guard_passed": int(joint["concentration_guard_passed"].sum()),
        "target_and_static_structure_passed": int(
            joint["target_and_static_structure_passed"].sum()
        ),
        "cluster_all_sensitivity_passed": int(
            joint["cluster_all_sensitivity_passed"].sum()
        ),
        "target_and_all_structure_passed": int(
            joint["target_and_all_structure_passed"].sum()
        ),
        "incumbent_guard_passed": int(joint["incumbent_gate_passed"].sum()),
        "training_family_passed": int(family["training_family_passed"].sum()),
    }
    return joint, shortlist, family, counts


def plan_ndx_correlation_diagnostics(
    experiment_dir: str | Path,
    *,
    strategy_config_path: str | Path,
    canonical_cost_bps: float = 10.0,
    lookback_days: Iterable[int] = DEFAULT_LOOKBACK_DAYS,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
) -> dict:
    root = Path(experiment_dir)
    manifest, evidence = _read_verified_bundle(
        root,
        strategy_config_path=strategy_config_path,
    )
    selection_plan = build_selection_plan(
        evidence["selections"],
        canonical_cost_bps=canonical_cost_bps,
    )
    audit = selection_plan["audit"]
    lookbacks = parse_positive_ints(lookback_days)
    threshold_grid = parse_thresholds(thresholds)
    return {
        "experiment_id": manifest.get("experiment_id"),
        "objective_contract": manifest.get("objective_contract"),
        **audit,
        "lookback_days": lookbacks,
        "thresholds": threshold_grid,
        "expected_correlation_matrices": (
            audit["unique_date_ticker_universes"] + len(
                set(selection_plan["universes"]["selection_date"])
            ) + 1
        ) * len(lookbacks),
        "expected_weighted_scenario_rows": (
            audit["unique_weight_scenarios"] + len(
                set(selection_plan["universes"]["selection_date"])
            ) + 1
        ) * len(lookbacks) * len(threshold_grid),
        "research_only": True,
    }


def run_ndx_correlation_diagnostics(
    experiment_dir: str | Path,
    cfg,
    *,
    strategy_config_path: str | Path,
    canonical_cost_bps: float = 10.0,
    lookback_days: Iterable[int] = DEFAULT_LOOKBACK_DAYS,
    thresholds: Iterable[float] = DEFAULT_THRESHOLDS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
) -> tuple[dict[str, pd.DataFrame], dict]:
    root = Path(experiment_dir)
    manifest, evidence = _read_verified_bundle(
        root,
        strategy_config_path=strategy_config_path,
    )
    selection_plan = build_selection_plan(
        evidence["selections"],
        canonical_cost_bps=canonical_cost_bps,
    )
    lookbacks = parse_positive_ints(lookback_days)
    threshold_grid = parse_thresholds(thresholds)
    if int(min_observations) < 20:
        raise NdxCorrelationClusterError("min observations must be at least 20")
    close, price_version = load_verified_price_panel(cfg, evidence["versions"])

    experiment_universes = selection_plan["universes"].copy()
    experiment_universes["universe_scope"] = "experiment_selection"
    baseline_universes, baseline_scenarios = _baseline_inputs(
        cfg,
        experiment_universes["selection_date"],
        close.index.max(),
    )
    baseline_universes["universe_scope"] = "current_config_static_hindsight_baseline"
    all_universes = pd.concat(
        [
            experiment_universes[
                ["selection_date", "tickers", "universe_id", "universe_scope"]
            ],
            baseline_universes[
                ["selection_date", "tickers", "universe_id", "universe_scope"]
            ],
        ],
        ignore_index=True,
    ).drop_duplicates("universe_id")

    matrix_cache: dict[tuple[str, int], tuple[pd.DataFrame, dict]] = {}
    label_cache: dict[tuple[str, int, float], dict[str, int]] = {}
    universe_rows = []
    pair_rows = []
    cluster_rows = []
    skip_rows = []
    for universe in all_universes.to_dict("records"):
        tickers = _ticker_list(universe["tickers"])
        for lookback in lookbacks:
            try:
                corr, meta = correlation_matrix_before(
                    close,
                    tickers,
                    universe["selection_date"],
                    lookback_days=lookback,
                    min_observations=min_observations,
                )
            except Exception as exc:
                skip_rows.append({
                    **universe,
                    "lookback_days": lookback,
                    "reason": f"{type(exc).__name__}: {exc}",
                })
                continue
            matrix_cache[(universe["universe_id"], lookback)] = (corr, meta)
            pair_values = corr.to_numpy()[np.triu_indices(len(corr), k=1)]
            universe_rows.append({
                **universe,
                **meta,
                "security_count": len(tickers),
                "pair_count": len(pair_values),
                "pair_corr_min": float(np.min(pair_values)),
                "pair_corr_p50": float(np.median(pair_values)),
                "pair_corr_p90": float(np.quantile(pair_values, 0.90)),
                "pair_corr_max": float(np.max(pair_values)),
            })
            pair_rows.extend(_pair_rows(universe, corr, meta))
            for threshold in threshold_grid:
                labels = complete_linkage_clusters(corr, threshold)
                label_cache[(universe["universe_id"], lookback, threshold)] = labels
                cluster_rows.extend(
                    _cluster_rows(universe, corr, meta, threshold, labels)
                )

    experiment_scenarios = selection_plan["scenarios"].copy()
    experiment_scenarios["scenario_scope"] = "experiment_selection"
    baseline_scenarios["scenario_scope"] = "current_config_static_hindsight_baseline"
    all_scenarios = pd.concat(
        [
            experiment_scenarios[
                [
                    "selection_date",
                    "tickers",
                    "weights",
                    "universe_id",
                    "scenario_id",
                    "scenario_scope",
                ]
            ],
            baseline_scenarios[
                [
                    "selection_date",
                    "tickers",
                    "weights",
                    "universe_id",
                    "scenario_id",
                    "scenario_scope",
                ]
            ],
        ],
        ignore_index=True,
    ).drop_duplicates("scenario_id")

    weighted_rows = []
    for scenario in all_scenarios.to_dict("records"):
        for lookback in lookbacks:
            cached = matrix_cache.get((scenario["universe_id"], lookback))
            if cached is None:
                continue
            corr, meta = cached
            for threshold in threshold_grid:
                labels = label_cache[(scenario["universe_id"], lookback, threshold)]
                weighted_rows.append({
                    **scenario_cluster_metrics(scenario, corr, meta, threshold, labels),
                    "scenario_scope": scenario["scenario_scope"],
                })
    weighted = pd.DataFrame(weighted_rows)
    if weighted.empty:
        raise NdxCorrelationClusterError("no weighted correlation diagnostics were produced")

    baseline = baseline_scenarios.merge(
        weighted,
        on=[
            "selection_date",
            "tickers",
            "weights",
            "universe_id",
            "scenario_id",
            "scenario_scope",
        ],
        validate="one_to_many",
    )
    shape_summary, shape_stress, threshold_summary = _shape_outputs(
        selection_plan["shape_events"],
        weighted[weighted["scenario_scope"].eq("experiment_selection")],
        evidence["candidates"],
        baseline,
        canonical_cost_bps=canonical_cost_bps,
    )
    joint_decisions, joint_shortlist, robust_family_decisions, joint_counts = (
        _joint_decision_outputs(
            evidence["candidates"],
            evidence["selections"],
            shape_summary,
            cfg,
            canonical_cost_bps=canonical_cost_bps,
        )
    )
    audit_frame = pd.DataFrame([selection_plan["audit"]])
    frames = {
        "cost_invariance": audit_frame,
        "threshold_summary": threshold_summary,
        "joint_shortlist": joint_shortlist,
        "joint_decisions": joint_decisions,
        "robust_family_decisions": robust_family_decisions,
        "shape_summary": shape_summary.sort_values(
            [
                "lookback_days",
                "threshold",
                "incumbent_cluster_diagnostic_passed",
                "target_excess_p50",
            ],
            ascending=[True, True, False, False],
        ),
        "shape_stress": shape_stress,
        "incumbent_baseline": baseline,
        "weighted_scenarios": weighted,
        "universe_summary": pd.DataFrame(universe_rows),
        "clusters": pd.DataFrame(cluster_rows),
        "pair_correlations": pd.DataFrame(pair_rows),
        "skips": pd.DataFrame(skip_rows),
    }
    summary = {
        "schema_version": CORRELATION_SCHEMA_VERSION,
        "analysis_id": f"{manifest.get('experiment_id')}_correlation_clusters_v1",
        "source_experiment_id": manifest.get("experiment_id"),
        "objective_contract": manifest.get("objective_contract"),
        "primary_target": (
            (manifest.get("objective_contract") or {}).get("primary_target")
            or sorted(
                set(evidence["candidates"]["target_benchmark"].dropna().astype(str))
            )[0]
        ),
        "source_manifest_sha256": _content_hash(root / "manifest.json"),
        "source_evidence_sha256": {
            key: value.get("sha256")
            for key, value in (manifest.get("evidence_files") or {}).items()
        },
        "price_version": price_version,
        "canonical_cost_bps": float(canonical_cost_bps),
        "lookback_days": lookbacks,
        "thresholds": threshold_grid,
        "min_observations": int(min_observations),
        "selection_event_policy": (
            "unique point-in-time portfolio states; overlapping rolling-window duplicates removed"
        ),
        "asof_rule": "price_date < selection_date",
        "cluster_algorithm": (
            "complete-linkage on distance=1-correlation; every within-cluster pair meets threshold"
        ),
        "threshold_policy": "sensitivity grid only; no threshold is a live hard gate",
        "baseline_policy": (
            "current config static holdings evaluated at historical selection dates; hindsight hurdle only"
        ),
        "cost_invariance": selection_plan["audit"],
        "correlation_matrices": len(matrix_cache),
        "weighted_scenario_rows": len(weighted),
        "shape_summary_rows": len(shape_summary),
        "joint_decision_counts": joint_counts,
        "skipped_matrix_rows": len(skip_rows),
        "strict_asof_passed": bool(
            not frames["universe_summary"].empty
            and frames["universe_summary"]["strict_asof_passed"].all()
        ),
        "research_only": True,
        "promotion_allowed": False,
        "locked_validation_enabled": False,
    }
    return frames, summary


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _json_default(value: Any):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def write_ndx_correlation_bundle(
    frames: dict[str, pd.DataFrame],
    summary: dict,
    output_dir: str | Path,
    *,
    write_xlsx: bool = True,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    evidence_files = {}
    for name, frame in frames.items():
        filename = f"{name}.csv"
        path = output / filename
        _atomic_csv(frame, path)
        files[name] = filename
        evidence_files[name] = {
            "filename": filename,
            "rows": len(frame),
            "sha256": _content_hash(path),
        }

    if write_xlsx:
        workbook_path = output / "ndx_correlation_cluster_report.xlsx"
        temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
        readme = pd.DataFrame([
            {
                "field": key,
                "value": json.dumps(value, ensure_ascii=False, default=_json_default),
            }
            for key, value in summary.items()
        ])
        try:
            with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
                readme.to_excel(writer, sheet_name="README", index=False)
                for name, frame in frames.items():
                    frame.to_excel(writer, sheet_name=name[:31], index=False)
            os.replace(temporary, workbook_path)
            files["workbook"] = workbook_path.name
        finally:
            if temporary.exists():
                temporary.unlink()

    payload = {
        **summary,
        "files": files,
        "output_evidence": evidence_files,
    }
    atomic_write_text(
        output / "manifest.json",
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        ) + "\n",
    )
    return payload
