"""Evidence-driven staged search for Nasdaq-100 stock portfolios.

Stage 1 converts a completed, neutral-allocation experiment into a broad,
sector-aware frozen stock shortlist. Stage 2 is generated from that evidence
and searches holding count and allocation methods without changing the pool.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_competition import _issuer_key, _price_universe_version
from backtest.ndx_experiment_analysis import _read_verified_bundle
from backtest.ndx_experiment_lab import _format_workbook, _localized_excel_frame
from backtest.ndx_quality import load_quality_score_evidence
from backtest.preference_walkforward import _load_series, _research_cfg
from core.helpers import atomic_write_text
from data.ndx_history import constituents_asof, get_ndx_point_in_time_history
from data.candidate_pool import get_nasdaq_100_snapshot


SCORE_INPUTS = (
    "selection_support_rate",
    "rule_family_support_rate",
    "lookback_support_rate",
    "selection_date_support_rate",
    "membership_date_coverage",
    "forward_score_p50",
    "forward_score_p10",
    "forward_positive_rate",
)

CONTEXT_COLUMNS = (
    "incumbent_win_rate",
    "incumbent_xirr_p10_margin",
    "incumbent_xirr_p50_margin",
    "incumbent_dd_relief_p50",
    "incumbent_dd_relief_p90",
    "turnover_x_p50",
)


class NdxStagedSearchError(ValueError):
    """Raised when staged-search evidence is incomplete or inconsistent."""


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


def _parse_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    return [
        item.strip().upper()
        for item in str(value).replace(",", ";").split(";")
        if item.strip()
    ]


def _profile_family(profile_id: str) -> str:
    return str(profile_id).split("__", 1)[0]


def _verified_source_version(
    versions: pd.DataFrame,
    source_name: str,
    observed_version_id: str | None,
) -> None:
    expected = set(
        versions.loc[
            versions["source_name"].astype(str).eq(source_name), "version_id"
        ].dropna().astype(str)
    )
    if not observed_version_id or observed_version_id not in expected:
        raise NdxStagedSearchError(
            f"{source_name} version changed since the experiment: "
            f"observed={observed_version_id!r}, expected={sorted(expected)!r}"
        )


def load_stock_screen_analysis_spec(path: str | Path) -> dict:
    source = Path(path)
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or int(raw.get("schema_version") or 0) != 1:
        raise NdxStagedSearchError("unsupported stock-screen analysis schema")
    required = {
        "analysis_id",
        "source_experiment_id",
        "forward_horizons_trading_days",
        "forward_period_score",
        "stock_score_formula",
    }
    missing = sorted(required - set(raw))
    if missing or raw.get("research_only") is not True:
        raise NdxStagedSearchError(
            f"stock-screen analysis spec is incomplete: {missing}"
        )
    horizons = sorted({int(value) for value in raw["forward_horizons_trading_days"]})
    if len(horizons) < 2 or min(horizons) < 21:
        raise NdxStagedSearchError("at least two forward horizons are required")
    raw["forward_horizons_trading_days"] = horizons
    for field in ("forward_period_score", "stock_score_formula"):
        weights = {key: float(value) for key, value in raw[field].items()}
        if not np.isclose(sum(weights.values()), 1.0, atol=1e-12):
            raise NdxStagedSearchError(f"{field} weights must sum to one")
        raw[field] = weights
    if set(raw["stock_score_formula"]) != set(SCORE_INPUTS):
        raise NdxStagedSearchError("stock score formula fields changed")
    return raw


def _forward_stock_evidence(
    cfg,
    history: pd.DataFrame,
    quality_scores: pd.DataFrame,
    universe_by_date: dict[str, set[str]],
    versions: pd.DataFrame,
    analysis_contract: dict,
    *,
    research_end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    research_cfg = _research_cfg(cfg, True)
    current_ndx, _ = get_nasdaq_100_snapshot(research_cfg)
    requested = sorted(
        set(history["ticker"].astype(str).str.upper())
        | set(current_ndx["ticker"].astype(str).str.upper())
        | {symbol.ticker for symbol in research_cfg.symbols}
    )
    series, _, errors = _load_series(research_cfg, requested)
    missing = sorted(set(history["ticker"].astype(str).str.upper()) & set(errors))
    if missing:
        raise NdxStagedSearchError(
            f"forward stock evidence lacks historical prices: {missing}"
        )
    price_version = _price_universe_version(series)
    _verified_source_version(
        versions, "price_universe", price_version.get("version_id")
    )

    quality = quality_scores.copy()
    quality["selection_date"] = pd.to_datetime(quality["selection_date"])
    quality["ticker"] = quality["ticker"].astype(str).str.upper()
    quality_by_ticker = {
        ticker: group.sort_values("selection_date", kind="stable")
        for ticker, group in quality.groupby("ticker", sort=False)
    }
    horizons = analysis_contract["forward_horizons_trading_days"]
    end_date = pd.Timestamp(research_end)
    rows = []
    for date, universe in sorted(universe_by_date.items()):
        selection_date = pd.Timestamp(date)
        for ticker in sorted(universe):
            ticker_quality = quality_by_ticker.get(ticker)
            available_quality = (
                ticker_quality[ticker_quality["selection_date"] <= selection_date]
                if ticker_quality is not None else pd.DataFrame()
            )
            if available_quality.empty:
                raise NdxStagedSearchError(
                    f"forward evidence lacks point-in-time SIC for {ticker} at {date}"
                )
            classification = available_quality.iloc[-1]
            classification_date = pd.Timestamp(
                classification["selection_date"]
            ).strftime("%Y-%m-%d")
            frame = series.get(ticker)
            if frame is None:
                continue
            future = frame[
                (frame.index >= selection_date) & (frame.index <= end_date)
            ].sort_index()
            if future.empty or future.index[0].normalize() != selection_date.normalize():
                continue
            entry = float(future.iloc[0]["Open"])
            if not np.isfinite(entry) or entry <= 0:
                continue
            for horizon in horizons:
                if len(future) <= int(horizon):
                    continue
                path = future.iloc[: int(horizon) + 1]["Close"].to_numpy(dtype=float)
                if not np.isfinite(path).all() or (path <= 0).any():
                    continue
                path = path.copy()
                path[0] = entry
                peak = np.maximum.accumulate(path)
                drawdown = np.where(peak > 0, (peak - path) / peak, np.nan)
                rows.append({
                    "selection_date": date,
                    "ticker": ticker,
                    "horizon_trading_days": int(horizon),
                    "entry_date": future.index[0].strftime("%Y-%m-%d"),
                    "exit_date": future.index[int(horizon)].strftime("%Y-%m-%d"),
                    "forward_return": float(path[-1] / entry - 1.0),
                    "forward_maxdd": float(np.nanmax(drawdown)),
                    "sic2": str(classification["sic_group_2d"]),
                    "sic4": str(classification["sic"]),
                    "sic_description": classification.get("sic_description"),
                    "classification_evidence_date": classification_date,
                    "classification_future_data_guard_passed": bool(
                        classification_date <= date
                    ),
                })
    details = pd.DataFrame(rows)
    if details.empty:
        raise NdxStagedSearchError("no complete forward stock outcomes are available")
    if not details["classification_future_data_guard_passed"].all():
        raise NdxStagedSearchError("forward SIC classification used future data")
    group_keys = ["selection_date", "horizon_trading_days"]
    details["universe_return_percentile"] = details.groupby(group_keys)[
        "forward_return"
    ].rank(method="average", pct=True)
    details["universe_drawdown_percentile"] = (-details["forward_maxdd"]).groupby(
        [details[key] for key in group_keys]
    ).rank(method="average", pct=True)
    sector_keys = group_keys + ["sic2"]
    details["sic2_return_percentile"] = details.groupby(sector_keys)[
        "forward_return"
    ].rank(method="average", pct=True)
    details["sic2_drawdown_percentile"] = (-details["forward_maxdd"]).groupby(
        [details[key] for key in sector_keys]
    ).rank(method="average", pct=True)
    period_weights = analysis_contract["forward_period_score"]
    expected_period_fields = {
        "universe_return_percentile",
        "sic2_return_percentile",
        "universe_drawdown_percentile",
        "sic2_drawdown_percentile",
    }
    if set(period_weights) != expected_period_fields:
        raise NdxStagedSearchError("forward period score fields changed")
    details["forward_period_score"] = sum(
        float(weight) * details[field]
        for field, weight in period_weights.items()
    )

    rows = []
    for ticker, group in details.groupby("ticker", sort=True):
        horizon_counts = group.groupby("horizon_trading_days").size()
        rows.append({
            "ticker": ticker,
            "forward_observations": len(group),
            "forward_horizon_count": int(group["horizon_trading_days"].nunique()),
            "forward_observations_by_horizon": ";".join(
                f"{int(horizon)}:{int(count)}"
                for horizon, count in horizon_counts.items()
            ),
            "forward_score_p50": float(group["forward_period_score"].median()),
            "forward_score_p10": float(group["forward_period_score"].quantile(0.10)),
            "forward_positive_rate": float((group["forward_return"] > 0).mean()),
            "forward_return_p50": float(group["forward_return"].median()),
            "forward_return_p10": float(group["forward_return"].quantile(0.10)),
            "forward_maxdd_p50": float(group["forward_maxdd"].median()),
            "forward_maxdd_p90": float(group["forward_maxdd"].quantile(0.90)),
            "universe_return_percentile_p50": float(
                group["universe_return_percentile"].median()
            ),
            "sic2_return_percentile_p50": float(
                group["sic2_return_percentile"].median()
            ),
        })
    return pd.DataFrame(rows), details


def _deduplicate_decisions(selections: pd.DataFrame) -> pd.DataFrame:
    required = {
        "job_id",
        "profile_id",
        "selection_date",
        "tickers",
        "weights",
        "lookback_years",
    }
    missing = sorted(required - set(selections.columns))
    if missing:
        raise NdxStagedSearchError(
            f"stock-screen selections are missing columns: {missing}"
        )
    keys = ["job_id", "profile_id", "selection_date"]
    rows = []
    for _, group in selections.groupby(keys, dropna=False, sort=False):
        signatures = {
            (str(row.tickers), str(row.weights))
            for row in group.itertuples(index=False)
        }
        if len(signatures) != 1:
            identity = group.iloc[0][keys].to_dict()
            raise NdxStagedSearchError(
                f"duplicate decision changed across rolling windows: {identity}"
            )
        rows.append(group.sort_values("window_start", kind="stable").iloc[0])
    result = pd.DataFrame(rows).reset_index(drop=True)
    result["selection_date"] = result["selection_date"].astype(str).str[:10]
    result["rule_family"] = result["profile_id"].astype(str).map(_profile_family)
    result["decision_id"] = (
        result["job_id"].astype(str)
        + "|"
        + result["profile_id"].astype(str)
        + "|"
        + result["selection_date"]
    )
    result["profile_job_id"] = (
        result["job_id"].astype(str) + "|" + result["profile_id"].astype(str)
    )
    return result


def _classification_table(
    quality_scores: pd.DataFrame,
    *,
    start: str,
    end: str,
) -> pd.DataFrame:
    frame = quality_scores.copy()
    frame["selection_date"] = pd.to_datetime(frame["selection_date"])
    frame = frame[
        frame["selection_date"].between(pd.Timestamp(start), pd.Timestamp(end))
    ].copy()
    if frame.empty:
        raise NdxStagedSearchError("quality/SIC evidence has no stock-screen dates")

    def stable_mode(series: pd.Series) -> Any:
        values = series.dropna().astype(str)
        if values.empty:
            return None
        counts = values.value_counts()
        return sorted(counts[counts.eq(counts.max())].index)[0]

    rows = []
    for ticker, group in frame.groupby(frame["ticker"].astype(str).str.upper()):
        group = group.sort_values("selection_date", kind="stable")
        sic2 = stable_mode(group["sic_group_2d"])
        sic4 = stable_mode(group["sic"])
        matching = group[
            group["sic"].astype(str).eq(str(sic4))
        ] if sic4 is not None else group.iloc[0:0]
        rows.append({
            "ticker": ticker,
            "sic2": sic2,
            "sic4": sic4,
            "sic_description": (
                str(matching.iloc[-1]["sic_description"])
                if not matching.empty and "sic_description" in matching else None
            ),
            "sic_division": (
                str(matching.iloc[-1]["sic_division"])
                if not matching.empty and "sic_division" in matching else None
            ),
            "sic2_values": int(group["sic_group_2d"].dropna().astype(str).nunique()),
            "sic4_values": int(group["sic"].dropna().astype(str).nunique()),
        })
    return pd.DataFrame(rows)


def _stock_ranking(
    cfg,
    manifest: dict,
    frames: dict[str, pd.DataFrame],
    analysis_contract: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, set[str]]]:
    candidates = frames["candidates"].copy()
    selections = frames["selections"].copy()
    decisions = _deduplicate_decisions(selections)
    candidate_keys = ["job_id", "profile_id"]
    if candidates.duplicated(candidate_keys).any():
        raise NdxStagedSearchError("stock-screen candidate keys are not unique")
    missing_context = sorted(set(CONTEXT_COLUMNS) - set(candidates.columns))
    if missing_context:
        raise NdxStagedSearchError(
            f"stock-screen candidates are missing incumbent metrics: {missing_context}"
        )
    decisions = decisions.merge(
        candidates[candidate_keys + list(CONTEXT_COLUMNS)],
        on=candidate_keys,
        how="left",
        validate="many_to_one",
    )
    if decisions[list(CONTEXT_COLUMNS)].isna().all(axis=1).any():
        raise NdxStagedSearchError("selection decisions cannot be joined to candidates")

    history, history_meta = get_ndx_point_in_time_history(cfg)
    history_version = history_meta.to_dict().get("version_id")
    _verified_source_version(frames["versions"], "ndx_history", history_version)
    quality_scores, quality_meta = load_quality_score_evidence(cfg)
    _verified_source_version(
        frames["versions"], "quality_scores", quality_meta.get("version_id")
    )

    universe_by_date: dict[str, set[str]] = {}
    all_dates = sorted(decisions["selection_date"].unique())
    for date in all_dates:
        snapshot, evidence = constituents_asof(history, date)
        if evidence.get("future_data_guard_passed") is not True:
            raise NdxStagedSearchError("constituent future-data guard failed")
        universe_by_date[date] = set(
            snapshot["ticker"].astype(str).str.upper()
        )

    eligible_decisions: dict[str, set[str]] = defaultdict(set)
    eligible_profile_jobs: dict[str, set[str]] = defaultdict(set)
    eligible_dates: dict[str, set[str]] = defaultdict(set)
    selected_decisions: dict[str, set[str]] = defaultdict(set)
    selected_profile_jobs: dict[str, set[str]] = defaultdict(set)
    selected_dates: dict[str, set[str]] = defaultdict(set)
    selected_families: dict[str, set[str]] = defaultdict(set)
    selected_lookbacks: dict[str, set[float]] = defaultdict(set)
    event_rows = []
    for row in decisions.itertuples(index=False):
        universe = universe_by_date[row.selection_date]
        selected = _parse_list(row.tickers)
        outside = sorted(set(selected) - universe)
        if outside:
            raise NdxStagedSearchError(
                f"selection contains non-member securities at {row.selection_date}: {outside}"
            )
        for ticker in universe:
            eligible_decisions[ticker].add(row.decision_id)
            eligible_profile_jobs[ticker].add(row.profile_job_id)
            eligible_dates[ticker].add(row.selection_date)
        for ticker in selected:
            selected_decisions[ticker].add(row.decision_id)
            selected_profile_jobs[ticker].add(row.profile_job_id)
            selected_dates[ticker].add(row.selection_date)
            selected_families[ticker].add(row.rule_family)
            selected_lookbacks[ticker].add(float(row.lookback_years))
            event_rows.append({
                "ticker": ticker,
                "selection_date": row.selection_date,
                "job_id": row.job_id,
                "profile_id": row.profile_id,
                "profile_job_id": row.profile_job_id,
                "rule_family": row.rule_family,
                "lookback_years": float(row.lookback_years),
                **{column: getattr(row, column) for column in CONTEXT_COLUMNS},
            })
    events = pd.DataFrame(event_rows)
    if events.empty:
        raise NdxStagedSearchError("stock-screen produced no selected securities")
    profile_context = events.drop_duplicates(
        ["ticker", "profile_job_id"], keep="first"
    )
    context = profile_context.groupby("ticker", as_index=False).agg(
        incumbent_win_rate_context=("incumbent_win_rate", "median"),
        incumbent_xirr_p10_context=("incumbent_xirr_p10_margin", "median"),
        incumbent_xirr_p50_context=("incumbent_xirr_p50_margin", "median"),
        incumbent_dd_relief_p50_context=("incumbent_dd_relief_p50", "median"),
        incumbent_dd_relief_p90_context=("incumbent_dd_relief_p90", "median"),
        turnover_context=("turnover_x_p50", "median"),
    )
    total_families = int(decisions["rule_family"].nunique())
    total_lookbacks = int(decisions["lookback_years"].nunique())
    total_dates = len(all_dates)
    rows = []
    for ticker in sorted(selected_decisions):
        rows.append({
            "ticker": ticker,
            "issuer_key": _issuer_key(ticker),
            "selected_decision_count": len(selected_decisions[ticker]),
            "eligible_decision_count": len(eligible_decisions[ticker]),
            "selection_support_rate": (
                len(selected_profile_jobs[ticker])
                / len(eligible_profile_jobs[ticker])
            ),
            "selected_profile_job_count": len(selected_profile_jobs[ticker]),
            "eligible_profile_job_count": len(eligible_profile_jobs[ticker]),
            "selected_rule_family_count": len(selected_families[ticker]),
            "rule_family_support_rate": len(selected_families[ticker]) / total_families,
            "selected_lookback_count": len(selected_lookbacks[ticker]),
            "lookback_support_rate": len(selected_lookbacks[ticker]) / total_lookbacks,
            "selected_date_count": len(selected_dates[ticker]),
            "eligible_date_count": len(eligible_dates[ticker]),
            "selection_date_support_rate": (
                len(selected_dates[ticker]) / len(eligible_dates[ticker])
            ),
            "membership_date_coverage": len(eligible_dates[ticker]) / total_dates,
            "first_selected_date": min(selected_dates[ticker]),
            "last_selected_date": max(selected_dates[ticker]),
            "rule_families": ";".join(sorted(selected_families[ticker])),
            "lookbacks": ";".join(
                f"{value:g}" for value in sorted(selected_lookbacks[ticker])
            ),
        })
    ranking = pd.DataFrame(rows).merge(context, on="ticker", validate="one_to_one")
    start = str(candidates["research_start"].dropna().astype(str).min())[:10]
    end = str(candidates["research_end"].dropna().astype(str).max())[:10]
    classifications = _classification_table(quality_scores, start=start, end=end)
    ranking = ranking.merge(classifications, on="ticker", how="left", validate="one_to_one")
    if ranking[["sic2", "sic4"]].isna().any().any():
        missing = ranking.loc[ranking["sic2"].isna(), "ticker"].tolist()
        raise NdxStagedSearchError(f"selected stocks lack SIC evidence: {missing}")

    forward, forward_details = _forward_stock_evidence(
        cfg,
        history,
        quality_scores,
        universe_by_date,
        frames["versions"],
        analysis_contract,
        research_end=end,
    )
    ranking = ranking.merge(forward, on="ticker", how="left", validate="one_to_one")

    weights = analysis_contract.get("stock_score_formula") or {}
    if set(weights) != set(SCORE_INPUTS):
        raise NdxStagedSearchError("stock score formula does not match the engine contract")
    parsed_weights = {key: float(value) for key, value in weights.items()}
    if not np.isclose(sum(parsed_weights.values()), 1.0, atol=1e-12):
        raise NdxStagedSearchError("stock score weights must sum to one")
    score = pd.Series(0.0, index=ranking.index)
    for field, weight in parsed_weights.items():
        values = pd.to_numeric(ranking[field], errors="coerce")
        percentile = values.rank(method="average", pct=True).fillna(0.0)
        ranking[f"{field}_percentile"] = percentile
        score += weight * percentile
    ranking["evidence_score"] = score
    ranking["current_strategy_member"] = ranking["ticker"].isin(
        {symbol.ticker for symbol in cfg.symbols}
    )
    latest_universe = universe_by_date[max(universe_by_date)]
    ranking["latest_ndx_member"] = ranking["ticker"].isin(latest_universe)
    ranking = ranking.sort_values(
        [
            "evidence_score",
            "selection_support_rate",
            "incumbent_xirr_p10_context",
            "incumbent_dd_relief_p90_context",
            "ticker",
        ],
        ascending=[False, False, False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    ranking.insert(0, "rank", np.arange(1, len(ranking) + 1))
    return ranking, events, forward_details, universe_by_date


def _balanced_shortlists(
    ranking: pd.DataFrame,
    universe_by_date: dict[str, set[str]],
    contract: dict,
    *,
    sizes: Iterable[int],
    max_per_sic2: int,
    required_top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = ranking[
        (ranking["membership_date_coverage"] >= float(
            contract.get("shortlist_min_membership_date_rate", 0.50)
        ))
        & (ranking["selected_rule_family_count"] >= int(
            contract.get("shortlist_min_rule_families", 2)
        ))
        & (ranking["selected_lookback_count"] >= int(
            contract.get("shortlist_min_lookbacks", 2)
        ))
        & (ranking["forward_observations"] >= int(
            contract.get("shortlist_min_forward_observations", 8)
        ))
        & (ranking["forward_horizon_count"] >= int(
            contract.get("shortlist_required_forward_horizons", 2)
        ))
    ].copy()
    pool_rows = []
    summary_rows = []
    for size in sorted({int(value) for value in sizes}):
        selected = []
        sector_counts: dict[str, int] = defaultdict(int)
        issuers = set()
        for row in eligible.itertuples(index=False):
            sector = str(row.sic2)
            if row.issuer_key in issuers or sector_counts[sector] >= int(max_per_sic2):
                continue
            issuers.add(row.issuer_key)
            sector_counts[sector] += 1
            selected.append(row)
            if len(selected) == size:
                break
        if len(selected) != size:
            raise NdxStagedSearchError(
                f"only {len(selected)} stocks satisfy pool{size} breadth rules"
            )
        tickers = {row.ticker for row in selected}
        member_counts = {
            date: len(tickers & universe)
            for date, universe in universe_by_date.items()
        }
        minimum_members = min(member_counts.values())
        if minimum_members < int(required_top_n):
            raise NdxStagedSearchError(
                f"pool{size} has only {minimum_members} members on its weakest date; "
                f"top{required_top_n} cannot be tested without changing the pool"
            )
        shortlist_id = f"pool{size}"
        for row in selected:
            payload = row._asdict()
            payload.update({
                "shortlist_id": shortlist_id,
                "shortlist_size": size,
                "shortlist_max_per_sic2": int(max_per_sic2),
            })
            pool_rows.append(payload)
        summary_rows.append({
            "shortlist_id": shortlist_id,
            "shortlist_size": size,
            "sic2_group_count": len(sector_counts),
            "maximum_names_in_one_sic2": max(sector_counts.values()),
            "minimum_point_in_time_members": minimum_members,
            "latest_point_in_time_members": member_counts[max(member_counts)],
            "ticker_list": ";".join(row.ticker for row in selected),
        })
    return pd.DataFrame(pool_rows), pd.DataFrame(summary_rows)


def _stage2_profiles(shortlists: pd.DataFrame) -> list[dict]:
    profiles = []
    for shortlist_id, pool in shortlists.groupby("shortlist_id", sort=True):
        tickers = pool.sort_values("rank")["ticker"].tolist()
        for sector_policy in ("uncapped", "sic_cap2"):
            for quality_weight in (0.0, 0.25):
                for top_n in (6, 8, 10, 12):
                    for weight_mode in (
                        "equal",
                        "inverse_vol",
                        "risk_parity",
                        "score_risk",
                        "source_weight",
                    ):
                        quality_tag = f"q{int(quality_weight * 100):02d}"
                        profile = {
                            "id": (
                                f"{shortlist_id}__{sector_policy}__{quality_tag}"
                                f"__top{top_n}__{weight_mode}"
                            ),
                            "candidate_tickers": tickers,
                            "top_n": top_n,
                            "weight_mode": weight_mode,
                            "rebalance_months": 6,
                            "safe_weight": 0.26,
                            "challenger_sleeve_weight": 1.0,
                            "max_weight": 0.20,
                            "min_weight": 0.02,
                            "selection_mode": "rank",
                            "fundamental_score_weight": quality_weight,
                            "defense_mode": "static",
                        }
                        if quality_weight > 0 or sector_policy == "sic_cap2":
                            profile["quality_policy_id"] = (
                                "ndx_sec_quality_three_sleeve_v1"
                            )
                        if sector_policy == "sic_cap2":
                            profile["max_names_per_sic4"] = 1
                            profile["max_names_per_sic2"] = 2
                        profiles.append(profile)
    return profiles


def _stage2_spec(
    source_manifest_path: Path,
    shortlists_path: Path,
    shortlists: pd.DataFrame,
    analysis_contract: dict,
) -> dict:
    profiles = _stage2_profiles(shortlists)
    baseline = next(
        profile["id"]
        for profile in profiles
        if "__uncapped__q00__top8__equal" in profile["id"]
    )
    return {
        "schema_version": 1,
        "experiment_id": "ndx_incumbent_allocation_search_v8b",
        "research_question": (
            "Within frozen, sector-balanced stock pools from v8a, which holding "
            "count and allocation rule most robustly improves on the current "
            "eight-name strategy?"
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
            "component_family": "incumbent_first_frozen_pool_allocation",
            "research_stage": "holding_count_and_allocation",
            "baseline_profile_id": baseline,
            "decision_priority": "incumbent_first",
            "target_role": "secondary_reference_only",
            "source_stage1_manifest_sha256": _content_hash(source_manifest_path),
            "source_stage1_shortlists_sha256": _content_hash(shortlists_path),
            "source_stock_analysis_id": analysis_contract["analysis_id"],
            "source_stock_analysis_sha256": hashlib.sha256(
                json.dumps(
                    analysis_contract,
                    ensure_ascii=True,
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "pool_change_policy": "forbidden_within_stage2",
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
                "phase_id": "allocation_training",
                "enabled": True,
                "role": "exploratory_training",
                "rationale": (
                    "The stock pools are frozen by v8a evidence. This stage varies "
                    "only holding count, allocation rule, quality blend, and the "
                    "declared SEC-SIC breadth policy."
                ),
                "start": "2022-01-11",
                "end": "2024-06-30",
                "target": "012922",
                "min_years": 1.0,
                "step_months": 1,
                "shared_grid": {
                    "top_ns": [8],
                    "weight_modes": ["equal"],
                    "safe_weights": [0.26],
                    "rebalance_months": [6],
                    "max_weights": [0.20],
                },
                "construction_profiles": profiles,
                "sweep": {
                    "lookback_years": [1, 2, 3],
                    "trade_cost_bps": [10],
                },
            },
            {
                "phase_id": "portfolio_stress_validation",
                "enabled": False,
                "role": "locked_validation",
                "rationale": (
                    "Enabled only after Pareto allocation candidates are frozen."
                ),
                "start": None,
                "end": None,
                "target": "012922",
                "locked_candidates": [],
            },
        ],
    }


RANKING_CN = {
    "rank": "综合排名",
    "ticker": "股票代码",
    "issuer_key": "发行人标识",
    "evidence_score": "白盒证据分",
    "selection_support_rate": "方案作业入选率",
    "rule_family_support_rate": "选股规则覆盖率",
    "lookback_support_rate": "回看周期覆盖率",
    "selection_date_support_rate": "历史日期入选率",
    "membership_date_coverage": "历史成分日期覆盖率",
    "selected_rule_family_count": "支持规则家族数",
    "selected_lookback_count": "支持回看周期数",
    "selected_date_count": "入选日期数",
    "eligible_date_count": "可参与日期数",
    "incumbent_win_rate_context": "所在组合战胜当前8只胜率中位",
    "incumbent_xirr_p10_context": "所在组合相对当前8只XIRR尾部差",
    "incumbent_xirr_p50_context": "所在组合相对当前8只XIRR中位差",
    "incumbent_dd_relief_p50_context": "所在组合回撤改善中位",
    "incumbent_dd_relief_p90_context": "所在组合回撤改善压力值",
    "turnover_context": "所在组合换手倍数中位",
    "forward_observations": "逐股前瞻观测数",
    "forward_horizon_count": "完整前瞻周期数",
    "forward_observations_by_horizon": "各前瞻周期观测数",
    "forward_score_p50": "逐股前瞻综合分中位",
    "forward_score_p10": "逐股前瞻综合分尾部",
    "forward_positive_rate": "逐股前瞻正收益率",
    "forward_return_p50": "逐股前瞻收益中位",
    "forward_return_p10": "逐股前瞻收益尾部",
    "forward_maxdd_p50": "逐股前瞻最大回撤中位",
    "forward_maxdd_p90": "逐股前瞻最大回撤压力值",
    "universe_return_percentile_p50": "全成分收益分位中位",
    "sic2_return_percentile_p50": "同SIC二位收益分位中位",
    "horizon_trading_days": "前瞻交易日数",
    "entry_date": "模拟买入日期",
    "exit_date": "模拟观察结束日期",
    "forward_return": "前瞻收益",
    "forward_maxdd": "前瞻最大回撤",
    "universe_return_percentile": "全成分收益分位",
    "universe_drawdown_percentile": "全成分回撤分位",
    "sic2_return_percentile": "同SIC二位收益分位",
    "sic2_drawdown_percentile": "同SIC二位回撤分位",
    "forward_period_score": "单期前瞻综合分",
    "classification_evidence_date": "行业分类证据日期",
    "classification_future_data_guard_passed": "行业分类未来数据防护通过",
    "sic2": "SEC SIC二位分类",
    "sic4": "SEC SIC四位分类",
    "sic_description": "SEC行业说明",
    "sic_division": "SEC行业大类",
    "first_selected_date": "首次入选日期",
    "last_selected_date": "最后入选日期",
    "rule_families": "支持选股规则",
    "lookbacks": "支持回看年数",
    "current_strategy_member": "是否属于当前8只",
    "latest_ndx_member": "最后研究日是否为纳指100成分",
    "shortlist_id": "冻结池编号",
    "shortlist_size": "冻结池股票数",
    "shortlist_max_per_sic2": "同SIC二位最多股票数",
    "sic2_group_count": "SIC二位行业组数",
    "maximum_names_in_one_sic2": "单一SIC二位最多股票数",
    "minimum_point_in_time_members": "最弱历史时点可参与股票数",
    "latest_point_in_time_members": "最后研究日可参与股票数",
    "ticker_list": "冻结股票列表",
}


def _chinese_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    columns = {}
    for column in result.columns:
        columns[column] = RANKING_CN.get(column, f"技术字段（{column}）")
    result = result.rename(columns=columns)
    for column in result.columns:
        if result[column].dtype == bool:
            result[column] = result[column].map({True: "是", False: "否"})
    return result


def build_stock_screen_bundle(
    cfg,
    experiment_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    shortlist_sizes: Iterable[int] = (18, 24, 30),
    max_per_sic2: int = 2,
    required_top_n: int = 12,
    strategy_config_path: str | Path | None = None,
    analysis_spec: dict | None = None,
) -> dict:
    root = Path(experiment_dir)
    manifest, frames = _read_verified_bundle(
        root,
        strategy_config_path=strategy_config_path,
    )
    experiment_contract = manifest.get("analysis_contract") or {}
    if experiment_contract.get("research_stage") != "stock_screen":
        raise NdxStagedSearchError("experiment is not a stock-screen stage")
    if experiment_contract.get("decision_priority") != "incumbent_first":
        raise NdxStagedSearchError("stock screen did not pre-register incumbent-first")
    contract = dict(analysis_spec or {})
    if not contract:
        raise NdxStagedSearchError("a versioned stock-screen analysis spec is required")
    if contract.get("source_experiment_id") != manifest.get("experiment_id"):
        raise NdxStagedSearchError("analysis spec points to a different experiment")
    candidates = frames["candidates"]
    if set(candidates["weight_mode"].dropna().astype(str)) != {"equal"}:
        raise NdxStagedSearchError("stock screen changed allocation away from equal weight")
    if set(pd.to_numeric(candidates["trade_cost_bps"])) != {10.0}:
        raise NdxStagedSearchError("stock screen cost is not fixed at 10bp")

    ranking, events, forward_details, universe_by_date = _stock_ranking(
        cfg, manifest, frames, contract
    )
    shortlists, shortlist_summary = _balanced_shortlists(
        ranking,
        universe_by_date,
        contract,
        sizes=shortlist_sizes,
        max_per_sic2=int(max_per_sic2),
        required_top_n=int(required_top_n),
    )
    output = Path(output_dir) if output_dir else root / "analysis" / "staged_search"
    output.mkdir(parents=True, exist_ok=True)
    ranking_path = output / "stage1_stock_ranking.csv"
    shortlists_path = output / "stage1_frozen_shortlists.csv"
    summary_path = output / "stage1_shortlist_summary.csv"
    events_path = output / "stage1_selection_events.csv"
    forward_path = output / "stage1_forward_stock_evidence.csv"
    _atomic_csv(ranking, ranking_path)
    _atomic_csv(shortlists, shortlists_path)
    _atomic_csv(shortlist_summary, summary_path)
    _atomic_csv(events, events_path)
    _atomic_csv(forward_details, forward_path)

    stage2 = _stage2_spec(
        root / "manifest.json", shortlists_path, shortlists, contract
    )
    stage2_path = output / "stage2_allocation_spec.yaml"
    atomic_write_text(
        stage2_path,
        yaml.safe_dump(stage2, allow_unicode=True, sort_keys=False),
    )

    workbook_path = output / "stage1_stock_screen_report.xlsx"
    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    explanation = pd.DataFrame([
        {"项目": "主比较基准", "内容": "当前8只策略配置"},
        {"项目": "第二层参照", "内容": "012922，仅作诊断，不参与第一排序"},
        {"项目": "QQQ角色", "内容": "历史成分代理与辅助参照，不是候选资产"},
        {"项目": "第一阶段职责", "内容": "形成冻结股票短名单，不决定最终持仓比例"},
        {"项目": "分数性质", "内容": "多规则入选稳定性与所在组合表现的关联证据，不是单股因果贡献"},
        {"项目": "逐股训练证据", "内容": "6/12个月前瞻收益与回撤，同时按全成分和同SIC二位行业排名"},
        {"项目": "分析方法版本", "内容": contract.get("analysis_id")},
        {"项目": "方法修订原因", "内容": contract.get("method_revision_reason")},
        {"项目": "行业分类", "内容": "按申报时点SEC SIC约束；不是GICS，也不是完整产业链分类"},
        {"项目": "下一阶段", "内容": "只在冻结池内搜索持仓数量和权重算法"},
    ])
    sector_summary = shortlists.groupby(
        ["shortlist_id", "sic2", "sic_description"], as_index=False
    ).agg(
        股票数=("ticker", "size"),
        股票列表=("ticker", lambda values: ";".join(values)),
        平均证据分=("evidence_score", "mean"),
    ).rename(columns={
        "shortlist_id": "冻结池编号",
        "sic2": "SEC SIC二位分类",
        "sic_description": "SEC行业说明",
    })
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            explanation.to_excel(writer, sheet_name="使用说明", index=False)
            _chinese_frame(ranking).to_excel(writer, sheet_name="股票综合排名", index=False)
            _chinese_frame(shortlists).to_excel(writer, sheet_name="冻结候选池", index=False)
            _chinese_frame(shortlist_summary).to_excel(writer, sheet_name="候选池摘要", index=False)
            sector_summary.to_excel(writer, sheet_name="板块覆盖", index=False)
            _chinese_frame(events).to_excel(writer, sheet_name="入选证据事件", index=False)
            _chinese_frame(forward_details).to_excel(
                writer, sheet_name="逐股前瞻证据", index=False
            )
            _localized_excel_frame(candidates)[0].to_excel(
                writer, sheet_name="组合方案表现", index=False
            )
            _localized_excel_frame(frames["versions"])[0].to_excel(
                writer, sheet_name="数据版本", index=False
            )
        _format_workbook(temporary)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    payload = {
        "schema_version": 1,
        "research_only": True,
        "source_experiment_id": manifest.get("experiment_id"),
        "source_manifest_sha256": _content_hash(root / "manifest.json"),
        "stock_analysis_id": contract.get("analysis_id"),
        "decision_priority": "incumbent_first",
        "primary_competition_benchmark": "current_config",
        "secondary_reference": "012922",
        "ranked_stock_count": len(ranking),
        "shortlists": shortlist_summary.to_dict(orient="records"),
        "score_formula": contract.get("stock_score_formula"),
        "forward_period_score": contract.get("forward_period_score"),
        "stage2_profile_count": len(stage2["phases"][0]["construction_profiles"]),
        "files": {
            "stock_ranking": ranking_path.name,
            "frozen_shortlists": shortlists_path.name,
            "shortlist_summary": summary_path.name,
            "selection_events": events_path.name,
            "forward_stock_evidence": forward_path.name,
            "workbook": workbook_path.name,
            "stage2_spec": stage2_path.name,
        },
    }
    atomic_write_text(
        output / "stage1_summary.json",
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return payload
