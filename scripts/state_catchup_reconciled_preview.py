"""Replay the strategy clock after separating current broker account truth."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import server
from backtest.broker_account_reconciliation import reconcile_strategy_book
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio, save_portfolio
from core.broker_account import save_broker_account
from data.versioning import file_sha256


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def _common_session_closes(portfolio, cfg, start: str, latest: str) -> dict[str, dict[str, float]]:
    series = {}
    for ticker in sorted(portfolio.symbols):
        frame = server._bars_for(ticker, cfg)
        series[ticker] = {idx.date().isoformat(): float(value) for idx, value in frame["Close"].items()}
    common = set.intersection(*(set(values) for values in series.values()))
    dates = sorted(day for day in common if start < day <= latest)
    return {day: {ticker: values[day] for ticker, values in series.items()} for day in dates}


def _position_events(audit_path: Path, after_date: str) -> list[dict]:
    latest_by_coordinate: dict[tuple[str, str], dict] = {}
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("action") != "set_position":
            continue
        detail = record.get("detail") or {}
        event_date = str(detail.get("buy_date") or "")[:10]
        ticker = str(detail.get("ticker") or "").upper()
        if ticker and event_date > after_date:
            latest_by_coordinate[(ticker, event_date)] = {"audit_timestamp": record.get("ts"), **detail}
    return sorted(latest_by_coordinate.values(), key=lambda row: (row["buy_date"], row["audit_timestamp"], row["ticker"]))


def _reconstruct_base(current, events: list[dict], base_date: str):
    base = copy.deepcopy(current)
    for event in sorted(events, key=lambda row: (row["buy_date"], row["audit_timestamp"]), reverse=True):
        state = base.symbols[event["ticker"]]
        for field, value in (event.get("old") or {}).items():
            setattr(state, field, value)
        state.entry_date = ""
        state.entry_price = 0.0
    base.last_run_date = base_date
    return base


def _apply_position_event(portfolio, event: dict) -> None:
    state = portfolio.symbols[event["ticker"]]
    new = event.get("new") or {}
    state.shares = float(event["shares"])
    state.cost_basis = float(new["cost_basis"])
    state.H = float(new["H"])
    state.cap_total = float(new["cap_total"])
    state.cum_injected = float(new["cum_injected"])
    state.entry_date = str(event["buy_date"])[:10]
    state.entry_price = float(event["buy_price"])


def _event_aware_replay(base, cfg, session_closes: dict[str, dict[str, float]], events: list[dict]):
    from core import live
    proposed = copy.deepcopy(base)
    by_date: dict[str, list[dict]] = {}
    for event in events:
        by_date.setdefault(str(event["buy_date"])[:10], []).append(event)
    ledger = []
    for session_date in sorted(session_closes):
        applied = []
        for event in by_date.get(session_date, []):
            _apply_position_event(proposed, event)
            applied.append(event["ticker"])
        before_index = proposed.day_index
        live.advance_trading_day(proposed, session_date)
        signals = live.generate_signals(proposed, session_closes[session_date], cfg)
        ledger.append({
            "session_date": session_date,
            "day_index_before": before_index,
            "day_index_after": proposed.day_index,
            "position_events_applied": ",".join(applied),
            "immediate_buy_count": sum(len(signal.immediate_buys) for signal in signals),
        })
    return proposed, ledger


def build_bundle(args) -> dict:
    state_path, config_path, source_path, audit_path = resolve(args.state), resolve(args.config), resolve(args.broker_source), resolve(args.audit)
    output_dir = resolve(args.output_dir)
    state_hash, config_hash = file_sha256(state_path), file_sha256(config_path)
    portfolio = load_portfolio(state_path)
    source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    reconciliation = reconcile_strategy_book(portfolio, source.get("positions") or [])
    rebase_date = str(portfolio.last_run_date)
    events = _position_events(audit_path, rebase_date)
    base = _reconstruct_base(portfolio, events, rebase_date)
    cfg = server._cfg_for_portfolio(portfolio)
    latest = server._latest_closed_session_date(cfg)
    if latest is None:
        raise ValueError("no latest completed session")
    latest_iso = latest.isoformat()
    closes = _common_session_closes(base, cfg, rebase_date, latest_iso)
    proposed, ledger = _event_aware_replay(base, cfg, closes, events)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "proposed": output_dir / "strategy_state_after_session_replay_proposed_not_live.json",
        "ledger": output_dir / "strategy_clock_session_ledger.csv",
        "patch": output_dir / "broker_position_patch_separate_user_approval_required.csv",
        "diff": output_dir / "strategy_clock_diff.json",
        "broker_proposed": output_dir / "broker_positions_proposed_not_live.json",
    }
    save_portfolio(proposed, paths["proposed"])
    save_broker_account(source, paths["broker_proposed"])
    pd.DataFrame(ledger).to_csv(paths["ledger"], index=False, encoding="utf-8-sig")
    patch_rows = [row for row in reconciliation["reconciliation"] if row["status"] != "MATCH"]
    pd.DataFrame(patch_rows).to_csv(paths["patch"], index=False, encoding="utf-8-sig")
    changed = []
    for ticker in sorted(portfolio.symbols):
        old, new = portfolio.symbols[ticker], proposed.symbols[ticker]
        fields = {name: {"before": getattr(old, name), "after": getattr(new, name)} for name in ("H", "tier_armed", "pending_ladder", "pending_core_cash", "shares", "cost_basis") if getattr(old, name) != getattr(new, name)}
        if fields:
            changed.append({"ticker": ticker, "fields": fields})
    diff = {
        "status": "USER_APPROVAL_REQUIRED_NOT_APPLIED",
        "strategy_clock_before": portfolio.last_run_date,
        "strategy_clock_rebase": rebase_date,
        "strategy_clock_after": proposed.last_run_date,
        "replayed_session_count": len(ledger),
        "position_events_replayed": [{"ticker": row["ticker"], "event_date": row["buy_date"], "audit_timestamp": row["audit_timestamp"]} for row in events],
        "strategy_symbols_changed": changed,
        "broker_patch_is_separate": True,
        "broker_patch_rows": len(patch_rows),
        "live_state_written": False,
        "orders_created": False,
    }
    atomic_write_text(paths["diff"], json.dumps(diff, ensure_ascii=False, indent=2) + "\n")
    if file_sha256(state_path) != state_hash or file_sha256(config_path) != config_hash:
        raise RuntimeError("protected config/state changed during catch-up preview")
    manifest = {
        "schema_version": 1,
        "manifest_type": "reconciled_strategy_clock_catchup_preview",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": diff["status"],
        "scope_contract": {
            "strategy_clock_replay": "original strategy book only",
            "broker_account_truth": "separate patch; broker-only AVGO/DRAM do not enter portfolio optimization",
            "portfolio_optimization": "VARIABLE_CARDINALITY",
            "migration_control_included": False,
        },
        "inputs": {
            "state": {"path": state_path.as_posix(), "sha256": state_hash},
            "config": {"path": config_path.as_posix(), "sha256": config_hash},
            "broker_source": {"path": source_path.as_posix(), "sha256": file_sha256(source_path)},
            "audit": {"path": audit_path.as_posix(), "sha256": file_sha256(audit_path)},
        },
        "clock": {"before": portfolio.last_run_date, "rebase": rebase_date, "after": proposed.last_run_date, "sessions": len(ledger), "position_events_replayed": len(events)},
        "artifacts": {
            "proposed_strategy_state": _artifact(paths["proposed"]),
            "session_ledger": _artifact(paths["ledger"], len(ledger)),
            "separate_broker_patch": _artifact(paths["patch"], len(patch_rows)),
            "strategy_clock_diff": _artifact(paths["diff"], len(changed)),
            "proposed_broker_account": _artifact(paths["broker_proposed"], len(source.get("positions") or [])),
        },
        "guards": {"return_data_read": False, "fresh_oos_consumed": False, "config_changed": False, "state_changed": False, "today_advice_changed": False, "orders_created": False, "automatic_apply_allowed": False},
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="策略时钟逐会话 catch-up 与券商持仓分层 patch 预览")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--broker-source", default="data/cache/research/broker_account_reconciliation_v1/broker_snapshot_source.yaml")
    parser.add_argument("--audit", default="data/audit.jsonl")
    parser.add_argument("--output-dir", default="data/cache/research/state_catchup_reconciled_preview_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"分层 catch-up 预览失败: {exc}", file=sys.stderr)
        return 2
    print(f"分层 catch-up 预览完成 | rebase={manifest['clock']['rebase']} | after={manifest['clock']['after']} | sessions={manifest['clock']['sessions']} | live_changed=False")
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
