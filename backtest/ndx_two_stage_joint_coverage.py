"""Pure research shortlist expansion for a single equal-weight k/date input.

Preserves the frozen four-frontier control, adds eight relative-metric fronts
and the complete deficit Pareto set. Selection only proposes security sets for
subsequent weight evaluation. It does not train weights or grant admission.
"""
from datetime import date
import math
import re

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import select_multifrontier_security_sets


MARGINAL_FRONTS = (
    ("FUND_RETURN_P50", "return_p50_vs_012922", False),
    ("FUND_RETURN_P10", "return_p10_vs_012922", False),
    ("FUND_DRAWDOWN_P50", "max_drawdown_p50_vs_012922", True),
    ("FUND_DRAWDOWN_P90", "max_drawdown_p90_vs_012922", True),
    ("PAIRED_INCUMBENT_RETURN_P50", "paired_return_p50_vs_incumbent", False),
    ("PAIRED_INCUMBENT_RETURN_P10", "paired_return_p10_vs_incumbent", False),
    ("PAIRED_INCUMBENT_DRAWDOWN_P50", "paired_drawdown_cost_p50_vs_incumbent", True),
    ("PAIRED_INCUMBENT_DRAWDOWN_P90", "paired_drawdown_cost_p90_vs_incumbent", True),
)
METRICS = ("return_p50", "return_p10", "max_drawdown_p90", "target_012922_distance") + tuple(
    column for _, column, _ in MARGINAL_FRONTS)
PREFERENCE = "AMAT;AVGO;CDNS;GOOG"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _date(value):
    _require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
             "Date must be a canonical ISO session")
    return date.fromisoformat(value)


def _positive_integer(value, label):
    _require(isinstance(value, int) and not isinstance(value, bool) and value > 0,
             f"{label} must be a positive integer")
    return value


def _pareto_indices(deficits, block_size):
    """Exact componentwise dominance, bounded comparison memory, all ties kept."""
    unique, inverse = np.unique(deficits, axis=0, return_inverse=True)
    zero = np.all(unique == 0., axis=1)
    if zero.any():
        return np.flatnonzero(zero[inverse])
    nondominated = np.ones(len(unique), dtype=bool)
    for first in range(0, len(unique), block_size):
        values = unique[first:first + block_size]
        dominated = np.zeros(len(values), dtype=bool)
        for other_first in range(0, len(unique), block_size):
            other = unique[other_first:other_first + block_size]
            dominates = (np.all(other[:, None, :] <= values[None, :, :], axis=2)
                         & np.any(other[:, None, :] < values[None, :, :], axis=2))
            dominated |= np.any(dominates, axis=0)
            if dominated.all():
                break
        nondominated[first:first + len(values)] = ~dominated
    return np.flatnonzero(nondominated[inverse])


def select_joint_coverage_security_sets(equal_weight_results, *, selection_date,
                                        decision_data_end, per_frontier_limit=16,
                                        pareto_block_size=256):
    """Return selected/control DataFrames and a coverage-only research audit.

    Dates are explicit because original first-stage rows may not carry scope
    columns yet. When scope columns exist, they must agree. No source identity
    metadata absent from the real stage-one schema is invented or required.
    """
    limit = _positive_integer(per_frontier_limit, "per_frontier_limit")
    block = _positive_integer(pareto_block_size, "pareto_block_size")
    _require(_date(decision_data_end) < _date(selection_date), "Decision must precede execution")
    _require(isinstance(equal_weight_results, pd.DataFrame) and not equal_weight_results.empty,
             "Equal-weight input must be nonempty")
    _require(not equal_weight_results.columns.duplicated().any(), "Duplicate columns")
    required = {"tickers", "weight_spec", "holding_count"} | set(METRICS)
    _require(required.issubset(equal_weight_results.columns), "Missing first-stage metrics")
    frame = equal_weight_results.copy(deep=True)
    _require(frame.weight_spec.eq("equal_weight").all(), "Only equal-weight first-stage rows accepted")
    for column, expected in (("selection_date", selection_date), ("decision_data_end", decision_data_end)):
        if column in frame:
            _require(frame[column].eq(expected).all(), "Mixed or mismatched decision coordinate")
    for column in ("source_batch", "universe_track"):
        if column in frame:
            _require(frame[column].map(lambda value: isinstance(value, str) and bool(value)
                                       and value == value.strip()).all()
                     and frame[column].nunique() == 1, "Mixed source scope")
    for column in ("holding_count",) + METRICS:
        _require(not frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).any(),
                 "Boolean is not a metric")
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        _require(np.isfinite(frame[column].to_numpy(dtype=float)).all(), "Nonfinite metric")
    k = float(frame.holding_count.iloc[0])
    _require(k > 0 and k.is_integer() and frame.holding_count.eq(k).all(), "Mixed or invalid k")
    for value in frame.tickers:
        _require(isinstance(value, str), "Invalid ticker set")
        names = value.split(";")
        _require(len(names) == int(k) and names == sorted(set(names))
                 and all(name and name == name.strip() for name in names),
                 "Ticker sets must be unique and canonical within k")
    _require(not frame.tickers.duplicated().any(), "Duplicate security set")
    if "weights" in frame:
        for tickers, text in zip(frame.tickers, frame.weights):
            _require(isinstance(text, str), "Malformed equal weights")
            weights = {}
            for item in text.split(";"):
                ticker, separator, value = item.rpartition(":")
                _require(separator and ticker not in weights, "Duplicate/malformed weights")
                number = float(value)
                _require(math.isfinite(number) and math.isclose(number, 1. / k, rel_tol=0., abs_tol=1e-8),
                         "First-stage weights are not equal")
                weights[ticker] = number
            _require(set(weights) == set(tickers.split(";")), "Weight/ticker mismatch")
    _require(frame.return_p50.ge(frame.return_p10).all()
             and frame.return_p10.ge(-1.).all() and frame.max_drawdown_p90.between(0., 1.).all()
             and frame.target_012922_distance.ge(0.).all(), "Invalid metric range/order")
    _require(frame.paired_return_p50_vs_incumbent.ge(frame.paired_return_p10_vs_incumbent).all()
             and frame.paired_drawdown_cost_p50_vs_incumbent.le(
                 frame.paired_drawdown_cost_p90_vs_incumbent).all(),
             "Invalid paired quantile order")
    legacy = select_multifrontier_security_sets(frame, per_frontier_limit=limit)
    tags = {row.tickers: row.second_stage_selection_tags.split(";")
            for row in legacy.itertuples(index=False)}
    for role, column, ascending in MARGINAL_FRONTS:
        chosen = frame.sort_values([column, "tickers"], ascending=[ascending, True], kind="stable").head(limit)
        for tickers in chosen.tickers:
            tags.setdefault(tickers, []).append(role)
    raw = frame[[column for _, column, _ in MARGINAL_FRONTS]].to_numpy(dtype=float)
    signs = np.asarray([1. if ascending else -1. for _, _, ascending in MARGINAL_FRONTS])
    deficits = np.maximum(raw * signs, 0.)
    pareto = frame.iloc[_pareto_indices(deficits, block)].tickers.tolist()
    for tickers in pareto:
        tags.setdefault(tickers, []).append("ONE_SIDED_DEFICIT_PARETO")
    preference_present = PREFERENCE in set(frame.tickers)
    if preference_present:
        tags.setdefault(PREFERENCE, []).append("USER_PREFERENCE")
    selected = pd.DataFrame([dict(tickers=tickers, second_stage_selection_tags=";".join(roles))
                             for tickers, roles in sorted(tags.items())])
    old = set(legacy.tickers)
    _require(old.issubset(tags), "Legacy control sets were lost")
    return dict(selected=selected, legacy_control=legacy,
                audit=dict(input_count=len(frame), legacy_selected_count=len(old),
                           newly_added_count=len(tags) - len(old), selected_count=len(tags),
                           remaining_count=len(frame) - len(tags), deficit_pareto_count=len(pareto),
                           user_preference_present=preference_present,
                           user_preference_added=preference_present and PREFERENCE not in old,
                           holding_count=int(k), selection_date=selection_date,
                           decision_data_end=decision_data_end, per_frontier_limit=limit,
                           pareto_exact=True, pareto_truncated=False, research_only=True,
                           legacy_control_preserved=True, admission_allowed=False,
                           promotion_allowed=False, live_mutation_allowed=False,
                           complete_weight_space_coverage=False,
                           weight_variants_evaluated=False,
                           coverage_denominator="PROVIDED_EQUAL_WEIGHT_SECURITY_SETS_ONLY"))
