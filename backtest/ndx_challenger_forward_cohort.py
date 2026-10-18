"""Future-only cohort registration primitives for the pure-equity challenger set."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from backtest.ndx_challenger_forward_registry import validate_forward_spec
from backtest.ndx_local_action_execution import evaluate_local_action_execution
from scripts.ndx_cardinality_frontier_attribution import parse_weight_string


class NdxChallengerForwardCohortError(ValueError):
    pass


def read_price_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise NdxChallengerForwardCohortError(f"price cache missing: {path}")
    frame = pd.read_csv(path)
    if not {"Date", "Open", "Close"}.issubset(frame.columns):
        raise NdxChallengerForwardCohortError(f"price cache columns missing: {path}")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in ("Open", "Close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["Date", "Open", "Close"]).drop_duplicates("Date").sort_values("Date").set_index("Date")


def observation_liquidity(
    frame: pd.DataFrame,
    observation_date: str,
    *,
    lookback: int,
    minimum_observations: int,
) -> dict[str, float | int]:
    """Calculate point-in-time median dollar volume without reading future rows."""
    if "Volume" not in frame.columns:
        raise NdxChallengerForwardCohortError("price cache Volume column missing for liquidity gate")
    history = frame.loc[frame.index <= pd.Timestamp(observation_date), ["Close", "Volume"]].tail(int(lookback)).copy()
    history["Volume"] = pd.to_numeric(history["Volume"], errors="coerce")
    dollar_volume = (history["Close"] * history["Volume"]).replace([float("inf"), float("-inf")], pd.NA).dropna()
    dollar_volume = dollar_volume.loc[dollar_volume.ge(0.0)]
    if len(dollar_volume) < int(minimum_observations):
        raise NdxChallengerForwardCohortError(
            f"insufficient point-in-time liquidity observations: {len(dollar_volume)} < {minimum_observations}"
        )
    return {
        "liquidity_observations": len(dollar_volume),
        "median_dollar_volume_usd": float(dollar_volume.median()),
    }


def expected_monthly_observation(sessions: pd.DatetimeIndex, not_before: str) -> str | None:
    """Return the first completed session in the first eligible calendar month."""
    eligible = pd.DatetimeIndex(sessions).normalize()
    eligible = eligible[eligible >= pd.Timestamp(not_before)]
    if eligible.empty:
        return None
    first_month = eligible[0].to_period("M")
    return eligible[eligible.to_period("M") == first_month][0].strftime("%Y-%m-%d")


def next_fresh_monthly_observation(
    sessions: pd.DatetimeIndex,
    not_before: str,
    as_of_date: str,
) -> tuple[str | None, list[str]]:
    """Advance past expired monthly anchors without ever backfilling them as fresh."""
    cursor = date.fromisoformat(not_before).isoformat()
    as_of = date.fromisoformat(as_of_date).isoformat()
    skipped: list[str] = []
    while True:
        expected = expected_monthly_observation(sessions, cursor)
        if expected is None or expected >= as_of:
            return expected, skipped
        skipped.append(expected)
        cursor = (pd.Timestamp(expected) + pd.offsets.MonthBegin()).strftime("%Y-%m-%d")


def validate_observation(
    observation_date: str,
    registered_date: str,
    qqq_sessions: pd.DatetimeIndex,
    *,
    first_not_before: str,
    previous_observations: list[str] | None = None,
    imported_seed: bool = False,
) -> dict[str, Any]:
    observed = date.fromisoformat(observation_date).isoformat()
    registered = date.fromisoformat(registered_date).isoformat()
    if observed > registered:
        raise NdxChallengerForwardCohortError("future observation registration is forbidden")
    if observed < registered and not imported_seed:
        raise NdxChallengerForwardCohortError("past observation requires explicit imported_seed")
    sessions = pd.DatetimeIndex(qqq_sessions).normalize().sort_values().unique()
    if pd.Timestamp(observed) not in sessions:
        raise NdxChallengerForwardCohortError("observation must be a completed QQQ session")
    previous = sorted(previous_observations or [])
    if previous and observed <= previous[-1]:
        raise NdxChallengerForwardCohortError("new observation must follow the immutable cohort chain")
    not_before = first_not_before if not previous else (pd.Timestamp(previous[-1]) + pd.offsets.MonthBegin()).strftime("%Y-%m-%d")
    if imported_seed:
        expected = expected_monthly_observation(sessions, not_before)
    else:
        expected, _ = next_fresh_monthly_observation(sessions, not_before, registered)
    if expected != observed:
        raise NdxChallengerForwardCohortError(f"observation is not the expected monthly session: expected={expected}")
    return {
        "observation_date": observed,
        "registered_date": registered,
        "cohort_origin": "imported_seed" if imported_seed else "same_day_registration",
        "fresh_oos_eligible": bool(not imported_seed and observed == registered),
    }


def _constraints(action_scope: str) -> dict[str, float]:
    dynamic = action_scope == "VARIABLE_CARDINALITY"
    return {
        "min_single_weight": 0.05 if dynamic else 0.0,
        "max_single_weight": 0.45,
        "top3_cap": 0.80,
        "minimum_effective_n_ratio": 0.70 if dynamic else 0.0,
        "risk_chain_top1_cap": 0.55,
    }


def build_cohort_snapshot(
    active_registry: pd.DataFrame,
    risk_map: pd.DataFrame,
    baseline: pd.DataFrame,
    observation_closes: Mapping[str, float],
    observation_liquidity_usd: Mapping[str, float],
    spec: Mapping[str, object],
    observation: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze target weights and independently resize whole lots at observation close."""
    validate_forward_spec(spec)
    forward = spec["forward_contract"]
    cash = float(forward["standardized_execution_cash_usd"])
    buffer = float(forward["minimum_cash_buffer_usd"])
    cohort_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []

    required_identity = {
        "registry_entry_id", "candidate_id", "selection_role", "action_scope",
        "research_track", "holding_count_interpretation", "candidate_tickers",
        "frozen_target_weights", "selection_rationale",
    }
    missing_identity = sorted(required_identity - set(active_registry.columns))
    if missing_identity:
        raise NdxChallengerForwardCohortError(
            f"active registry track identity columns are incomplete: {missing_identity}"
        )

    def add_track(
        entry_id: str, candidate_id: str, role: str, scope: str,
        research_track: str, holding_count_interpretation: str, selection_rationale: str,
        weights: Mapping[str, float], chains: Mapping[str, str], track_role: str,
    ) -> None:
        prices = {ticker: float(observation_closes[ticker]) for ticker in weights}
        liquidity = {ticker: float(observation_liquidity_usd[ticker]) for ticker in weights}
        result = evaluate_local_action_execution(
            weights, prices, chains, cash=cash, minimum_cash_buffer=buffer, **_constraints(scope),
        )
        minimum_liquidity = min(liquidity.values())
        liquidity_threshold = float(forward["minimum_median_dollar_volume_usd"])
        liquidity_passed = minimum_liquidity >= liquidity_threshold
        constraint_failures = [value for value in str(result["constraint_failures"]).split(";") if value]
        if not liquidity_passed:
            constraint_failures.append("median_dollar_volume")
        cohort_rows.append({
            **observation, "registry_entry_id": entry_id, "candidate_id": candidate_id,
            "selection_role": role, "action_scope": scope, "track_role": track_role,
            "research_track": research_track,
            "holding_count_interpretation": holding_count_interpretation,
            "holding_count": len(weights),
            "candidate_tickers": ";".join(sorted(weights)),
            "selection_rationale": selection_rationale,
            "frozen_target_weights": ";".join(f"{ticker}:{weights[ticker]:.12g}" for ticker in sorted(weights)),
            "continuous_track_status": "FROZEN_TARGET_WEIGHT_WAITING_FOR_ENTRY_OPEN",
            "execution_track_status": "COHORT_WHOLE_LOT_COMPLIANT" if result["constraints_passed"] and liquidity_passed else "COHORT_WHOLE_LOT_NONCOMPLIANT",
            "execution_constraint_failures": ";".join(constraint_failures),
            "minimum_median_dollar_volume_usd": liquidity_threshold,
            "portfolio_min_median_dollar_volume_usd": minimum_liquidity,
            "liquidity_gate_passed": liquidity_passed,
            "standardized_execution_cash_usd": cash, "residual_cash_usd": result["residual_cash_usd"],
            "deployment_ratio": result["deployment_ratio"], "future_entry_price_read": False,
            "promotion_allowed": False,
        })
        for ticker in sorted(weights):
            position_rows.append({
                "observation_date": observation["observation_date"], "registry_entry_id": entry_id,
                "candidate_id": candidate_id, "selection_role": role, "track_role": track_role,
                "action_scope": scope, "research_track": research_track,
                "holding_count_interpretation": holding_count_interpretation,
                "holding_count": len(weights),
                "ticker": ticker, "risk_chain": chains[ticker], "target_weight": weights[ticker],
                "observation_close": prices[ticker], "cohort_whole_lot_shares": result["shares"][ticker],
                "cohort_notional_usd": result["notionals"][ticker],
                "cohort_actual_weight": result["actual_risky_weights"][ticker],
                "median_dollar_volume_usd": liquidity[ticker],
                "liquidity_gate_passed": liquidity[ticker] >= liquidity_threshold,
                "historical_audit_shares_reused": False,
            })

    for entry in active_registry.to_dict("records"):
        scope = str(entry["action_scope"])
        research_track = str(entry["research_track"])
        interpretation = str(entry["holding_count_interpretation"])
        if scope == "VARIABLE_CARDINALITY":
            if research_track != "portfolio_optimization" or interpretation != "dynamic_k_portfolio_structure":
                raise NdxChallengerForwardCohortError(
                    f"portfolio optimization track identity mismatch: {entry['registry_entry_id']}"
                )
        elif scope in {"ADD_ONLY", "SINGLE_REPLACEMENT", "DOUBLE_REPLACEMENT"}:
            if research_track != "migration_control" or interpretation != "frozen_incumbent_migration_action_not_target_cardinality":
                raise NdxChallengerForwardCohortError(
                    f"migration control track identity mismatch: {entry['registry_entry_id']}"
                )
        else:
            raise NdxChallengerForwardCohortError(f"unsupported forward action scope: {scope}")
        entry_map = risk_map.loc[risk_map["registry_entry_id"].astype(str).eq(str(entry["registry_entry_id"]))]
        weights = parse_weight_string(entry["frozen_target_weights"])
        chains = dict(zip(entry_map["ticker"].astype(str), entry_map["risk_chain"].astype(str)))
        if set(weights) != set(chains):
            raise NdxChallengerForwardCohortError(f"risk-chain coverage changed: {entry['registry_entry_id']}")
        add_track(
            str(entry["registry_entry_id"]), str(entry["candidate_id"]), str(entry["selection_role"]),
            scope, research_track, interpretation, str(entry["selection_rationale"]),
            weights, chains, "CHALLENGER",
        )

    if not {"ticker", "frozen_weight", "issuer_id", "risk_chain"}.issubset(baseline.columns):
        raise NdxChallengerForwardCohortError("original-8 baseline attribution columns are incomplete")
    baseline_weights = dict(zip(baseline["ticker"].astype(str), pd.to_numeric(baseline["frozen_weight"])))
    if len(baseline_weights) != len(baseline) or baseline[["issuer_id", "risk_chain"]].astype(str).eq("").any().any():
        raise NdxChallengerForwardCohortError("original-8 baseline attribution is incomplete or duplicated")
    baseline_chains = dict(zip(baseline["ticker"].astype(str), baseline["risk_chain"].astype(str)))
    add_track(
        "ORIGINAL_8_CONTROL", "ORIGINAL_8", "SAME_DATE_CONTROL", "ORIGINAL_8_CONTROL",
        "benchmark_control", "original_8_incumbent_benchmark_not_target_cardinality",
        "same_date_original_8_control", baseline_weights, baseline_chains, "ORIGINAL_8_CONTROL",
    )
    return pd.DataFrame(cohort_rows), pd.DataFrame(position_rows)


__all__ = [
    "NdxChallengerForwardCohortError", "build_cohort_snapshot", "expected_monthly_observation",
    "next_fresh_monthly_observation", "observation_liquidity", "read_price_cache", "validate_observation",
]
