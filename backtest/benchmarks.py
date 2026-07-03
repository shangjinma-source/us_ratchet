"""三基准——全部领取与策略**完全相同**的现金流时间表，否则对比无效。

  1. 即时全仓·权重(cap)   : 每笔流入按 cap 权重立即全额买入持有（0 储备）
  2. 定投 DCA·权重(cap)    : 每笔流入在其后 N 个交易日内逐日均摊买入（入场平滑）
  3. 即时全仓·等权          : 每笔流入按等权立即全额买入持有

注：周期性注资下「即时全仓」本身已是 DCA 的一种；基准 2 通过逐笔再平滑入场与基准 1 区分。
"""
from __future__ import annotations

import numpy as np


def _weights_cap(cfg) -> dict:
    total = sum(s.cap_total for s in cfg.symbols)
    return {s.ticker: s.cap_total / total for s in cfg.symbols}


def _weights_equal(cfg) -> dict:
    n = len(cfg.symbols)
    return {s.ticker: 1.0 / n for s in cfg.symbols}


def run_benchmark(prices: dict, dates, flow_by_index: dict, cfg,
                  mode: str, dca_days: int = 5) -> np.ndarray:
    """返回每日组合净值曲线（持有市值 + 未投放现金）。
    prices: ticker -> np.ndarray（与 dates 对齐的收盘价）
    flow_by_index: {day_index: amount}
    mode: 'fullinvest_cap' / 'dca_cap' / 'fullinvest_equal'
    """
    n = len(dates)
    weights = _weights_equal(cfg) if mode == "fullinvest_equal" else _weights_cap(cfg)
    tickers = list(prices.keys())
    shares = {t: 0.0 for t in tickers}
    pending = []   # [(due_index, ticker, amount)] 仅 DCA 用；未投放金额即现金
    equity = np.zeros(n)

    for i in range(n):
        # 先消化到期批次（含当日 due=i）
        if pending:
            still = []
            for due, t, amt in pending:
                if i >= due:
                    shares[t] += amt / prices[t][i]
                else:
                    still.append((due, t, amt))
            pending = still
        # 当日流入
        inflow = flow_by_index.get(i, 0.0)
        if inflow > 0:
            if mode == "dca_cap":
                for t in tickers:
                    each = inflow * weights[t] / dca_days
                    for k in range(dca_days):
                        pending.append((i + k, t, each))
                # 立即消化当日那批 (due=i)
                still = []
                for due, t, amt in pending:
                    if due <= i:
                        shares[t] += amt / prices[t][i]
                    else:
                        still.append((due, t, amt))
                pending = still
            else:
                for t in tickers:
                    shares[t] += inflow * weights[t] / prices[t][i]
        # 净值 = 持仓市值 + 未投放现金（pending 余额）
        mv = sum(shares[t] * prices[t][i] for t in tickers)
        cash_left = sum(amt for _, _, amt in pending)
        equity[i] = mv + cash_left
    return equity
