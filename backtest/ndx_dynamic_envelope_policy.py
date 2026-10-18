"""New one-sided research hypothesis; not the existing formal admission gate.

The old gate compares absolute target distances against an incumbent. This
diagnostic instead tests direct one-sided differences against the fund, and
separately tests already-paired incumbent statistics. Paired quantiles are
never inverted to infer marginal incumbent quantiles. All candidates remain
visible; no unique selection, execution fallback, or trading action exists.
"""
from datetime import date
import math
import re

import pandas as pd


DIMENSIONS = ("return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90")
FUND_COLUMNS = dict(zip(DIMENSIONS, (
    "return_p50_vs_012922", "return_p10_vs_012922",
    "max_drawdown_p50_vs_012922", "max_drawdown_p90_vs_012922")))
INCUMBENT_COLUMNS = dict(zip(DIMENSIONS, (
    "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent",
    "paired_drawdown_cost_p50_vs_incumbent", "paired_drawdown_cost_p90_vs_incumbent")))
GROUP_COLUMNS = ("source_batch", "universe_track", "selection_date")
IDENTITY_COLUMNS = ("tickers", "security_ids", "issuer_ids", "risk_chains")
REQUIRED_COLUMNS = set(GROUP_COLUMNS) | set(IDENTITY_COLUMNS) | set(DIMENSIONS) | {
    "decision_data_end", "portfolio_id", "holding_count", "weight_spec", "weights",
    "declared_constraints_passed", "return_basis", "fit_strictly_before_evaluation",
    "last_fit_evaluation_boundary", "rolling_fit_window_count",
} | set(FUND_COLUMNS.values()) | set(INCUMBENT_COLUMNS.values())
USER_PREFERENCE = frozenset(("AMAT", "AVGO", "CDNS", "GOOG"))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, label):
    _require(isinstance(value, str) and value and value == value.strip(), f"Invalid {label}")
    return value


def _session(value, label):
    _text(value, label)
    _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, f"Noncanonical {label}")
    parsed = date.fromisoformat(value)
    _require(parsed.isoformat() == value, f"Noncanonical {label}")
    return parsed


def _number(value, label):
    _require(not isinstance(value, bool), f"Boolean is not a metric: {label}")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid numeric {label}") from exc
    _require(math.isfinite(number), f"Nonfinite {label}")
    return number


def _integer(value, label):
    number = _number(value, label)
    _require(number.is_integer() and number > 0, f"Invalid positive integer {label}")
    return int(number)


def _boolean(value, label):
    if isinstance(value, bool):
        return value
    _require(isinstance(value, str) and value in ("True", "False", "true", "false"),
             f"Invalid boolean {label}")
    return value.lower() == "true"


def _items(value, label):
    return [_text(item, label) for item in _text(value, label).split(";")]


def _validate_row(raw):
    group = tuple(_text(raw[name], name) for name in GROUP_COLUMNS)
    execution = _session(raw["selection_date"], "selection_date")
    cutoff = _session(raw["decision_data_end"], "decision_data_end")
    _require(cutoff < execution, "Decision cutoff must precede execution")
    _require(_boolean(raw["fit_strictly_before_evaluation"], "fit flag"),
             "Historical fit-before-evaluation declaration failed")
    boundary = _text(raw["last_fit_evaluation_boundary"], "fit boundary").split("<")
    _require(len(boundary) == 2, "Invalid historical fit boundary")
    fit, evaluation = (_session(value, "fit/evaluation date") for value in boundary)
    _require(fit < evaluation <= cutoff, "Historical fit boundary exceeds decision cutoff")
    _require(raw["return_basis"] == "NET_OF_MODELED_ENTRY_TURNOVER_COST", "Unknown return basis")
    rolling_windows = _integer(raw["rolling_fit_window_count"], "rolling_fit_window_count")
    count = _integer(raw["holding_count"], "holding_count")
    identity = {name: _items(raw[name], name) for name in IDENTITY_COLUMNS}
    _require(all(len(values) == count for values in identity.values()), "Identity cardinality mismatch")
    for name in ("tickers", "security_ids", "issuer_ids"):
        _require(len(set(identity[name])) == count, f"Duplicate {name}")
    _require(all(value.startswith("security:") and len(value) > 9 for value in identity["security_ids"]),
             "Invalid security_id namespace")
    _require(all(value.startswith("issuer:") and len(value) > 7 for value in identity["issuer_ids"]),
             "Invalid issuer_id namespace")
    weights = {}
    for item in _items(raw["weights"], "weights"):
        ticker, separator, value = item.rpartition(":")
        _require(separator and ticker and ticker not in weights, "Duplicate/malformed weight")
        weights[ticker] = _number(value, "weight")
        _require(weights[ticker] > 0, "Nonpositive weight")
    _require(set(weights) == set(identity["tickers"]), "Weight identity mismatch")
    _require(math.isclose(sum(weights.values()), 1., rel_tol=0., abs_tol=1e-6), "Weights do not sum to one")
    if raw['weight_spec'] == 'equal_weight':
        _require(all(math.isclose(value, 1. / count, rel_tol=0., abs_tol=1e-9)
                     for value in weights.values()), 'Equal-weight specification disagrees with weights')
    metrics = {name: _number(raw[name], name) for name in
               set(DIMENSIONS) | set(FUND_COLUMNS.values()) | set(INCUMBENT_COLUMNS.values())}
    _require(metrics["return_p50"] >= metrics["return_p10"] >= -1., "Invalid return quantile order")
    _require(0 <= metrics["max_drawdown_p50"] <= metrics["max_drawdown_p90"] <= 1.,
             "Invalid drawdown quantile order")
    _require(metrics["paired_return_p50_vs_incumbent"] >= metrics["paired_return_p10_vs_incumbent"],
             "Invalid paired return quantile order")
    _require(metrics["paired_drawdown_cost_p50_vs_incumbent"]
             <= metrics["paired_drawdown_cost_p90_vs_incumbent"], "Invalid paired drawdown quantile order")
    row = dict(portfolio_id=_text(raw["portfolio_id"], "portfolio_id"), holding_count=count,
               weight_spec=_text(raw["weight_spec"], "weight_spec"), tickers=identity["tickers"],
               weights=dict(sorted(weights.items())),
               identities=[dict(ticker=ticker, security_id=security, issuer_id=issuer, risk_chain=chain)
                           for ticker, security, issuer, chain in zip(*(identity[name] for name in IDENTITY_COLUMNS))],
               source_declared_constraints_passed=_boolean(raw["declared_constraints_passed"], "constraints flag"),
               training_metrics={name: metrics[name] for name in DIMENSIONS},
               rolling_fit_window_count=rolling_windows,
               source_fit_boundary=raw["last_fit_evaluation_boundary"],
               source_declarations_are_not_full_pit_proof=True)
    row["user_preference_reference"] = (set(identity["tickers"]) == USER_PREFERENCE
                                        and row["weight_spec"] == "equal_weight"
                                        and all(math.isclose(value, .25, rel_tol=0., abs_tol=1e-9)
                                                for value in weights.values()))
    return group, cutoff.isoformat(), row, metrics


def _diagnostic(metrics, columns):
    differences = {dimension: metrics[column] for dimension, column in columns.items()}
    margins = {dimension: value if dimension.startswith("return") else -value
               for dimension, value in differences.items()}
    noninferior = all(value >= 0. for value in margins.values())
    strict = any(value > 0. for value in margins.values())
    return dict(source_differences=differences, margins=margins,
                deficits={dimension: max(0., -value) for dimension, value in margins.items()},
                componentwise_noninferior=noninferior, has_strict_improvement=strict,
                noninferior_with_strict_improvement=noninferior and strict,
                failed_dimensions=[dimension for dimension, value in margins.items() if value < 0.])


def evaluate_componentwise_envelope_candidates(candidates: pd.DataFrame) -> dict:
    """Preserve grouped candidates and report direct-fund/paired-incumbent gaps.

    source_batch must be supplied by the caller's verified source manifest;
    this pure function cannot authenticate external provenance. Zero is the
    exact research comparison boundary, with no fitted tolerance or weighting.
    Deficit Pareto is economic-only and never filters the qualified collection.
    """
    _require(isinstance(candidates, pd.DataFrame) and not candidates.empty, "Candidates must be nonempty")
    _require(not candidates.columns.duplicated().any(), "Duplicate input columns")
    _require(REQUIRED_COLUMNS.issubset(candidates.columns),
             f"Missing required fields: {sorted(REQUIRED_COLUMNS - set(candidates.columns))}")
    groups, keys = {}, set()
    for raw in candidates.to_dict("records"):
        group_key, cutoff, row, metrics = _validate_row(raw)
        candidate_key = (*group_key, row["portfolio_id"])
        _require(candidate_key not in keys, "Duplicate scoped candidate key")
        keys.add(candidate_key)
        group = groups.setdefault(group_key, dict(zip(GROUP_COLUMNS, group_key),
                                                 decision_data_end=cutoff, candidates=[]))
        _require(group["decision_data_end"] == cutoff, "Inconsistent decision cutoff within group")
        row["fund"] = _diagnostic(metrics, FUND_COLUMNS)
        row["incumbent"] = _diagnostic(metrics, INCUMBENT_COLUMNS)
        row["dual_benchmark_qualified"] = (row["source_declared_constraints_passed"]
            and row["fund"]["noninferior_with_strict_improvement"]
            and row["incumbent"]["noninferior_with_strict_improvement"])
        group["candidates"].append(row)
    output = []
    for key in sorted(groups):
        group = groups[key]
        rows = sorted(group["candidates"], key=lambda row: row["portfolio_id"])
        vectors = {row["portfolio_id"]: tuple(row[benchmark]["deficits"][dimension]
                   for benchmark in ("fund", "incumbent") for dimension in DIMENSIONS) for row in rows}
        unique_vectors = set(vectors.values())
        frontier = {vector for vector in unique_vectors if not any(
            all(left <= right for left, right in zip(other, vector))
            and any(left < right for left, right in zip(other, vector))
            for other in unique_vectors)}
        group.update(candidates=rows,
                     dual_benchmark_qualified_ids=[row["portfolio_id"] for row in rows if row["dual_benchmark_qualified"]],
                     deficit_pareto_ids=[row["portfolio_id"] for row in rows if vectors[row["portfolio_id"]] in frontier],
                     economic_only_frontier=True, frontier_filters_qualified_set=False,
                     no_unique_selection=True)
        group.update(
            qualification_status=('COMPONENTWISE_FEASIBLE_CANDIDATES_PRESENT'
                if group['dual_benchmark_qualified_ids'] else 'NO_COMPONENTWISE_FEASIBLE_CANDIDATE'),
            qualification_requires_source_constraints_and_both_strict_improvements=True,
            feasibility_scope='SUPPLIED_RESEARCH_CANDIDATES_ONLY',
            global_infeasibility_proven=False)
        output.append(group)
    return dict(hypothesis="NEW_ONE_SIDED_RESEARCH_HYPOTHESIS", research_only=True,
                admission_allowed=False, promotion_allowed=False, live_mutation_allowed=False,
                order_creation_allowed=False, existing_formal_gate_equivalent=False,
                paired_quantiles_are_not_marginal_quantile_differences=True,
                candidate_count=len(keys), groups=output)
