"""状态管理 / 成只回填 / 手动 patch（第 6 步，让 state 闭环跟踪真实持仓）。

每个会改状态的命令都会：先备份 state.json→.bak，再写盘，并向 data/audit.jsonl 留痕。

子命令:
  show                            查看当前状态
  fill   NVDA --tier 0 [--price P] [--amount A] [--note "..."]   回填某档已成交（扣储备/加股数/记 TierFire/该档置已用）
  freeze NVDA  [--note "..."]     人工剔除=冻结：停止一切加仓、持仓保留、永不自动卖
  unfreeze NVDA                   解冻并重新装填档位
  rearm  NVDA  [--tier i]         手动重新装填全部/某档（预算重置为当前储备）
  set    NVDA --field H --value X 直接 patch 数值字段（H/reserve_cash/reserve_budget/shares/cost_basis/cap_total/cum_injected）
  buy    NVDA --amount A --price P   记录一笔人工核心买入（加股数/成本，不动档位/储备）

示例:
  python -m scripts.state_tool show
  python -m scripts.state_tool fill NVDA --tier 1 --price 96.30 --note "GTC成交"
  python -m scripts.state_tool freeze AMD --note "基本面恶化"
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config                       # noqa: E402
from core.helpers import setup_logging, resolve            # noqa: E402
from core.persist import (load_portfolio, save_portfolio,  # noqa: E402
                          backup_state, audit_log)
from core import engine as eng                             # noqa: E402
from core.state import TierFire                            # noqa: E402

STATE_PATH = "data/state.json"
SETTABLE = {"H", "reserve_cash", "reserve_budget", "shares", "cost_basis",
            "cap_total", "cum_injected"}


def _load(cfg):
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        print(f"未找到 {STATE_PATH}，请先 python -m scripts.live_signals --init")
        sys.exit(1)
    return pf


def _commit(pf, action, detail, note):
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    audit_log(action, detail, note)


def cmd_show(pf, cfg, args):
    print(f"\n{'标的':<7}{'股数':>12}{'成本基础':>14}{'储备':>12}{'参考H':>10}"
          f"{'累计注资':>12}{'档状态':>12}{'冻结':>6}")
    tv_sh = tv_res = tv_cost = tv_inj = 0.0
    for t, s in pf.symbols.items():
        armed = "".join("●" if a else "○" for a in s.tier_armed)
        print(f"{t:<7}{s.shares:>12.3f}{s.cost_basis:>14,.0f}{s.reserve_cash:>12,.0f}"
              f"{s.H:>10.2f}{s.cum_injected:>12,.0f}{armed:>12}{'是' if s.frozen else '':>6}")
        tv_sh += s.shares; tv_res += s.reserve_cash; tv_cost += s.cost_basis; tv_inj += s.cum_injected
    print(f"\n累计投入本金: {sum(f.amount for f in pf.flows):,.0f}  | 总成本基础: {tv_cost:,.0f}"
          f"  | 总储备: {tv_res:,.0f}")
    print("档状态: ●=已装填 ○=已用/未装填（顺序=浅档→深档）")
    fires = [(t, f) for t, s in pf.symbols.items() for f in s.fires]
    if fires:
        print(f"\n最近档位成交（共 {len(fires)} 笔）:")
        for t, f in fires[-8:]:
            print(f"  {f.date}  {t}  {f.threshold:+.0%}档  @{f.fill_price:.2f}  "
                  f"金额{f.amount:,.0f}  {f.shares:.3f}股")


def cmd_fill(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    i = args.tier
    thr = cfg.portfolio.tiers.thresholds
    if not (0 <= i < len(thr)):
        print(f"档位下标越界，应在 0..{len(thr)-1}"); return
    if not st.tier_armed[i]:
        print(f"{t} 第 {i} 档（{thr[i]:+.0%}）当前未装填，无法回填成交"); return
    limit = st.H * (1 + thr[i])
    ladder = {e.tier_index: e for e in eng.compute_ladder(st, cfg)}
    planned = ladder[i].amount if i in ladder else min(
        cfg.portfolio.tiers.deploy_ratios[i] * st.reserve_budget, st.reserve_cash)
    price = args.price if args.price is not None else limit
    amount = args.amount if args.amount is not None else planned
    amount = min(amount, st.reserve_cash)
    if amount <= 0 or price <= 0:
        print(f"金额/价格无效（amount={amount}, price={price}，储备={st.reserve_cash:,.0f}）"); return
    shares = amount / price
    st.shares += shares
    st.cost_basis += amount
    st.reserve_cash -= amount
    st.tier_armed[i] = False
    st.fires.append(TierFire(date=date.today().isoformat(), tier_index=i, threshold=thr[i],
                             limit_price=limit, fill_price=price, amount=amount, shares=shares))
    _commit(pf, "fill", {"ticker": t, "tier": i, "price": price,
                         "amount": amount, "shares": shares}, args.note)
    print(f"✓ 已回填 {t} {thr[i]:+.0%}档成交：{amount:,.0f} @ {price:.2f} = {shares:.3f}股；"
          f"该档置为已用，剩余储备 {st.reserve_cash:,.0f}")


def cmd_freeze(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    eng.freeze_symbol(st)
    _commit(pf, "freeze", {"ticker": t}, args.note)
    print(f"✓ {t} 已冻结：停止一切加仓，持仓 {st.shares:.3f} 股保留，核心永不自动卖。")


def cmd_unfreeze(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    st.frozen = False
    st.tier_armed = [True] * len(cfg.portfolio.tiers.thresholds)
    st.reserve_budget = st.reserve_cash
    _commit(pf, "unfreeze", {"ticker": t}, args.note)
    print(f"✓ {t} 已解冻并重新装填档位。")


def cmd_rearm(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    n = len(cfg.portfolio.tiers.thresholds)
    if args.tier is not None:
        st.tier_armed[args.tier] = True
        detail = {"ticker": t, "tier": args.tier}
    else:
        st.tier_armed = [True] * n
        st.reserve_budget = st.reserve_cash
        detail = {"ticker": t, "tier": "all"}
    _commit(pf, "rearm", detail, args.note)
    print(f"✓ {t} 已重新装填：{''.join('●' if a else '○' for a in st.tier_armed)}")


def cmd_set(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    if args.field not in SETTABLE:
        print(f"不可设置字段 {args.field}，可选: {sorted(SETTABLE)}"); return
    old = getattr(st, args.field)
    setattr(st, args.field, float(args.value))
    _commit(pf, "set", {"ticker": t, "field": args.field,
                        "old": old, "new": float(args.value)}, args.note)
    print(f"✓ {t}.{args.field}: {old} → {float(args.value)}（已备份 .bak、已留痕）")


def cmd_buy(pf, cfg, args):
    t = args.ticker.upper()
    st = pf.symbols[t]
    amount, price = float(args.amount), float(args.price)
    sh = amount / price
    st.shares += sh
    st.cost_basis += amount
    _commit(pf, "buy", {"ticker": t, "amount": amount, "price": price, "shares": sh}, args.note)
    print(f"✓ 记录 {t} 人工核心买入：{amount:,.0f} @ {price:.2f} = {sh:.3f}股（不动档位/储备）")


def main() -> int:
    ap = argparse.ArgumentParser(description="us_ratchet 状态管理")
    ap.add_argument("--config", default="config/config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("show")
    p = sub.add_parser("fill"); p.add_argument("ticker"); p.add_argument("--tier", type=int, required=True)
    p.add_argument("--price", type=float); p.add_argument("--amount", type=float); p.add_argument("--note", default="")
    p = sub.add_parser("freeze"); p.add_argument("ticker"); p.add_argument("--note", default="")
    p = sub.add_parser("unfreeze"); p.add_argument("ticker"); p.add_argument("--note", default="")
    p = sub.add_parser("rearm"); p.add_argument("ticker"); p.add_argument("--tier", type=int); p.add_argument("--note", default="")
    p = sub.add_parser("set"); p.add_argument("ticker"); p.add_argument("--field", required=True)
    p.add_argument("--value", required=True); p.add_argument("--note", default="")
    p = sub.add_parser("buy"); p.add_argument("ticker"); p.add_argument("--amount", required=True)
    p.add_argument("--price", required=True); p.add_argument("--note", default="")

    args = ap.parse_args()
    setup_logging(logging.WARNING)
    cfg = load_config(args.config)
    pf = _load(cfg)

    if args.cmd not in ("show",) and args.ticker.upper() not in pf.symbols:
        print(f"标的 {args.ticker.upper()} 不在组合中：{list(pf.symbols)}"); return 1

    {"show": cmd_show, "fill": cmd_fill, "freeze": cmd_freeze, "unfreeze": cmd_unfreeze,
     "rearm": cmd_rearm, "set": cmd_set, "buy": cmd_buy}[args.cmd](pf, cfg, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())