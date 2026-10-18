r"""Audit portfolio-wide pullback response gaps using production signal code.

The audit is deliberately diagnostic.  For every signal date it truncates all
OHLC inputs to information available on that date, calls the production market
gate and tactical-order functions, and reports when the whole portfolio is
forced to WAIT.  It does not simulate a new strategy, calculate forward
returns, mutate live files, or create executable orders.

PowerShell:
    python -B scripts\portfolio_pullback_response_audit.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import server
from core.config import load_config
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio
from core.state import SymbolState
from data.versioning import file_sha256
from scripts.nvda_tactical_audit import _read_local_bars


DETAIL_COLUMNS = {
    "signal_date": "信号日期",
    "ticker": "标的",
    "close": "收盘价",
    "one_day_change": "当日涨跌幅",
    "stock_regime": "个股市况",
    "market_regime": "市场市况",
    "final_regime": "最终市况",
    "action": "战术动作",
    "amount": "策略预算",
    "limit": "固定限价",
    "blocked_by_market_bear": "是否被熊市门控阻断",
    "reserve_cash": "状态储备金",
    "reason": "原因",
}

DAILY_COLUMNS = {
    "signal_date": "信号日期",
    "market_regime": "市场市况",
    "ticker_count": "标的数",
    "down_count": "下跌标的数",
    "down_3pct_count": "跌幅至少3%的标的数",
    "down_5pct_count": "跌幅至少5%的标的数",
    "worst_one_day_change": "最差当日涨跌幅",
    "buy_now_count": "立即买入数",
    "place_limit_count": "限价候选数",
    "wait_count": "等待数",
    "blocked_by_market_bear_count": "被熊市门控阻断数",
    "all_tactical_wait": "是否全组合战术等待",
    "pullback_dead_zone": "是否出现组合回调死区",
    "gate_min_distance_to_ma50": "门控指数距MA50最小值",
}

CURRENT_COLUMNS = {
    "ticker": "标的",
    "signal_date": "信号日期",
    "close": "收盘价",
    "state_h": "状态H",
    "drawdown_from_state_h": "相对状态H回撤",
    "first_ratchet_threshold": "首档棘轮阈值",
    "first_ratchet_limit": "首档棘轮限价",
    "distance_to_first_ratchet": "距首档棘轮",
    "deep_ratchet_triggered": "深跌棘轮是否触发",
    "tactical_action": "战术动作",
    "tactical_limit": "战术限价",
    "blocked_by_market_bear": "是否被熊市门控阻断",
    "position_status": "持仓口径",
}


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _actual_state_for(ticker: str, portfolio) -> SymbolState | None:
    return portfolio.symbols.get(ticker) if portfolio is not None else None


def _signal_state_for(ticker: str, portfolio) -> SymbolState:
    """Use positive normalized reserve to isolate rule eligibility from stale account state."""
    actual = _actual_state_for(ticker, portfolio)
    return SymbolState(
        ticker=ticker,
        cap_total=float(actual.cap_total) if actual is not None else 1.0,
        reserve_cash=1_000_000.0,
    )


def _market_on_prefix(frames: dict[str, pd.DataFrame], cfg, signal_date: pd.Timestamp) -> dict:
    gate_tickers = [str(x).upper() for x in cfg.tactical_orders.market_gate_tickers]
    server._bars_cache.clear()
    for name, frame in frames.items():
        server._bars_cache[name] = frame.loc[:signal_date].copy()
    prices = {
        name: float(frames[name].loc[signal_date, "Close"])
        for name in gate_tickers
        if signal_date in frames[name].index
    }
    meta = {
        "items": {
            name: {
                "source": "local_cache",
                "mode": "daily_close",
                "previous_close": price,
                "quote_time": "",
                "market_time": "",
            }
            for name, price in prices.items()
        }
    }
    return server._market_phase_payload(cfg, prices, meta) or {
        "enabled": False, "regime": "UNKNOWN", "items": [], "errors": {}
    }


def replay_portfolio_response(
    frames: dict[str, pd.DataFrame],
    cfg,
    *,
    portfolio=None,
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Replay the production tactical stack without reading later bars."""
    tickers = [str(symbol.ticker).upper() for symbol in cfg.symbols]
    gate_tickers = (
        [str(x).upper() for x in cfg.tactical_orders.market_gate_tickers]
        if cfg.tactical_orders.market_gate_enabled else []
    )
    required = list(dict.fromkeys(tickers + gate_tickers))
    missing = [name for name in required if name not in frames]
    if missing:
        raise ValueError(f"missing local bars for {missing}")

    dates = frames[required[0]].index
    for name in required[1:]:
        dates = dates.intersection(frames[name].index)
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    if end:
        dates = dates[dates <= pd.Timestamp(end)]
    dates = dates.sort_values()

    detail_rows: list[dict] = []
    daily_rows: list[dict] = []
    gate_rows: list[dict] = []
    for signal_date in dates:
        market = _market_on_prefix(frames, cfg, signal_date)
        gate_distances = []
        for item in market.get("items") or []:
            price = float(item.get("signal_price") or 0.0)
            ma50 = float(item.get("ma50") or 0.0)
            distance = (price / ma50 - 1.0) if price > 0 and ma50 > 0 else None
            if distance is not None:
                gate_distances.append(distance)
            gate_rows.append({
                "signal_date": signal_date.strftime("%Y-%m-%d"),
                "ticker": item.get("ticker"),
                "signal_price": item.get("signal_price"),
                "ma20": item.get("ma20"),
                "ma50": item.get("ma50"),
                "ma200": item.get("ma200"),
                "distance_to_ma50": distance,
                "regime": item.get("regime"),
                "signal_price_source": item.get("signal_price_source"),
            })

        day_rows = []
        for ticker in tickers:
            frame = frames[ticker]
            loc = frame.index.get_loc(signal_date)
            close = float(frame.iloc[loc]["Close"])
            previous = float(frame.iloc[loc - 1]["Close"]) if loc > 0 else None
            one_day_change = close / previous - 1.0 if previous and previous > 0 else None
            info = {
                "source": "local_cache",
                "mode": "daily_close",
                "previous_close": close,
                "quote_time": "",
                "market_time": "",
            }
            actual_state = _actual_state_for(ticker, portfolio)
            result = server._tactical_order(
                ticker, _signal_state_for(ticker, portfolio), close, cfg, market, info
            )
            blocked = bool(
                market.get("regime") == "BEAR"
                and result.get("regime") == "BEAR"
                and result.get("action") == "WAIT"
                and float(result.get("amount") or 0.0) <= 0
            )
            row = {
                "signal_date": signal_date.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "close": close,
                "one_day_change": one_day_change,
                "stock_regime": result.get("stock_regime"),
                "market_regime": result.get("market_regime"),
                "final_regime": result.get("regime"),
                "action": result.get("action"),
                "amount": float(result.get("amount") or 0.0),
                "limit": result.get("limit"),
                "blocked_by_market_bear": blocked,
                "reserve_cash": float(actual_state.reserve_cash) if actual_state is not None else None,
                "reason": result.get("reason") or result.get("text"),
            }
            detail_rows.append(row)
            day_rows.append(row)

        changes = [r["one_day_change"] for r in day_rows if r["one_day_change"] is not None]
        all_wait = all(r["action"] == "WAIT" for r in day_rows)
        down_3 = sum(1 for x in changes if x <= -0.03)
        daily_rows.append({
            "signal_date": signal_date.strftime("%Y-%m-%d"),
            "market_regime": market.get("regime"),
            "ticker_count": len(day_rows),
            "down_count": sum(1 for x in changes if x < 0),
            "down_3pct_count": down_3,
            "down_5pct_count": sum(1 for x in changes if x <= -0.05),
            "worst_one_day_change": min(changes) if changes else None,
            "buy_now_count": sum(1 for r in day_rows if r["action"] == "BUY_NOW"),
            "place_limit_count": sum(1 for r in day_rows if r["action"] == "PLACE_LIMIT"),
            "wait_count": sum(1 for r in day_rows if r["action"] == "WAIT"),
            "blocked_by_market_bear_count": sum(1 for r in day_rows if r["blocked_by_market_bear"]),
            "all_tactical_wait": all_wait,
            "pullback_dead_zone": bool(all_wait and down_3 > 0),
            "gate_min_distance_to_ma50": min(gate_distances) if gate_distances else None,
        })

    return pd.DataFrame(detail_rows), pd.DataFrame(daily_rows), gate_rows


def current_gap_snapshot(detail: pd.DataFrame, cfg, portfolio) -> pd.DataFrame:
    if detail.empty:
        return pd.DataFrame(columns=list(CURRENT_COLUMNS))
    latest_date = str(detail["signal_date"].max())
    latest = detail[detail["signal_date"] == latest_date]
    threshold = float(cfg.portfolio.tiers.thresholds[0])
    rows = []
    for row in latest.to_dict("records"):
        ticker = row["ticker"]
        state = portfolio.symbols.get(ticker) if portfolio is not None else None
        state_h = float(state.H) if state is not None and state.H > 0 else None
        first_limit = state_h * (1.0 + threshold) if state_h else None
        close = float(row["close"])
        rows.append({
            "ticker": ticker,
            "signal_date": latest_date,
            "close": close,
            "state_h": state_h,
            "drawdown_from_state_h": close / state_h - 1.0 if state_h else None,
            "first_ratchet_threshold": threshold,
            "first_ratchet_limit": first_limit,
            "distance_to_first_ratchet": close / first_limit - 1.0 if first_limit else None,
            "deep_ratchet_triggered": bool(first_limit and close <= first_limit),
            "tactical_action": row["action"],
            "tactical_limit": row["limit"],
            "blocked_by_market_bear": row["blocked_by_market_bear"],
            "position_status": "real_position" if state is not None and state.entry_date else "book_or_unknown",
        })
    return pd.DataFrame(rows)


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {
        "path": path.as_posix(), "rows": rows,
        "sha256": file_sha256(path), "bytes": path.stat().st_size,
    }


def build_bundle(args) -> dict:
    config_path = resolve(args.config)
    state_path = resolve(args.state)
    cache_dir = resolve(args.cache_dir)
    output_dir = resolve(args.output_dir)
    cfg = load_config(config_path)
    portfolio = load_portfolio(state_path)
    protected_hashes_before = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }
    names = list(dict.fromkeys(
        [str(s.ticker).upper() for s in cfg.symbols]
        + [str(x).upper() for x in cfg.tactical_orders.market_gate_tickers]
    ))
    cache_paths = {name: cache_dir / f"{name}.csv" for name in names}
    frames = {name: _read_local_bars(path) for name, path in cache_paths.items()}
    detail, daily, gate_rows = replay_portfolio_response(
        frames, cfg, portfolio=portfolio, start=args.start or None, end=args.end or None
    )
    current = current_gap_snapshot(detail, cfg, portfolio)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "detail": output_dir / "portfolio_signal_detail.csv",
        "daily": output_dir / "daily_dead_zone_summary.csv",
        "gate": output_dir / "market_gate_detail.csv",
        "current": output_dir / "current_gap_snapshot.csv",
        "workbook": output_dir / "portfolio_pullback_response_audit.xlsx",
    }
    detail.to_csv(paths["detail"], index=False, encoding="utf-8-sig")
    daily.to_csv(paths["daily"], index=False, encoding="utf-8-sig")
    pd.DataFrame(gate_rows).to_csv(paths["gate"], index=False, encoding="utf-8-sig")
    current.to_csv(paths["current"], index=False, encoding="utf-8-sig")
    temporary = paths["workbook"].with_name(paths["workbook"].stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            daily.rename(columns=DAILY_COLUMNS).to_excel(writer, sheet_name="逐日组合摘要", index=False)
            detail.rename(columns=DETAIL_COLUMNS).to_excel(writer, sheet_name="逐标的信号", index=False)
            current.rename(columns=CURRENT_COLUMNS).to_excel(writer, sheet_name="当前策略空档", index=False)
            pd.DataFrame(gate_rows).rename(columns={
                "signal_date": "信号日期", "ticker": "门控指数", "signal_price": "信号收盘价",
                "ma20": "MA20", "ma50": "MA50", "ma200": "MA200",
                "distance_to_ma50": "距MA50", "regime": "市况",
                "signal_price_source": "信号价格来源",
            }).to_excel(writer, sheet_name="市场门控", index=False)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()

    dead_zone_days = daily[daily["pullback_dead_zone"]] if not daily.empty else daily
    latest = daily.iloc[-1].to_dict() if not daily.empty else {}
    inputs = {
        "config": {"path": config_path.as_posix(), "sha256": file_sha256(config_path)},
        "state": {"path": state_path.as_posix(), "sha256": file_sha256(state_path)},
        **{
            f"price_{name}": {"path": path.as_posix(), "sha256": file_sha256(path)}
            for name, path in cache_paths.items()
        },
    }
    row_counts = {
        "detail": len(detail), "daily": len(daily), "gate": len(gate_rows), "current": len(current)
    }
    protected_hashes_after = {
        "config": file_sha256(config_path),
        "state": file_sha256(state_path),
    }
    if protected_hashes_after != protected_hashes_before:
        raise RuntimeError("protected config/state hash changed during read-only audit")
    manifest = {
        "schema_version": 1,
        "manifest_type": "portfolio_pullback_response_audit",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "DIAGNOSTIC_ONLY_NO_STRATEGY_PROMOTION",
        "window": {
            "start": daily.iloc[0]["signal_date"] if not daily.empty else None,
            "end": daily.iloc[-1]["signal_date"] if not daily.empty else None,
            "sessions": len(daily),
        },
        "diagnosis": {
            "market_bear_sessions": int((daily["market_regime"] == "BEAR").sum()) if not daily.empty else 0,
            "all_tactical_wait_sessions": int(daily["all_tactical_wait"].sum()) if not daily.empty else 0,
            "pullback_dead_zone_sessions": int(len(dead_zone_days)),
            "latest": latest,
        },
        "definitions": {
            "pullback_dead_zone": "同一完整日线至少一只现有标的跌幅达到3%，且全组合战术动作均为WAIT",
            "three_and_five_percent_counts": "描述性压力标签，不是候选参数、买入阈值或晋级门",
        },
        "audit_boundary": {
            "price_ohlc_read": True,
            "signal_day_price_change_calculated": True,
            "forward_return_data_read": False,
            "future_data_guard": "每个信号日先截断全部OHLC，再调用生产市场门控与战术函数",
            "historical_ratchet_state_reconstructed": False,
            "historical_account_state_reconstructed": False,
            "signal_eligibility_uses_normalized_positive_reserve": True,
            "current_ratchet_gap_uses_state_snapshot_only": True,
            "config_changed": False,
            "state_changed": False,
            "today_advice_changed": False,
            "orders_created": False,
            "protected_hashes_unchanged": True,
        },
        "inputs": inputs,
        "artifacts": {
            name: _artifact(path, None if name == "workbook" else row_counts[name])
            for name, path in paths.items()
        },
    }
    manifest_path = output_dir / "manifest.json"
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False, default=_json_default) + "\n",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="组合级回调响应/战术死区点时审计（只读）")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--start", default="2026-06-10")
    parser.add_argument("--end", default="")
    parser.add_argument("--output-dir", default="data/cache/research/portfolio_pullback_response_audit_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"组合回调响应审计失败: {exc}", file=sys.stderr)
        return 2
    diagnosis = manifest["diagnosis"]
    print(
        "组合回调响应审计完成 | "
        f"sessions={manifest['window']['sessions']} | "
        f"bear={diagnosis['market_bear_sessions']} | "
        f"dead_zone={diagnosis['pullback_dead_zone_sessions']} | "
        "forward_return_data_read=False | live_changed=False"
    )
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
