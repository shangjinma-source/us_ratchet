"""Paired future-only evaluation for frozen challenger cohort tracks."""
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from backtest.ndx_portfolio_objective import evaluate_componentwise_target_gate


class NdxChallengerForwardEvaluationError(ValueError):
    pass


def annotate_paired_execution_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Label whether a candidate/control whole-lot comparison is valid evidence."""
    execution = str(payload.get("execution_status") or "")
    candidate = str(payload.get("cohort_execution_track_status") or "")
    control = str(payload.get("original_8_cohort_execution_track_status") or "")
    failures = []
    if execution != "MATURE_EXECUTABLE":
        failures.append(execution or "EXECUTION_STATUS_MISSING")
    if candidate != "COHORT_WHOLE_LOT_COMPLIANT":
        failures.append("CANDIDATE_COHORT_NONCOMPLIANT")
    if control != "COHORT_WHOLE_LOT_COMPLIANT":
        failures.append("ORIGINAL_8_CONTROL_COHORT_NONCOMPLIANT")
    return {
        "paired_execution_evidence_eligible": not failures,
        "paired_execution_evidence_status": (
            "PAIRED_EXECUTION_EVIDENCE_ELIGIBLE" if not failures else ";".join(failures)
        ),
    }


def _max_drawdown(nav: np.ndarray) -> float:
    values = np.concatenate(([1.0], np.asarray(nav, dtype=float)))
    peak = np.maximum.accumulate(values)
    return float(np.max((peak - values) / peak))


def _continuous_nav(positions: pd.DataFrame, prices: Mapping[str, pd.DataFrame], dates: pd.DatetimeIndex, cost: float) -> np.ndarray:
    nav = np.zeros(len(dates), dtype=float)
    for row in positions.to_dict("records"):
        ticker = str(row["ticker"])
        entry_open = float(prices[ticker].loc[dates[0], "Open"])
        nav += float(row["target_weight"]) * prices[ticker].loc[dates, "Close"].to_numpy(dtype=float) / entry_open
    return (1.0 - cost) * nav


def _execution_nav(
    positions: pd.DataFrame,
    prices: Mapping[str, pd.DataFrame],
    dates: pd.DatetimeIndex,
    *,
    cash: float,
    minimum_cash_buffer: float,
    cost: float,
) -> tuple[np.ndarray | None, dict[str, float | bool]]:
    entry_notional = 0.0
    market_values = np.zeros(len(dates), dtype=float)
    for row in positions.to_dict("records"):
        ticker = str(row["ticker"])
        shares = int(row["cohort_whole_lot_shares"])
        entry_notional += shares * float(prices[ticker].loc[dates[0], "Open"])
        market_values += shares * prices[ticker].loc[dates, "Close"].to_numpy(dtype=float)
    entry_cost = entry_notional * cost
    residual = cash - entry_notional - entry_cost
    detail: dict[str, float | bool] = {
        "entry_notional_usd": entry_notional, "entry_transaction_cost_usd": entry_cost,
        "entry_residual_cash_usd": residual, "entry_cash_buffer_passed": residual >= minimum_cash_buffer - 1e-9,
    }
    if not detail["entry_cash_buffer_passed"]:
        return None, detail
    return (residual + market_values) / cash, detail


def _track_metrics(nav: np.ndarray, control_nav: np.ndarray) -> dict[str, float]:
    portfolio_return = float(nav[-1] - 1.0)
    control_return = float(control_nav[-1] - 1.0)
    portfolio_dd = _max_drawdown(nav)
    control_dd = _max_drawdown(control_nav)
    return {
        "return": portfolio_return, "control_return": control_return,
        "return_delta_vs_original_8": portfolio_return - control_return,
        "max_drawdown": portfolio_dd, "control_max_drawdown": control_dd,
        "drawdown_cost_vs_original_8": portfolio_dd - control_dd,
    }


def _target_metrics(target_nav: pd.DataFrame | None, entry: pd.Timestamp, exit_: pd.Timestamp) -> dict[str, Any]:
    empty = {
        "target_012922_mature": False, "target_012922_entry_date": None,
        "target_012922_exit_date": None, "target_012922_return": None,
        "target_012922_max_drawdown": None,
    }
    if target_nav is None or target_nav.empty:
        return empty
    window = target_nav.loc[(target_nav.index >= entry) & (target_nav.index <= exit_), "Close"].dropna()
    if len(window) < 2:
        return empty
    entry_lag = int(np.busday_count(entry.date(), window.index[0].date()))
    exit_lag = int(np.busday_count(window.index[-1].date(), exit_.date()))
    if entry_lag > 3 or exit_lag > 3:
        return empty
    normalized = window.to_numpy(dtype=float) / float(window.iloc[0])
    return {
        "target_012922_mature": True,
        "target_012922_entry_date": window.index[0].strftime("%Y-%m-%d"),
        "target_012922_exit_date": window.index[-1].strftime("%Y-%m-%d"),
        "target_012922_return": float(normalized[-1] - 1.0),
        "target_012922_max_drawdown": _max_drawdown(normalized),
    }


def evaluate_candidate_pair(
    candidate_positions: pd.DataFrame,
    control_positions: pd.DataFrame,
    prices: Mapping[str, pd.DataFrame],
    *,
    observation_date: str,
    horizon: int,
    standardized_cash: float,
    minimum_cash_buffer: float,
    transaction_cost_bps: float,
    target_nav: pd.DataFrame | None = None,
) -> dict[str, Any]:
    required = {"ticker", "target_weight", "cohort_whole_lot_shares"}
    if not required.issubset(candidate_positions.columns) or not required.issubset(control_positions.columns):
        raise NdxChallengerForwardEvaluationError("cohort position columns are incomplete")
    tickers = sorted(set(candidate_positions["ticker"].astype(str)).union(control_positions["ticker"].astype(str)))
    if set(tickers) != set(prices):
        raise NdxChallengerForwardEvaluationError("price mapping must exactly cover candidate and control tickers")
    observed = pd.Timestamp(observation_date)
    common: pd.DatetimeIndex | None = None
    for ticker in tickers:
        dates = prices[ticker].index[prices[ticker].index > observed]
        common = dates if common is None else common.intersection(dates)
    dates = pd.DatetimeIndex([]) if common is None else pd.DatetimeIndex(common).sort_values()
    waiting_status = "WAITING_FOR_MATURITY" if len(dates) else "WAITING_FOR_ENTRY_OPEN"
    base: dict[str, Any] = {
        "observation_date": observation_date,
        "entry_date": dates[0].strftime("%Y-%m-%d") if len(dates) else None,
        "available_common_sessions": len(dates), "horizon_trading_days": int(horizon),
        "mature": len(dates) >= int(horizon), "promotion_allowed": False,
        # Keep the gate schema complete before any outcome exists.  These are
        # lifecycle fields, not return metrics, so emitting them cannot leak or
        # manufacture forward evidence.
        "execution_status": waiting_status,
        "target_012922_mature": False,
    }
    if len(dates) < int(horizon):
        return {**base, "status": waiting_status}
    dates = dates[:int(horizon)]
    cost = max(0.0, float(transaction_cost_bps)) / 10_000.0
    candidate_continuous = _continuous_nav(candidate_positions, prices, dates, cost)
    control_continuous = _continuous_nav(control_positions, prices, dates, cost)
    candidate_execution, candidate_entry = _execution_nav(
        candidate_positions, prices, dates, cash=standardized_cash,
        minimum_cash_buffer=minimum_cash_buffer, cost=cost,
    )
    control_execution, control_entry = _execution_nav(
        control_positions, prices, dates, cash=standardized_cash,
        minimum_cash_buffer=minimum_cash_buffer, cost=cost,
    )
    target = _target_metrics(target_nav, dates[0], dates[-1])
    result = {
        **base, "exit_date": dates[-1].strftime("%Y-%m-%d"), "status": "MATURE",
        **{f"continuous_{key}": value for key, value in _track_metrics(candidate_continuous, control_continuous).items()},
        **{f"candidate_execution_{key}": value for key, value in candidate_entry.items()},
        **{f"control_execution_{key}": value for key, value in control_entry.items()},
        **target,
    }
    if target["target_012922_mature"]:
        result["continuous_return_delta_vs_012922"] = result["continuous_return"] - target["target_012922_return"]
        result["continuous_drawdown_cost_vs_012922"] = result["continuous_max_drawdown"] - target["target_012922_max_drawdown"]
    else:
        result["continuous_return_delta_vs_012922"] = None
        result["continuous_drawdown_cost_vs_012922"] = None
    if candidate_execution is None or control_execution is None:
        result["execution_status"] = "ENTRY_CASH_BUFFER_FAILED"
    else:
        result["execution_status"] = "MATURE_EXECUTABLE"
        result.update({f"execution_{key}": value for key, value in _track_metrics(candidate_execution, control_execution).items()})
        result["execution_return_delta_vs_012922"] = (
            result["execution_return"] - target["target_012922_return"] if target["target_012922_mature"] else None
        )
        result["execution_drawdown_cost_vs_012922"] = (
            result["execution_max_drawdown"] - target["target_012922_max_drawdown"] if target["target_012922_mature"] else None
        )
    return result


def summarize_forward_readiness(
    active_registry: pd.DataFrame,
    evaluations: pd.DataFrame,
    forward_contract: Mapping[str, Any],
    promotion_contract: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Keep continuous maturity separate from executable whole-lot maturity."""
    minimum_cohorts = int(forward_contract["minimum_fresh_mature_cohorts"])
    minimum_regimes = int(forward_contract["minimum_distinct_regimes"])
    required_identity = {
        "registry_entry_id", "candidate_id", "selection_role", "action_scope",
        "research_track", "holding_count_interpretation", "candidate_tickers",
        "frozen_target_weights", "selection_rationale",
    }
    missing_identity = sorted(required_identity - set(active_registry.columns))
    if missing_identity:
        raise NdxChallengerForwardEvaluationError(
            f"active registry track identity columns are incomplete: {missing_identity}"
        )
    if not evaluations.empty:
        required_evaluation = {
            "registry_entry_id", "fresh_oos_eligible", "mature", "execution_status",
            "cohort_execution_track_status", "original_8_cohort_execution_track_status",
            "observation_regime", "target_012922_mature",
        }
        missing_evaluation = sorted(required_evaluation - set(evaluations.columns))
        if missing_evaluation:
            raise NdxChallengerForwardEvaluationError(
                f"forward evaluation gate columns are incomplete: {missing_evaluation}"
            )
    rows: list[dict[str, Any]] = []
    for entry in active_registry.to_dict("records"):
        if evaluations.empty:
            group = pd.DataFrame()
        else:
            group = evaluations.loc[
                evaluations["registry_entry_id"].astype(str).eq(str(entry["registry_entry_id"]))
            ].copy()
        fresh = group.loc[group["fresh_oos_eligible"].astype(bool)] if not group.empty else group
        continuous = fresh.loc[fresh["mature"].astype(bool)] if not fresh.empty else fresh
        if not continuous.empty and "paired_execution_evidence_eligible" in continuous.columns:
            executable = continuous.loc[continuous["paired_execution_evidence_eligible"].astype(bool)]
        else:
            executable = continuous.loc[
                continuous["execution_status"].astype(str).eq("MATURE_EXECUTABLE")
                & continuous["cohort_execution_track_status"].astype(str).eq("COHORT_WHOLE_LOT_COMPLIANT")
                & continuous["original_8_cohort_execution_track_status"].astype(str).eq("COHORT_WHOLE_LOT_COMPLIANT")
            ] if not continuous.empty else continuous
        continuous_regimes = (
            set(continuous["observation_regime"].astype(str)) - {"INSUFFICIENT_HISTORY"}
            if not continuous.empty else set()
        )
        executable_regimes = (
            set(executable["observation_regime"].astype(str)) - {"INSUFFICIENT_HISTORY"}
            if not executable.empty else set()
        )
        continuous_ready = len(continuous) >= minimum_cohorts and len(continuous_regimes) >= minimum_regimes
        execution_ready = len(executable) >= minimum_cohorts and len(executable_regimes) >= minimum_regimes
        target_complete = bool(
            continuous_ready
            and not continuous.empty
            and continuous["target_012922_mature"].astype(bool).all()
        )
        all_evidence_ready = continuous_ready and execution_ready and target_complete
        metrics: dict[str, float | bool | None] = {}
        policy_passed = False
        if all_evidence_ready:
            def quantile(frame: pd.DataFrame, column: str, q: float) -> float:
                values = pd.to_numeric(frame[column], errors="coerce").dropna()
                if len(values) != len(frame):
                    raise NdxChallengerForwardEvaluationError(f"mature forward metric is incomplete: {column}")
                return float(values.quantile(q))

            policy = (promotion_contract or {}).get("policy_gate") or {}
            require_strict_target_improvement = bool(policy.get(
                "require_at_least_one_strict_target_dimension_improvement", True
            ))
            for prefix, frame in (("continuous", continuous), ("execution", executable)):
                metrics[f"{prefix}_paired_return_p50"] = quantile(frame, f"{prefix}_return_delta_vs_original_8", 0.50)
                metrics[f"{prefix}_paired_return_p10"] = quantile(frame, f"{prefix}_return_delta_vs_original_8", 0.10)
                metrics[f"{prefix}_paired_drawdown_cost_p50"] = quantile(frame, f"{prefix}_drawdown_cost_vs_original_8", 0.50)
                metrics[f"{prefix}_paired_drawdown_cost_p90"] = quantile(frame, f"{prefix}_drawdown_cost_vs_original_8", 0.90)
                candidate_target = {
                    "return_p50": quantile(frame, f"{prefix}_return", 0.50),
                    "return_p10": quantile(frame, f"{prefix}_return", 0.10),
                    "max_drawdown_p50": quantile(frame, f"{prefix}_max_drawdown", 0.50),
                    "max_drawdown_p90": quantile(frame, f"{prefix}_max_drawdown", 0.90),
                }
                control_target = {
                    "return_p50": quantile(frame, f"{prefix}_control_return", 0.50),
                    "return_p10": quantile(frame, f"{prefix}_control_return", 0.10),
                    "max_drawdown_p50": quantile(frame, f"{prefix}_control_max_drawdown", 0.50),
                    "max_drawdown_p90": quantile(frame, f"{prefix}_control_max_drawdown", 0.90),
                }
                target = {
                    "return_p50": quantile(frame, "target_012922_return", 0.50),
                    "return_p10": quantile(frame, "target_012922_return", 0.10),
                    "max_drawdown_p50": quantile(frame, "target_012922_max_drawdown", 0.50),
                    "max_drawdown_p90": quantile(frame, "target_012922_max_drawdown", 0.90),
                }
                target_gate = evaluate_componentwise_target_gate(
                    candidate_target, control_target, target,
                    require_strict_improvement=require_strict_target_improvement,
                )
                candidate_distance = target_gate["scalar_l1_reporting_only"]["candidate"]
                control_distance = target_gate["scalar_l1_reporting_only"]["control"]
                metrics[f"{prefix}_target_012922_distance"] = candidate_distance
                metrics[f"{prefix}_original_8_target_012922_distance"] = control_distance
                metrics[f"{prefix}_target_012922_distance_improvement"] = control_distance - candidate_distance
                metrics[f"{prefix}_target_012922_componentwise_passed"] = target_gate["componentwise_passed"]
                metrics[f"{prefix}_target_012922_strict_requirement_passed"] = target_gate["strict_requirement_passed"]
                metrics[f"{prefix}_target_012922_componentwise_gate_passed"] = target_gate["passed"]
                metrics[f"{prefix}_target_012922_strict_improvement_count"] = target_gate["strict_improvement_count"]
                for dimension, check in target_gate["checks"].items():
                    metrics[f"{prefix}_target_012922_{dimension}_distance_improvement"] = (
                        check["control_absolute_distance"] - check["candidate_absolute_distance"]
                    )
            return_p50_minimum = float(policy.get("paired_return_p50_minimum", 0.0))
            return_p10_minimum = float(policy.get("paired_return_p10_minimum", 0.0))
            drawdown_p50_maximum = float(policy.get("paired_drawdown_cost_p50_maximum", 0.0))
            drawdown_p90_maximum = float(policy.get("paired_drawdown_cost_p90_maximum", 0.0))
            target_componentwise_required = bool(policy.get(
                "target_012922_componentwise_not_worse_than_original_8",
                policy.get("target_012922_distance_not_worse_than_original_8", True),
            ))
            paired_checks = []
            strict_values = []
            for prefix in ("continuous", "execution"):
                returns = [metrics[f"{prefix}_paired_return_p50"], metrics[f"{prefix}_paired_return_p10"]]
                drawdowns = [metrics[f"{prefix}_paired_drawdown_cost_p50"], metrics[f"{prefix}_paired_drawdown_cost_p90"]]
                paired_checks.extend([
                    returns[0] >= return_p50_minimum,
                    returns[1] >= return_p10_minimum,
                    drawdowns[0] <= drawdown_p50_maximum,
                    drawdowns[1] <= drawdown_p90_maximum,
                ])
                if target_componentwise_required:
                    paired_checks.append(metrics[f"{prefix}_target_012922_componentwise_gate_passed"])
                strict_values.extend([
                    returns[0] - return_p50_minimum,
                    returns[1] - return_p10_minimum,
                    drawdown_p50_maximum - drawdowns[0],
                    drawdown_p90_maximum - drawdowns[1],
                ])
            metrics.update({
                "policy_paired_return_p50_minimum": return_p50_minimum,
                "policy_paired_return_p10_minimum": return_p10_minimum,
                "policy_paired_drawdown_cost_p50_maximum": drawdown_p50_maximum,
                "policy_paired_drawdown_cost_p90_maximum": drawdown_p90_maximum,
                "policy_target_012922_componentwise_not_worse_required": target_componentwise_required,
                "policy_require_strict_target_dimension_improvement": require_strict_target_improvement,
                "policy_target_012922_scalar_l1_used_for_admission": False,
            })
            policy_passed = bool(
                policy
                and all(paired_checks)
                and (not policy.get("require_at_least_one_strict_incumbent_improvement") or any(value > 0.0 for value in strict_values))
            )
        rows.append({
            "registry_entry_id": entry["registry_entry_id"], "candidate_id": entry["candidate_id"],
            "selection_role": entry["selection_role"], "action_scope": entry["action_scope"],
            "research_track": entry["research_track"],
            "holding_count_interpretation": entry["holding_count_interpretation"],
            "holding_count": len(str(entry["candidate_tickers"]).split(";")),
            "candidate_tickers": entry["candidate_tickers"],
            "frozen_target_weights": entry["frozen_target_weights"],
            "selection_rationale": entry["selection_rationale"],
            "registered_fresh_cohorts": len(fresh),
            "mature_fresh_cohorts": len(continuous),
            "executable_mature_fresh_cohorts": len(executable),
            "execution_failed_mature_fresh_cohorts": len(continuous) - len(executable),
            "distinct_mature_regimes": len(continuous_regimes),
            "distinct_executable_mature_regimes": len(executable_regimes),
            "minimum_mature_fresh_cohorts": minimum_cohorts,
            "minimum_distinct_regimes": minimum_regimes,
            "continuous_evidence_ready": continuous_ready,
            "execution_evidence_ready": execution_ready,
            "incumbent_gate_ready": continuous_ready and execution_ready,
            "target_012922_gate_ready": target_complete,
            "policy_gate_ready": all_evidence_ready,
            "policy_gate_passed": policy_passed,
            "admission_status": (
                "FORWARD_POLICY_GATE_PASSED_REQUIRES_TODAY_DIFF_ROLLBACK_AND_USER_APPROVAL" if policy_passed
                else "FORWARD_POLICY_GATE_FAILED" if all_evidence_ready
                else "INSUFFICIENT_FRESH_FORWARD_EVIDENCE"
            ),
            "promotion_allowed": False,
            **metrics,
        })
    return pd.DataFrame(rows)


def summarize_research_tracks(summary: pd.DataFrame) -> pd.DataFrame:
    """Keep portfolio optimization evidence separate from incumbent migration controls."""
    required = {
        "research_track", "holding_count", "registered_fresh_cohorts", "mature_fresh_cohorts",
        "policy_gate_ready", "policy_gate_passed", "promotion_allowed",
    }
    missing = sorted(required - set(summary.columns))
    if missing:
        raise NdxChallengerForwardEvaluationError(f"research track summary columns are incomplete: {missing}")
    expected_tracks = {"portfolio_optimization", "migration_control"}
    observed_tracks = set(summary["research_track"].astype(str))
    if observed_tracks != expected_tracks:
        raise NdxChallengerForwardEvaluationError(
            f"forward research tracks changed: expected={sorted(expected_tracks)} observed={sorted(observed_tracks)}"
        )
    rows = []
    semantics = {
        "portfolio_optimization": "DYNAMIC_K_FORWARD_REFERENCES_NOT_FIXED_CARDINALITY",
        "migration_control": "FROZEN_INCUMBENT_MIGRATION_ACTION_CONTROL_NOT_TARGET_CARDINALITY",
    }
    for track, group in summary.groupby("research_track", sort=True):
        counts = sorted(pd.to_numeric(group["holding_count"], errors="raise").astype(int).unique().tolist())
        rows.append({
            "research_track": track,
            "target_cardinality_semantics": semantics[str(track)],
            "active_candidate_count": len(group),
            "observed_holding_counts": ";".join(str(value) for value in counts),
            "registered_fresh_cohorts_min": int(pd.to_numeric(group["registered_fresh_cohorts"]).min()),
            "registered_fresh_cohorts_max": int(pd.to_numeric(group["registered_fresh_cohorts"]).max()),
            "mature_fresh_cohorts_min": int(pd.to_numeric(group["mature_fresh_cohorts"]).min()),
            "mature_fresh_cohorts_max": int(pd.to_numeric(group["mature_fresh_cohorts"]).max()),
            "policy_gate_ready_count": int(group["policy_gate_ready"].astype(bool).sum()),
            "policy_gate_passed_count": int(group["policy_gate_passed"].astype(bool).sum()),
            "promotion_allowed_count": int(group["promotion_allowed"].astype(bool).sum()),
            "status": "FORWARD_MONITORING_ONLY_NOT_ADMISSION",
        })
    return pd.DataFrame(rows)


__all__ = [
    "NdxChallengerForwardEvaluationError", "annotate_paired_execution_evidence", "evaluate_candidate_pair",
    "summarize_forward_readiness", "summarize_research_tracks",
]
