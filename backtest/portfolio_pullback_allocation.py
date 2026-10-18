"""Research-only pooled-reserve whole-lot allocation helpers.

This module deliberately contains no live configuration, state, advice, or
order mutation.  It converts a fixed cash budget and pre-registered target
weights into the closest affordable whole-share basket.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


class PortfolioPullbackAllocationError(ValueError):
    """Raised when a pooled-reserve allocation contract is invalid."""


@dataclass(frozen=True)
class WholeLotAllocation:
    shares: dict[str, int]
    notionals: dict[str, float]
    fees_usd: float
    residual_cash_usd: float
    deployment_ratio: float
    target_l1_drift: float
    top1_weight: float
    top3_weight: float
    effective_n: float


def parse_weight_map(value: str | Mapping[str, float]) -> dict[str, float]:
    """Parse and strictly normalize ``TICKER:weight`` target weights."""
    if isinstance(value, str):
        items: dict[str, float] = {}
        for token in value.split(";"):
            if not token.strip():
                continue
            ticker, separator, raw = token.partition(":")
            if not separator:
                raise PortfolioPullbackAllocationError("invalid target weight token")
            items[ticker.strip().upper()] = float(raw)
    else:
        items = {str(ticker).upper(): float(weight) for ticker, weight in value.items()}
    if not items or any(not math.isfinite(weight) or weight <= 0 for weight in items.values()):
        raise PortfolioPullbackAllocationError("target weights must be positive finite values")
    total = sum(items.values())
    if not math.isfinite(total) or total <= 0:
        raise PortfolioPullbackAllocationError("target weight sum must be positive")
    return {ticker: weight / total for ticker, weight in sorted(items.items())}


def _shape(notionals: Mapping[str, float]) -> tuple[float, float, float]:
    invested = sum(notionals.values())
    if invested <= 0:
        return 0.0, 0.0, 0.0
    weights = sorted((value / invested for value in notionals.values() if value > 0), reverse=True)
    return weights[0], sum(weights[:3]), 1.0 / sum(weight * weight for weight in weights)


def allocate_whole_lots(
    budget_usd: float,
    target_weights: str | Mapping[str, float],
    limit_prices: Mapping[str, float],
    *,
    fee_bps: float = 0.0,
) -> WholeLotAllocation:
    """Find the affordable whole-share basket closest to fixed target weights.

    The search is exact for the supplied small registered basket.  The score is
    squared tracking error over the original cash budget, including residual
    cash as an untargeted asset.  Ties prefer higher deployment and then a
    stable ticker/share tuple.  No sale or fractional share is possible.
    """
    budget = float(budget_usd)
    bps = float(fee_bps)
    targets = parse_weight_map(target_weights)
    prices = {ticker: float(limit_prices.get(ticker, 0.0)) for ticker in targets}
    if not math.isfinite(budget) or budget < 0 or not math.isfinite(bps) or bps < 0:
        raise PortfolioPullbackAllocationError("budget and fee must be non-negative finite values")
    if any(not math.isfinite(price) or price <= 0 for price in prices.values()):
        raise PortfolioPullbackAllocationError("every target requires a positive finite limit price")

    unit_costs = {ticker: price * (1.0 + bps / 10_000.0) for ticker, price in prices.items()}
    tickers = sorted(targets)
    best_key: tuple[float, float, tuple[int, ...]] | None = None
    best_shares: dict[str, int] = {ticker: 0 for ticker in tickers}

    def visit(index: int, remaining: float, shares: dict[str, int]) -> None:
        nonlocal best_key, best_shares
        if index == len(tickers):
            notionals = {ticker: shares[ticker] * prices[ticker] for ticker in tickers}
            fees = sum(notionals.values()) * bps / 10_000.0
            residual = max(0.0, budget - sum(notionals.values()) - fees)
            scale = budget if budget > 0 else 1.0
            error = sum(
                ((notionals[ticker] / scale) - targets[ticker]) ** 2
                for ticker in tickers
            ) + (residual / scale) ** 2
            invested = sum(notionals.values())
            signature = tuple(shares[ticker] for ticker in tickers)
            key = (round(error, 15), -round(invested, 8), signature)
            if best_key is None or key < best_key:
                best_key = key
                best_shares = dict(shares)
            return
        ticker = tickers[index]
        maximum = int(math.floor((remaining + 1e-9) / unit_costs[ticker]))
        for count in range(maximum + 1):
            shares[ticker] = count
            visit(index + 1, remaining - count * unit_costs[ticker], shares)

    visit(0, budget, {})
    notionals = {
        ticker: best_shares[ticker] * prices[ticker]
        for ticker in tickers
        if best_shares[ticker] > 0
    }
    fees = sum(notionals.values()) * bps / 10_000.0
    residual = max(0.0, budget - sum(notionals.values()) - fees)
    deployed = sum(notionals.values())
    scale = deployed if deployed > 0 else 1.0
    actual = {ticker: notionals.get(ticker, 0.0) / scale for ticker in tickers}
    l1_drift = sum(abs(actual[ticker] - targets[ticker]) for ticker in tickers)
    top1, top3, effective_n = _shape(notionals)
    return WholeLotAllocation(
        shares={ticker: count for ticker, count in best_shares.items() if count > 0},
        notionals=notionals,
        fees_usd=fees,
        residual_cash_usd=residual,
        deployment_ratio=deployed / budget if budget > 0 else 0.0,
        target_l1_drift=l1_drift,
        top1_weight=top1,
        top3_weight=top3,
        effective_n=effective_n,
    )


def risk_chain_shape(
    notionals: Mapping[str, float], risk_chains: Mapping[str, str]
) -> tuple[float, float]:
    """Return risk-chain Top1/Top3 weights for an allocated basket."""
    total = sum(float(value) for value in notionals.values())
    if total <= 0:
        return 0.0, 0.0
    chains: dict[str, float] = {}
    for ticker, value in notionals.items():
        chain = str(risk_chains.get(ticker) or "UNCLASSIFIED")
        chains[chain] = chains.get(chain, 0.0) + float(value) / total
    ordered = sorted(chains.values(), reverse=True)
    return ordered[0], sum(ordered[:3])


__all__ = [
    "PortfolioPullbackAllocationError",
    "WholeLotAllocation",
    "allocate_whole_lots",
    "parse_weight_map",
    "risk_chain_shape",
]
