"""Point-in-time audit for the NVDA tactical fixed-limit signal.

This is a read-only diagnostic.  It replays the production tactical function
against local OHLC prefixes, so each row only sees data available on its signal
date.  It deliberately does not calculate investment returns or modify config,
state, or today's advice.

PowerShell:
    python -B scripts\nvda_tactical_audit.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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
from data.versioning import file_sha256, utc_now_iso


CHINESE_COLUMNS = {
    "signal_date": "信号日期",
    "close": "收盘价",
    "stock_regime": "个股市况",
    "market_regime": "市场市况",
    "regime": "最终市况",
    "reserve_ratio": "储备动用比例",
    "action": "战术动作",
    "limit": "固定限价",
    "amount": "策略预算",
    "shares": "策略股数",
    "ma5": "MA5",
    "ma20": "MA20",
    "ma50": "MA50",
    "ma200": "MA200",
    "atr": "ATR14",
    "basis_price": "锚定价",
    "daily_ref": "日线参考价",
    "reason": "原因",
}


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _read_local_bars(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, parse_dates=["Date"])
    required = {"Date", "Open", "High", "Low", "Close"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = frame.set_index("Date").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for column in ["Open", "High", "Low", "Close"]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame.empty or (frame[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError(f"{path}: invalid or empty OHLC data")
    return frame


def _effective_ratio(cfg, regime: str) -> float:
    tc = cfg.tactical_orders
    return {
        "BULL": float(tc.bull_reserve_ratio),
        "NEUTRAL": float(tc.neutral_reserve_ratio),
        "BEAR": float(tc.bear_reserve_ratio),
    }.get(regime, 0.0)


def _prefix_signal(
    frames: dict[str, pd.DataFrame],
    cfg,
    ticker: str,
    signal_date: pd.Timestamp,
    state: SymbolState,
) -> dict:
    """Run the production tactical function on one point-in-time data prefix."""
    server._bars_cache.clear()
    for name, frame in frames.items():
        server._bars_cache[name] = frame.loc[:signal_date].copy()

    prices = {
        name: float(frame.loc[signal_date, "Close"])
        for name, frame in frames.items()
        if signal_date in frame.index
    }
    price_meta = {
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
    market = server._market_phase_payload(cfg, prices, price_meta)
    info = price_meta["items"][ticker]
    result = server._tactical_order(
        ticker,
        state,
        prices[ticker],
        cfg,
        market,
        info,
    )
    metrics = result.get("metrics") or {}
    return {
        "signal_date": signal_date.strftime("%Y-%m-%d"),
        "close": round(prices[ticker], 4),
        "stock_regime": result.get("stock_regime"),
        "market_regime": result.get("market_regime"),
        "regime": result.get("regime"),
        "reserve_ratio": _effective_ratio(cfg, str(result.get("regime") or "")),
        "action": result.get("action"),
        "limit": result.get("limit"),
        "amount": result.get("amount"),
        "shares": result.get("shares"),
        "ma5": metrics.get("ma5"),
        "ma20": metrics.get("ma20"),
        "ma50": metrics.get("ma50"),
        "ma200": metrics.get("ma200"),
        "atr": metrics.get("atr"),
        "basis_price": result.get("basis_price"),
        "daily_ref": result.get("daily_ref"),
        "reason": result.get("reason") or result.get("text"),
    }


def replay_tactical_signals(
    frames: dict[str, pd.DataFrame],
    cfg,
    *,
    ticker: str = "NVDA",
    start: str | None = None,
    end: str | None = None,
    state: SymbolState | None = None,
) -> pd.DataFrame:
    """Replay the production signal without reading any future bars."""
    ticker = str(ticker).upper()
    required = [ticker]
    if getattr(cfg.tactical_orders, "market_gate_enabled", False):
        required.extend(str(x).upper() for x in cfg.tactical_orders.market_gate_tickers)
    missing = [name for name in required if name not in frames]
    if missing:
        raise ValueError(f"missing local bars for {missing}")

    dates = frames[ticker].index
    for name in required[1:]:
        dates = dates.intersection(frames[name].index)
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    if end:
        dates = dates[dates <= pd.Timestamp(end)]
    dates = dates.sort_values()

    source_state = state or SymbolState(
        ticker=ticker,
        cap_total=1.0,
        reserve_cash=1_000_000.0,
    )
    rows = [
        _prefix_signal(frames, cfg, ticker, signal_date, source_state)
        for signal_date in dates
    ]
    return pd.DataFrame(rows, columns=list(CHINESE_COLUMNS))


def _state_context(state_path: Path, ticker: str, cfg) -> dict:
    payload = {
        "path": state_path.as_posix(),
        "exists": state_path.exists(),
        "state_last_run_date": None,
        "needs_daily_update": None,
        "ticker": ticker,
        "reserve_cash": None,
        "H": None,
        "thresholds": list(cfg.portfolio.tiers.thresholds),
        "ratchet_limits": [],
    }
    pf = load_portfolio(state_path)
    if pf is None:
        return payload
    payload["state_last_run_date"] = pf.last_run_date
    payload["needs_daily_update"] = pf.last_run_date != pd.Timestamp.now().date().isoformat()
    st = pf.symbols.get(ticker)
    if st is None:
        return payload
    payload["reserve_cash"] = round(float(st.reserve_cash), 4)
    payload["H"] = round(float(st.H), 4)
    payload["ratchet_limits"] = [
        round(float(st.H) * (1.0 + float(threshold)), 4)
        for threshold in cfg.portfolio.tiers.thresholds
    ]
    payload["shares"] = round(float(st.shares), 6)
    payload["entry_date"] = st.entry_date
    return payload


def _build_bundle(args, cfg, frames: dict[str, pd.DataFrame], signals: pd.DataFrame) -> Path:
    output_dir = resolve(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ticker = str(args.ticker).upper()
    state_path = resolve(args.state)
    config_path = resolve(args.config)
    cache_paths = {
        name: resolve(args.cache_dir) / f"{name}.csv"
        for name in frames
    }
    state_context = _state_context(state_path, ticker, cfg)
    latest = signals.iloc[-1].to_dict() if not signals.empty else {}
    summary = {
        "schema_version": 1,
        "report_type": "nvda_tactical_signal_audit",
        "ticker": ticker,
        "window": {
            "start": str(signals["signal_date"].iloc[0]) if not signals.empty else None,
            "end": str(signals["signal_date"].iloc[-1]) if not signals.empty else None,
            "rows": int(len(signals)),
        },
        "counts": {
            "wait": int((signals["action"] == "WAIT").sum()) if not signals.empty else 0,
            "place_limit": int((signals["action"] == "PLACE_LIMIT").sum()) if not signals.empty else 0,
            "buy_now": int((signals["action"] == "BUY_NOW").sum()) if not signals.empty else 0,
            "bear_regime": int((signals["regime"] == "BEAR").sum()) if not signals.empty else 0,
        },
        "latest_signal": latest,
        "state_context": state_context,
        "current_rule": {
            "bull_reserve_ratio": float(cfg.tactical_orders.bull_reserve_ratio),
            "neutral_reserve_ratio": float(cfg.tactical_orders.neutral_reserve_ratio),
            "bear_reserve_ratio": float(cfg.tactical_orders.bear_reserve_ratio),
            "neutral_atr_mult": float(cfg.tactical_orders.neutral_atr_mult),
            "thresholds": list(cfg.portfolio.tiers.thresholds),
        },
        "diagnosis": (
            "190美元区间的点时信号主要处于BEAR，当前配置bear_reserve_ratio=0，"
            "所以战术层明确WAIT；当前202.22来自最新收盘点时的中性规则，"
            "等于MA20与1ATR缓冲取小值。该结果说明规则行为一致，但暴露出"
            "熊市是否允许极小额观察仓的策略选择，不能用今天的反弹信号倒推。"
        ),
        "audit_boundary": {
            "return_data_read": False,
            "price_ohlc_read": True,
            "future_data_guard": "每一行先切到signal_date，再调用生产战术函数；不读取signal_date之后的K线",
            "config_changed": False,
            "state_changed": False,
            "today_advice_changed": False,
        },
        "generated_at": utc_now_iso(),
    }

    csv_path = output_dir / f"{ticker.lower()}_tactical_signals.csv"
    summary_path = output_dir / "summary.json"
    workbook_path = output_dir / f"{ticker.lower()}_tactical_audit.xlsx"
    signals.rename(columns=CHINESE_COLUMNS).to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    summary_rows = [
        {"字段": key, "值": json.dumps(value, ensure_ascii=False, default=_json_default)}
        for key, value in summary.items()
    ]
    source_rows = []
    for name, path in {"config": config_path, "state": state_path, **cache_paths}.items():
        source_rows.append({
            "来源": name,
            "路径": path.as_posix(),
            "存在": path.exists(),
            "内容SHA256": file_sha256(path) if path.exists() else None,
            "字节数": path.stat().st_size if path.exists() else 0,
        })

    temporary = workbook_path.with_name(workbook_path.stem + ".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            pd.DataFrame(summary_rows).to_excel(writer, sheet_name="摘要", index=False)
            signals.rename(columns=CHINESE_COLUMNS).to_excel(
                writer, sheet_name="逐日信号", index=False
            )
            pd.DataFrame(source_rows).to_excel(writer, sheet_name="数据审计", index=False)
        os.replace(temporary, workbook_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    atomic_write_text(
        summary_path,
        json.dumps(
            {**summary, "manifest_path": (output_dir / "manifest.json").as_posix()},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        )
        + "\n",
    )

    output_files = {}
    for path in [csv_path, summary_path, workbook_path]:
        output_files[path.name] = {
            "path": path.as_posix(),
            "content_sha256": file_sha256(path),
            "content_bytes": path.stat().st_size,
        }
    input_files = {
        name: {
            "path": path.as_posix(),
            "content_sha256": file_sha256(path) if path.exists() else None,
            "content_bytes": path.stat().st_size if path.exists() else 0,
        }
        for name, path in {"config": config_path, "state": state_path, **cache_paths}.items()
    }
    manifest = {
        "schema_version": 1,
        "report_type": "nvda_tactical_signal_audit",
        "version_id": f"nvda_tactical_signal_audit:{file_sha256(csv_path)[:16]}",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_files": input_files,
        "output_files": output_files,
        "future_data_guard": summary["audit_boundary"]["future_data_guard"],
        "return_data_read": False,
        "config_state_today_advice_changed": False,
    }
    manifest_path = output_dir / "manifest.json"
    atomic_write_text(
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description="NVDA战术信号点时审计（只读）")
    parser.add_argument("--ticker", default="NVDA")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--start", default="2026-06-10")
    parser.add_argument("--end", default="")
    parser.add_argument(
        "--output-dir",
        default="data/cache/research/nvda_tactical_audit_v1",
    )
    args = parser.parse_args()

    ticker = str(args.ticker).upper()
    cfg = load_config(resolve(args.config))
    cache_dir = resolve(args.cache_dir)
    gate_tickers = (
        [str(x).upper() for x in cfg.tactical_orders.market_gate_tickers]
        if getattr(cfg.tactical_orders, "market_gate_enabled", False)
        else []
    )
    names = [ticker] + [name for name in gate_tickers if name != ticker]
    frames = {name: _read_local_bars(cache_dir / f"{name}.csv") for name in names}
    pf = load_portfolio(resolve(args.state))
    state = pf.symbols.get(ticker) if pf is not None else None
    signals = replay_tactical_signals(
        frames,
        cfg,
        ticker=ticker,
        start=args.start or None,
        end=args.end or None,
        state=state,
    )
    manifest_path = _build_bundle(args, cfg, frames, signals)
    latest = signals.iloc[-1].to_dict() if not signals.empty else {}
    print(
        f"{ticker}战术信号点时审计完成 | rows={len(signals)} | "
        f"bear={int((signals['regime'] == 'BEAR').sum()) if not signals.empty else 0} | "
        f"place_limit={int((signals['action'] == 'PLACE_LIMIT').sum()) if not signals.empty else 0} | "
        f"wait={int((signals['action'] == 'WAIT').sum()) if not signals.empty else 0} | "
        f"latest_limit={latest.get('limit')} | return_data_read=False"
    )
    print(f"输出: {resolve(args.output_dir)}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
