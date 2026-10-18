"""White-box attribution for completed NDX quality/SIC experiments.

The report describes how declared quality profiles changed selections and how
those changes were associated with paired-window outcomes. It does not infer
causality, retune factor weights, or promote a training profile.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from backtest.ndx_experiment_analysis import _read_verified_bundle
from backtest.ndx_quality import QUALITY_POLICY_ID, load_quality_score_evidence
from core.helpers import atomic_write_text
from data.versioning import file_sha256


ATTRIBUTION_SCHEMA_VERSION = 1
ATTRIBUTION_METHOD_ID = "ndx_quality_replacement_attribution_v1"
QUALITY_COLUMNS = (
    "quality_score",
    "growth_sleeve",
    "profitability_sleeve",
    "balance_sleeve",
    "revenue_growth_percentile",
    "operating_margin_percentile",
    "free_cash_flow_margin_percentile",
    "operating_cash_flow_to_assets_percentile",
    "equity_to_assets_percentile",
    "cash_to_assets_percentile",
)
PERFORMANCE_COLUMNS = (
    "strategy_xirr",
    "strategy_maxdd",
    "target_excess_xirr",
    "target_dd_relief",
    "incumbent_xirr_margin",
    "incumbent_dd_relief",
    "turnover_x",
)
STATE_COLUMNS = (
    *(f"weighted_{column}" for column in QUALITY_COLUMNS),
    "quality_weight_coverage",
    "effective_n",
    "top1_weight",
    "top3_weight",
    "max_sic4_weight",
    "max_sic2_weight",
)
ASSOCIATION_OUTCOMES = (
    "target_excess_xirr_delta",
    "target_dd_relief_delta",
    "incumbent_xirr_margin_delta",
    "incumbent_dd_relief_delta",
)
ASSOCIATION_FEATURES = (
    "weighted_quality_score_delta",
    "weighted_growth_sleeve_delta",
    "weighted_profitability_sleeve_delta",
    "weighted_balance_sleeve_delta",
    "effective_n_delta",
    "top1_weight_delta",
    "top3_weight_delta",
    "max_sic4_weight_delta",
    "max_sic2_weight_delta",
)


class NdxQualityAttributionError(ValueError):
    """Raised when attribution evidence is incomplete or internally inconsistent."""


def _as_bool(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"true", "1"}:
        return True
    if normalized in {"false", "0"}:
        return False
    raise NdxQualityAttributionError(f"invalid boolean evidence: {value!r}")


def _hash_payload(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_map(value: Any, parser) -> dict[str, Any]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return {}
    parsed = {}
    for item in str(value).split(";"):
        if not item:
            continue
        ticker, separator, raw = item.partition(":")
        if not separator or not ticker.strip():
            raise NdxQualityAttributionError(f"invalid map item: {item!r}")
        key = ticker.strip().upper()
        if key in parsed:
            raise NdxQualityAttributionError(f"duplicate map key: {key}")
        parsed[key] = parser(raw)
    return parsed


def _selection_weights(row: Mapping[str, Any]) -> dict[str, float]:
    weights = _parse_map(row.get("weights"), float)
    tickers = {
        ticker.strip().upper()
        for ticker in str(row.get("tickers") or "").split(";")
        if ticker.strip()
    }
    if not weights or tickers != set(weights):
        raise NdxQualityAttributionError("selection ticker/weight evidence changed")
    values = np.asarray(list(weights.values()), dtype=float)
    if (
        not np.isfinite(values).all()
        or (values <= 0).any()
        or not np.isclose(values.sum(), 1.0, atol=1e-6)
    ):
        raise NdxQualityAttributionError("selection weights are invalid")
    return weights


def _quality_index(scores: pd.DataFrame) -> pd.DataFrame:
    required = {
        "selection_date",
        "ticker",
        "quality_policy_id",
        "quality_eligible",
        "quality_confidence",
        "sic",
        "sic_group_2d",
        "sic_description",
        *QUALITY_COLUMNS,
    }
    missing = sorted(required - set(scores.columns))
    if missing:
        raise NdxQualityAttributionError(
            f"quality attribution columns are missing: {missing}"
        )
    frame = scores.copy()
    frame["selection_date"] = pd.to_datetime(
        frame["selection_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    if frame.duplicated(["selection_date", "ticker"]).any():
        raise NdxQualityAttributionError("quality evidence has duplicate ticker dates")
    if set(frame["quality_policy_id"].astype(str)) != {QUALITY_POLICY_ID}:
        raise NdxQualityAttributionError("quality attribution policy changed")
    return frame.set_index(["selection_date", "ticker"], drop=False).sort_index()


def _quality_row(
    quality: pd.DataFrame,
    selection_date: str,
    ticker: str,
) -> pd.Series:
    key = (str(selection_date), str(ticker).upper())
    try:
        row = quality.loc[key]
    except KeyError as exc:
        raise NdxQualityAttributionError(
            f"quality evidence is missing for {key[0]} {key[1]}"
        ) from exc
    if isinstance(row, pd.DataFrame):
        raise NdxQualityAttributionError(f"ambiguous quality evidence for {key}")
    return row


def _weighted_value(
    holdings: list[dict],
    column: str,
) -> tuple[float | None, float]:
    available = [
        row for row in holdings
        if pd.notna(row.get(column)) and np.isfinite(float(row[column]))
    ]
    coverage = float(sum(float(row["weight"]) for row in available))
    if coverage <= 0:
        return None, 0.0
    value = sum(
        float(row["weight"]) * float(row[column]) for row in available
    ) / coverage
    return float(value), coverage


def build_selection_evidence(
    selections: pd.DataFrame,
    quality_scores: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one state row and one long-form holding row per selection."""
    quality = _quality_index(quality_scores)
    state_rows = []
    holding_rows = []
    for raw in selections.to_dict(orient="records"):
        weights = _selection_weights(raw)
        selection_date = pd.Timestamp(raw["selection_date"]).strftime("%Y-%m-%d")
        holdings = []
        for ticker, weight in sorted(weights.items()):
            evidence = _quality_row(quality, selection_date, ticker)
            holding = {
                "phase_id": raw.get("phase_id"),
                "job_id": raw.get("job_id"),
                "window_start": raw.get("window_start"),
                "profile_id": raw.get("profile_id"),
                "selection_date": selection_date,
                "trigger": raw.get("trigger"),
                "ticker": ticker,
                "weight": float(weight),
                "quality_eligible": _as_bool(evidence["quality_eligible"]),
                "quality_confidence": evidence["quality_confidence"],
                "sic": int(evidence["sic"]),
                "sic_group_2d": str(evidence["sic_group_2d"]),
                "sic_description": evidence["sic_description"],
            }
            for column in QUALITY_COLUMNS:
                value = pd.to_numeric(pd.Series([evidence[column]]), errors="coerce").iloc[0]
                holding[column] = float(value) if pd.notna(value) else None
            holdings.append(holding)
        portfolio_state_id = "ndx_quality_state:" + _hash_payload({
            "selection_date": selection_date,
            "weights": sorted((ticker, round(weight, 12)) for ticker, weight in weights.items()),
        })[:16]
        for holding in holdings:
            holding["portfolio_state_id"] = portfolio_state_id
            holding_rows.append(holding)
        sorted_weights = sorted(weights.values(), reverse=True)
        sic4_weights: dict[int, float] = {}
        sic2_weights: dict[str, float] = {}
        for holding in holdings:
            sic4 = int(holding["sic"])
            sic2 = str(holding["sic_group_2d"])
            sic4_weights[sic4] = sic4_weights.get(sic4, 0.0) + holding["weight"]
            sic2_weights[sic2] = sic2_weights.get(sic2, 0.0) + holding["weight"]
        state = {
            "phase_id": raw.get("phase_id"),
            "job_id": raw.get("job_id"),
            "window_start": raw.get("window_start"),
            "profile_id": raw.get("profile_id"),
            "selection_date": selection_date,
            "trigger": raw.get("trigger"),
            "portfolio_state_id": portfolio_state_id,
            "tickers": ";".join(sorted(weights)),
            "weights": ";".join(
                f"{ticker}:{weights[ticker]:.8f}" for ticker in sorted(weights)
            ),
            "ticker_count": len(weights),
            "effective_n": float(1.0 / sum(weight * weight for weight in weights.values())),
            "top1_weight": float(sorted_weights[0]),
            "top3_weight": float(sum(sorted_weights[:3])),
            "max_sic4_weight": float(max(sic4_weights.values())),
            "max_sic2_weight": float(max(sic2_weights.values())),
        }
        quality_coverage = 0.0
        for column in QUALITY_COLUMNS:
            value, coverage = _weighted_value(holdings, column)
            state[f"weighted_{column}"] = value
            if column == "quality_score":
                quality_coverage = coverage
        state["quality_weight_coverage"] = quality_coverage
        state_rows.append(state)
    states = pd.DataFrame(state_rows)
    holdings = pd.DataFrame(holding_rows)
    return states, holdings


def _duration_weighted(group: pd.DataFrame, end: pd.Timestamp, column: str) -> float | None:
    values = pd.to_numeric(group[column], errors="coerce")
    dates = pd.to_datetime(group["selection_date"], errors="raise")
    next_dates = dates.shift(-1).fillna(end + pd.Timedelta(days=1))
    durations = (next_dates - dates).dt.days.clip(lower=1).astype(float)
    ready = values.notna() & np.isfinite(values)
    if not ready.any():
        return None
    return float(np.average(values[ready], weights=durations[ready]))


def build_window_features(
    windows: pd.DataFrame,
    states: pd.DataFrame,
) -> pd.DataFrame:
    """Attach calendar-duration-weighted selection characteristics to each window."""
    rows = []
    for window in windows.to_dict(orient="records"):
        profile = str(window["profile_id"])
        start = pd.Timestamp(window["start"])
        end = pd.Timestamp(window["end"])
        selected = states[
            states["profile_id"].astype(str).eq(profile)
            & states["window_start"].astype(str).eq(start.strftime("%Y-%m-%d"))
        ].sort_values("selection_date")
        if selected.empty:
            raise NdxQualityAttributionError(
                f"selection states are missing for {profile} {start:%Y-%m-%d}"
            )
        if selected["selection_date"].duplicated().any():
            raise NdxQualityAttributionError(
                f"duplicate selection dates for {profile} {start:%Y-%m-%d}"
            )
        if pd.Timestamp(selected.iloc[0]["selection_date"]) != start:
            raise NdxQualityAttributionError(
                f"first selection does not equal window start for {profile}"
            )
        row = {key: window.get(key) for key in (
            "phase_id",
            "job_id",
            "start",
            "end",
            "profile_id",
            "lookback_years",
            "trade_cost_bps",
            *PERFORMANCE_COLUMNS,
        )}
        row["selection_state_count"] = len(selected)
        row["emergency_selection_count"] = int(
            selected["trigger"].astype(str).eq("stale_holding").sum()
        )
        for column in STATE_COLUMNS:
            row[column] = _duration_weighted(selected, end, column)
        rows.append(row)
    return pd.DataFrame(rows)


def _ticker_metric_means(
    quality: pd.DataFrame,
    selection_date: str,
    tickers: set[str],
) -> dict[str, float | None]:
    result = {}
    for column in QUALITY_COLUMNS:
        values = [
            _quality_row(quality, selection_date, ticker)[column]
            for ticker in sorted(tickers)
        ]
        numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
        result[column] = float(numeric.mean()) if not numeric.empty else None
    return result


def build_replacement_evidence(
    selections: pd.DataFrame,
    states: pd.DataFrame,
    quality_scores: pd.DataFrame,
    *,
    baseline_profile_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compare exact-date states without inventing ticker-to-ticker pairings."""
    quality = _quality_index(quality_scores)
    events = []
    ticker_rows = []
    mismatch_rows = []
    state_lookup = states.set_index(
        ["window_start", "profile_id", "selection_date"], drop=False
    )
    windows = sorted(set(selections["window_start"].astype(str)))
    alternatives = sorted(
        set(selections["profile_id"].astype(str)) - {baseline_profile_id}
    )
    for window_start in windows:
        baseline = selections[
            selections["window_start"].astype(str).eq(window_start)
            & selections["profile_id"].astype(str).eq(baseline_profile_id)
        ]
        baseline_by_date = {
            str(row["selection_date"]): row
            for row in baseline.to_dict(orient="records")
        }
        for alternative in alternatives:
            alt = selections[
                selections["window_start"].astype(str).eq(window_start)
                & selections["profile_id"].astype(str).eq(alternative)
            ]
            alt_by_date = {
                str(row["selection_date"]): row
                for row in alt.to_dict(orient="records")
            }
            all_dates = sorted(set(baseline_by_date) | set(alt_by_date))
            for selection_date in all_dates:
                base_raw = baseline_by_date.get(selection_date)
                alt_raw = alt_by_date.get(selection_date)
                if base_raw is None or alt_raw is None:
                    present = alt_raw if base_raw is None else base_raw
                    mismatch_rows.append({
                        "window_start": window_start,
                        "alternative_profile_id": alternative,
                        "selection_date": selection_date,
                        "present_side": (
                            "alternative_only" if base_raw is None else "baseline_only"
                        ),
                        "trigger": present.get("trigger"),
                        "tickers": present.get("tickers"),
                        "reason": "selection_schedule_differs",
                    })
                    continue
                base_weights = _selection_weights(base_raw)
                alt_weights = _selection_weights(alt_raw)
                base_tickers = set(base_weights)
                alt_tickers = set(alt_weights)
                entered = alt_tickers - base_tickers
                exited = base_tickers - alt_tickers
                retained = base_tickers & alt_tickers
                entered_means = _ticker_metric_means(
                    quality, selection_date, entered
                )
                exited_means = _ticker_metric_means(
                    quality, selection_date, exited
                )
                pair_id = "ndx_quality_pair:" + _hash_payload({
                    "alternative": alternative,
                    "selection_date": selection_date,
                    "baseline": sorted((key, round(value, 12)) for key, value in base_weights.items()),
                    "alternative_weights": sorted((key, round(value, 12)) for key, value in alt_weights.items()),
                })[:16]
                event = {
                    "window_start": window_start,
                    "baseline_profile_id": baseline_profile_id,
                    "alternative_profile_id": alternative,
                    "selection_date": selection_date,
                    "portfolio_pair_id": pair_id,
                    "baseline_trigger": base_raw.get("trigger"),
                    "alternative_trigger": alt_raw.get("trigger"),
                    "retained_tickers": ";".join(sorted(retained)),
                    "entered_tickers": ";".join(sorted(entered)),
                    "exited_tickers": ";".join(sorted(exited)),
                    "retained_count": len(retained),
                    "entered_count": len(entered),
                    "exited_count": len(exited),
                    "ticker_jaccard": (
                        len(retained) / len(base_tickers | alt_tickers)
                        if base_tickers | alt_tickers else 1.0
                    ),
                    "one_way_weight_turnover": 0.5 * sum(
                        abs(alt_weights.get(ticker, 0.0) - base_weights.get(ticker, 0.0))
                        for ticker in base_tickers | alt_tickers
                    ),
                }
                for column in QUALITY_COLUMNS:
                    entered_value = entered_means[column]
                    exited_value = exited_means[column]
                    event[f"entered_mean_{column}"] = entered_value
                    event[f"exited_mean_{column}"] = exited_value
                    event[f"entered_minus_exited_{column}"] = (
                        entered_value - exited_value
                        if entered_value is not None and exited_value is not None
                        else None
                    )
                base_state = state_lookup.loc[
                    (window_start, baseline_profile_id, selection_date)
                ]
                alt_state = state_lookup.loc[
                    (window_start, alternative, selection_date)
                ]
                if isinstance(base_state, pd.DataFrame) or isinstance(alt_state, pd.DataFrame):
                    raise NdxQualityAttributionError("ambiguous state attribution key")
                for column in STATE_COLUMNS:
                    left = pd.to_numeric(pd.Series([base_state[column]]), errors="coerce").iloc[0]
                    right = pd.to_numeric(pd.Series([alt_state[column]]), errors="coerce").iloc[0]
                    event[f"{column}_delta"] = (
                        float(right - left)
                        if pd.notna(left) and pd.notna(right) else None
                    )
                events.append(event)
                for role, tickers in (("entered", entered), ("exited", exited)):
                    for ticker in sorted(tickers):
                        evidence = _quality_row(quality, selection_date, ticker)
                        ticker_row = {
                            "window_start": window_start,
                            "alternative_profile_id": alternative,
                            "selection_date": selection_date,
                            "portfolio_pair_id": pair_id,
                            "role": role,
                            "ticker": ticker,
                            "weight": (
                                alt_weights[ticker] if role == "entered" else base_weights[ticker]
                            ),
                            "quality_eligible": _as_bool(evidence["quality_eligible"]),
                            "quality_confidence": evidence["quality_confidence"],
                            "sic": int(evidence["sic"]),
                            "sic_group_2d": str(evidence["sic_group_2d"]),
                            "sic_description": evidence["sic_description"],
                        }
                        for column in QUALITY_COLUMNS:
                            value = pd.to_numeric(
                                pd.Series([evidence[column]]), errors="coerce"
                            ).iloc[0]
                            ticker_row[column] = float(value) if pd.notna(value) else None
                        ticker_rows.append(ticker_row)
    event_frame = pd.DataFrame(events)
    if not event_frame.empty:
        counts = event_frame.groupby("portfolio_pair_id").size()
        event_frame["overlapping_window_duplicate_count"] = event_frame[
            "portfolio_pair_id"
        ].map(counts).astype(int)
    return event_frame, pd.DataFrame(ticker_rows), pd.DataFrame(mismatch_rows)


def build_window_attribution(
    features: pd.DataFrame,
    events: pd.DataFrame,
    mismatches: pd.DataFrame,
    *,
    baseline_profile_id: str,
) -> pd.DataFrame:
    baseline = features[features["profile_id"].astype(str).eq(baseline_profile_id)]
    alternatives = sorted(
        set(features["profile_id"].astype(str)) - {baseline_profile_id}
    )
    index = ["phase_id", "job_id", "start", "end", "lookback_years", "trade_cost_bps"]
    rows = []
    compare_columns = [*PERFORMANCE_COLUMNS, *STATE_COLUMNS]
    for alternative in alternatives:
        alt = features[features["profile_id"].astype(str).eq(alternative)]
        paired = baseline[index + compare_columns].merge(
            alt[index + compare_columns],
            on=index,
            how="inner",
            suffixes=("_baseline", "_alternative"),
            validate="one_to_one",
        )
        if len(paired) != len(baseline) or len(paired) != len(alt):
            raise NdxQualityAttributionError(
                f"window pairing is incomplete for {alternative}"
            )
        for raw in paired.to_dict(orient="records"):
            row = {key: raw[key] for key in index}
            row["baseline_profile_id"] = baseline_profile_id
            row["alternative_profile_id"] = alternative
            for column in compare_columns:
                left = raw.get(f"{column}_baseline")
                right = raw.get(f"{column}_alternative")
                row[f"{column}_baseline"] = left
                row[f"{column}_alternative"] = right
                row[f"{column}_delta"] = (
                    float(right - left)
                    if pd.notna(left) and pd.notna(right) else None
                )
            window_start = str(raw["start"])
            matched = events[
                events["window_start"].astype(str).eq(window_start)
                & events["alternative_profile_id"].astype(str).eq(alternative)
            ] if not events.empty else pd.DataFrame()
            unmatched = mismatches[
                mismatches["window_start"].astype(str).eq(window_start)
                & mismatches["alternative_profile_id"].astype(str).eq(alternative)
            ] if not mismatches.empty else pd.DataFrame()
            row["matched_selection_dates"] = len(matched)
            row["replacement_selection_dates"] = int(
                matched["entered_count"].gt(0).sum()
            ) if not matched.empty else 0
            row["weight_only_selection_dates"] = int(
                (
                    matched["entered_count"].eq(0)
                    & matched["one_way_weight_turnover"].gt(1e-10)
                ).sum()
            ) if not matched.empty else 0
            row["unmatched_selection_dates"] = len(unmatched)
            rows.append(row)
    return pd.DataFrame(rows)


def build_factor_associations(window_attribution: pd.DataFrame) -> pd.DataFrame:
    """Return descriptive Spearman associations for overlapping windows."""
    rows = []
    for alternative, group in window_attribution.groupby(
        "alternative_profile_id", sort=True
    ):
        for feature in ASSOCIATION_FEATURES:
            for outcome in ASSOCIATION_OUTCOMES:
                subset = group[[feature, outcome]].apply(
                    pd.to_numeric, errors="coerce"
                ).dropna()
                correlation = None
                if (
                    len(subset) >= 5
                    and subset[feature].nunique() > 1
                    and subset[outcome].nunique() > 1
                ):
                    correlation = float(
                        subset[feature].corr(subset[outcome], method="spearman")
                    )
                rows.append({
                    "alternative_profile_id": alternative,
                    "feature": feature,
                    "outcome": outcome,
                    "pairs": len(subset),
                    "spearman": correlation,
                    "overlapping_windows": True,
                    "statistical_inference_allowed": False,
                    "interpretation": "descriptive_association_not_causal",
                })
    return pd.DataFrame(rows)


def build_start_year_summary(window_attribution: pd.DataFrame) -> pd.DataFrame:
    """Describe stability by start year without assigning market-regime labels."""
    frame = window_attribution.copy()
    frame["window_start_year"] = pd.to_datetime(
        frame["start"], errors="raise"
    ).dt.year
    rows = []
    for (alternative, year), group in frame.groupby(
        ["alternative_profile_id", "window_start_year"], sort=True
    ):
        row = {
            "alternative_profile_id": alternative,
            "window_start_year": int(year),
            "paired_windows": len(group),
            "overlapping_windows": True,
            "statistical_inference_allowed": False,
        }
        for metric in (*ASSOCIATION_OUTCOMES, *ASSOCIATION_FEATURES):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_p10"] = (
                float(values.quantile(0.10)) if not values.empty else None
            )
            row[f"{metric}_p50"] = (
                float(values.median()) if not values.empty else None
            )
            row[f"{metric}_p90"] = (
                float(values.quantile(0.90)) if not values.empty else None
            )
            if metric in ASSOCIATION_OUTCOMES:
                row[f"{metric}_improvement_rate"] = (
                    float((values > 0).mean()) if not values.empty else None
                )
        rows.append(row)
    return pd.DataFrame(rows)


def build_window_stress(window_attribution: pd.DataFrame, *, count: int = 3) -> pd.DataFrame:
    rows = []
    for alternative, group in window_attribution.groupby(
        "alternative_profile_id", sort=True
    ):
        for metric in ("target_excess_xirr_delta", "target_dd_relief_delta"):
            ordered = group.sort_values(metric, ascending=True).head(int(count))
            for rank, raw in enumerate(ordered.to_dict(orient="records"), start=1):
                rows.append({
                    "alternative_profile_id": alternative,
                    "stress_metric": metric,
                    "stress_rank": rank,
                    **raw,
                })
    return pd.DataFrame(rows)


def _verify_selection_cost_invariance(
    selections: pd.DataFrame,
    canonical_cost_bps: float,
) -> None:
    identity_columns = [
        "phase_id",
        "window_start",
        "profile_id",
        "selection_date",
        "trigger",
        "tickers",
        "weights",
    ]
    canonical = selections[
        np.isclose(
            pd.to_numeric(selections["trade_cost_bps"], errors="coerce"),
            float(canonical_cost_bps),
        )
    ]
    if canonical.empty:
        raise NdxQualityAttributionError("canonical selection cost is absent")
    expected = set(map(tuple, canonical[identity_columns].fillna("").to_numpy()))
    for cost, group in selections.groupby("trade_cost_bps", dropna=False):
        observed = set(map(tuple, group[identity_columns].fillna("").to_numpy()))
        if observed != expected:
            raise NdxQualityAttributionError(
                f"selection states changed across trade costs at {cost} bps"
            )


def _profile_summary(window_attribution: pd.DataFrame) -> list[dict]:
    rows = []
    for alternative, group in window_attribution.groupby(
        "alternative_profile_id", sort=True
    ):
        row = {"alternative_profile_id": alternative, "paired_windows": len(group)}
        for metric in ASSOCIATION_OUTCOMES:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_p10"] = float(values.quantile(0.10))
            row[f"{metric}_p50"] = float(values.median())
            row[f"{metric}_p90"] = float(values.quantile(0.90))
            row[f"{metric}_improvement_rate"] = float((values > 0).mean())
        for metric in (
            "weighted_growth_sleeve_delta",
            "weighted_profitability_sleeve_delta",
            "weighted_balance_sleeve_delta",
            "max_sic4_weight_delta",
            "max_sic2_weight_delta",
        ):
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            row[f"{metric}_p50"] = float(values.median()) if not values.empty else None
        rows.append(row)
    return rows


def analyze_quality_attribution(
    experiment_dir: str | Path,
    cfg,
    *,
    canonical_cost_bps: float = 10.0,
    strategy_config_path: str | Path | None = None,
) -> tuple[dict[str, pd.DataFrame], dict]:
    root = Path(experiment_dir)
    manifest, evidence = _read_verified_bundle(
        root,
        strategy_config_path=strategy_config_path,
    )
    contract = manifest.get("analysis_contract") or {}
    if contract.get("component_family") != "quality_sic":
        raise NdxQualityAttributionError(
            "experiment does not declare the quality_sic analysis family"
        )
    baseline_profile_id = str(contract.get("baseline_profile_id") or "").strip()
    if not baseline_profile_id:
        raise NdxQualityAttributionError("quality attribution baseline is missing")
    candidates = evidence["candidates"]
    profiles = set(candidates["profile_id"].dropna().astype(str))
    if baseline_profile_id not in profiles or len(profiles) < 2:
        raise NdxQualityAttributionError("quality attribution profiles are incomplete")
    _verify_selection_cost_invariance(evidence["selections"], canonical_cost_bps)
    quality_scores, quality_meta = load_quality_score_evidence(cfg)
    expected_versions = set(
        evidence["versions"].loc[
            evidence["versions"]["source_name"].astype(str).eq("quality_scores"),
            "version_id",
        ].dropna().astype(str)
    )
    if expected_versions != {str(quality_meta.get("version_id"))}:
        raise NdxQualityAttributionError("quality score version changed")
    selections = evidence["selections"][
        np.isclose(
            pd.to_numeric(evidence["selections"]["trade_cost_bps"], errors="coerce"),
            float(canonical_cost_bps),
        )
    ].copy()
    windows = evidence["windows"][
        np.isclose(
            pd.to_numeric(evidence["windows"]["trade_cost_bps"], errors="coerce"),
            float(canonical_cost_bps),
        )
    ].copy()
    states, holdings = build_selection_evidence(selections, quality_scores)
    features = build_window_features(windows, states)
    events, replacement_tickers, mismatches = build_replacement_evidence(
        selections,
        states,
        quality_scores,
        baseline_profile_id=baseline_profile_id,
    )
    window_attribution = build_window_attribution(
        features,
        events,
        mismatches,
        baseline_profile_id=baseline_profile_id,
    )
    associations = build_factor_associations(window_attribution)
    start_year_summary = build_start_year_summary(window_attribution)
    stress = build_window_stress(window_attribution)
    summary = {
        "schema_version": ATTRIBUTION_SCHEMA_VERSION,
        "attribution_method_id": ATTRIBUTION_METHOD_ID,
        "analysis_id": f"{manifest.get('experiment_id')}_quality_attribution",
        "source_experiment_id": manifest.get("experiment_id"),
        "source_manifest_sha256": file_sha256(root / "manifest.json"),
        "analysis_contract": contract,
        "baseline_profile_id": baseline_profile_id,
        "alternative_profile_ids": sorted(profiles - {baseline_profile_id}),
        "canonical_cost_bps": float(canonical_cost_bps),
        "quality_policy_id": QUALITY_POLICY_ID,
        "quality_score_version_id": quality_meta.get("version_id"),
        "quality_score_sha256": quality_meta.get("content_sha256"),
        "selection_cost_invariance_passed": True,
        "selection_state_rows": len(states),
        "selection_holding_rows": len(holdings),
        "matched_replacement_event_rows": len(events),
        "replacement_ticker_rows": len(replacement_tickers),
        "schedule_mismatch_rows": len(mismatches),
        "paired_window_rows": len(window_attribution),
        "profile_summary": _profile_summary(window_attribution),
        "return_data_read": True,
        "overlapping_windows": True,
        "statistical_inference_allowed": False,
        "causal_claim_allowed": False,
        "training_only": True,
        "locked_validation_opened": False,
        "promotion_allowed": False,
        "decision": "DIAGNOSTIC_ONLY_NO_PROMOTION",
        "next_action": (
            "Use sleeve and replacement evidence to pre-register the next factor policy; "
            "do not tune weights from these overlapping-window associations."
        ),
    }
    frames = {
        "selection_states": states,
        "selection_holdings": holdings,
        "replacement_events": events,
        "replacement_tickers": replacement_tickers,
        "schedule_mismatches": mismatches,
        "window_features": features,
        "window_attribution": window_attribution,
        "factor_associations": associations,
        "start_year_summary": start_year_summary,
        "window_stress": stress,
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


def write_quality_attribution_bundle(
    frames: dict[str, pd.DataFrame],
    summary: dict,
    output_dir: str | Path,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    evidence_files = {}
    for name, frame in frames.items():
        filename = f"{name}.csv"
        path = output / filename
        _atomic_csv(frame, path)
        evidence_files[name] = {
            "filename": filename,
            "rows": len(frame),
            "sha256": file_sha256(path),
        }
    workbook_path = output / "ndx_quality_attribution.xlsx"
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
    finally:
        if temporary.exists():
            temporary.unlink()
    payload = {
        **summary,
        "evidence_files": evidence_files,
        "workbook": workbook_path.name,
    }
    atomic_write_text(
        output / "quality_attribution_summary.json",
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        ) + "\n",
    )
    return payload
