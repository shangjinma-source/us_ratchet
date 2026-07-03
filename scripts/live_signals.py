"""每日实盘信号 / 限价挂单阶梯（你每天收盘后跑这个，照着挂次日 GTC 单）。

用法（PyCharm 终端）:
    python -m scripts.live_signals --init          # 首次建仓（按 config 的 cap 建核心+储备）
    python -m scripts.live_signals                 # 每日：更新 H、输出挂单阶梯
    python -m scripts.live_signals --set-cap NVDA 120000   # 把 NVDA 上限调到 12 万(=注资)

状态落盘在 data/state.json，重启不丢。
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config              # noqa: E402
from core.helpers import setup_logging, resolve   # noqa: E402
from core.persist import save_portfolio, load_portfolio  # noqa: E402
from core import live                              # noqa: E402
from data.fetch import get_bars                    # noqa: E402

STATE_PATH = "data/state.json"


def _latest_closes(cfg) -> dict:
    out = {}
    for s in cfg.symbols:
        df, _ = get_bars(s.ticker, cfg)
        out[s.ticker] = float(df["Close"].iloc[-1])
    return out


def _safe_price(cfg) -> float | None:
    """抓安全腿(SGOV)最新收盘。无 safe_leg 配置 → None（防御层关闭）。"""
    sl = getattr(cfg, "safe_leg", None)
    if sl is None:
        return None
    df, _ = get_bars(sl.ticker, cfg)
    return float(df["Close"].iloc[-1])


def _print_defensive(dfn, safe_price: float) -> None:
    if dfn is None:
        return
    print(f"\n{'='*78}")
    print(f"防御层再平衡  |  方向 {dfn.direction.upper()}  "
          f"安全腿权重 {dfn.safe_weight:.1%} → 目标 {dfn.target_weight:.0%}  "
          f"(偏离 {abs(dfn.safe_weight - dfn.target_weight):.1%} ≥ 执行带，触发)")
    print(f"{'='*78}")
    verb = "卖出篮子→增厚安全腿" if dfn.direction == "trim" else "卖出安全腿→回补篮子"
    print(f"  篮子市值 {dfn.basket_value:,.0f}  安全腿市值 {dfn.safe_value:,.0f}  "
          f"|  本次挪动 {abs(dfn.move):,.0f}（{verb}）")
    print(f"    {'标的':<8}{'方向':>6}{'金额':>12}{'股数':>10}{'(其中抽储备)':>14}")
    for o in dfn.orders:
        extra = f"{o.from_reserve:,.0f}" if o.from_reserve > 0 else "-"
        print(f"    {o.ticker:<8}{o.side:>6}{o.amount:>12,.0f}{o.shares:>10.2f}{extra:>14}")
    so = dfn.safe_order
    print(f"    {'-'*50}")
    print(f"    {so.ticker:<8}{so.side:>6}{so.amount:>12,.0f}{so.shares:>10.2f}{'(安全腿反向单 @'+f'{safe_price:.2f}'+')':>22}")


def _print_signals(signals, cfg):
    total_res = sum(s.reserve_cash for s in signals)
    total_mv = sum(s.market_value for s in signals)
    print(f"\n{'='*78}")
    print(f"每日挂单阶梯  |  持仓市值 {total_mv:,.0f}  储备余额 {total_res:,.0f}")
    print(f"{'='*78}")
    for s in signals:
        tag = " [已冻结]" if s.frozen else ""
        print(f"\n▌{s.ticker}{tag}  现价 {s.last_close:.2f}  参考高点H {s.H:.2f}  "
              f"距高点 {s.drawdown:+.1%}  储备 {s.reserve_cash:,.0f}")
        for amt, px, why in s.immediate_buys:
            print(f"    ★ 立即买入: {amt:,.0f}  @≈{px:.2f}  （{why}）")
        if not s.ladder:
            if not s.frozen:
                print("    （无已装填档位：可能已全部触发，等创新高 re-arm）")
            continue
        print(f"    {'档':>5}{'触发限价':>12}{'计划金额':>12}{'股数':>10}")
        for e in s.ladder:
            print(f"    {e.threshold:>5.0%}{e.limit_price:>12.2f}{e.amount:>12,.0f}{e.shares:>10.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 实盘信号")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--init", action="store_true", help="首次建仓")
    ap.add_argument("--set-cap", nargs=2, metavar=("TICKER", "AMOUNT"),
                    help="调整某只 cap 上限（增量=注资）")
    args = ap.parse_args()

    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    state_path = resolve(STATE_PATH)
    today = date.today().isoformat()

    print("抓取最新收盘价...")
    closes = _latest_closes(cfg)
    safe_px = _safe_price(cfg)        # SGOV 最新收盘（无 safe_leg → None）

    if args.init:
        if load_portfolio(state_path) is not None:
            print(f"⚠ 状态已存在 {state_path}，--init 会覆盖。如确认请先删除该文件。")
            return 1
        pf = live.init_portfolio(cfg, closes, safe_px)
        live.advance_trading_day(pf, today)      # 建仓日 = 第 1 个交易日
        save_portfolio(pf, state_path)
        print("已建仓。各标的立即买入核心：")
        for t, st in pf.symbols.items():
            print(f"  {t}: 核心买入 {st.cost_basis:,.0f} @≈{closes[t]:.2f}  储备 {st.reserve_cash:,.0f}")
        if pf.target_safe_weight > 0 and safe_px:
            basket0 = sum(s.market_value(closes[t]) + s.reserve_cash
                          for t, s in pf.symbols.items())
            safe0 = pf.safe_shares * safe_px
            print(f"  {pf.safe_ticker}: 安全腿建仓 {safe0:,.0f} @≈{safe_px:.2f} "
                  f"= {pf.safe_shares:,.2f} 股  |  篮子 {basket0:,.0f} : 安全腿 {safe0:,.0f} "
                  f"= {basket0/(basket0+safe0):.0%}:{safe0/(basket0+safe0):.0%}")
        signals = live.generate_signals(pf, closes, cfg)
        dfn = live.compute_defensive(pf, closes, safe_px, cfg)   # 建仓首日已在目标比，通常 None
        save_portfolio(pf, state_path)
        _print_signals(signals, cfg)
        _print_defensive(dfn, safe_px or 0.0)
        return 0

    pf = load_portfolio(state_path)
    if pf is None:
        print(f"未找到状态文件 {state_path}，请先运行：python -m scripts.live_signals --init")
        return 1

    live.advance_trading_day(pf, today)          # 推进当日交易日序号（同日多次运行幂等）

    if args.set_cap:
        ticker, amount = args.set_cap[0].upper(), float(args.set_cap[1])
        if ticker not in pf.symbols:
            print(f"标的 {ticker} 不在组合中")
            return 1
        delta = live.apply_cap_change(pf, ticker, amount, closes[ticker], cfg)
        if delta > 0:
            print(f"{ticker} 注资 {delta:,.0f}：立即核心买入 + 储备已更新。")
        else:
            print(f"{ticker} cap 未提高，无注资。")
        save_portfolio(pf, state_path)

    signals = live.generate_signals(pf, closes, cfg)
    dfn = live.compute_defensive(pf, closes, safe_px, cfg)   # 防御层（在棘轮之后）
    save_portfolio(pf, state_path)   # 持久化 H / re-arm / 交易日序号 / 防御层 shares&safe_shares
    _print_signals(signals, cfg)
    _print_defensive(dfn, safe_px or 0.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())