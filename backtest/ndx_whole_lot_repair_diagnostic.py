"""Research-only floor/ceil whole-lot rebalance projection.

This module isolates one execution mechanism from portfolio selection.  It does
not change the ticker set, target weights, rebalance date, risk thresholds, or
capital.  The search is deliberately limited to the floor/ceil neighborhood of
the supplied target notionals and therefore makes no claim about the full
integer allocation space or about portfolio optimality.

The older ``repair_whole_lot_allocation`` helper is not called here because it
starts from fresh cash and does not price the buys and sells from an existing
position with bilateral transaction costs.  Its deterministic,
constraint-first intent is retained, but the accounting below is continuous
from the caller-supplied shares and cash.
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Mapping
from typing import Any


class NdxWholeLotRepairDiagnosticError(ValueError):
    """Raised when a research projection input violates the fixed contract."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NdxWholeLotRepairDiagnosticError(f"{field} must be finite numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxWholeLotRepairDiagnosticError(
            f"{field} must be finite numeric"
        ) from exc
    if not math.isfinite(result):
        raise NdxWholeLotRepairDiagnosticError(f"{field} must be finite numeric")
    return result


def _whole_quantity(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise NdxWholeLotRepairDiagnosticError(
            f"{field} must be a nonnegative whole-share quantity"
        )
    return value


def _empty_result(
    *,
    status: str,
    search_complete: bool,
    search_space_size: int,
    max_evaluations: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "research_only": True,
        "research_track": "portfolio_optimization_execution_diagnostic",
        "candidate_set_changed": False,
        "target_weights_changed": False,
        "rebalance_cadence_changed": False,
        "risk_thresholds_changed": False,
        "issuer_uniqueness_checked": False,
        "search_space": "PER_TICKER_TARGET_NOTIONAL_FLOOR_OR_CEIL_ONLY",
        "search_space_size": search_space_size,
        "max_evaluations": max_evaluations,
        "evaluations_completed": 0,
        "search_complete": search_complete,
        "feasible_projection_found": False,
        "projected_shares": {},
        "portfolio_optimality_claimed": False,
        "full_integer_space_infeasibility_claimed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def project_whole_lot_rebalance(
    *,
    current_shares: Mapping[str, int],
    current_cash_usd: float,
    prices: Mapping[str, float],
    target_weights: Mapping[str, float],
    risk_chain_by_ticker: Mapping[str, str],
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
    max_evaluations: int = 262_144,
) -> dict[str, Any]:
    """Project one rebalance within the complete per-ticker floor/ceil set.

    A completed feasible result is selected by a deterministic tuple:
    risky-weight L1 drift, maximum absolute drift, traded notional, and the
    lexicographically ordered share vector.  If the complete neighborhood is
    larger than ``max_evaluations``, no partial allocation is returned.
    """

    if not isinstance(current_shares, Mapping) or not current_shares:
        raise NdxWholeLotRepairDiagnosticError("current_shares must be nonempty")
    if any(
        not isinstance(ticker, str)
        or not ticker
        or ticker != ticker.strip()
        for ticker in current_shares
    ):
        raise NdxWholeLotRepairDiagnosticError(
            "ticker identities must be canonical nonempty strings"
        )
    tickers = sorted(current_shares)
    expected = set(tickers)
    for name, values in (
        ("prices", prices),
        ("target_weights", target_weights),
        ("risk_chain_by_ticker", risk_chain_by_ticker),
    ):
        if not isinstance(values, Mapping) or set(values) != expected:
            raise NdxWholeLotRepairDiagnosticError(
                f"{name} must cover exactly the current ticker set"
            )

    shares = {
        ticker: _whole_quantity(current_shares[ticker], f"shares[{ticker}]")
        for ticker in tickers
    }
    marks = {ticker: _finite(prices[ticker], f"price[{ticker}]") for ticker in tickers}
    if any(value <= 0 for value in marks.values()):
        raise NdxWholeLotRepairDiagnosticError("prices must be positive")
    weights = {
        ticker: _finite(target_weights[ticker], f"weight[{ticker}]")
        for ticker in tickers
    }
    if any(value <= 0 for value in weights.values()):
        raise NdxWholeLotRepairDiagnosticError("target weights must be positive")
    total_weight = sum(weights.values())
    if not math.isclose(total_weight, 1.0, rel_tol=0.0, abs_tol=1e-8):
        raise NdxWholeLotRepairDiagnosticError("target weights must sum to one")
    weights = {ticker: value / total_weight for ticker, value in weights.items()}
    if any(
        not isinstance(risk_chain_by_ticker[ticker], str)
        or not risk_chain_by_ticker[ticker]
        or risk_chain_by_ticker[ticker] != risk_chain_by_ticker[ticker].strip()
        for ticker in tickers
    ):
        raise NdxWholeLotRepairDiagnosticError(
            "risk-chain identities must be canonical nonempty strings"
        )
    chains = {ticker: risk_chain_by_ticker[ticker] for ticker in tickers}

    cash = _finite(current_cash_usd, "current_cash_usd")
    buffer = _finite(minimum_cash_buffer_usd, "minimum_cash_buffer_usd")
    bps = _finite(transaction_cost_bps, "transaction_cost_bps")
    thresholds = {
        "max_single_weight": _finite(max_single_weight, "max_single_weight"),
        "min_single_weight": _finite(min_single_weight, "min_single_weight"),
        "top_weight_cap": _finite(top_weight_cap, "top_weight_cap"),
        "minimum_effective_n_ratio": _finite(
            minimum_effective_n_ratio, "minimum_effective_n_ratio"
        ),
        "risk_chain_top1_cap": _finite(
            risk_chain_top1_cap, "risk_chain_top1_cap"
        ),
    }
    if cash < 0 or buffer < 0 or bps < 0:
        raise NdxWholeLotRepairDiagnosticError(
            "cash, cash buffer, and transaction cost must be nonnegative"
        )
    if not (
        0 <= thresholds["min_single_weight"] <= thresholds["max_single_weight"] <= 1
        and 0 <= thresholds["top_weight_cap"] <= 1
        and 0 <= thresholds["minimum_effective_n_ratio"] <= 1
        and 0 <= thresholds["risk_chain_top1_cap"] <= 1
    ):
        raise NdxWholeLotRepairDiagnosticError("risk thresholds are outside [0, 1]")
    if isinstance(max_evaluations, bool) or not isinstance(max_evaluations, int):
        raise NdxWholeLotRepairDiagnosticError("max_evaluations must be an integer")
    if max_evaluations <= 0:
        raise NdxWholeLotRepairDiagnosticError("max_evaluations must be positive")

    pretrade_holdings = sum(shares[ticker] * marks[ticker] for ticker in tickers)
    pretrade_equity = cash + pretrade_holdings
    if not math.isfinite(pretrade_equity) or pretrade_equity <= buffer:
        raise NdxWholeLotRepairDiagnosticError(
            "pretrade equity must be finite and exceed the cash buffer"
        )
    investable = pretrade_equity - buffer
    share_options: dict[str, tuple[int, ...]] = {}
    for ticker in tickers:
        raw_target = investable * weights[ticker] / marks[ticker]
        if not math.isfinite(raw_target):
            raise NdxWholeLotRepairDiagnosticError(
                f"target share coordinate overflowed for {ticker}"
            )
        lower = int(math.floor(raw_target))
        upper = int(math.ceil(raw_target))
        share_options[ticker] = (lower,) if lower == upper else (lower, upper)
    floor_shares = {ticker: share_options[ticker][0] for ticker in tickers}
    search_space_size = math.prod(len(share_options[ticker]) for ticker in tickers)
    if search_space_size > max_evaluations:
        return _empty_result(
            status="RESEARCH_SEARCH_BUDGET_EXHAUSTED",
            search_complete=False,
            search_space_size=search_space_size,
            max_evaluations=max_evaluations,
        )

    fee_rate = bps / 10_000.0
    best: tuple[tuple[Any, ...], dict[str, Any]] | None = None
    evaluations = 0
    for quantities in itertools.product(*(share_options[ticker] for ticker in tickers)):
        candidate = {
            ticker: quantities[index]
            for index, ticker in enumerate(tickers)
        }
        evaluations += 1
        buy_notional = sum(
            max(0, candidate[ticker] - shares[ticker]) * marks[ticker]
            for ticker in tickers
        )
        sell_notional = sum(
            max(0, shares[ticker] - candidate[ticker]) * marks[ticker]
            for ticker in tickers
        )
        traded_notional = buy_notional + sell_notional
        transaction_cost = traded_notional * fee_rate
        posttrade_cash = cash + sell_notional - buy_notional - transaction_cost
        notionals = {
            ticker: candidate[ticker] * marks[ticker] for ticker in tickers
        }
        invested = sum(notionals.values())
        if (
            min(candidate.values()) < 1
            or posttrade_cash < buffer - 1e-9
            or invested <= 0
        ):
            continue
        actual_weights = {
            ticker: notionals[ticker] / invested for ticker in tickers
        }
        ordered = sorted(actual_weights.values(), reverse=True)
        effective_n = 1.0 / sum(value * value for value in ordered)
        chain_weights: dict[str, float] = {}
        for ticker, weight in actual_weights.items():
            chain = chains[ticker]
            chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
        checks = {
            "whole_lot": True,
            "cash_buffer": posttrade_cash >= buffer - 1e-9,
            "min_single_weight": ordered[-1]
            >= thresholds["min_single_weight"] - 1e-9,
            "max_single_weight": ordered[0]
            <= thresholds["max_single_weight"] + 1e-9,
            "top3_weight": sum(ordered[:3])
            <= thresholds["top_weight_cap"] + 1e-9,
            "minimum_effective_n": effective_n
            >= thresholds["minimum_effective_n_ratio"] * len(tickers) - 1e-9,
            "risk_chain_top1_weight": max(chain_weights.values())
            <= thresholds["risk_chain_top1_cap"] + 1e-9,
        }
        if not all(checks.values()):
            continue
        differences = {
            ticker: actual_weights[ticker] - weights[ticker] for ticker in tickers
        }
        score = (
            sum(abs(value) for value in differences.values()),
            max(abs(value) for value in differences.values()),
            traded_notional,
            tuple(candidate[ticker] for ticker in tickers),
        )
        payload = {
            "projected_shares": candidate,
            "buy_notional_usd": buy_notional,
            "sell_notional_usd": sell_notional,
            "traded_notional_usd": traded_notional,
            "transaction_cost_usd": transaction_cost,
            "posttrade_cash_usd": posttrade_cash,
            "posttrade_invested_usd": invested,
            "posttrade_equity_usd": posttrade_cash + invested,
            "actual_risky_weights": actual_weights,
            "minimum_single_weight": ordered[-1],
            "maximum_single_weight": ordered[0],
            "top3_weight": sum(ordered[:3]),
            "effective_n": effective_n,
            "risk_chain_top1_weight": max(chain_weights.values()),
            "risk_chain_weights": dict(sorted(chain_weights.items())),
            "risky_weight_l1_drift": score[0],
            "risky_weight_max_abs_drift": score[1],
            "constraint_checks": checks,
        }
        if best is None or score < best[0]:
            best = (score, payload)

    if best is None:
        result = _empty_result(
            status="NO_FEASIBLE_PROJECTION_IN_COMPLETE_FLOOR_CEIL_NEIGHBORHOOD",
            search_complete=True,
            search_space_size=search_space_size,
            max_evaluations=max_evaluations,
        )
        result["evaluations_completed"] = evaluations
        return result

    result = _empty_result(
        status="FEASIBLE_RESEARCH_PROJECTION_FOUND",
        search_complete=True,
        search_space_size=search_space_size,
        max_evaluations=max_evaluations,
    )
    result.update(best[1])
    result.update(
        {
            "evaluations_completed": evaluations,
            "feasible_projection_found": True,
            "pretrade_cash_usd": cash,
            "pretrade_holdings_usd": pretrade_holdings,
            "pretrade_equity_usd": pretrade_equity,
            "floor_shares": floor_shares,
            "accounting_conservation_error_usd": (
                result["posttrade_equity_usd"]
                - (pretrade_equity - result["transaction_cost_usd"])
            ),
            "deterministic_tie_break": (
                "MIN_L1_THEN_MAX_ABS_DRIFT_THEN_TRADE_NOTIONAL_THEN_SHARES"
            ),
        }
    )
    return result


__all__ = [
    "NdxWholeLotRepairDiagnosticError",
    "project_whole_lot_rebalance",
]
