"""Point-in-time readiness primitives for variable-cardinality discovery."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from core.helpers import atomic_write_text
from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from backtest.weights import project_concentration_envelope_weights
from data.versioning import file_sha256


class NdxCardinalityDiscoveryError(ValueError):
    pass


def load_discovery_spec(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NdxCardinalityDiscoveryError("discovery spec must be a mapping")
    return payload


def validate_discovery_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    if spec.get("schema_version") != 1 or not spec.get("discovery_id"):
        raise NdxCardinalityDiscoveryError("discovery identity/schema changed")
    if spec.get("status") != "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION":
        raise NdxCardinalityDiscoveryError("discovery status must remain training-only")
    if spec.get("promotion_allowed") is not False or spec.get("live_mutation_allowed") is not False:
        raise NdxCardinalityDiscoveryError("promotion/live mutation must be disabled")
    pit = spec.get("point_in_time_contract") or {}
    if pit.get("require_evidence_available_on_selection_date") is not True:
        raise NdxCardinalityDiscoveryError("evidence available-date gate is required")
    if pit.get("current_taxonomy_backfill_allowed") is not False:
        raise NdxCardinalityDiscoveryError("current taxonomy backfill must be forbidden")
    if pit.get("historical_backtest_allowed") is not False:
        raise NdxCardinalityDiscoveryError("event gaps must continue to block historical admission")
    if pit.get("exact_ndx_membership_valid") is not False:
        raise NdxCardinalityDiscoveryError("exact historical NDX membership must remain blocked")
    search = spec.get("search_contract") or {}
    if search.get("holding_count_policy") != "dynamic_from_one_to_available_issuer_count":
        raise NdxCardinalityDiscoveryError("holding count must remain dynamic")
    if search.get("tracks") != ["strict_technology", "technology_plus_adjacent"]:
        raise NdxCardinalityDiscoveryError("discovery tracks changed")
    if int(search.get("exact_enumeration_max_feasible_combinations") or 0) <= 0:
        raise NdxCardinalityDiscoveryError("exact enumeration limit must be positive")
    if search.get("resume_required") is not True:
        raise NdxCardinalityDiscoveryError("resume contract must remain enabled")
    if set(search.get("required_frontiers") or []) != {"RETURN", "DRAWDOWN", "BAD_TAIL", "012922_DISTANCE", "PARETO"}:
        raise NdxCardinalityDiscoveryError("required frontier contract changed")
    history = spec.get("history_contract") or {}
    if int(history.get("primary_horizon_trading_days") or 0) <= 0:
        raise NdxCardinalityDiscoveryError("primary horizon must be positive")
    if int(history.get("minimum_mature_windows_per_cardinality") or 0) <= 0:
        raise NdxCardinalityDiscoveryError("minimum mature windows must be positive")
    smoke = spec.get("synthetic_smoke_contract") or {}
    if smoke.get("status") != "SYNTHETIC_ENGINE_VALIDATION_ONLY":
        raise NdxCardinalityDiscoveryError("synthetic smoke role changed")
    for key in ("business_days", "rolling_window_days", "rolling_step_days", "covariance_fit_days", "beam_width"):
        if int(smoke.get(key) or 0) <= 0:
            raise NdxCardinalityDiscoveryError(f"synthetic smoke {key} must be positive")
    if smoke.get("weight_specifications") != [
        "equal_weight", "constrained_fixed_shrinkage",
        "constrained_fixed_shrinkage_turnover_anchor",
    ]:
        raise NdxCardinalityDiscoveryError("synthetic weight specifications changed")
    if not 0.0 <= float(smoke.get("fixed_shrinkage_intensity", -1)) <= 1.0:
        raise NdxCardinalityDiscoveryError("fixed shrinkage intensity must be in [0,1]")
    if not 0.0 < float(smoke.get("risk_chain_top1_cap", 0.0)) <= 1.0:
        raise NdxCardinalityDiscoveryError("synthetic risk-chain Top1 cap must be in (0,1]")
    if not 0.0 <= float(smoke.get("turnover_anchor_strength", -1.0)) <= 1.0:
        raise NdxCardinalityDiscoveryError("synthetic turnover anchor strength must be in [0,1]")
    cash = float(smoke.get("portfolio_cash_usd", 0.0))
    buffer = float(smoke.get("minimum_cash_buffer_usd", -1.0))
    if cash <= 0 or not 0 <= buffer < cash:
        raise NdxCardinalityDiscoveryError("synthetic whole-lot cash contract is invalid")
    if float(smoke.get("minimum_median_dollar_volume_usd", 0.0)) <= 0:
        raise NdxCardinalityDiscoveryError("synthetic liquidity threshold must be positive")
    result = spec.get("result_contract") or {}
    if result.get("portfolio_scope") != "hsbc_us_equity_sleeve_only":
        raise NdxCardinalityDiscoveryError("result scope must remain the HSBC US equity sleeve only")
    if result.get("safe_leg_role") != "excluded_from_optimization_and_comparison":
        raise NdxCardinalityDiscoveryError("safe leg must remain outside discovery comparisons")
    if result.get("external_index_context") != "user_managed_outside_strategy_approximately_half_of_total_assets":
        raise NdxCardinalityDiscoveryError("external index allocation is context only")
    if result.get("incumbent_role") != "current_8_stock_sleeve_guard":
        raise NdxCardinalityDiscoveryError("incumbent must remain the current eight-stock sleeve")
    if result.get("fresh_oos_consumed") is not False or int(result.get("candidate_promotion_count") or 0) != 0:
        raise NdxCardinalityDiscoveryError("result promotion/OOS contract changed")
    real_inputs = spec.get("real_input_contract") or {}
    if int(real_inputs.get("fit_days_strictly_before_selection") or 0) <= 0:
        raise NdxCardinalityDiscoveryError("real input fit window must be positive")
    if int(real_inputs.get("evaluation_horizon_trading_days") or 0) != int(history["primary_horizon_trading_days"]):
        raise NdxCardinalityDiscoveryError("real input horizon must match discovery horizon")
    if real_inputs.get("availability_modes") != ["complete_universe", "degraded_research"]:
        raise NdxCardinalityDiscoveryError("real input availability modes changed")
    if real_inputs.get("degraded_research_promotion_allowed") is not False:
        raise NdxCardinalityDiscoveryError("degraded research must not allow promotion")
    if real_inputs.get("valuation_only_price_reuse_allowed") is not False:
        raise NdxCardinalityDiscoveryError("valuation-only prices must not enter returns")
    if str(real_inputs.get("target_fund")) != "012922":
        raise NdxCardinalityDiscoveryError("012922 must remain the real input target")
    real_search = spec.get("real_training_search_contract") or {}
    if real_search.get("method") != "equal_weight_full_or_bounded_then_multifrontier_shrinkage":
        raise NdxCardinalityDiscoveryError("real training search method changed")
    if real_search.get("first_stage_weight_specification") != "equal_weight":
        raise NdxCardinalityDiscoveryError("real training first stage must be equal weight")
    if real_search.get("second_stage_weight_specifications") != [
        "constrained_fixed_shrinkage", "constrained_fixed_shrinkage_turnover_anchor"
    ]:
        raise NdxCardinalityDiscoveryError("real training second-stage weight specs changed")
    if int(real_search.get("second_stage_per_frontier_security_sets") or 0) <= 0:
        raise NdxCardinalityDiscoveryError("real training second-stage frontier limit must be positive")
    if real_search.get("second_stage_selection_frontiers") != [
        "RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"
    ]:
        raise NdxCardinalityDiscoveryError("real training second-stage frontiers changed")
    if real_search.get("continuous_weight_grid_search_allowed") is not False:
        raise NdxCardinalityDiscoveryError("continuous real-training weight search must remain disabled")
    if real_search.get("unsearched_weight_space_must_be_reported") is not True:
        raise NdxCardinalityDiscoveryError("unsearched real-training weight space must be reported")
    if real_search.get("promotion_allowed") is not False:
        raise NdxCardinalityDiscoveryError("real training search cannot promote")
    return {"passed": True, "spec_sha256": None}


def monthly_selection_dates(calendar_dates: pd.Series | pd.DatetimeIndex, start: str, end: str) -> list[pd.Timestamp]:
    dates = pd.DatetimeIndex(pd.to_datetime(calendar_dates)).normalize().unique().sort_values()
    if dates.hasnans:
        raise NdxCardinalityDiscoveryError("calendar contains invalid dates")
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise NdxCardinalityDiscoveryError("discovery start date is after end date")
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    if dates.empty:
        raise NdxCardinalityDiscoveryError("calendar has no dates in discovery range")
    frame = pd.DataFrame({"date": dates})
    return frame.groupby(frame["date"].dt.to_period("M"), sort=True)["date"].first().tolist()


def build_point_in_time_taxonomy_panel(
    records: pd.DataFrame,
    search_plan: Mapping[str, Any],
    membership_observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Expand reviewed taxonomy records to their observed membership snapshots.

    The panel deliberately retains unclassified rows so the latest *global*
    membership snapshot can be selected without accidentally carrying an older
    technology-only snapshot forward. Eligibility is derived only from accepted
    point-in-time risk-chain evidence in the immutable search plan.
    """
    required = {
        "ticker", "security_id", "issuer_id", "selection_dates", "risk_chain",
        "evidence_available_date", "status",
    }
    missing = sorted(required - set(records.columns))
    if missing:
        raise NdxCardinalityDiscoveryError(f"taxonomy record columns missing: {missing}")
    tracks = search_plan.get("universe_tracks") or {}
    strict = tracks.get("strict_technology") or {}
    adjacent = tracks.get("technology_plus_adjacent") or {}
    strict_chains = set(strict.get("accepted_risk_chains") or [])
    if not strict_chains:
        raise NdxCardinalityDiscoveryError("strict technology risk-chain contract is empty")
    if adjacent.get("inherits") != "strict_technology":
        raise NdxCardinalityDiscoveryError("technology-plus-adjacent inheritance changed")
    adjacent_chains = strict_chains | set(adjacent.get("additional_risk_chains") or [])

    panel = records.copy()
    panel["membership_snapshot_date"] = panel["selection_dates"].fillna("").astype(str).str.split(";")
    panel = panel.explode("membership_snapshot_date", ignore_index=True)
    panel["membership_snapshot_date"] = pd.to_datetime(
        panel["membership_snapshot_date"], errors="coerce"
    ).dt.normalize()
    if panel["membership_snapshot_date"].isna().any():
        raise NdxCardinalityDiscoveryError("taxonomy records contain invalid membership snapshots")
    if membership_observations is not None:
        observation_required = {"available_date", "ticker", "cusip"}
        missing_observations = sorted(observation_required - set(membership_observations.columns))
        if missing_observations:
            raise NdxCardinalityDiscoveryError(
                f"membership observation columns missing: {missing_observations}"
            )
        if "cusip" not in panel:
            raise NdxCardinalityDiscoveryError("taxonomy records are missing cusip for ticker resolution")
        observations = membership_observations[list(observation_required)].copy()
        observations["membership_snapshot_date"] = pd.to_datetime(
            observations.pop("available_date"), errors="coerce"
        ).dt.normalize()
        observations["cusip"] = observations["cusip"].astype(str).str.strip().str.upper()
        observations["ticker"] = observations["ticker"].astype(str).str.strip().str.upper()
        if observations[["membership_snapshot_date", "cusip", "ticker"]].isna().any().any():
            raise NdxCardinalityDiscoveryError("membership observations contain invalid identity values")
        if observations.duplicated(["membership_snapshot_date", "cusip"]).any():
            raise NdxCardinalityDiscoveryError("membership observations duplicate snapshot/cusip")
        panel["cusip"] = panel["cusip"].astype(str).str.strip().str.upper()
        panel = panel.rename(columns={"ticker": "taxonomy_ticker_aliases"}).merge(
            observations,
            on=["membership_snapshot_date", "cusip"],
            how="left",
            validate="many_to_one",
        )
        if panel["ticker"].isna().any() or panel["ticker"].astype(str).str.strip().eq("").any():
            raise NdxCardinalityDiscoveryError("membership snapshot ticker resolution is incomplete")
    accepted = panel["status"].astype(str).str.lower().eq("accepted")
    panel["strict_technology_eligible"] = accepted & panel["risk_chain"].isin(strict_chains)
    panel["technology_plus_adjacent_eligible"] = accepted & panel["risk_chain"].isin(adjacent_chains)
    duplicate = panel.duplicated(["security_id", "membership_snapshot_date"], keep=False)
    if duplicate.any():
        keys = panel.loc[duplicate, ["security_id", "membership_snapshot_date"]].head(5)
        raise NdxCardinalityDiscoveryError(
            f"taxonomy panel has duplicate security snapshots: {keys.to_dict('records')}"
        )
    return panel


def point_in_time_track_memberships(
    panel: pd.DataFrame,
    selection_dates: list[pd.Timestamp],
    *,
    track: str,
    ticker_lifecycle: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Materialize the exact security rows used by each as-of selection."""
    column = {
        "strict_technology": "strict_technology_eligible",
        "technology_plus_adjacent": "technology_plus_adjacent_eligible",
    }.get(track)
    required = {
        "membership_snapshot_date", "ticker", "security_id", "issuer_id",
        "risk_chain", "evidence_available_date",
    }
    if not column:
        raise NdxCardinalityDiscoveryError(f"unknown track: {track}")
    required.add(column)
    missing = sorted(required - set(panel.columns))
    if missing:
        raise NdxCardinalityDiscoveryError(f"taxonomy panel columns missing: {missing}")
    work = panel.copy()
    work["membership_snapshot_date"] = pd.to_datetime(
        work["membership_snapshot_date"], errors="coerce"
    ).dt.normalize()
    work["evidence_available_date"] = pd.to_datetime(
        work["evidence_available_date"], errors="coerce", utc=True
    ).dt.tz_convert(None).dt.normalize()
    if work["membership_snapshot_date"].isna().any():
        raise NdxCardinalityDiscoveryError("taxonomy panel has invalid snapshots")
    snapshots = pd.DatetimeIndex(work["membership_snapshot_date"]).unique().sort_values()
    eligible = work.loc[work[column].astype(str).str.lower().eq("true")].copy()
    rows = []
    for raw_selection in selection_dates:
        selection = pd.Timestamp(raw_selection).normalize()
        prior = snapshots[snapshots <= selection]
        if not len(prior):
            continue
        snapshot = prior.max()
        active = eligible.loc[
            eligible["membership_snapshot_date"].eq(snapshot)
            & eligible["evidence_available_date"].le(selection)
        ].copy()
        if active.duplicated("security_id").any():
            raise NdxCardinalityDiscoveryError("active membership duplicates security_id")
        active["source_membership_ticker"] = active["ticker"]
        active["price_ticker_resolution"] = "source_membership_ticker"
        active["ticker_lifecycle_rule_id"] = ""
        if ticker_lifecycle is not None:
            if ticker_lifecycle.get("schema_version") != 1:
                raise NdxCardinalityDiscoveryError("ticker lifecycle schema changed")
            for rule in ticker_lifecycle.get("rules") or []:
                if "cik" not in active or "cusip" not in active:
                    raise NdxCardinalityDiscoveryError(
                        "taxonomy panel lacks cik/cusip for ticker lifecycle resolution"
                    )
                cik = str(rule.get("cik") or "").zfill(10)
                cusip = str(rule.get("cusip") or "").strip().upper()
                mask = (
                    active["cik"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(10).eq(cik)
                    & active["cusip"].astype(str).str.strip().str.upper().eq(cusip)
                )
                if not mask.any():
                    continue
                recognized = {str(item).upper() for item in (rule.get("recognized_tickers") or [])}
                observed = set(active.loc[mask, "ticker"].astype(str).str.upper())
                if not observed.issubset(recognized):
                    raise NdxCardinalityDiscoveryError(
                        f"ticker lifecycle source ticker changed for {rule.get('rule_id')}"
                    )
                matches = []
                for interval in rule.get("intervals") or []:
                    start = pd.Timestamp(interval["effective_from"]) if interval.get("effective_from") else None
                    end = pd.Timestamp(interval["effective_to"]) if interval.get("effective_to") else None
                    if (start is None or selection >= start) and (end is None or selection <= end):
                        matches.append(interval)
                if len(matches) != 1 or not matches[0].get("price_ticker"):
                    raise NdxCardinalityDiscoveryError(
                        f"ticker lifecycle interval is not unique for {rule.get('rule_id')} on {selection.date()}"
                    )
                active.loc[mask, "ticker"] = str(matches[0]["price_ticker"]).upper()
                active.loc[mask, "price_ticker_resolution"] = "reviewed_ticker_lifecycle"
                active.loc[mask, "ticker_lifecycle_rule_id"] = str(rule.get("rule_id") or "")
        active.insert(0, "universe_track", track)
        active.insert(1, "selection_date", selection.date().isoformat())
        active["membership_snapshot_date"] = snapshot.date().isoformat()
        active["membership_snapshot_age_days"] = int((selection - snapshot).days)
        rows.append(active)
    if not rows:
        return pd.DataFrame(columns=["universe_track", "selection_date"] + list(panel.columns))
    result = pd.concat(rows, ignore_index=True)
    preferred = [
        "universe_track", "selection_date", "membership_snapshot_date",
        "membership_snapshot_age_days", "ticker", "taxonomy_ticker_aliases",
        "security_id", "issuer_id", "risk_chain", "evidence_available_date",
    ]
    ordered = [name for name in preferred if name in result.columns]
    return result[ordered + [name for name in result.columns if name not in ordered]]


def point_in_time_cardinality_readiness(
    universe: pd.DataFrame,
    selection_dates: list[pd.Timestamp],
    calendar_dates: pd.DatetimeIndex,
    *,
    track: str,
    horizon_days: int,
    minimum_windows: int,
    event_gap_scope: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    column = {
        "strict_technology": "strict_technology_eligible",
        "technology_plus_adjacent": "technology_plus_adjacent_eligible",
    }.get(track)
    if not column or column not in universe:
        raise NdxCardinalityDiscoveryError(f"unknown or missing track: {track}")
    panel_mode = "membership_snapshot_date" in universe.columns
    global_snapshots = None
    if panel_mode:
        global_snapshots = pd.DatetimeIndex(pd.to_datetime(
            universe["membership_snapshot_date"], errors="coerce"
        )).normalize().unique().sort_values()
        if global_snapshots.hasnans or global_snapshots.empty:
            raise NdxCardinalityDiscoveryError("point-in-time taxonomy panel has invalid snapshots")
    work = universe.loc[universe[column].astype(str).str.lower().eq("true")].copy()
    required = {"ticker", "security_id", "issuer_id", "evidence_available_date", column}
    if panel_mode:
        required.add("membership_snapshot_date")
    missing = sorted(required - set(universe.columns))
    if missing:
        raise NdxCardinalityDiscoveryError(f"discovery universe columns missing: {missing}")
    if work.empty:
        raise NdxCardinalityDiscoveryError(f"eligible discovery track is empty: {track}")
    for key in ("ticker", "security_id", "issuer_id"):
        if work[key].isna().any() or work[key].astype(str).str.strip().eq("").any():
            raise NdxCardinalityDiscoveryError(f"eligible universe has blank {key}")
    if panel_mode:
        work["membership_snapshot_date"] = pd.to_datetime(
            work["membership_snapshot_date"], errors="coerce"
        ).dt.normalize()
        if work["membership_snapshot_date"].isna().any():
            raise NdxCardinalityDiscoveryError("eligible taxonomy panel has invalid snapshots")
        if work.duplicated(["security_id", "membership_snapshot_date"]).any():
            raise NdxCardinalityDiscoveryError("eligible taxonomy panel security snapshots must be unique")
    elif work["ticker"].duplicated().any() or work["security_id"].duplicated().any():
        raise NdxCardinalityDiscoveryError("eligible universe ticker/security_id must be unique")
    work["evidence_available_date"] = pd.to_datetime(
        work["evidence_available_date"], errors="coerce", utc=True
    ).dt.tz_convert(None).dt.normalize()
    if work["evidence_available_date"].isna().any():
        bad = work.loc[work["evidence_available_date"].isna(), "ticker"].astype(str).tolist()
        raise NdxCardinalityDiscoveryError(f"eligible rows missing evidence_available_date: {bad}")
    calendar = pd.DatetimeIndex(calendar_dates).normalize().unique().sort_values()
    gaps = pd.DataFrame(columns=[
        "case_id", "ticker", "blocked_selection_start", "blocked_selection_end",
        "status", "promotion_allowed", "evidence_match",
    ])
    if event_gap_scope is not None:
        gaps = event_gap_scope.copy()
        required_gap_columns = {
            "case_id", "ticker", "blocked_selection_start", "blocked_selection_end",
            "status", "promotion_allowed", "evidence_match",
        }
        missing_gaps = sorted(required_gap_columns - set(gaps.columns))
        if missing_gaps:
            raise NdxCardinalityDiscoveryError(f"event gap scope columns missing: {missing_gaps}")
        if gaps.empty:
            raise NdxCardinalityDiscoveryError("event gap scope is unexpectedly empty")
        for key in ("case_id", "ticker", "status"):
            if gaps[key].isna().any() or gaps[key].astype(str).str.strip().eq("").any():
                raise NdxCardinalityDiscoveryError(f"event gap scope has blank {key}")
        gaps["blocked_selection_start"] = pd.to_datetime(
            gaps["blocked_selection_start"], errors="coerce"
        ).dt.normalize()
        gaps["blocked_selection_end"] = pd.to_datetime(
            gaps["blocked_selection_end"], errors="coerce"
        ).dt.normalize()
        if gaps[["blocked_selection_start", "blocked_selection_end"]].isna().any().any():
            raise NdxCardinalityDiscoveryError("event gap scope has invalid blocked dates")
        if gaps["blocked_selection_start"].gt(gaps["blocked_selection_end"]).any():
            raise NdxCardinalityDiscoveryError("event gap scope start is after end")
        evidence_match = gaps["evidence_match"].astype(str).str.lower().eq("true")
        promotion_false = gaps["promotion_allowed"].astype(str).str.lower().eq("false")
        if not evidence_match.all() or not promotion_false.all():
            raise NdxCardinalityDiscoveryError("event gap scope safety disposition changed")
    rows = []
    for selection in selection_dates:
        selection = pd.Timestamp(selection).normalize()
        if selection not in calendar:
            raise NdxCardinalityDiscoveryError(f"selection date is not in calendar: {selection.date()}")
        pos = int(calendar.searchsorted(selection))
        maturity_pos = pos + int(horizon_days)
        matured = pos < len(calendar) and maturity_pos < len(calendar)
        membership_snapshot = None
        if panel_mode:
            prior_snapshots = global_snapshots[global_snapshots <= selection]
            membership_snapshot = prior_snapshots.max() if len(prior_snapshots) else None
            available = work.iloc[0:0] if membership_snapshot is None else work.loc[
                work["membership_snapshot_date"].eq(membership_snapshot)
                & work["evidence_available_date"].le(selection)
            ]
        else:
            available = work.loc[work["evidence_available_date"].le(selection)]
        active_gaps = gaps.loc[
            gaps["blocked_selection_start"].le(selection)
            & gaps["blocked_selection_end"].ge(selection)
        ]
        event_gap_blocked = not active_gaps.empty
        multiplicities = available.groupby("issuer_id")["security_id"].size().astype(int).tolist()
        max_count = len(multiplicities)
        counts = [1]
        for multiplicity in multiplicities:
            counts.append(0)
            for k in range(len(counts) - 1, 0, -1):
                counts[k] += counts[k - 1] * multiplicity
        rows.append({
            "universe_track": track,
            "selection_date": selection.date().isoformat(),
            "maturity_date": calendar[maturity_pos].date().isoformat() if matured else None,
            "matured_horizon": matured,
            "event_gap_blocked": event_gap_blocked,
            "event_gap_case_ids": ";".join(sorted(active_gaps["case_id"].astype(str))),
            "event_gap_tickers": ";".join(sorted(active_gaps["ticker"].astype(str).unique())),
            "membership_window_eligible": bool(matured and not event_gap_blocked),
            "horizon_trading_days": int(horizon_days),
            "membership_snapshot_date": (
                membership_snapshot.date().isoformat() if membership_snapshot is not None else None
            ),
            "membership_snapshot_age_days": (
                int((selection - membership_snapshot).days) if membership_snapshot is not None else None
            ),
            "available_security_count": len(available),
            "available_issuer_count": max_count,
            "available_tickers": ";".join(sorted(available["ticker"].astype(str))),
            "issuer_dedup_combinations_by_k": ";".join(
                f"{k}:{counts[k]}" for k in range(1, len(counts))
            ),
            "status": (
                "NOT_MATURE" if not matured else
                "EVENT_GAP_BLOCKED_NOT_TRAINING_ELIGIBLE" if event_gap_blocked else
                "POINT_IN_TIME_DISCOVERY_WINDOW"
            ),
        })
    windows = pd.DataFrame(rows)
    max_k = int(windows["available_issuer_count"].max()) if not windows.empty else 0
    coverage = []
    for k in range(1, max_k + 1):
        raw_eligible_windows = windows.loc[
            windows["matured_horizon"] & windows["available_issuer_count"].ge(k)
        ]
        eligible_windows = raw_eligible_windows.loc[raw_eligible_windows["membership_window_eligible"]]
        coverage.append({
            "universe_track": track,
            "holding_count": k,
            "mature_window_count": len(eligible_windows),
            "raw_mature_window_count_before_event_gap_exclusion": len(raw_eligible_windows),
            "event_gap_blocked_mature_window_count": int(raw_eligible_windows["event_gap_blocked"].sum()),
            "minimum_required_windows": int(minimum_windows),
            "training_evaluation_ready": len(eligible_windows) >= int(minimum_windows),
            "first_eligible_selection_date": (
                eligible_windows["selection_date"].min() if not eligible_windows.empty else None
            ),
            "status": (
                "TRAINING_WINDOW_COUNT_READY" if len(eligible_windows) >= int(minimum_windows)
                else "INSUFFICIENT_POINT_IN_TIME_WINDOWS"
            ),
            "promotion_allowed": False,
        })
    return windows, pd.DataFrame(coverage)


def build_training_job_plan(
    memberships: pd.DataFrame,
    windows: pd.DataFrame,
    coverage: pd.DataFrame,
    *,
    exact_limit: int,
) -> pd.DataFrame:
    """Create immutable dry-run coordinates without reading return data."""
    if exact_limit <= 0:
        raise NdxCardinalityDiscoveryError("exact enumeration limit must be positive")
    membership_required = {
        "universe_track", "selection_date", "ticker", "security_id", "issuer_id",
        "risk_chain", "membership_window_eligible",
    }
    missing = sorted(membership_required - set(memberships.columns))
    if missing:
        raise NdxCardinalityDiscoveryError(f"job-plan membership columns missing: {missing}")
    ready = coverage.loc[coverage["training_evaluation_ready"].astype(bool), [
        "universe_track", "holding_count",
    ]].copy()
    mature = windows.loc[
        windows["membership_window_eligible"].astype(bool),
        ["universe_track", "selection_date"],
    ].drop_duplicates()
    eligible = memberships.loc[memberships["membership_window_eligible"].astype(bool)].copy()
    eligible = eligible.merge(mature, on=["universe_track", "selection_date"], validate="many_to_one")
    rows = []
    for (track, selection), active in eligible.groupby(
        ["universe_track", "selection_date"], sort=True
    ):
        if active["security_id"].duplicated().any():
            raise NdxCardinalityDiscoveryError("job-plan active security ids are not unique")
        active = active.sort_values(["issuer_id", "security_id"]).reset_index(drop=True)
        membership_payload = active[[
            "ticker", "security_id", "issuer_id", "risk_chain",
        ]].to_dict("records")
        membership_sha256 = _canonical_sha256({"members": membership_payload})
        ready_k = ready.loc[ready["universe_track"].eq(track), "holding_count"].astype(int)
        max_issuers = int(active["issuer_id"].nunique())
        for holding_count in sorted(k for k in ready_k.tolist() if k <= max_issuers):
            feasible = issuer_dedup_feasible_count(active, holding_count)
            raw = math.comb(len(active), holding_count)
            coordinate = validate_checkpoint_coordinate({
                "universe_track": str(track),
                "selection_date": str(selection),
                "holding_count": int(holding_count),
                "shard_id": "0000",
            })
            rows.append({
                **coordinate,
                "coordinate_sha256": _canonical_sha256(coordinate),
                "membership_sha256": membership_sha256,
                "available_security_count": len(active),
                "available_issuer_count": max_issuers,
                "raw_security_combinations": raw,
                "issuer_dedup_feasible_combinations": feasible,
                "issuer_pruned_combinations": raw - feasible,
                "planned_search_method": (
                    "EXACT_ENUMERATION" if feasible <= exact_limit
                    else "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"
                ),
                "return_data_read": False,
                "execution_status": "DRY_RUN_BLOCKED_HISTORICAL_MEMBERSHIP_SEMANTICS",
                "promotion_allowed": False,
            })
    columns = [
        "universe_track", "selection_date", "holding_count", "shard_id",
        "coordinate_sha256", "membership_sha256", "available_security_count",
        "available_issuer_count", "raw_security_combinations",
        "issuer_dedup_feasible_combinations", "issuer_pruned_combinations",
        "planned_search_method", "return_data_read", "execution_status",
        "promotion_allowed",
    ]
    return pd.DataFrame(rows, columns=columns)


def verify_plan_bundle(plan_manifest_path: Path, universe_path: Path, base_plan_id: str) -> dict[str, Any]:
    manifest = json.loads(plan_manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_type") != "ndx_variable_cardinality_search_plan":
        raise NdxCardinalityDiscoveryError("unexpected base plan manifest type")
    if manifest.get("plan_id") != base_plan_id:
        raise NdxCardinalityDiscoveryError("base plan id mismatch")
    artifact = (manifest.get("artifacts") or {}).get("universe") or {}
    if artifact.get("sha256") != file_sha256(universe_path):
        raise NdxCardinalityDiscoveryError("base universe hash mismatch")
    if manifest.get("fresh_oos_consumed") is not False:
        raise NdxCardinalityDiscoveryError("base plan unexpectedly consumed fresh OOS")
    return manifest


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def synthetic_fixture(*, seed: int, business_days: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, list[str]]:
    """Create deterministic returns with one duplicate issuer and two risk chains."""
    if business_days < 160:
        raise NdxCardinalityDiscoveryError("synthetic fixture needs at least 160 business days")
    universe = pd.DataFrame([
        {"ticker": "ALFA", "security_id": "s1", "issuer_id": "i1", "risk_chain": "compute", "synthetic_price": 210.0, "median_dollar_volume_usd": 500_000_000.0},
        {"ticker": "ALFB", "security_id": "s2", "issuer_id": "i1", "risk_chain": "compute", "synthetic_price": 205.0, "median_dollar_volume_usd": 450_000_000.0},
        {"ticker": "BETA", "security_id": "s3", "issuer_id": "i2", "risk_chain": "compute", "synthetic_price": 480.0, "median_dollar_volume_usd": 300_000_000.0},
        {"ticker": "GAMM", "security_id": "s4", "issuer_id": "i3", "risk_chain": "software", "synthetic_price": 160.0, "median_dollar_volume_usd": 250_000_000.0},
        {"ticker": "DELT", "security_id": "s5", "issuer_id": "i4", "risk_chain": "software", "synthetic_price": 90.0, "median_dollar_volume_usd": 100_000_000.0},
        {"ticker": "EPSI", "security_id": "s6", "issuer_id": "i5", "risk_chain": "network", "synthetic_price": 140.0, "median_dollar_volume_usd": 80_000_000.0},
    ])
    rng = np.random.default_rng(int(seed))
    dates = pd.bdate_range("2020-01-02", periods=int(business_days))
    market = rng.normal(0.00045, 0.011, len(dates))
    compute = rng.normal(0.00020, 0.006, len(dates))
    software = rng.normal(0.00015, 0.005, len(dates))
    idio = rng.normal(0.0, 0.006, (len(dates), len(universe)))
    drifts = np.asarray([0.00035, 0.00025, 0.00030, 0.00018, 0.00012, 0.00022])
    betas = np.asarray([1.20, 1.10, 1.05, 0.85, 0.75, 0.95])
    values = market[:, None] * betas + idio + drifts
    values[:, :3] += compute[:, None]
    values[:, 3:5] += software[:, None]
    returns = pd.DataFrame(values, index=dates, columns=universe["ticker"])
    target = returns[["ALFA", "GAMM", "EPSI"]].mul([0.35, 0.40, 0.25]).sum(axis=1)
    incumbent = ["ALFA", "BETA", "GAMM"]
    return universe, returns, target.rename("012922_SYNTHETIC"), incumbent


def issuer_dedup_feasible_count(universe: pd.DataFrame, holding_count: int) -> int:
    multiplicities = universe.groupby("issuer_id")["security_id"].size().astype(int).tolist()
    dp = [1]
    for multiplicity in multiplicities:
        dp.append(0)
        for k in range(len(dp) - 1, 0, -1):
            dp[k] += dp[k - 1] * multiplicity
    return int(dp[holding_count]) if 0 <= holding_count < len(dp) else 0


def _issuer_unique(combo: tuple[str, ...], issuer_by_ticker: Mapping[str, str]) -> bool:
    issuers = [issuer_by_ticker[ticker] for ticker in combo]
    return len(issuers) == len(set(issuers))


def _window_metrics(
    series: pd.Series, window_days: int, step_days: int, *, entry_cost: float = 0.0,
) -> tuple[list[float], list[float]]:
    if window_days <= 0 or step_days <= 0 or not 0.0 <= entry_cost < 1.0:
        raise NdxCardinalityDiscoveryError("window/step/cost inputs are invalid")
    numeric = series.astype(float)
    if not np.isfinite(numeric.to_numpy()).all() or bool((numeric <= -1.0).any()):
        raise NdxCardinalityDiscoveryError("return series must be finite and greater than -100%")
    annualized: list[float] = []
    drawdowns: list[float] = []
    for start in range(0, len(series) - window_days + 1, step_days):
        values = numeric.iloc[start:start + window_days].copy()
        values.iloc[0] = (1.0 + values.iloc[0]) * (1.0 - entry_cost) - 1.0
        path = (1.0 + values).cumprod().to_numpy(dtype=float)
        nav = pd.Series(np.concatenate(([1.0], path)))
        annualized.append(float(nav.iloc[-1] ** (252.0 / len(values)) - 1.0))
        drawdowns.append(float((1.0 - nav / nav.cummax()).max()))
    if not annualized:
        raise NdxCardinalityDiscoveryError("synthetic evaluation has no rolling windows")
    return annualized, drawdowns


def constrained_fixed_shrinkage_weights(
    history: pd.DataFrame,
    combo: tuple[str, ...],
    *,
    shrinkage_intensity: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_by_ticker: Mapping[str, str] | None = None,
    risk_chain_top1_cap: float = 1.0,
    anchor_weights: pd.Series | None = None,
    turnover_anchor_strength: float = 0.0,
) -> pd.Series:
    """Fit one pre-registered diagonal-shrinkage minimum-variance weight vector."""
    if not combo or len(set(combo)) != len(combo):
        raise NdxCardinalityDiscoveryError("shrinkage combo must be non-empty and unique")
    if any(ticker not in history.columns for ticker in combo):
        raise NdxCardinalityDiscoveryError("shrinkage history is missing a portfolio ticker")
    values = history[list(combo)].astype(float)
    if len(values) < max(20, len(combo) * 3):
        raise NdxCardinalityDiscoveryError("shrinkage fit history is too short")
    if not np.isfinite(values.to_numpy()).all():
        raise NdxCardinalityDiscoveryError("shrinkage history must be finite")
    if len(combo) == 1:
        result = pd.Series([1.0], index=list(combo), dtype=float)
        result.attrs["risk_chain_projection_relaxed"] = float(risk_chain_top1_cap) < 1.0
        return result
    intensity = float(shrinkage_intensity)
    if not 0.0 <= intensity <= 1.0:
        raise NdxCardinalityDiscoveryError("shrinkage intensity must be in [0,1]")
    sample = np.atleast_2d(np.cov(values.to_numpy(), rowvar=False, ddof=1))
    diagonal = np.diag(np.diag(sample))
    covariance = (1.0 - intensity) * sample + intensity * diagonal
    if not np.isfinite(covariance).all():
        raise NdxCardinalityDiscoveryError("shrunk covariance is not finite")
    raw = np.linalg.pinv(covariance, hermitian=True) @ np.ones(len(combo), dtype=float)
    raw = np.clip(raw, 0.0, None)
    if float(raw.sum()) <= 0:
        raw = np.ones(len(combo), dtype=float)
    raw_series = pd.Series(raw, index=list(combo), dtype=float)
    anchor_strength = float(turnover_anchor_strength)
    if not 0.0 <= anchor_strength <= 1.0:
        raise NdxCardinalityDiscoveryError("turnover anchor strength must be in [0,1]")
    if anchor_strength > 0.0:
        if anchor_weights is None:
            anchor = pd.Series(1.0 / len(combo), index=list(combo), dtype=float)
        else:
            anchor = anchor_weights.reindex(list(combo), fill_value=0.0).astype(float)
            if not np.isfinite(anchor.to_numpy()).all() or bool((anchor < 0).any()):
                raise NdxCardinalityDiscoveryError("turnover anchor weights are invalid")
            if float(anchor.sum()) <= 0:
                anchor = pd.Series(1.0 / len(combo), index=list(combo), dtype=float)
            else:
                anchor = anchor / float(anchor.sum())
        raw_series = (
            (1.0 - anchor_strength) * (raw_series / float(raw_series.sum()))
            + anchor_strength * anchor
        )
    top_count = min(3, len(combo) - 1)
    effective_floor = max(1.0, float(minimum_effective_n_ratio) * len(combo))
    feasible_top_cap = max(float(top_weight_cap), top_count / len(combo))
    group_labels = None
    declared_risk_cap = float(risk_chain_top1_cap)
    if not 0.0 < declared_risk_cap <= 1.0:
        raise NdxCardinalityDiscoveryError("risk-chain Top1 cap must be in (0,1]")
    if risk_chain_by_ticker is not None:
        group_labels = {ticker: str(risk_chain_by_ticker.get(ticker) or "") for ticker in combo}
        if any(not label.strip() for label in group_labels.values()):
            raise NdxCardinalityDiscoveryError("risk-chain label is missing for shrinkage projection")
    # A declared single-name cap below 1 / k is structurally impossible.  Keep
    # the declared cap in the result audit, but use the smallest mathematically
    # feasible cap for projection so small-k research rows can be evaluated and
    # then explicitly marked as failing the declared constraint.
    projection_kwargs = dict(
        max_weight=max(float(max_single_weight), 1.0 / len(combo)),
        min_weight=float(min_single_weight),
        top_weight_count=top_count,
        top_weight_cap=feasible_top_cap,
        min_effective_n=effective_floor,
    )
    try:
        result = project_concentration_envelope_weights(
            raw_series,
            **projection_kwargs,
            group_labels=group_labels,
            max_group_weight=declared_risk_cap if group_labels is not None else None,
        )
        result.attrs["risk_chain_projection_relaxed"] = False
        return result
    except ValueError as risk_exc:
        if group_labels is None:
            raise NdxCardinalityDiscoveryError(f"shrinkage concentration projection failed: {risk_exc}") from risk_exc
        try:
            result = project_concentration_envelope_weights(raw_series, **projection_kwargs)
        except ValueError as base_exc:
            raise NdxCardinalityDiscoveryError(
                f"shrinkage concentration projection failed: {base_exc}"
            ) from base_exc
        result.attrs["risk_chain_projection_relaxed"] = True
        return result


def evaluate_synthetic_portfolio(
    combo: tuple[str, ...], universe: pd.DataFrame, returns: pd.DataFrame,
    target: pd.Series, incumbent: list[str], *, window_days: int,
    step_days: int, transaction_cost_bps: float,
    weight_spec: str = "equal_weight", fit_days: int = 63,
    shrinkage_intensity: float = 0.35, max_single_weight: float = 0.45,
    min_single_weight: float = 0.05, top_weight_cap: float = 0.80,
    minimum_effective_n_ratio: float = 0.70,
    risk_chain_top1_cap: float = 0.55,
    turnover_anchor_strength: float = 0.25,
    portfolio_cash_usd: float = 5000.0,
    minimum_cash_buffer_usd: float = 100.0,
    minimum_median_dollar_volume_usd: float = 50_000_000.0,
    incumbent_weights: Mapping[str, float] | None = None,
    execution_prices: pd.DataFrame | None = None,
) -> dict[str, Any]:
    if not combo or len(set(combo)) != len(combo):
        raise NdxCardinalityDiscoveryError("portfolio combo must contain unique tickers")
    issuer_by_ticker = universe.set_index("ticker")["issuer_id"].astype(str).to_dict()
    if not _issuer_unique(combo, issuer_by_ticker):
        raise NdxCardinalityDiscoveryError("portfolio combo contains duplicate issuer")
    if weight_spec not in {
        "equal_weight", "constrained_fixed_shrinkage",
        "constrained_fixed_shrinkage_turnover_anchor",
    }:
        raise NdxCardinalityDiscoveryError(f"unknown synthetic weight spec: {weight_spec}")
    if not returns.index.equals(target.index):
        raise NdxCardinalityDiscoveryError("synthetic target/return indexes must match")
    if fit_days <= 0 or len(returns) < fit_days + window_days:
        raise NdxCardinalityDiscoveryError("synthetic fit/evaluation range is too short")
    if not 0.0 < float(risk_chain_top1_cap) <= 1.0:
        raise NdxCardinalityDiscoveryError("risk-chain Top1 cap must be in (0,1]")
    if not 0.0 <= float(turnover_anchor_strength) <= 1.0:
        raise NdxCardinalityDiscoveryError("turnover anchor strength must be in [0,1]")
    cash = float(portfolio_cash_usd)
    cash_buffer = float(minimum_cash_buffer_usd)
    if not np.isfinite(cash) or not np.isfinite(cash_buffer) or cash <= 0 or not 0 <= cash_buffer < cash:
        raise NdxCardinalityDiscoveryError("synthetic whole-lot cash contract is invalid")
    required_execution_columns = {"synthetic_price", "median_dollar_volume_usd"}
    if not required_execution_columns.issubset(universe.columns):
        raise NdxCardinalityDiscoveryError("synthetic execution columns are missing")
    price_by_ticker = universe.set_index("ticker")["synthetic_price"].astype(float).to_dict()
    liquidity_by_ticker = universe.set_index("ticker")["median_dollar_volume_usd"].astype(float).to_dict()
    if any(not np.isfinite(price_by_ticker[ticker]) or price_by_ticker[ticker] <= 0 for ticker in combo):
        raise NdxCardinalityDiscoveryError("synthetic prices must be finite and positive")
    if any(not np.isfinite(liquidity_by_ticker[ticker]) or liquidity_by_ticker[ticker] <= 0 for ticker in combo):
        raise NdxCardinalityDiscoveryError("synthetic liquidity must be finite and positive")
    if execution_prices is not None:
        if not set(combo).issubset(execution_prices.columns):
            raise NdxCardinalityDiscoveryError("whole-lot execution price columns are missing")
        aligned_execution_prices = execution_prices.loc[:, list(combo)].copy()
        if (
            aligned_execution_prices.empty
            or aligned_execution_prices.isna().any().any()
            or (~np.isfinite(aligned_execution_prices)).any().any()
            or (aligned_execution_prices <= 0).any().any()
        ):
            raise NdxCardinalityDiscoveryError("whole-lot execution prices are invalid")
    else:
        aligned_execution_prices = None
    if incumbent_weights is None:
        normalized_incumbent_weights = {ticker: 1.0 / len(incumbent) for ticker in incumbent}
    else:
        normalized_incumbent_weights = {
            ticker: float(incumbent_weights.get(ticker, 0.0)) for ticker in incumbent
        }
        if any(not np.isfinite(value) or value < 0 for value in normalized_incumbent_weights.values()):
            raise NdxCardinalityDiscoveryError("incumbent weights are invalid")
        total_incumbent_weight = sum(normalized_incumbent_weights.values())
        if total_incumbent_weight <= 0:
            raise NdxCardinalityDiscoveryError("incumbent weights sum must be positive")
        normalized_incumbent_weights = {
            ticker: value / total_incumbent_weight
            for ticker, value in normalized_incumbent_weights.items()
        }
    chain_by_ticker = universe.set_index("ticker")["risk_chain"].astype(str).to_dict()
    c_ret: list[float] = []
    c_dd: list[float] = []
    i_ret: list[float] = []
    i_dd: list[float] = []
    t_ret: list[float] = []
    t_dd: list[float] = []
    turnovers: list[float] = []
    costs: list[float] = []
    effective_names: list[float] = []
    chain_top1_values: list[float] = []
    chain_top3_values: list[float] = []
    issuer_top1_values: list[float] = []
    weight_top1_values: list[float] = []
    weight_top3_values: list[float] = []
    risk_chain_projection_relaxed: list[bool] = []
    whole_lot_executable: list[bool] = []
    whole_lot_min_shares: list[int] = []
    whole_lot_residual_cash: list[float] = []
    last_weights: pd.Series | None = None
    rebalance_schedule: list[tuple[pd.Timestamp, dict[str, float]]] = []
    execution_path_end: pd.Timestamp | None = None
    fit_eval_audit: list[str] = []
    fit_before_flags: list[bool] = []
    for start in range(fit_days, len(returns) - window_days + 1, step_days):
        history = returns.iloc[start - fit_days:start]
        if weight_spec == "equal_weight":
            weights = pd.Series(1.0 / len(combo), index=list(combo), dtype=float)
            projection_relaxed = False
        else:
            anchored = weight_spec == "constrained_fixed_shrinkage_turnover_anchor"
            weights = constrained_fixed_shrinkage_weights(
                history, combo,
                shrinkage_intensity=shrinkage_intensity,
                max_single_weight=max_single_weight,
                min_single_weight=min_single_weight,
                top_weight_cap=top_weight_cap,
                minimum_effective_n_ratio=minimum_effective_n_ratio,
                risk_chain_by_ticker=chain_by_ticker,
                risk_chain_top1_cap=risk_chain_top1_cap,
                anchor_weights=last_weights if anchored else None,
                turnover_anchor_strength=turnover_anchor_strength if anchored else 0.0,
            )
            projection_relaxed = bool(weights.attrs.get("risk_chain_projection_relaxed", False))
        candidate_weights = weights.to_dict()
        reference_weights = normalized_incumbent_weights if last_weights is None else last_weights.to_dict()
        turnover = 0.5 * sum(
            abs(candidate_weights.get(ticker, 0.0) - reference_weights.get(ticker, 0.0))
            for ticker in set(candidate_weights) | set(reference_weights)
        )
        transaction_cost = float(turnover * transaction_cost_bps / 10000.0)
        forward = returns.iloc[start:start + window_days]
        investable_cash = cash - cash_buffer
        window_price_by_ticker = price_by_ticker
        if aligned_execution_prices is not None:
            rebalance_date = forward.index[0]
            if rebalance_date not in aligned_execution_prices.index:
                raise NdxCardinalityDiscoveryError("rebalance date missing from execution prices")
            window_price_by_ticker = {
                ticker: float(aligned_execution_prices.loc[rebalance_date, ticker])
                for ticker in combo
            }
        shares = {
            ticker: int(math.floor(investable_cash * float(weights[ticker]) / window_price_by_ticker[ticker]))
            for ticker in combo
        }
        invested = sum(shares[ticker] * window_price_by_ticker[ticker] for ticker in combo)
        whole_lot_executable.append(all(value >= 1 for value in shares.values()))
        whole_lot_min_shares.append(min(shares.values()))
        whole_lot_residual_cash.append(cash - invested)
        candidate_series = forward[list(combo)].mul(weights, axis=1).sum(axis=1)
        incumbent_series = forward[incumbent].mul(
            pd.Series(normalized_incumbent_weights), axis=1
        ).sum(axis=1)
        target_series = target.iloc[start:start + window_days]
        cr, cd = _window_metrics(candidate_series, window_days, window_days, entry_cost=transaction_cost)
        ir, idd = _window_metrics(incumbent_series, window_days, window_days)
        tr, td = _window_metrics(target_series, window_days, window_days)
        c_ret.extend(cr); c_dd.extend(cd); i_ret.extend(ir); i_dd.extend(idd); t_ret.extend(tr); t_dd.extend(td)
        turnovers.append(turnover); costs.append(transaction_cost)
        risk_chain_projection_relaxed.append(projection_relaxed)
        effective_names.append(float(1.0 / np.square(weights.to_numpy()).sum()))
        ordered_security_weights = sorted(weights.to_numpy(dtype=float), reverse=True)
        weight_top1_values.append(float(ordered_security_weights[0]))
        weight_top3_values.append(float(sum(ordered_security_weights[:3])))
        chain_weights: dict[str, float] = {}
        issuer_weights: dict[str, float] = {}
        for ticker, weight in candidate_weights.items():
            chain = chain_by_ticker[ticker]
            issuer = issuer_by_ticker[ticker]
            chain_weights[chain] = chain_weights.get(chain, 0.0) + float(weight)
            issuer_weights[issuer] = issuer_weights.get(issuer, 0.0) + float(weight)
        chain_values = sorted(chain_weights.values(), reverse=True)
        chain_top1_values.append(chain_values[0])
        chain_top3_values.append(float(sum(chain_values[:3])))
        issuer_top1_values.append(max(issuer_weights.values()))
        fit_eval_audit.append(
            f"{history.index[-1].date().isoformat()}<{forward.index[0].date().isoformat()}"
        )
        fit_before_flags.append(bool(history.index[-1] < forward.index[0]))
        rebalance_schedule.append((forward.index[0], candidate_weights))
        execution_path_end = forward.index[-1]
        last_weights = weights
    if last_weights is None:
        raise NdxCardinalityDiscoveryError("synthetic evaluation produced no fitted windows")
    return_p50 = float(np.quantile(c_ret, 0.50))
    return_p10 = float(np.quantile(c_ret, 0.10))
    dd_p50 = float(np.quantile(c_dd, 0.50))
    dd_p90 = float(np.quantile(c_dd, 0.90))
    target_return_p50 = float(np.quantile(t_ret, 0.50))
    target_return_p10 = float(np.quantile(t_ret, 0.10))
    target_dd_p50 = float(np.quantile(t_dd, 0.50))
    target_dd_p90 = float(np.quantile(t_dd, 0.90))
    chain_top1_p50 = float(np.quantile(chain_top1_values, 0.50))
    chain_top1_p90 = float(np.quantile(chain_top1_values, 0.90))
    chain_top3_p50 = float(np.quantile(chain_top3_values, 0.50))
    chain_top3_p90 = float(np.quantile(chain_top3_values, 0.90))
    effective_n_min = float(np.min(effective_names))
    effective_n_p10 = float(np.quantile(effective_names, 0.10))
    effective_n_p50 = float(np.quantile(effective_names, 0.50))
    declared_max_passed = float(np.max(issuer_top1_values)) <= float(max_single_weight) + 1e-9
    weight_top3_max = float(np.max(weight_top3_values))
    declared_top3_passed = weight_top3_max <= float(top_weight_cap) + 1e-9
    declared_risk_chain_passed = float(np.max(chain_top1_values)) <= float(risk_chain_top1_cap) + 1e-9
    declared_effective_passed = effective_n_min >= float(minimum_effective_n_ratio) * len(combo) - 1e-9
    liquidity_passed = min(liquidity_by_ticker[ticker] for ticker in combo) >= float(minimum_median_dollar_volume_usd)
    whole_lot_summary: dict[str, Any] = {
        "whole_lot_execution_mode": "FIXED_SELECTION_PRICE_INDEPENDENT_WINDOWS",
    }
    whole_lot_passed = all(whole_lot_executable)
    if aligned_execution_prices is not None:
        assert execution_path_end is not None
        execution_path = aligned_execution_prices.loc[
            rebalance_schedule[0][0]:execution_path_end, list(combo)
        ]
        whole_lot_summary, _ = simulate_continuous_whole_lot_rebalance(
            execution_path,
            rebalance_schedule,
            risk_chain_by_ticker=chain_by_ticker,
            portfolio_cash_usd=cash,
            minimum_cash_buffer_usd=cash_buffer,
            transaction_cost_bps=transaction_cost_bps,
            max_single_weight=max_single_weight,
            min_single_weight=min_single_weight,
            top_weight_cap=top_weight_cap,
            minimum_effective_n_ratio=minimum_effective_n_ratio,
            risk_chain_top1_cap=risk_chain_top1_cap,
        )
        whole_lot_passed = bool(
            whole_lot_summary["whole_lot_cash_buffer_preserved"]
            and whole_lot_summary["whole_lot_constraints_preserved_all_days"]
            and all(whole_lot_executable)
        )
    failures = []
    if not declared_max_passed:
        failures.append("DECLARED_MAX_SINGLE_WEIGHT_FAILED")
    if not declared_top3_passed:
        failures.append("DECLARED_SECURITY_TOP3_WEIGHT_FAILED")
    if not declared_risk_chain_passed:
        failures.append("DECLARED_RISK_CHAIN_TOP1_WEIGHT_FAILED")
    if not declared_effective_passed:
        failures.append("DECLARED_EFFECTIVE_N_FAILED")
    if not liquidity_passed:
        failures.append("MINIMUM_MEDIAN_DOLLAR_VOLUME_FAILED")
    if not whole_lot_passed:
        failures.append("WHOLE_LOT_EXECUTABILITY_FAILED")
    return {
        "portfolio_id": hashlib.sha256((weight_spec + "|" + ";".join(combo)).encode("utf-8")).hexdigest()[:16],
        "holding_count": len(combo),
        "weight_spec": weight_spec,
        "tickers": ";".join(combo),
        "weights": ";".join(f"{ticker}:{last_weights[ticker]:.10f}" for ticker in combo),
        "rolling_fit_window_count": len(c_ret),
        "fit_strictly_before_evaluation": all(fit_before_flags),
        "last_fit_evaluation_boundary": fit_eval_audit[-1],
        "return_p50": return_p50,
        "return_p10": return_p10,
        "max_drawdown_p50": dd_p50,
        "max_drawdown_p90": dd_p90,
        "paired_return_p50_vs_incumbent": float(np.quantile(np.asarray(c_ret) - np.asarray(i_ret), 0.50)),
        "paired_return_p10_vs_incumbent": float(np.quantile(np.asarray(c_ret) - np.asarray(i_ret), 0.10)),
        "paired_drawdown_cost_p50_vs_incumbent": float(np.quantile(np.asarray(c_dd) - np.asarray(i_dd), 0.50)),
        "paired_drawdown_cost_p90_vs_incumbent": float(np.quantile(np.asarray(c_dd) - np.asarray(i_dd), 0.90)),
        "return_p50_vs_012922": return_p50 - target_return_p50,
        "return_p10_vs_012922": return_p10 - target_return_p10,
        "max_drawdown_p50_vs_012922": dd_p50 - target_dd_p50,
        "max_drawdown_p90_vs_012922": dd_p90 - target_dd_p90,
        "target_012922_distance": abs(return_p50 - target_return_p50) + abs(return_p10 - target_return_p10) + abs(dd_p50 - target_dd_p50) + abs(dd_p90 - target_dd_p90),
        "risk_chain_top1": float(np.max(chain_top1_values)),
        "risk_chain_top1_p50": chain_top1_p50,
        "risk_chain_top1_p90": chain_top1_p90,
        "risk_chain_top3": float(np.max(chain_top3_values)),
        "risk_chain_top3_p50": chain_top3_p50,
        "risk_chain_top3_p90": chain_top3_p90,
        "issuer_top1": float(np.max(issuer_top1_values)),
        "weight_top1_p50": float(np.quantile(weight_top1_values, 0.50)),
        "weight_top1_p90": float(np.quantile(weight_top1_values, 0.90)),
        "weight_top3_p50": float(np.quantile(weight_top3_values, 0.50)),
        "weight_top3_p90": float(np.quantile(weight_top3_values, 0.90)),
        "weight_top3_max": weight_top3_max,
        "effective_n": effective_n_p50,
        "effective_n_min": effective_n_min,
        "effective_n_p10": effective_n_p10,
        "effective_n_p50": effective_n_p50,
        "declared_max_single_weight": float(max_single_weight),
        "effective_max_single_weight": max(float(max_single_weight), 1.0 / len(combo)),
        "structural_single_cap_relaxation": 1.0 / len(combo) > float(max_single_weight),
        "declared_max_single_passed": declared_max_passed,
        "declared_security_top3_weight_cap": float(top_weight_cap),
        "declared_security_top3_weight_passed": declared_top3_passed,
        "declared_risk_chain_top1_weight_cap": float(risk_chain_top1_cap),
        "declared_risk_chain_top1_weight_passed": declared_risk_chain_passed,
        "risk_chain_projection_relaxed_any_window": any(risk_chain_projection_relaxed),
        "declared_minimum_effective_n": float(minimum_effective_n_ratio) * len(combo),
        "declared_effective_n_passed": declared_effective_passed,
        "declared_constraints_passed": not failures,
        "constraint_failure_reasons": ";".join(failures),
        "turnover": float(np.quantile(turnovers, 0.50)),
        "initial_turnover": float(turnovers[0]),
        "initial_transaction_cost": float(costs[0]),
        "ongoing_rebalance_turnover_p50": (
            float(np.quantile(turnovers[1:], 0.50)) if len(turnovers) > 1 else 0.0
        ),
        "turnover_p90": float(np.quantile(turnovers, 0.90)),
        "turnover_max": float(np.max(turnovers)),
        "turnover_reference": "INCUMBENT_FIRST_WINDOW_THEN_PREVIOUS_REBALANCE",
        "turnover_regularization": (
            "L2_PREVIOUS_WEIGHT_ANCHOR" if weight_spec == "constrained_fixed_shrinkage_turnover_anchor"
            else "NONE"
        ),
        "turnover_anchor_strength": (
            float(turnover_anchor_strength)
            if weight_spec == "constrained_fixed_shrinkage_turnover_anchor" else 0.0
        ),
        "transaction_cost": float(np.quantile(costs, 0.50)),
        "return_basis": "NET_OF_MODELED_ENTRY_TURNOVER_COST",
        "minimum_median_dollar_volume_usd": float(minimum_median_dollar_volume_usd),
        "portfolio_min_median_dollar_volume_usd": min(liquidity_by_ticker[ticker] for ticker in combo),
        "liquidity_constraint_passed": liquidity_passed,
        "portfolio_cash_usd": cash,
        "minimum_cash_buffer_usd": cash_buffer,
        "whole_lot_executable_all_windows": whole_lot_passed,
        "whole_lot_min_shares": min(whole_lot_min_shares),
        "whole_lot_residual_cash_p50": float(np.quantile(whole_lot_residual_cash, 0.50)),
        "whole_lot_executability": whole_lot_summary["whole_lot_execution_mode"],
        **whole_lot_summary,
        "result_role": "SYNTHETIC_ENGINE_VALIDATION_ONLY",
        "promotion_allowed": False,
    }


def pareto_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool, index=frame.index)
    objectives = frame[["return_p50", "return_p10"]].to_numpy(dtype=float)
    costs = frame[[
        "max_drawdown_p50", "max_drawdown_p90", "target_012922_distance", "turnover"
    ]].to_numpy(dtype=float)
    if not np.isfinite(objectives).all() or not np.isfinite(costs).all():
        raise NdxCardinalityDiscoveryError("Pareto objectives must be finite")
    keep = np.ones(len(frame), dtype=bool)
    for i in range(len(frame)):
        if not keep[i]:
            continue
        better_or_equal = np.all(objectives >= objectives[i], axis=1) & np.all(costs <= costs[i], axis=1)
        strictly_better = np.any(objectives > objectives[i], axis=1) | np.any(costs < costs[i], axis=1)
        if bool(np.any(better_or_equal & strictly_better)):
            keep[i] = False
    return pd.Series(keep, index=frame.index)


def _frontier_tags(frame: pd.DataFrame) -> pd.Series:
    tags = {index: [] for index in frame.index}
    selectors = {
        "RETURN": frame["return_p50"].idxmax(),
        "BAD_TAIL": frame["return_p10"].idxmax(),
        "DRAWDOWN": frame["max_drawdown_p90"].idxmin(),
        "012922_DISTANCE": frame["target_012922_distance"].idxmin(),
    }
    for tag, index in selectors.items():
        tags[index].append(tag)
    for index in frame.index[pareto_mask(frame)]:
        tags[index].append("PARETO")
    return pd.Series({index: ";".join(values) for index, values in tags.items()})


def _partial_beam_objectives(
    combo: tuple[str, ...], returns: pd.DataFrame, target: pd.Series | None,
) -> dict[str, float]:
    """Point-in-time prefix proxies for a diverse approximate beam.

    These are heuristic fit-window objectives, not admissible mathematical
    bounds.  Keeping the label explicit prevents an approximation from being
    mistaken for branch-and-bound optimality evidence.
    """
    series = returns[list(combo)].mean(axis=1).astype(float)
    nav = (1.0 + series).cumprod()
    peak = nav.cummax()
    drawdown = float(((peak - nav) / peak).max())
    if target is None:
        target_series = pd.Series(0.0, index=series.index)
    else:
        target_series = pd.to_numeric(target.reindex(series.index), errors="coerce")
        if target_series.isna().any():
            raise NdxCardinalityDiscoveryError("bounded beam target fit window is incomplete")
    target_nav = (1.0 + target_series).cumprod()
    target_peak = target_nav.cummax()
    target_drawdown = float(((target_peak - target_nav) / target_peak).max())
    return {
        "RETURN": float(series.mean()),
        "BAD_TAIL": float(series.quantile(0.10)),
        "DRAWDOWN": drawdown,
        "012922_DISTANCE": (
            abs(float(nav.iloc[-1] - 1.0) - float(target_nav.iloc[-1] - 1.0))
            + abs(float(series.quantile(0.10)) - float(target_series.quantile(0.10)))
            + abs(drawdown - target_drawdown)
        ),
    }


def _multiobjective_partial_beam_order(
    combos: set[tuple[str, ...]],
    returns: pd.DataFrame,
    target: pd.Series | None,
) -> list[tuple[str, ...]]:
    """Round-robin four objective rankings with deterministic tie breaks."""
    scores = {
        combo: _partial_beam_objectives(combo, returns, target)
        for combo in sorted(combos)
    }
    rankings = {
        "RETURN": sorted(combos, key=lambda combo: (-scores[combo]["RETURN"], combo)),
        "BAD_TAIL": sorted(combos, key=lambda combo: (-scores[combo]["BAD_TAIL"], combo)),
        "DRAWDOWN": sorted(combos, key=lambda combo: (scores[combo]["DRAWDOWN"], combo)),
        "012922_DISTANCE": sorted(combos, key=lambda combo: (scores[combo]["012922_DISTANCE"], combo)),
    }
    ordered: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for rank in range(len(combos)):
        for objective in ("RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"):
            combo = rankings[objective][rank]
            if combo not in seen:
                ordered.append(combo)
                seen.add(combo)
        if len(ordered) == len(combos):
            break
    return ordered


def _issuer_unique_combos(universe: pd.DataFrame, holding_count: int) -> list[tuple[str, ...]]:
    groups = [
        tuple(sorted(group["ticker"].astype(str)))
        for _, group in universe.sort_values(["issuer_id", "ticker"], kind="stable").groupby("issuer_id", sort=True)
    ]
    combos: list[tuple[str, ...]] = []
    for selected_groups in itertools.combinations(groups, holding_count):
        for securities in itertools.product(*selected_groups):
            combos.append(tuple(sorted(securities)))
    return sorted(combos)


def _bounded_issuer_unique_beam_combos(
    universe: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    holding_count: int,
    beam_width: int,
    fit_days: int,
    target: pd.Series | None = None,
) -> tuple[list[tuple[str, ...]], int, int]:
    """Build a deterministic multiobjective beam with no optimality claim."""
    tickers = sorted(universe["ticker"].astype(str))
    issuer_by_ticker = universe.set_index("ticker")["issuer_id"].astype(str).to_dict()
    position_by_ticker = {ticker: index for index, ticker in enumerate(tickers)}
    level: list[tuple[str, ...]] = [tuple()]
    expanded = pruned = 0
    for depth in range(1, holding_count + 1):
        candidates: set[tuple[str, ...]] = set()
        remaining_needed = holding_count - depth
        for prefix in level:
            start = position_by_ticker[prefix[-1]] + 1 if prefix else 0
            for index in range(start, len(tickers)):
                ticker = tickers[index]
                combo = prefix + (ticker,)
                expanded += 1
                if not _issuer_unique(combo, issuer_by_ticker):
                    pruned += 1
                    continue
                used_issuers = {issuer_by_ticker[item] for item in combo}
                available_issuers = {
                    issuer_by_ticker[item]
                    for item in tickers[index + 1:]
                    if issuer_by_ticker[item] not in used_issuers
                }
                if len(available_issuers) < remaining_needed:
                    pruned += 1
                    continue
                candidates.add(combo)
        if not candidates:
            raise NdxCardinalityDiscoveryError(
                f"bounded beam has no completable issuer-unique prefixes at depth={depth} for k={holding_count}"
            )
        ordered = _multiobjective_partial_beam_order(
            candidates,
            returns.iloc[:fit_days],
            target.iloc[:fit_days] if target is not None else None,
        )
        if depth < holding_count and len(ordered) > int(beam_width):
            pruned += len(ordered) - int(beam_width)
            ordered = ordered[:int(beam_width)]
        level = ordered
    return level, expanded, pruned


def search_synthetic_cardinality(
    universe: pd.DataFrame, returns: pd.DataFrame, target: pd.Series,
    incumbent: list[str], *, holding_count: int, exact_limit: int,
    beam_width: int, window_days: int, step_days: int,
    transaction_cost_bps: float,
    weight_specs: tuple[str, ...] = ("equal_weight",),
    fit_days: int = 63, shrinkage_intensity: float = 0.35,
    max_single_weight: float = 0.45, min_single_weight: float = 0.05,
    top_weight_cap: float = 0.80, minimum_effective_n_ratio: float = 0.70,
    risk_chain_top1_cap: float = 0.55, turnover_anchor_strength: float = 0.25,
    portfolio_cash_usd: float = 5000.0, minimum_cash_buffer_usd: float = 100.0,
    minimum_median_dollar_volume_usd: float = 50_000_000.0,
    incumbent_weights: Mapping[str, float] | None = None,
    execution_prices: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not isinstance(holding_count, int) or holding_count <= 0:
        raise NdxCardinalityDiscoveryError("holding_count must be a positive integer")
    if exact_limit <= 0 or beam_width <= 0 or window_days <= 0 or step_days <= 0 or fit_days <= 0:
        raise NdxCardinalityDiscoveryError("search limits/windows must be positive")
    if len(returns) < fit_days + window_days:
        raise NdxCardinalityDiscoveryError("search fit/evaluation range is too short")
    if transaction_cost_bps < 0:
        raise NdxCardinalityDiscoveryError("transaction cost cannot be negative")
    if not weight_specs or any(
        spec not in {
            "equal_weight", "constrained_fixed_shrinkage",
            "constrained_fixed_shrinkage_turnover_anchor",
        } for spec in weight_specs
    ):
        raise NdxCardinalityDiscoveryError("synthetic weight specs are invalid")
    if "median_dollar_volume_usd" not in universe:
        raise NdxCardinalityDiscoveryError("synthetic universe liquidity column is missing")
    liquidity = pd.to_numeric(universe["median_dollar_volume_usd"], errors="coerce")
    if liquidity.isna().any() or bool((liquidity <= 0).any()):
        raise NdxCardinalityDiscoveryError("synthetic universe liquidity is invalid")
    theoretical = issuer_dedup_feasible_count(universe, holding_count)
    liquid_universe = universe.loc[liquidity.ge(float(minimum_median_dollar_volume_usd))].copy()
    liquidity_feasible = issuer_dedup_feasible_count(liquid_universe, holding_count)
    liquidity_pruned = theoretical - liquidity_feasible
    if liquidity_feasible <= 0:
        raise NdxCardinalityDiscoveryError(f"no issuer-unique portfolios for k={holding_count}")
    tickers = sorted(liquid_universe["ticker"].astype(str))
    issuer_by_ticker = liquid_universe.set_index("ticker")["issuer_id"].astype(str).to_dict()
    expanded = pruned = 0
    if liquidity_feasible <= int(exact_limit):
        combos = _issuer_unique_combos(liquid_universe, holding_count)
        expanded = len(combos)
        mode = "EXACT_ENUMERATION"
        exhaustive = True
    else:
        combos, expanded, pruned = _bounded_issuer_unique_beam_combos(
            liquid_universe, returns,
            holding_count=holding_count, beam_width=beam_width, fit_days=fit_days,
            target=target,
        )
        mode = "MULTIOBJECTIVE_DETERMINISTIC_BEAM_APPROXIMATION"
        exhaustive = len(combos) == liquidity_feasible
    rows = []
    for combo in combos:
        for weight_spec in weight_specs:
            rows.append(evaluate_synthetic_portfolio(
                combo, universe, returns, target, incumbent,
                window_days=window_days, step_days=step_days,
                transaction_cost_bps=transaction_cost_bps,
                weight_spec=weight_spec, fit_days=fit_days,
                shrinkage_intensity=shrinkage_intensity,
                max_single_weight=max_single_weight,
                min_single_weight=min_single_weight,
                top_weight_cap=top_weight_cap,
                minimum_effective_n_ratio=minimum_effective_n_ratio,
                risk_chain_top1_cap=risk_chain_top1_cap,
                turnover_anchor_strength=turnover_anchor_strength,
                portfolio_cash_usd=portfolio_cash_usd,
                minimum_cash_buffer_usd=minimum_cash_buffer_usd,
                minimum_median_dollar_volume_usd=minimum_median_dollar_volume_usd,
                incumbent_weights=incumbent_weights,
                execution_prices=execution_prices,
            ))
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise NdxCardinalityDiscoveryError(
            f"search produced no evaluated portfolios for k={holding_count}"
        )
    frame = frame.sort_values("portfolio_id", kind="stable").reset_index(drop=True)
    frame["frontier_tags"] = _frontier_tags(frame)
    frame["constrained_frontier_tags"] = ""
    compliant = frame["declared_constraints_passed"].astype(bool)
    if bool(compliant.any()):
        frame.loc[compliant, "constrained_frontier_tags"] = _frontier_tags(
            frame.loc[compliant]
        )
    frame["search_mode"] = mode
    frame["search_exhaustive"] = exhaustive
    audit = {
        "holding_count": holding_count,
        "theoretical_feasible_portfolios": theoretical,
        "liquidity_feasible_portfolios": liquidity_feasible,
        "liquidity_pruned_portfolios": liquidity_pruned,
        "expanded_nodes": expanded,
        "pruned_nodes": pruned,
        "fully_evaluated_portfolios": len(combos),
        "evaluated_security_sets": len(combos),
        "weight_specification_count": len(weight_specs),
        "evaluation_rows": len(frame),
        "unevaluated_feasible_portfolios": max(0, liquidity_feasible - len(combos)),
        "search_mode": mode,
        "search_exhaustive": exhaustive,
        "optimality_claim_allowed": bool(exhaustive),
        "bounded_prefix_objectives": (
            ["RETURN", "BAD_TAIL", "DRAWDOWN", "012922_DISTANCE"]
            if not exhaustive else []
        ),
        "mathematical_bound_certificate_available": False,
        "result_label": "SYNTHETIC_EXACT_FRONTIER" if exhaustive else "SYNTHETIC_CURRENT_SEARCHED_FRONTIER",
    }
    return frame, audit


def select_multifrontier_security_sets(
    equal_weight_results: pd.DataFrame,
    *,
    per_frontier_limit: int,
) -> pd.DataFrame:
    """Select a deterministic union of four objective-specific security sets."""
    required = {
        "tickers", "weight_spec", "return_p50", "return_p10",
        "max_drawdown_p90", "target_012922_distance",
    }
    if not required.issubset(equal_weight_results.columns):
        raise NdxCardinalityDiscoveryError("two-stage first-stage result columns are missing")
    if int(per_frontier_limit) <= 0:
        raise NdxCardinalityDiscoveryError("two-stage per-frontier limit must be positive")
    frame = equal_weight_results.loc[
        equal_weight_results["weight_spec"].eq("equal_weight")
    ].copy()
    if frame.empty or frame["tickers"].duplicated().any():
        raise NdxCardinalityDiscoveryError("two-stage first stage must have one row per security set")
    selectors = {
        "RETURN": ("return_p50", False),
        "BAD_TAIL": ("return_p10", False),
        "DRAWDOWN": ("max_drawdown_p90", True),
        "012922_DISTANCE": ("target_012922_distance", True),
    }
    tags: dict[str, list[str]] = {}
    limit = int(per_frontier_limit)
    for role, (column, ascending) in selectors.items():
        selected = frame.sort_values(
            [column, "tickers"], ascending=[ascending, True], kind="stable"
        ).head(limit)
        for tickers in selected["tickers"].astype(str):
            tags.setdefault(tickers, []).append(role)
    return pd.DataFrame([
        {"tickers": tickers, "second_stage_selection_tags": ";".join(roles)}
        for tickers, roles in sorted(tags.items())
    ])


def search_two_stage_cardinality(
    universe: pd.DataFrame, returns: pd.DataFrame, target: pd.Series,
    incumbent: list[str], *, holding_count: int, exact_limit: int,
    beam_width: int, window_days: int, step_days: int,
    transaction_cost_bps: float, second_stage_per_frontier: int,
    second_stage_weight_specs: tuple[str, ...], fit_days: int = 63,
    shrinkage_intensity: float = 0.35, max_single_weight: float = 0.45,
    min_single_weight: float = 0.05, top_weight_cap: float = 0.80,
    minimum_effective_n_ratio: float = 0.70, risk_chain_top1_cap: float = 0.55,
    turnover_anchor_strength: float = 0.25, portfolio_cash_usd: float = 5000.0,
    minimum_cash_buffer_usd: float = 100.0,
    minimum_median_dollar_volume_usd: float = 50_000_000.0,
    incumbent_weights: Mapping[str, float] | None = None,
    execution_prices: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if not second_stage_weight_specs or "equal_weight" in second_stage_weight_specs:
        raise NdxCardinalityDiscoveryError("two-stage second stage must contain non-equal specs")
    common = dict(
        holding_count=holding_count, exact_limit=exact_limit, beam_width=beam_width,
        window_days=window_days, step_days=step_days,
        transaction_cost_bps=transaction_cost_bps, fit_days=fit_days,
        shrinkage_intensity=shrinkage_intensity, max_single_weight=max_single_weight,
        min_single_weight=min_single_weight, top_weight_cap=top_weight_cap,
        minimum_effective_n_ratio=minimum_effective_n_ratio,
        risk_chain_top1_cap=risk_chain_top1_cap,
        turnover_anchor_strength=turnover_anchor_strength,
        portfolio_cash_usd=portfolio_cash_usd,
        minimum_cash_buffer_usd=minimum_cash_buffer_usd,
        minimum_median_dollar_volume_usd=minimum_median_dollar_volume_usd,
        incumbent_weights=incumbent_weights,
        execution_prices=execution_prices,
    )
    first_stage, first_audit = search_synthetic_cardinality(
        universe, returns, target, incumbent,
        weight_specs=("equal_weight",), **common,
    )
    shortlist = select_multifrontier_security_sets(
        first_stage, per_frontier_limit=second_stage_per_frontier,
    )
    tag_by_set = shortlist.set_index("tickers")["second_stage_selection_tags"].to_dict()
    second_rows = []
    failure_rows = []
    for tickers in shortlist["tickers"].astype(str):
        combo = tuple(tickers.split(";"))
        for weight_spec in second_stage_weight_specs:
            try:
                row = evaluate_synthetic_portfolio(
                    combo, universe, returns, target, incumbent,
                    weight_spec=weight_spec,
                    window_days=window_days, step_days=step_days,
                    transaction_cost_bps=transaction_cost_bps, fit_days=fit_days,
                    shrinkage_intensity=shrinkage_intensity,
                    max_single_weight=max_single_weight, min_single_weight=min_single_weight,
                    top_weight_cap=top_weight_cap,
                    minimum_effective_n_ratio=minimum_effective_n_ratio,
                    risk_chain_top1_cap=risk_chain_top1_cap,
                    turnover_anchor_strength=turnover_anchor_strength,
                    portfolio_cash_usd=portfolio_cash_usd,
                    minimum_cash_buffer_usd=minimum_cash_buffer_usd,
                    minimum_median_dollar_volume_usd=minimum_median_dollar_volume_usd,
                    incumbent_weights=incumbent_weights,
                    execution_prices=execution_prices,
                )
            except NdxCardinalityDiscoveryError as exc:
                failure_rows.append({
                    "tickers": tickers,
                    "weight_spec": weight_spec,
                    "failure_type": type(exc).__name__,
                    "failure_reason": str(exc),
                })
            else:
                row["second_stage_selection_tags"] = tag_by_set[tickers]
                second_rows.append(row)
    failure_frame = pd.DataFrame(failure_rows)
    if failure_frame.empty:
        shortlist["second_stage_failure_count"] = 0
        shortlist["second_stage_failure_reasons"] = ""
    else:
        failure_summary = failure_frame.groupby("tickers", sort=True).agg(
            second_stage_failure_count=("weight_spec", "size"),
            second_stage_failure_reasons=(
                "failure_reason", lambda values: ";".join(sorted(set(map(str, values))))
            ),
        )
        shortlist = shortlist.merge(
            failure_summary, left_on="tickers", right_index=True, how="left", validate="one_to_one"
        )
        shortlist["second_stage_failure_count"] = shortlist["second_stage_failure_count"].fillna(0).astype(int)
        shortlist["second_stage_failure_reasons"] = shortlist["second_stage_failure_reasons"].fillna("")
    first_stage = first_stage.copy()
    first_stage["second_stage_selection_tags"] = first_stage["tickers"].map(tag_by_set).fillna("")
    combined = pd.concat([first_stage, pd.DataFrame(second_rows)], ignore_index=True, sort=False)
    combined["frontier_tags"] = _frontier_tags(combined)
    combined["constrained_frontier_tags"] = ""
    compliant = combined["declared_constraints_passed"].astype(bool)
    if bool(compliant.any()):
        combined.loc[compliant, "constrained_frontier_tags"] = _frontier_tags(
            combined.loc[compliant]
        )
    combined["search_mode"] = first_audit["search_mode"]
    combined["search_exhaustive"] = False
    fully_evaluated_sets = int(first_audit["fully_evaluated_portfolios"])
    second_stage_sets = len(shortlist)
    audit = {
        **first_audit,
        "search_method": "EQUAL_WEIGHT_FULL_OR_BOUNDED_THEN_MULTIFRONTIER_SHRINKAGE",
        "first_stage_security_sets": fully_evaluated_sets,
        "second_stage_security_sets": second_stage_sets,
        "second_stage_per_frontier_limit": int(second_stage_per_frontier),
        "second_stage_weight_specifications": list(second_stage_weight_specs),
        "second_stage_evaluation_rows": len(second_rows),
        "second_stage_failed_evaluations": len(failure_rows),
        "second_stage_failure_rows": failure_rows,
        "evaluation_rows": len(combined),
        "weight_space_fully_evaluated_security_sets": second_stage_sets,
        "weight_space_unevaluated_security_sets": max(0, fully_evaluated_sets - second_stage_sets),
        "search_exhaustive": False,
        "optimality_claim_allowed": False,
        "result_label": "REAL_TRAINING_CURRENT_SEARCHED_FRONTIER",
    }
    return combined.sort_values("portfolio_id", kind="stable").reset_index(drop=True), shortlist, audit


def synthetic_run_fingerprint(spec_sha256: str, smoke_contract: Mapping[str, Any]) -> str:
    return _canonical_sha256({
        "schema_version": 1,
        "spec_sha256": spec_sha256,
        "smoke_contract": dict(smoke_contract),
        "engine_sha256": file_sha256(Path(__file__)),
    })


def _checkpoint_content_hash(payload: Mapping[str, Any]) -> str:
    return _canonical_sha256({key: value for key, value in payload.items() if key != "checkpoint_sha256"})


def write_synthetic_checkpoint(path: Path, payload: Mapping[str, Any]) -> None:
    committed = dict(payload)
    committed["checkpoint_sha256"] = _checkpoint_content_hash(committed)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(committed, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _validate_synthetic_cardinality_block(
    audit: Mapping[str, Any], rows: list[Mapping[str, Any]], holding_count: int,
) -> None:
    if int(audit.get("holding_count") or 0) != holding_count:
        raise NdxCardinalityDiscoveryError("checkpoint audit holding count changed")
    if int(audit.get("evaluation_rows") or -1) != len(rows):
        raise NdxCardinalityDiscoveryError("checkpoint evaluated row count changed")
    for row in rows:
        if int(row.get("holding_count") or 0) != holding_count:
            raise NdxCardinalityDiscoveryError("checkpoint candidate holding count changed")
        if row.get("promotion_allowed") is not False:
            raise NdxCardinalityDiscoveryError("checkpoint candidate promotion flag changed")


def validate_checkpoint_coordinate(coordinate: Mapping[str, Any]) -> dict[str, Any]:
    required = {"universe_track", "selection_date", "holding_count", "shard_id"}
    missing = sorted(required - set(coordinate))
    if missing:
        raise NdxCardinalityDiscoveryError(f"checkpoint coordinate fields missing: {missing}")
    normalized = {
        "universe_track": str(coordinate["universe_track"]),
        "selection_date": str(coordinate["selection_date"]),
        "holding_count": int(coordinate["holding_count"]),
        "shard_id": str(coordinate["shard_id"]),
    }
    component = re.compile(r"^[A-Za-z0-9_-]+$")
    for key in ("universe_track", "selection_date", "shard_id"):
        if not component.fullmatch(normalized[key]):
            raise NdxCardinalityDiscoveryError(f"checkpoint coordinate {key} is unsafe")
    if normalized["holding_count"] <= 0:
        raise NdxCardinalityDiscoveryError("checkpoint coordinate holding_count is invalid")
    return normalized


def read_synthetic_cardinality_shard(
    path: Path, expected_fingerprint: str, expected_holding_count: int,
    expected_coordinate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxCardinalityDiscoveryError(f"synthetic checkpoint shard is unreadable: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard schema changed")
    if payload.get("status") != "SYNTHETIC_CARDINALITY_SHARD_ONLY":
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard role changed")
    if payload.get("run_fingerprint") != expected_fingerprint:
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard fingerprint changed")
    if int(payload.get("holding_count") or 0) != int(expected_holding_count):
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard cardinality changed")
    coordinate = payload.get("checkpoint_coordinate")
    if coordinate is not None:
        if not isinstance(coordinate, dict):
            raise NdxCardinalityDiscoveryError("synthetic checkpoint shard coordinate is invalid")
        normalized_coordinate = validate_checkpoint_coordinate(coordinate)
        if normalized_coordinate["holding_count"] != int(expected_holding_count):
            raise NdxCardinalityDiscoveryError("synthetic checkpoint coordinate cardinality changed")
        if expected_coordinate is not None and normalized_coordinate != validate_checkpoint_coordinate(expected_coordinate):
            raise NdxCardinalityDiscoveryError("synthetic checkpoint shard coordinate changed")
    elif expected_coordinate is not None:
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard coordinate is missing")
    if payload.get("checkpoint_sha256") != _checkpoint_content_hash(payload):
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard content hash mismatch")
    audit = payload.get("audit") or {}
    rows = payload.get("rows") or []
    if not isinstance(audit, dict) or not isinstance(rows, list):
        raise NdxCardinalityDiscoveryError("synthetic checkpoint shard payload is invalid")
    _validate_synthetic_cardinality_block(audit, rows, int(expected_holding_count))
    return payload


def write_synthetic_cardinality_shard(path: Path, payload: Mapping[str, Any]) -> None:
    """Write once per run fingerprint; a conflicting existing shard fails closed."""
    expected = dict(payload)
    expected["checkpoint_sha256"] = _checkpoint_content_hash(expected)
    if path.exists():
        existing = read_synthetic_cardinality_shard(
            path,
            str(payload.get("run_fingerprint") or ""),
            int(payload.get("holding_count") or 0),
            payload.get("checkpoint_coordinate"),
        )
        if existing != expected:
            raise NdxCardinalityDiscoveryError("immutable synthetic checkpoint shard changed")
        return
    write_synthetic_checkpoint(path, payload)


def read_synthetic_checkpoint(path: Path, expected_fingerprint: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxCardinalityDiscoveryError(f"synthetic checkpoint is unreadable: {exc}") from exc
    if payload.get("schema_version") != 1:
        raise NdxCardinalityDiscoveryError("synthetic checkpoint schema changed")
    if payload.get("run_fingerprint") != expected_fingerprint:
        raise NdxCardinalityDiscoveryError("synthetic checkpoint fingerprint changed")
    if payload.get("status") != "SYNTHETIC_ENGINE_VALIDATION_ONLY":
        raise NdxCardinalityDiscoveryError("synthetic checkpoint role changed")
    if payload.get("checkpoint_sha256") != _checkpoint_content_hash(payload):
        raise NdxCardinalityDiscoveryError("synthetic checkpoint content hash mismatch")
    completed = payload.get("completed_cardinalities")
    if completed is not None and not isinstance(completed, dict):
        raise NdxCardinalityDiscoveryError("synthetic checkpoint completed set is invalid")
    if isinstance(completed, dict):
        keys = sorted(int(key) for key in completed)
        if keys and keys != list(range(1, max(keys) + 1)):
            raise NdxCardinalityDiscoveryError("synthetic checkpoint cardinalities are not contiguous")
        for key, block in completed.items():
            holding_count = int(key)
            if isinstance(block, dict) and "shard_path" in block:
                relative = Path(str(block.get("shard_path") or ""))
                if relative.is_absolute() or not relative.parts:
                    raise NdxCardinalityDiscoveryError("checkpoint shard path is invalid")
                root = path.parent.resolve()
                shard_path = (root / relative).resolve()
                if not shard_path.is_relative_to(root):
                    raise NdxCardinalityDiscoveryError("checkpoint shard escaped output directory")
                if file_sha256(shard_path) != str(block.get("shard_sha256") or ""):
                    raise NdxCardinalityDiscoveryError("checkpoint shard file hash mismatch")
                shard = read_synthetic_cardinality_shard(
                    shard_path, expected_fingerprint, holding_count,
                    block.get("checkpoint_coordinate"),
                )
                if int(block.get("evaluation_rows") or -1) != len(shard["rows"]):
                    raise NdxCardinalityDiscoveryError("checkpoint shard index row count changed")
                continue
            audit = (block or {}).get("audit") or {}
            rows = (block or {}).get("rows") or []
            _validate_synthetic_cardinality_block(audit, rows, holding_count)
    return payload
