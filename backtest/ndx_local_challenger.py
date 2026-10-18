from __future__ import annotations

import hashlib
from typing import Any, Mapping

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import NdxCardinalityDiscoveryError, _window_metrics, pareto_mask


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    normalized = {str(ticker): float(weight) for ticker, weight in weights.items() if float(weight) > 0}
    if not normalized or any(not np.isfinite(weight) for weight in normalized.values()):
        raise NdxCardinalityDiscoveryError("fixed challenger weights are invalid")
    total = sum(normalized.values())
    if total <= 0:
        raise NdxCardinalityDiscoveryError("fixed challenger weights must sum positive")
    return {ticker: weight / total for ticker, weight in normalized.items()}


def evaluate_fixed_weight_challenger(
    *,
    operation: str,
    removed: tuple[str, ...],
    added: tuple[str, ...],
    weights: Mapping[str, float],
    returns: pd.DataFrame,
    target: pd.Series,
    incumbent_weights: Mapping[str, float],
    fit_days: int,
    window_days: int,
    step_days: int,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    candidate = normalize_weights(weights)
    incumbent = normalize_weights(incumbent_weights)
    if not returns.index.equals(target.index):
        raise NdxCardinalityDiscoveryError("fixed challenger target/return indexes must match")
    required = set(candidate) | set(incumbent)
    if not required.issubset(returns.columns):
        raise NdxCardinalityDiscoveryError("fixed challenger returns are incomplete")
    if len(returns) < fit_days + window_days:
        raise NdxCardinalityDiscoveryError("fixed challenger evaluation range is too short")
    turnover = 0.5 * sum(
        abs(candidate.get(ticker, 0.0) - incumbent.get(ticker, 0.0))
        for ticker in required
    )
    entry_cost = turnover * float(transaction_cost_bps) / 10000.0
    candidate_return: list[float] = []
    candidate_drawdown: list[float] = []
    incumbent_return: list[float] = []
    incumbent_drawdown: list[float] = []
    target_return: list[float] = []
    target_drawdown: list[float] = []
    for start in range(fit_days, len(returns) - window_days + 1, step_days):
        forward = returns.iloc[start:start + window_days]
        c_series = forward[list(candidate)].mul(pd.Series(candidate), axis=1).sum(axis=1)
        i_series = forward[list(incumbent)].mul(pd.Series(incumbent), axis=1).sum(axis=1)
        t_series = target.iloc[start:start + window_days]
        cr, cd = _window_metrics(c_series, window_days, window_days, entry_cost=entry_cost)
        ir, idd = _window_metrics(i_series, window_days, window_days)
        tr, td = _window_metrics(t_series, window_days, window_days)
        candidate_return.extend(cr); candidate_drawdown.extend(cd)
        incumbent_return.extend(ir); incumbent_drawdown.extend(idd)
        target_return.extend(tr); target_drawdown.extend(td)
    if not candidate_return:
        raise NdxCardinalityDiscoveryError("fixed challenger produced no rolling windows")
    c_ret = np.asarray(candidate_return); c_dd = np.asarray(candidate_drawdown)
    i_ret = np.asarray(incumbent_return); i_dd = np.asarray(incumbent_drawdown)
    t_ret = np.asarray(target_return); t_dd = np.asarray(target_drawdown)
    return_p50 = float(np.quantile(c_ret, 0.50))
    return_p10 = float(np.quantile(c_ret, 0.10))
    dd_p50 = float(np.quantile(c_dd, 0.50))
    dd_p90 = float(np.quantile(c_dd, 0.90))
    target_distance = (
        abs(return_p50 - float(np.quantile(t_ret, 0.50)))
        + abs(return_p10 - float(np.quantile(t_ret, 0.10)))
        + abs(dd_p50 - float(np.quantile(t_dd, 0.50)))
        + abs(dd_p90 - float(np.quantile(t_dd, 0.90)))
    )
    identity = f"{operation}|{';'.join(removed)}|{';'.join(added)}|" + ";".join(
        f"{ticker}:{candidate[ticker]:.12f}" for ticker in sorted(candidate)
    )
    ordered_weights = sorted(candidate.values(), reverse=True)
    return {
        "challenger_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "operation": operation,
        "removed": ";".join(removed),
        "added": ";".join(added),
        "holding_count": len(candidate),
        "tickers": ";".join(sorted(candidate)),
        "weights": ";".join(f"{ticker}:{candidate[ticker]:.10f}" for ticker in sorted(candidate)),
        "rolling_window_count": len(c_ret),
        "return_p50": return_p50,
        "return_p10": return_p10,
        "max_drawdown_p50": dd_p50,
        "max_drawdown_p90": dd_p90,
        "paired_return_p50_vs_incumbent": float(np.quantile(c_ret - i_ret, 0.50)),
        "paired_return_p10_vs_incumbent": float(np.quantile(c_ret - i_ret, 0.10)),
        "paired_drawdown_cost_p50_vs_incumbent": float(np.quantile(c_dd - i_dd, 0.50)),
        "paired_drawdown_cost_p90_vs_incumbent": float(np.quantile(c_dd - i_dd, 0.90)),
        "return_p50_vs_012922": return_p50 - float(np.quantile(t_ret, 0.50)),
        "return_p10_vs_012922": return_p10 - float(np.quantile(t_ret, 0.10)),
        "max_drawdown_p50_vs_012922": dd_p50 - float(np.quantile(t_dd, 0.50)),
        "max_drawdown_p90_vs_012922": dd_p90 - float(np.quantile(t_dd, 0.90)),
        "target_012922_distance": target_distance,
        "weight_top1": ordered_weights[0],
        "weight_top3": sum(ordered_weights[:3]),
        "effective_n": 1.0 / sum(weight * weight for weight in ordered_weights),
        "declared_constraints_passed": (
            ordered_weights[0] <= 0.45 + 1e-12
            and sum(ordered_weights[:3]) <= 0.80 + 1e-12
        ),
        "turnover": turnover,
        "transaction_cost": entry_cost,
        "result_role": "REAL_POINT_IN_TIME_TRAINING_LOCAL_CHALLENGER_ONLY",
        "promotion_allowed": False,
    }


def tag_local_frontiers(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["frontier_tags"] = ""
    for _, group in result.groupby("operation", sort=True):
        tags = {index: [] for index in group.index}
        selectors = {
            "RETURN": group["return_p50"].idxmax(),
            "BAD_TAIL": group["return_p10"].idxmax(),
            "DRAWDOWN": group["max_drawdown_p90"].idxmin(),
            "012922_DISTANCE": group["target_012922_distance"].idxmin(),
        }
        for tag, index in selectors.items():
            tags[index].append(tag)
        for index in group.index[pareto_mask(group)]:
            tags[index].append("PARETO")
        for index, values in tags.items():
            result.at[index, "frontier_tags"] = ";".join(values)
    return result


def aggregate_local_challenger_stability(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    if len(frames) < 2:
        raise NdxCardinalityDiscoveryError("local stability audit needs at least two starts")
    metric_columns = [
        "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent",
        "paired_drawdown_cost_p50_vs_incumbent", "paired_drawdown_cost_p90_vs_incumbent",
        "target_012922_distance", "turnover",
    ]
    indexed: list[pd.DataFrame] = []
    for start, source in sorted(frames.items()):
        required = {"operation", "removed", "added", "holding_count", *metric_columns}
        if not required.issubset(source.columns):
            raise NdxCardinalityDiscoveryError(f"local stability input columns missing: {start}")
        frame = source.copy().fillna("")
        frame["structure_key"] = (
            frame["operation"].astype(str) + "|" + frame["removed"].astype(str)
            + "|" + frame["added"].astype(str)
        )
        if frame["structure_key"].duplicated().any():
            raise NdxCardinalityDiscoveryError(f"duplicate local structure key: {start}")
        keep = ["structure_key", "operation", "removed", "added", "holding_count", *metric_columns]
        indexed.append(frame[keep].set_index("structure_key").add_suffix(f"__{start}"))
    joined = indexed[0]
    for frame in indexed[1:]:
        joined = joined.join(frame, how="inner", validate="one_to_one")
    starts = sorted(frames)
    rows = []
    for key, row in joined.iterrows():
        passes = []
        for start in starts:
            passes.append(
                float(row[f"paired_return_p50_vs_incumbent__{start}"]) > 0
                and float(row[f"paired_return_p10_vs_incumbent__{start}"]) > 0
                and float(row[f"paired_drawdown_cost_p50_vs_incumbent__{start}"]) <= 0
                and float(row[f"paired_drawdown_cost_p90_vs_incumbent__{start}"]) <= 0
            )
        return_p50 = [float(row[f"paired_return_p50_vs_incumbent__{start}"]) for start in starts]
        return_p10 = [float(row[f"paired_return_p10_vs_incumbent__{start}"]) for start in starts]
        dd_p50 = [float(row[f"paired_drawdown_cost_p50_vs_incumbent__{start}"]) for start in starts]
        dd_p90 = [float(row[f"paired_drawdown_cost_p90_vs_incumbent__{start}"]) for start in starts]
        distance = [float(row[f"target_012922_distance__{start}"]) for start in starts]
        first = starts[0]
        rows.append({
            "structure_key": key,
            "operation": row[f"operation__{first}"],
            "removed": row[f"removed__{first}"],
            "added": row[f"added__{first}"],
            "holding_count": int(row[f"holding_count__{first}"]),
            "common_start_count": len(starts),
            "four_dimension_pass_count": sum(passes),
            "four_dimension_pass_all_starts": all(passes),
            "return_tail_positive_all_starts": min(return_p50) > 0 and min(return_p10) > 0,
            "drawdown_nonworse_all_starts": max(dd_p50) <= 0 and max(dd_p90) <= 0,
            "worst_paired_return_p50": min(return_p50),
            "worst_paired_return_p10": min(return_p10),
            "worst_paired_drawdown_cost_p50": max(dd_p50),
            "worst_paired_drawdown_cost_p90": max(dd_p90),
            "median_target_012922_distance": float(np.median(distance)),
            "turnover": float(row[f"turnover__{first}"]),
        })
    return pd.DataFrame(rows).sort_values(
        ["four_dimension_pass_count", "worst_paired_return_p10", "worst_paired_drawdown_cost_p90"],
        ascending=[False, False, True], kind="stable",
    ).reset_index(drop=True)
