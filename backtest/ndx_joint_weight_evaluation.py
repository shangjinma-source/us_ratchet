"""Evaluate one research weight task from explicit, already prepared inputs.

No live state, price cache, or NAV file is read here. Historical source recovery
and durable resume belong to the caller; this is not an admission verifier.
"""
from collections.abc import Mapping
from numbers import Real

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import evaluate_synthetic_portfolio


CONTRACT_FIELDS = frozenset({
    "window_days", "step_days", "transaction_cost_bps", "fit_days",
    "shrinkage_intensity", "max_single_weight", "min_single_weight",
    "top_weight_cap", "minimum_effective_n_ratio", "risk_chain_top1_cap",
    "turnover_anchor_strength", "portfolio_cash_usd", "minimum_cash_buffer_usd",
    "minimum_median_dollar_volume_usd",
})
WEIGHT_SPECS = frozenset({"constrained_fixed_shrinkage",
                          "constrained_fixed_shrinkage_turnover_anchor"})


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _numeric_values(frame, label):
    values = frame.to_numpy()
    _require(all(isinstance(value, Real) and not isinstance(value, (bool, np.bool_))
                 for value in values.flat), "Non-numeric or boolean " + label)
    numbers = values.astype(float)
    _require(np.isfinite(numbers).all(), "Nonfinite " + label)
    return numbers


def evaluate_joint_weight_task(task, *, universe, returns, target_returns,
                               nominal_prices, incumbent_weights, contract):
    """Run the real weight/continuous whole-lot evaluator, without I/O.

    A result whose constraints fail remains a successfully evaluated negative
    result. Computation exceptions propagate and must not become completed jobs.
    The caller must bind these explicit inputs to the experiment's sources.
    Return/drawdown quantiles are the legacy fractional-weight model statistics;
    whole-lot path/eligibility fields are separate and must not be conflated.
    """
    _require(isinstance(task, Mapping), "Task must be a mapping")
    _require(task.get("weight_spec") in WEIGHT_SPECS, "Unsupported delta weight spec")
    tickers = str(task.get("tickers", "")).split(";")
    _require(all(tickers) and tickers == sorted(set(tickers)), "Invalid ticker set")
    _require(type(task.get("holding_count")) is int
             and task["holding_count"] == len(tickers), "Task k mismatch")
    cutoff = pd.Timestamp(task["decision_data_end"])
    selection = pd.Timestamp(task["selection_date"])
    _require(not pd.isna(cutoff) and not pd.isna(selection)
             and cutoff.tzinfo is None and selection.tzinfo is None
             and cutoff == cutoff.normalize() and selection == selection.normalize()
             and cutoff < selection, "Invalid decision/execution dates")
    _require(isinstance(contract, Mapping) and set(contract) == CONTRACT_FIELDS,
             "Complete explicit evaluation contract required")
    for key, value in contract.items():
        _require(not isinstance(value, (bool, np.bool_)) and isinstance(value, (int, float))
                 and np.isfinite(value), "Invalid contract number: " + key)
    for key in ("fit_days", "window_days", "step_days"):
        _require(type(contract[key]) is int and contract[key] > 0,
                 "Positive integer required: " + key)
    _require(contract["transaction_cost_bps"] >= 0
             and contract["minimum_median_dollar_volume_usd"] > 0,
             "Invalid costs/liquidity contract")
    for key in ("shrinkage_intensity", "turnover_anchor_strength"):
        _require(0 <= contract[key] <= 1, "Invalid fraction: " + key)
    for key in ("max_single_weight", "min_single_weight", "top_weight_cap",
                "minimum_effective_n_ratio", "risk_chain_top1_cap"):
        _require(0 < contract[key] <= 1, "Invalid risk bound: " + key)
    _require(contract["min_single_weight"] <= contract["max_single_weight"],
             "Reversed weight bounds")
    _require(isinstance(universe, pd.DataFrame) and not universe.empty
             and not universe.columns.duplicated().any(), "Invalid universe")
    required = {"ticker", "security_id", "issuer_id", "risk_chain",
                "synthetic_price", "median_dollar_volume_usd"}
    _require(required.issubset(universe), "Incomplete universe identities/price/liquidity")
    for key in ("ticker", "security_id", "issuer_id", "risk_chain"):
        _require(universe[key].map(lambda x: isinstance(x, str) and bool(x)
                                  and x == x.strip()).all(), "Blank universe identity")
    _require(not universe.ticker.duplicated().any()
             and not universe.security_id.duplicated().any(), "Ambiguous universe identity")
    _require((_numeric_values(universe[["synthetic_price", "median_dollar_volume_usd"]],
                              "universe prices/liquidity") > 0).all(),
             "Nonpositive universe prices/liquidity")
    _require(set(tickers).issubset(set(universe.ticker)), "Task outside supplied universe")
    _require(isinstance(incumbent_weights, Mapping) and bool(incumbent_weights),
             "Explicit incumbent weights required; no live/default weights")
    _require(all(isinstance(k, str) and k and k == k.strip()
                 and not isinstance(v, (bool, np.bool_)) and isinstance(v, (int, float))
                 and np.isfinite(v) and v >= 0 for k, v in incumbent_weights.items())
             and abs(sum(incumbent_weights.values()) - 1.) <= 1e-10,
             "Incumbent weights must be finite and normalized")
    _require(isinstance(returns, pd.DataFrame) and not returns.empty
             and not returns.columns.duplicated().any(), "Invalid return panel")
    _require(isinstance(returns.index, pd.DatetimeIndex) and returns.index.tz is None
             and not returns.index.hasnans and returns.index.is_unique
             and returns.index.is_monotonic_increasing
             and returns.index.equals(returns.index.normalize())
             and returns.index.max() == cutoff, "Invalid return calendar/cutoff")
    _require(set(tickers) | set(incumbent_weights) <= set(returns), "Missing return columns")
    _require(isinstance(target_returns, pd.Series)
             and returns.index.equals(target_returns.index), "Target calendar mismatch")
    _require(isinstance(nominal_prices, pd.DataFrame)
             and not nominal_prices.columns.duplicated().any()
             and returns.index.equals(nominal_prices.index)
             and set(tickers).issubset(nominal_prices), "Nominal calendar/columns mismatch")
    for values, label in ((_numeric_values(returns, "returns"), "returns"),
                          (_numeric_values(target_returns, "target"), "target"),
                          (_numeric_values(nominal_prices, "nominal"), "nominal")):
        _require((values > 0).all() if label == "nominal" else (values >= -1).all(),
                 "Invalid " + label)
    return evaluate_synthetic_portfolio(
        tuple(tickers), universe.copy(deep=True), returns.copy(deep=True),
        target_returns.copy(deep=True), sorted(incumbent_weights),
        weight_spec=task["weight_spec"], incumbent_weights=dict(incumbent_weights),
        execution_prices=nominal_prices.copy(deep=True), **dict(contract))
