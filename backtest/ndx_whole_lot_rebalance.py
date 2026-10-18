"""Point-in-time ticker stitching and continuous whole-lot rebalancing."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from data.ndx_security_identity import SecurityLifecycle, SecurityLifecycleRule
from data.versioning import file_sha256


class NdxWholeLotRebalanceError(ValueError):
    pass


def _load_bars(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise NdxWholeLotRebalanceError(f"price file missing: {path}")
    frame = pd.read_csv(path, usecols=["Date", "Close", "Volume"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame["Volume"] = pd.to_numeric(frame["Volume"], errors="coerce")
    if frame.isna().any().any() or frame["Date"].duplicated().any():
        raise NdxWholeLotRebalanceError(f"invalid price bars: {path}")
    if not frame["Date"].is_monotonic_increasing:
        raise NdxWholeLotRebalanceError(f"unsorted price bars: {path}")
    if (~np.isfinite(frame[["Close", "Volume"]])).any().any():
        raise NdxWholeLotRebalanceError(f"non-finite price bars: {path}")
    if (frame["Close"] <= 0).any() or (frame["Volume"] < 0).any():
        raise NdxWholeLotRebalanceError(f"non-positive price bars: {path}")
    return frame.set_index("Date")


def lifecycle_rule_for_security(
    security_id: str,
    lifecycle: SecurityLifecycle,
) -> SecurityLifecycleRule | None:
    parts = str(security_id).split(":")
    if len(parts) < 3 or parts[0] != "security" or not parts[1].isdigit():
        raise NdxWholeLotRebalanceError(f"invalid security_id: {security_id!r}")
    return lifecycle.rules_by_cik.get(f"{int(parts[1]):010d}")


def load_point_in_time_security_bars(
    *,
    ticker: str,
    security_id: str,
    return_cache_dir: Path,
    lifecycle: SecurityLifecycle,
    end_exclusive: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load one security strictly before a cutoff, stitching reviewed ticker eras."""
    cutoff = pd.Timestamp(end_exclusive).normalize()
    rule = lifecycle_rule_for_security(security_id, lifecycle)
    if rule is None:
        path = return_cache_dir / f"{ticker}.csv"
        result = _load_bars(path).loc[lambda frame: frame.index < cutoff].copy()
        if result.empty:
            raise NdxWholeLotRebalanceError(f"no pre-cutoff bars for {ticker}")
        return result, {
            "ticker": ticker,
            "security_id": security_id,
            "lifecycle_rule_id": "",
            "source_tickers": ticker,
            "source_files": path.as_posix(),
            "source_sha256": file_sha256(path),
            "segment_count": 1,
            "cross_ticker_stitched": False,
            "data_start": result.index.min().date().isoformat(),
            "data_end": result.index.max().date().isoformat(),
            "rows": len(result),
        }
    if ticker not in rule.recognized_tickers:
        raise NdxWholeLotRebalanceError(
            f"{rule.rule_id}: ticker {ticker} is not recognized for {security_id}"
        )
    segments: list[pd.DataFrame] = []
    source_rows: list[dict[str, Any]] = []
    for interval in rule.intervals:
        if interval.effective_from is not None and interval.effective_from >= cutoff:
            continue
        path = return_cache_dir / f"{interval.price_ticker}.csv"
        frame = _load_bars(path)
        mask = frame.index < cutoff
        if interval.effective_from is not None:
            mask &= frame.index >= interval.effective_from
        if interval.effective_to is not None:
            mask &= frame.index <= interval.effective_to
        segment = frame.loc[mask].copy()
        if segment.empty:
            continue
        segment["source_price_ticker"] = interval.price_ticker
        segments.append(segment)
        source_rows.append({
            "ticker": interval.price_ticker,
            "path": path.as_posix(),
            "sha256": file_sha256(path),
            "rows": len(segment),
            "start": segment.index.min().date().isoformat(),
            "end": segment.index.max().date().isoformat(),
        })
    if not segments:
        raise NdxWholeLotRebalanceError(
            f"{rule.rule_id}: no lifecycle bars strictly before {cutoff.date()}"
        )
    result = pd.concat(segments).sort_index(kind="stable")
    if result.index.duplicated().any():
        raise NdxWholeLotRebalanceError(f"{rule.rule_id}: stitched dates overlap")
    used_tickers = [row["ticker"] for row in source_rows]
    return result, {
        "ticker": ticker,
        "security_id": security_id,
        "lifecycle_rule_id": rule.rule_id,
        "source_tickers": ";".join(used_tickers),
        "source_files": ";".join(row["path"] for row in source_rows),
        "source_sha256": ";".join(row["sha256"] for row in source_rows),
        "segment_count": len(source_rows),
        "cross_ticker_stitched": len(set(used_tickers)) > 1,
        "data_start": result.index.min().date().isoformat(),
        "data_end": result.index.max().date().isoformat(),
        "rows": len(result),
    }


def _constraint_snapshot(
    notionals: Mapping[str, float],
    *,
    risk_chain_by_ticker: Mapping[str, str],
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    invested = float(sum(notionals.values()))
    if invested <= 0:
        return {
            "top1": 1.0, "top3": 1.0, "effective_n": 0.0,
            "risk_chain_top1": 1.0, "constraints_passed": False,
        }
    weights = {ticker: value / invested for ticker, value in notionals.items()}
    ordered = sorted(weights.values(), reverse=True)
    chain_weights: dict[str, float] = {}
    for ticker, weight in weights.items():
        chain = str(risk_chain_by_ticker.get(ticker) or "")
        if not chain:
            raise NdxWholeLotRebalanceError(f"risk-chain missing for {ticker}")
        chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
    effective_n = 1.0 / sum(value * value for value in weights.values())
    passed = bool(
        max(ordered) <= max_single_weight + 1e-9
        and min(ordered) >= min_single_weight - 1e-9
        and sum(ordered[:3]) <= top_weight_cap + 1e-9
        and effective_n >= minimum_effective_n_ratio * len(weights) - 1e-9
        and max(chain_weights.values()) <= risk_chain_top1_cap + 1e-9
    )
    return {
        "top1": max(ordered),
        "top3": sum(ordered[:3]),
        "effective_n": effective_n,
        "risk_chain_top1": max(chain_weights.values()),
        "constraints_passed": passed,
    }


def simulate_continuous_whole_lot_rebalance(
    prices: pd.DataFrame,
    schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Self-financing whole-share path; cash and shares carry across rebalances."""
    items = [(pd.Timestamp(date).normalize(), dict(weights)) for date, weights in schedule]
    if not items or items != sorted(items, key=lambda item: item[0]):
        raise NdxWholeLotRebalanceError("rebalance schedule must be nonempty and sorted")
    if len({date for date, _ in items}) != len(items):
        raise NdxWholeLotRebalanceError("rebalance schedule dates must be unique")
    tickers = sorted(items[0][1])
    if not tickers or any(sorted(weights) != tickers for _, weights in items):
        raise NdxWholeLotRebalanceError("rebalance schedule ticker set changed")
    if not set(tickers).issubset(prices.columns):
        raise NdxWholeLotRebalanceError("execution price columns are missing")
    path = prices.loc[items[0][0]:, tickers].copy()
    if path.empty or any(date not in path.index for date, _ in items):
        raise NdxWholeLotRebalanceError("rebalance date is absent from execution prices")
    if path.isna().any().any() or (~np.isfinite(path)).any().any() or (path <= 0).any().any():
        raise NdxWholeLotRebalanceError("execution prices are not positive finite")
    cash = float(portfolio_cash_usd)
    buffer = float(minimum_cash_buffer_usd)
    bps = float(transaction_cost_bps)
    if not np.isfinite(cash) or not 0 <= buffer < cash or bps < 0:
        raise NdxWholeLotRebalanceError("whole-lot execution contract is invalid")
    fee_rate = bps / 10000.0
    shares = {ticker: 0 for ticker in tickers}
    schedule_by_date = {date: weights for date, weights in items}
    ledger: list[dict[str, Any]] = []
    values: list[float] = []
    constraints_all_days = True
    minimum_cash = cash
    total_cost = 0.0
    total_trade_notional = 0.0
    share_change_count = 0
    initial_shares = ""
    for date, row in path.iterrows():
        marks = {ticker: float(row[ticker]) for ticker in tickers}
        if date in schedule_by_date:
            weights = {ticker: float(schedule_by_date[date][ticker]) for ticker in tickers}
            if any(not np.isfinite(value) or value <= 0 for value in weights.values()):
                raise NdxWholeLotRebalanceError("target weights must be positive finite")
            total_weight = sum(weights.values())
            weights = {ticker: value / total_weight for ticker, value in weights.items()}
            pretrade_equity = cash + sum(shares[ticker] * marks[ticker] for ticker in tickers)
            investable = max(0.0, pretrade_equity - buffer)
            desired = {
                ticker: int(math.floor(investable * weights[ticker] / marks[ticker]))
                for ticker in tickers
            }
            def projected_cash(target: Mapping[str, int]) -> tuple[float, float, float]:
                buy = sum(max(0, target[t] - shares[t]) * marks[t] for t in tickers)
                sell = sum(max(0, shares[t] - target[t]) * marks[t] for t in tickers)
                fees = (buy + sell) * fee_rate
                return cash + sell - buy - fees, buy + sell, fees
            after_cash, traded, fees = projected_cash(desired)
            while after_cash < buffer - 1e-9:
                reducible = [ticker for ticker in tickers if desired[ticker] > shares[ticker]]
                if not reducible:
                    raise NdxWholeLotRebalanceError("transaction costs breach cash buffer")
                ticker = max(reducible, key=lambda name: (marks[name], name))
                desired[ticker] -= 1
                after_cash, traded, fees = projected_cash(desired)
            changes = sum(desired[ticker] != shares[ticker] for ticker in tickers)
            share_change_count += changes
            shares = desired
            cash = after_cash
            total_trade_notional += traded
            total_cost += fees
            notionals = {ticker: shares[ticker] * marks[ticker] for ticker in tickers}
            snapshot = _constraint_snapshot(
                notionals,
                risk_chain_by_ticker=risk_chain_by_ticker,
                max_single_weight=max_single_weight,
                min_single_weight=min_single_weight,
                top_weight_cap=top_weight_cap,
                minimum_effective_n_ratio=minimum_effective_n_ratio,
                risk_chain_top1_cap=risk_chain_top1_cap,
            )
            if not initial_shares:
                initial_shares = ";".join(f"{ticker}:{shares[ticker]}" for ticker in tickers)
            ledger.append({
                "rebalance_date": date.date().isoformat(),
                "pretrade_equity_usd": pretrade_equity,
                "posttrade_cash_usd": cash,
                "traded_notional_usd": traded,
                "transaction_cost_usd": fees,
                "changed_ticker_count": changes,
                "shares": ";".join(f"{ticker}:{shares[ticker]}" for ticker in tickers),
                **snapshot,
            })
        notionals = {ticker: shares[ticker] * marks[ticker] for ticker in tickers}
        snapshot = _constraint_snapshot(
            notionals,
            risk_chain_by_ticker=risk_chain_by_ticker,
            max_single_weight=max_single_weight,
            min_single_weight=min_single_weight,
            top_weight_cap=top_weight_cap,
            minimum_effective_n_ratio=minimum_effective_n_ratio,
            risk_chain_top1_cap=risk_chain_top1_cap,
        )
        constraints_all_days &= bool(snapshot["constraints_passed"])
        minimum_cash = min(minimum_cash, cash)
        values.append(cash + sum(notionals.values()))
    series = pd.Series(values, index=path.index, dtype=float)
    drawdown = 1.0 - series / series.cummax()
    ledger_frame = pd.DataFrame(ledger)
    records = ledger_frame.to_dict("records")
    trace_hash = hashlib.sha256(
        json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    terminal_shares = ";".join(f"{ticker}:{shares[ticker]}" for ticker in tickers)
    summary = {
        "whole_lot_rebalance_count": len(ledger),
        "whole_lot_initial_shares": initial_shares,
        "whole_lot_terminal_shares": terminal_shares,
        "whole_lot_share_change_count": share_change_count,
        "whole_lot_total_trade_notional_usd": total_trade_notional,
        "whole_lot_total_transaction_cost_usd": total_cost,
        "whole_lot_min_cash_usd": minimum_cash,
        "whole_lot_cash_buffer_preserved": minimum_cash >= buffer - 1e-9,
        "whole_lot_constraints_preserved_all_days": constraints_all_days,
        "whole_lot_terminal_value_usd": float(series.iloc[-1]),
        "whole_lot_path_return_net": float(series.iloc[-1] / portfolio_cash_usd - 1.0),
        "whole_lot_path_max_drawdown": float(drawdown.max()),
        "whole_lot_rebalance_trace_sha256": trace_hash,
        "whole_lot_execution_mode": "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES",
    }
    return summary, ledger_frame


__all__ = [
    "NdxWholeLotRebalanceError",
    "lifecycle_rule_for_security",
    "load_point_in_time_security_bars",
    "simulate_continuous_whole_lot_rebalance",
]
