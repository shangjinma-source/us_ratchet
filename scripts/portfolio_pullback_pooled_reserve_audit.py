r"""Replay a research-only pooled-reserve whole-share pullback candidate.

The control is the current production rule.  The candidate changes only two
execution mechanics in BEAR sessions: it reuses the already registered neutral
reserve ratio and pools the incumbent's fragmented reserve cash before whole-
share sizing.  It does not scan a new threshold, mutate live files, or create
broker orders.

PowerShell:
    python -B scripts\portfolio_pullback_pooled_reserve_audit.py
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
from backtest.portfolio_pullback_allocation import (
    allocate_whole_lots,
    parse_weight_map,
    risk_chain_shape,
)
from core.config import load_config
from core.helpers import atomic_write_text, resolve
from core.persist import load_portfolio
from core.state import SymbolState
from data.versioning import file_sha256
from scripts.nvda_tactical_audit import _read_local_bars
from scripts.portfolio_pullback_response_audit import (
    _market_on_prefix,
    replay_portfolio_response,
)


SUMMARY_CN = {
    "signal_date": "信号日期", "candidate_id": "候选ID", "selection_role": "候选角色",
    "mechanism_id": "候选机制",
    "research_track": "研究轨", "holding_count": "目标结构持仓数",
    "market_regime": "市场市况", "current_rule_order_count": "现行规则订单数",
    "pooled_reserve_start_usd": "资金池期初储备金", "candidate_budget_usd": "本期候选预算",
    "proposed_order_count": "研究限价单数", "proposed_whole_shares": "研究限价总股数",
    "proposed_notional_usd": "研究限价名义金额", "proposal_residual_usd": "本期预算余款",
    "proposal_deployment_ratio": "本期预算部署率", "proposal_target_l1_drift": "整股目标L1漂移",
    "filled_order_count": "当日回放成交单数", "filled_notional_usd": "当日回放成交金额",
    "pooled_reserve_end_usd": "资金池期末储备金", "cumulative_filled_usd": "累计成交金额",
    "cumulative_effective_n": "累计成交有效持仓数", "cumulative_top1": "累计成交单名Top1",
    "cumulative_top3": "累计成交单名Top3", "cumulative_risk_chain_top1": "累计风险链Top1",
    "cumulative_risk_chain_top3": "累计风险链Top3", "paired_return_p50": "相对原八只收益P50",
    "posttrade_effective_n": "原八只加成交后有效持仓数", "posttrade_top1": "原八只加成交后单名Top1",
    "posttrade_top3": "原八只加成交后单名Top3", "posttrade_risk_chain_top1": "原八只加成交后风险链Top1",
    "posttrade_risk_chain_top3": "原八只加成交后风险链Top3",
    "paired_return_p10": "相对原八只收益P10", "paired_drawdown_cost_p50": "相对原八只回撤成本P50",
    "paired_drawdown_cost_p90": "相对原八只回撤成本P90",
    "target_012922_distance": "012922距离", "promotion_allowed": "允许晋级",
}

ORDER_CN = {
    "signal_date": "信号日期", "candidate_id": "候选ID", "selection_role": "候选角色",
    "mechanism_id": "候选机制",
    "ticker": "股票", "risk_chain": "风险链", "side": "方向", "shares": "整股股数",
    "limit_price": "限价", "notional_usd": "名义金额", "valid_for": "有效期",
    "status": "状态", "fill_date": "回放成交日期", "fill_price": "回放成交价",
}


def _artifact(path: Path, rows: int | None = None) -> dict:
    return {"path": path.as_posix(), "rows": rows, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def _shape(notionals: dict[str, float]) -> tuple[float, float, float]:
    total = sum(notionals.values())
    if total <= 0:
        return 0.0, 0.0, 0.0
    weights = sorted((value / total for value in notionals.values() if value > 0), reverse=True)
    return weights[0], sum(weights[:3]), 1.0 / sum(weight * weight for weight in weights)


def _candidate_tables(registry_path: Path, master_path: Path, risk_path: Path):
    registry = pd.read_csv(registry_path)
    active = registry[registry["research_track"].eq("portfolio_optimization")].copy()
    if active.empty or not active["action_scope"].eq("VARIABLE_CARDINALITY").all():
        raise ValueError("portfolio_optimization VARIABLE_CARDINALITY registry is missing")
    if active["holding_count_interpretation"].str.contains("migration", case=False, na=False).any():
        raise ValueError("migration-control cardinality leaked into portfolio optimization")
    master = pd.read_csv(master_path)
    master = master[master["candidate_id"].isin(active["candidate_id"])].copy()
    if master["candidate_id"].duplicated().any():
        raise ValueError("portfolio-optimization master candidates are not unique")
    active = active.merge(master, on="candidate_id", how="left", suffixes=("_registry", "_master"), validate="one_to_one")
    if active["target_012922_distance"].isna().any():
        raise ValueError("dual-benchmark training metrics are missing")
    risks = pd.read_csv(risk_path)
    risks = risks[risks["candidate_id"].isin(active["candidate_id"])].copy()
    risk_maps = {
        candidate_id: dict(zip(group["ticker"].astype(str), group["risk_chain"].astype(str)))
        for candidate_id, group in risks.groupby("candidate_id")
    }
    return active, risk_maps


def _fill_pending(pending: list[dict], frames: dict[str, pd.DataFrame], date: pd.Timestamp, fee_bps: float):
    fills: list[dict] = []
    spent = 0.0
    for order in pending:
        bar = frames[order["ticker"]].loc[date]
        if float(bar["Low"]) <= order["limit_price"] + 1e-9:
            price = min(float(bar["Open"]), float(order["limit_price"]))
            notional = price * order["shares"]
            cost = notional * (1.0 + fee_bps / 10_000.0)
            fills.append({**order, "fill_date": date.strftime("%Y-%m-%d"), "fill_price": price, "fill_notional_usd": notional, "fill_total_cost_usd": cost})
            spent += cost
    return fills, spent


def _candidate_limit(ticker: str, close: float, cfg, market: dict, mechanism_id: str) -> float:
    signal = server._tactical_order(
        ticker, SymbolState(ticker=ticker, cap_total=1.0, reserve_cash=1_000_000.0),
        close, cfg, market,
        {"source": "local_cache", "mode": "daily_close", "previous_close": close},
    )
    if mechanism_id == "POOL_BEAR_ANCHOR_NEUTRAL_BUDGET":
        return float(signal["limit"])
    if mechanism_id != "POOL_NEUTRAL_ANCHOR_NEUTRAL_BUDGET":
        raise ValueError(f"unknown candidate mechanism {mechanism_id}")
    bars = server._bars_for(ticker, cfg)
    ma20 = float(server._mean_tail(bars["Close"], cfg.tactical_orders.ma_mid) or 0.0)
    atr = float(server._atr_tail(bars, cfg.tactical_orders.atr_window) or 0.0)
    if ma20 <= 0 or atr <= 0:
        raise ValueError(f"neutral anchor inputs are missing for {ticker}")
    cap = close * (1.0 - float(cfg.tactical_orders.min_discount_pct))
    anchor = min(ma20, close - float(cfg.tactical_orders.neutral_atr_mult) * atr)
    return round(float(min(anchor, cap)), 2)


def replay_pooled_candidates(
    frames: dict[str, pd.DataFrame], cfg, portfolio, active: pd.DataFrame,
    risk_maps: dict[str, dict[str, str]], daily_control: pd.DataFrame,
    baseline_notionals: dict[str, float], baseline_risk_chains: dict[str, str],
    *, start: str | None = None, end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replay next-session fills independently for each registered candidate."""
    dates = pd.DatetimeIndex(pd.to_datetime(daily_control["signal_date"]))
    if start:
        dates = dates[dates >= pd.Timestamp(start)]
    if end:
        dates = dates[dates <= pd.Timestamp(end)]
    total_reserve = sum(max(0.0, float(state.reserve_cash)) for state in portfolio.symbols.values())
    ratio = float(cfg.tactical_orders.neutral_reserve_ratio)
    fee_bps = float(getattr(cfg.execution, "fee_bps", 0.0) or 0.0)
    control_by_date = daily_control.set_index("signal_date").to_dict("index")
    summaries: list[dict] = []
    orders: list[dict] = []
    fills_all: list[dict] = []

    mechanisms = [
        "POOL_BEAR_ANCHOR_NEUTRAL_BUDGET",
        "POOL_NEUTRAL_ANCHOR_NEUTRAL_BUDGET",
    ]
    for candidate in active.to_dict("records"):
        candidate_id = str(candidate["candidate_id"])
        role = str(candidate.get("selection_role_registry") or candidate.get("selection_role_master") or "")
        weights = parse_weight_map(str(candidate["frozen_target_weights"]))
        for mechanism_id in mechanisms:
            cash = total_reserve
            pending: list[dict] = []
            filled_notionals: dict[str, float] = {}
            for date in dates:
                fills, spent = _fill_pending(pending, frames, date, fee_bps)
                if spent > cash + 0.01:
                    raise RuntimeError("pending whole-lot fills exceeded pooled reserve")
                cash -= spent
                for fill in fills:
                    ticker = fill["ticker"]
                    filled_notionals[ticker] = filled_notionals.get(ticker, 0.0) + fill["fill_notional_usd"]
                    fills_all.append(fill)
                pending = []

                date_text = date.strftime("%Y-%m-%d")
                control = control_by_date[date_text]
                market = _market_on_prefix(frames, cfg, date)
                budget = cash * ratio if market.get("regime") == "BEAR" else 0.0
                proposal = None
                if budget > 0:
                    limits = {
                        ticker: _candidate_limit(
                            ticker, float(frames[ticker].loc[date, "Close"]), cfg, market, mechanism_id
                        )
                        for ticker in weights
                    }
                    proposal = allocate_whole_lots(budget, weights, limits, fee_bps=fee_bps)
                    for ticker, shares in proposal.shares.items():
                        row = {
                            "signal_date": date_text, "candidate_id": candidate_id,
                            "selection_role": role, "mechanism_id": mechanism_id, "ticker": ticker,
                            "risk_chain": risk_maps.get(candidate_id, {}).get(ticker, "UNCLASSIFIED"),
                            "side": "BUY", "shares": shares, "limit_price": limits[ticker],
                            "notional_usd": shares * limits[ticker], "valid_for": "NEXT_US_SESSION_ONLY",
                            "status": "RESEARCH_PROPOSAL_NOT_LIVE", "fill_date": "", "fill_price": np.nan,
                        }
                        pending.append(row)
                        orders.append(row)
                top1, top3, effective_n = _shape(filled_notionals)
                chain_top1, chain_top3 = risk_chain_shape(filled_notionals, risk_maps.get(candidate_id, {}))
                posttrade = dict(baseline_notionals)
                for ticker, value in filled_notionals.items():
                    posttrade[ticker] = posttrade.get(ticker, 0.0) + value
                post_top1, post_top3, post_effective_n = _shape(posttrade)
                post_risk_map = {**baseline_risk_chains, **risk_maps.get(candidate_id, {})}
                post_chain_top1, post_chain_top3 = risk_chain_shape(posttrade, post_risk_map)
                summaries.append({
                "signal_date": date_text, "candidate_id": candidate_id, "selection_role": role, "mechanism_id": mechanism_id,
                "research_track": "portfolio_optimization", "holding_count": len(weights),
                "market_regime": market.get("regime"),
                "current_rule_order_count": int(control["buy_now_count"] + control["place_limit_count"]),
                "pooled_reserve_start_usd": cash + spent, "candidate_budget_usd": budget,
                "proposed_order_count": len(proposal.shares) if proposal else 0,
                "proposed_whole_shares": sum(proposal.shares.values()) if proposal else 0,
                "proposed_notional_usd": sum(proposal.notionals.values()) if proposal else 0.0,
                "proposal_residual_usd": proposal.residual_cash_usd if proposal else budget,
                "proposal_deployment_ratio": proposal.deployment_ratio if proposal else 0.0,
                "proposal_target_l1_drift": proposal.target_l1_drift if proposal else np.nan,
                "filled_order_count": len(fills), "filled_notional_usd": sum(x["fill_notional_usd"] for x in fills),
                "pooled_reserve_end_usd": cash, "cumulative_filled_usd": sum(filled_notionals.values()),
                "cumulative_effective_n": effective_n, "cumulative_top1": top1, "cumulative_top3": top3,
                "cumulative_risk_chain_top1": chain_top1, "cumulative_risk_chain_top3": chain_top3,
                "posttrade_effective_n": post_effective_n, "posttrade_top1": post_top1, "posttrade_top3": post_top3,
                "posttrade_risk_chain_top1": post_chain_top1, "posttrade_risk_chain_top3": post_chain_top3,
                "paired_return_p50": candidate["paired_return_p50"], "paired_return_p10": candidate["paired_return_p10"],
                "paired_drawdown_cost_p50": candidate["paired_drawdown_cost_p50"],
                "paired_drawdown_cost_p90": candidate["paired_drawdown_cost_p90"],
                "target_012922_distance": candidate["target_012922_distance"], "promotion_allowed": False,
                })
    return pd.DataFrame(summaries), pd.DataFrame(orders), pd.DataFrame(fills_all)


def build_bundle(args) -> dict:
    config_path, state_path = resolve(args.config), resolve(args.state)
    registry_path, master_path = resolve(args.registry), resolve(args.master)
    baseline_path = resolve(args.baseline)
    risk_path, cache_dir, output_dir = resolve(args.risk_map), resolve(args.cache_dir), resolve(args.output_dir)
    protected_before = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    cfg, portfolio = load_config(config_path), load_portfolio(state_path)
    active, risk_maps = _candidate_tables(registry_path, master_path, risk_path)
    baseline = pd.read_csv(baseline_path)
    baseline_notionals = dict(zip(baseline["ticker"].astype(str), baseline["cap_total_usd"].astype(float)))
    baseline_risk_chains = dict(zip(baseline["ticker"].astype(str), baseline["risk_chain"].astype(str)))
    baseline_top1, baseline_top3, baseline_effective_n = _shape(baseline_notionals)
    baseline_chain_top1, baseline_chain_top3 = risk_chain_shape(baseline_notionals, baseline_risk_chains)
    incumbent_tickers = [str(item.ticker).upper() for item in cfg.symbols]
    target_tickers = sorted({ticker for value in active["frozen_target_weights"] for ticker in parse_weight_map(value)})
    names = list(dict.fromkeys(incumbent_tickers + list(cfg.tactical_orders.market_gate_tickers) + target_tickers))
    cache_paths = {ticker: cache_dir / f"{ticker}.csv" for ticker in names}
    frames = {ticker: _read_local_bars(path) for ticker, path in cache_paths.items()}
    _, daily, _ = replay_portfolio_response(frames, cfg, portfolio=portfolio, start=args.start, end=args.end or None)
    summary, orders, fills = replay_pooled_candidates(
        frames, cfg, portfolio, active, risk_maps, daily, baseline_notionals, baseline_risk_chains,
        start=args.start, end=args.end or None
    )
    decision_rows = []
    for (mechanism_id, candidate_id), group in summary.groupby(["mechanism_id", "candidate_id"], sort=True):
        latest = group.iloc[-1]
        four_metric_gate = bool(
            float(latest["paired_return_p50"]) >= 0
            and float(latest["paired_return_p10"]) >= 0
            and float(latest["paired_drawdown_cost_p50"]) <= 0
            and float(latest["paired_drawdown_cost_p90"]) <= 0
        )
        decision_rows.append({
            "mechanism_id": mechanism_id, "candidate_id": candidate_id,
            "selection_role": latest["selection_role"], "research_track": "portfolio_optimization",
            "holding_count": int(latest["holding_count"]),
            "proposal_rows": int(group["proposed_order_count"].sum()),
            "strict_next_session_fills": int(group["filled_order_count"].sum()),
            "filled_notional_usd": float(latest["cumulative_filled_usd"]),
            "remaining_reserve_usd": float(latest["pooled_reserve_end_usd"]),
            "posttrade_effective_n": float(latest["posttrade_effective_n"]),
            "posttrade_top1": float(latest["posttrade_top1"]),
            "posttrade_risk_chain_top1": float(latest["posttrade_risk_chain_top1"]),
            "paired_return_p50": float(latest["paired_return_p50"]),
            "paired_return_p10": float(latest["paired_return_p10"]),
            "paired_drawdown_cost_p50": float(latest["paired_drawdown_cost_p50"]),
            "paired_drawdown_cost_p90": float(latest["paired_drawdown_cost_p90"]),
            "target_012922_distance": float(latest["target_012922_distance"]),
            "incumbent_four_metric_gate_pass": four_metric_gate,
            "live_candidate_allowed": False,
            "decision_required": "USER_APPROVAL_AFTER_TODAY_DIFF_AND_ROLLBACK",
        })
    decision = pd.DataFrame(decision_rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary": output_dir / "pooled_reserve_daily_comparison.csv",
        "orders": output_dir / "research_order_proposals.csv",
        "fills": output_dir / "next_session_fill_replay.csv",
        "decision": output_dir / "live_change_decision_matrix.csv",
        "workbook": output_dir / "portfolio_pullback_pooled_reserve_audit.xlsx",
    }
    summary.to_csv(paths["summary"], index=False, encoding="utf-8-sig")
    orders.to_csv(paths["orders"], index=False, encoding="utf-8-sig")
    fills.to_csv(paths["fills"], index=False, encoding="utf-8-sig")
    decision.to_csv(paths["decision"], index=False, encoding="utf-8-sig")
    temporary = paths["workbook"].with_suffix(".tmp.xlsx")
    try:
        with pd.ExcelWriter(temporary, engine="openpyxl") as writer:
            summary.rename(columns=SUMMARY_CN).to_excel(writer, sheet_name="逐日候选对照", index=False)
            orders.rename(columns=ORDER_CN).to_excel(writer, sheet_name="研究限价草案", index=False)
            fills.rename(columns=ORDER_CN).to_excel(writer, sheet_name="次日成交回放", index=False)
            decision.to_excel(writer, sheet_name="实盘决策矩阵", index=False)
        os.replace(temporary, paths["workbook"])
    finally:
        if temporary.exists():
            temporary.unlink()
    protected_after = {"config": file_sha256(config_path), "state": file_sha256(state_path)}
    if protected_after != protected_before:
        raise RuntimeError("protected live config/state changed during research audit")
    state_date = pd.Timestamp(portfolio.last_run_date)
    window_end = pd.Timestamp(summary["signal_date"].max()) if not summary.empty else state_date
    manifest = {
        "schema_version": 1, "manifest_type": "portfolio_pullback_pooled_reserve_audit",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "RESEARCH_ONLY_COUNTERFACTUAL_NOT_LIVE_ORDER",
        "mechanism": {
            "control": "CURRENT_PER_TICKER_RESERVE_WITH_BEAR_RATIO_ZERO",
            "candidates": [
                "POOL_BEAR_ANCHOR_NEUTRAL_BUDGET",
                "POOL_NEUTRAL_ANCHOR_NEUTRAL_BUDGET",
            ],
            "candidate_budget_ratio": float(cfg.tactical_orders.neutral_reserve_ratio),
            "mechanism_interpretation": "first isolates pooling; second reuses the existing neutral anchor as a shallow BEAR trial",
            "threshold_scan_performed": False, "outcome_selected_parameter": False, "whole_lot_required": True,
            "pending_order_validity": "NEXT_US_SESSION_ONLY",
            "fill_rule": "next_session_low_at_or_below_limit; fill=min(open,limit)",
        },
        "tracks": {
            "portfolio_optimization": {"active": True, "dynamic_k_reference_counts": sorted(active["holding_count"].astype(int).unique().tolist())},
            "migration_control": {"active": False, "reason": "8/9-name incumbent migration actions are not target cardinality"},
        },
        "original_8_baseline": {
            "ticker_count": len(baseline_notionals), "top1": baseline_top1, "top3": baseline_top3,
            "effective_n": baseline_effective_n, "risk_chain_top1": baseline_chain_top1,
            "risk_chain_top3": baseline_chain_top3,
        },
        "state_freshness": {
            "state_last_run_date": portfolio.last_run_date,
            "window_end": window_end.strftime("%Y-%m-%d"),
            "calendar_age_days": int((window_end - state_date).days),
            "historical_cash_reconstructed": False,
            "interpretation": "STATIC_STALE_STATE_CAPACITY_STRESS_NOT_ACCOUNT_LEDGER",
        },
        "evidence_boundary": {
            "historical_return_metrics_source": "consumed_training_master_table",
            "fresh_oos_consumed": False, "forward_return_used_for_parameter_selection": False,
            "promotion_allowed": False, "live_config_changed": False, "state_changed": False,
            "today_advice_changed": False, "orders_created": False, "protected_hashes_unchanged": True,
        },
        "diagnosis": {
            "candidate_count": int(active.shape[0]), "sessions": int(daily.shape[0]),
            "bear_sessions": int((daily["market_regime"] == "BEAR").sum()),
            "current_rule_zero_order_bear_sessions": int(((daily["market_regime"] == "BEAR") & ((daily["buy_now_count"] + daily["place_limit_count"]) == 0)).sum()),
            "research_proposal_rows": int(len(orders)), "next_session_fill_rows": int(len(fills)),
            "decision_rows": int(len(decision)),
            "four_metric_gate_pass_rows": int(decision["incumbent_four_metric_gate_pass"].sum()),
        },
        "inputs": {
            "config": {"path": config_path.as_posix(), "sha256": file_sha256(config_path)},
            "state": {"path": state_path.as_posix(), "sha256": file_sha256(state_path)},
            "registry": {"path": registry_path.as_posix(), "sha256": file_sha256(registry_path)},
            "master": {"path": master_path.as_posix(), "sha256": file_sha256(master_path)},
            "risk_map": {"path": risk_path.as_posix(), "sha256": file_sha256(risk_path)},
            "original_8_baseline": {"path": baseline_path.as_posix(), "sha256": file_sha256(baseline_path)},
            **{f"price_{ticker}": {"path": path.as_posix(), "sha256": file_sha256(path)} for ticker, path in cache_paths.items()},
        },
        "artifacts": {
            "summary": _artifact(paths["summary"], len(summary)), "orders": _artifact(paths["orders"], len(orders)),
            "fills": _artifact(paths["fills"], len(fills)), "workbook": _artifact(paths["workbook"]),
            "decision": _artifact(paths["decision"], len(decision)),
        },
    }
    atomic_write_text(output_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="组合回调资金池化整股反事实审计（只读）")
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--registry", default="data/cache/research/ndx_challenger_forward_registry_v3/active_forward_registry.csv")
    parser.add_argument("--master", default="data/cache/research/ndx_challenger_master_table_v1/challenger_master_table.csv")
    parser.add_argument("--risk-map", default="data/cache/research/ndx_challenger_forward_registry_v3/frozen_candidate_risk_chain_map.csv")
    parser.add_argument("--baseline", default="data/cache/research/ndx_challenger_forward_registry_v3/original_8_forward_baseline.csv")
    parser.add_argument("--start", default="2026-07-15")
    parser.add_argument("--end", default="")
    parser.add_argument("--output-dir", default="data/cache/research/portfolio_pullback_pooled_reserve_audit_v1")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args)
    except (OSError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"组合回调资金池化审计失败: {exc}", file=sys.stderr)
        return 2
    diagnosis = manifest["diagnosis"]
    print(
        "组合回调资金池化审计完成 | "
        f"sessions={diagnosis['sessions']} | bear={diagnosis['bear_sessions']} | "
        f"proposals={diagnosis['research_proposal_rows']} | fills={diagnosis['next_session_fill_rows']} | "
        "live_changed=False"
    )
    print(f"Manifest: {resolve(args.output_dir) / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
