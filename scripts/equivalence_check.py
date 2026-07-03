"""回测/实盘 equivalence 自检。

证明四件事：
  [结构] 实盘 compute_ladder 给出的触发限价 == 回测 fire_tiers 判定成交用的限价
         （二者都是 H×(1+档位阈值)，同一函数同一公式）。
  [行为] 同一条价格路径下，"实盘阶梯 + 市场撮合(low≤limit 成交)" 的累计买入
         == 回测内部 fire_tiers 的累计买入（股数/储备/成本基础一致）。
  [空弹药触及] 档位被触及但当时储备为空、其后注资补回 → 回测 fire_tiers 与实盘阶梯撮合一致
         （守 A1 回归：无弹药时不得 disarm 档位）。
  [注资分批] 注资触发分批(ladder_core) 时，回测式 day-index 循环 与实盘式
         (advance_trading_day + apply_cap_change + generate_signals) 的分批到期/累计买入一致
         （守 A2 回归：实盘必须按真实交易日逐批兑现，而非一次性冲掉）。

用法: python -m scripts.equivalence_check
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import load_config, Symbol   # noqa: E402
from core import engine as eng                 # noqa: E402
from core import live                          # noqa: E402
from core.state import SymbolState, Portfolio  # noqa: E402
from backtest.engine import _run_defensive_fund  # noqa: E402


def _fresh_state(cfg, cap, price):
    return eng.init_symbol("TEST", cap, price, cfg)


def check_structural(cfg, n=200) -> bool:
    """随机状态下，compute_ladder 的限价 == H×(1+thr)。"""
    rng = np.random.default_rng(0)
    thr = cfg.portfolio.tiers.thresholds
    ok = True
    for _ in range(n):
        st = _fresh_state(cfg, 10000, 100.0)
        st.H = float(rng.uniform(50, 500))
        st.reserve_cash = float(rng.uniform(0, 5000))
        st.reserve_budget = st.reserve_cash
        st.tier_armed = [bool(rng.integers(0, 2)) for _ in thr]
        ladder = eng.compute_ladder(st, cfg)
        for e in ladder:
            expect = st.H * (1 + thr[e.tier_index])
            if abs(e.limit_price - expect) > 1e-9:
                ok = False
                print(f"  ✗ 限价不一致: tier {e.tier_index} got {e.limit_price} expect {expect}")
    print(f"[结构] {n} 随机状态：限价公式一致 = {'通过' if ok else '失败'}")
    return ok


def check_behavioral(cfg, days=600) -> bool:
    """同一价格路径：回测 fire_tiers vs 实盘阶梯+撮合，结果一致。"""
    rng = np.random.default_rng(7)
    r = rng.normal(0.0005, 0.02, days)
    r[200:240] += (1 - 0.45) ** (1 / 40) - 1
    close = 100 * np.exp(np.cumsum(r))
    opn = close * (1 + rng.normal(0, 0.003, days))
    low = np.minimum(opn, close) * (1 - np.abs(rng.normal(0, 0.006, days)))

    # --- A: 回测路径（fire_tiers 内部撮合）---
    a = _fresh_state(cfg, 100000, close[0])
    for i in range(1, days):
        if i > 0:
            eng.fire_tiers(a, opn[i], low[i], f"d{i}", cfg)
        eng.update_high(a, close[i], cfg)

    # --- B: 实盘路径（compute_ladder 出限价 → 市场撮合 low≤limit → 成交 min(open,limit)）---
    b = _fresh_state(cfg, 100000, close[0])
    for i in range(1, days):
        ladder = eng.compute_ladder(b, cfg)      # 收盘后挂次日单
        # 次日撮合
        for e in ladder:
            if low[i] <= e.limit_price:
                fill = min(opn[i], e.limit_price)
                amt = min(e.amount, b.reserve_cash)
                if amt > 0:
                    b.shares += amt / fill
                    b.cost_basis += amt
                    b.reserve_cash -= amt
                b.tier_armed[e.tier_index] = False
        eng.update_high(b, close[i], cfg)

    same = (abs(a.shares - b.shares) < 1e-6 and
            abs(a.reserve_cash - b.reserve_cash) < 1e-6 and
            abs(a.cost_basis - b.cost_basis) < 1e-6)
    print(f"[行为] 回测撮合 vs 实盘阶梯撮合：")
    print(f"        股数 A={a.shares:.4f} B={b.shares:.4f}")
    print(f"        储备 A={a.reserve_cash:.2f} B={b.reserve_cash:.2f}")
    print(f"        成本 A={a.cost_basis:.2f} B={b.cost_basis:.2f}")
    print(f"        一致 = {'通过' if same else '失败'}")
    return same


def check_empty_reserve_touch(cfg) -> bool:
    """覆盖 A1：档位被价格触及、但当时储备为空 → 注资补回、价格仍在档下方 → 两引擎应一致。
    （修复前 fire_tiers 会在此情形把该档 disarm 导致回测少买；本用例专门守这条回归。）"""
    thr = cfg.portfolio.tiers.thresholds
    H = 100.0
    limit0 = H * (1 + thr[0])
    low_touch = limit0 - 5.0      # 跌穿最浅档线下方
    opn = low_touch + 2.0

    def fresh():
        st = eng.init_symbol("T", 10000, 100.0, cfg)
        st.reserve_cash = 0.0      # 干火药暂时为 0（上一轮深跌已花光）
        st.reserve_budget = 10000.0
        st.tier_armed = [True] * len(thr)
        st.H = H
        return st

    def live_match(st):
        for e in eng.compute_ladder(st, cfg):
            if low_touch <= e.limit_price:
                fill = min(opn, e.limit_price)
                amt = min(e.amount, st.reserve_cash)
                if amt > 0:
                    st.shares += amt / fill
                    st.cost_basis += amt
                    st.reserve_cash -= amt
                st.tier_armed[e.tier_index] = False

    a = fresh()   # 回测引擎路径
    b = fresh()   # 实盘引擎路径
    # 第1天：触及最浅档，但储备=0
    eng.fire_tiers(a, opn, low_touch, "d1", cfg)
    live_match(b)
    # 第2天：注资补回储备，价格仍在档下方
    a.reserve_cash = 10000.0
    b.reserve_cash = 10000.0
    eng.fire_tiers(a, opn, low_touch, "d2", cfg)
    live_match(b)

    same = (abs(a.shares - b.shares) < 1e-6 and
            abs(a.reserve_cash - b.reserve_cash) < 1e-6 and
            abs(a.cost_basis - b.cost_basis) < 1e-6)
    print(f"[空弹药触及] 注资补回后回测 vs 实盘：")
    print(f"        股数 A={a.shares:.4f} B={b.shares:.4f}")
    print(f"        储备 A={a.reserve_cash:.2f} B={b.reserve_cash:.2f}")
    print(f"        一致 = {'通过' if same else '失败'}")
    return same


def check_injection_ladder(cfg) -> bool:
    """覆盖 A2：注资触发分批(ladder_core) 时，回测式 day-index 循环 与实盘式
    (advance_trading_day + apply_cap_change + generate_signals) 的分批到期/累计买入应一致。
    修复前实盘用 today_index=0 排批、generate_signals 用 10**9 冲掉 → 分批立即变一次性。"""
    c = copy.deepcopy(cfg)
    c.portfolio.injection_mode = "ladder_core"
    c.portfolio.injection_ladder_tranches = 4
    c.portfolio.injection_ladder_spacing_days = 5
    c.portfolio.core_ratio = 0.90
    c.portfolio.injection_core_ratio = 0.90
    c.symbols = [Symbol(ticker="X", cap_total=100000)]

    price = 100.0
    days = 30
    inject_day = 3
    inject_amount = 50000.0

    # A: 回测式直接循环（与 backtest/engine 同构：process_pending(i) → 注资(i) → update_high）
    a = eng.init_symbol("X", 100000, price, c)
    for i in range(1, days + 1):
        eng.process_pending(a, price, i)
        if i == inject_day:
            eng.apply_injection(a, inject_amount, price, i, c)
        eng.update_high(a, price, c)

    # B: 实盘式（live 包装：每日 advance → 注资 → generate_signals[内部 process_pending]）
    pf = Portfolio(symbols={"X": eng.init_symbol("X", 100000, price, c)}, flows=[])
    closes = {"X": price}
    for i in range(1, days + 1):
        live.advance_trading_day(pf, f"2025-01-{i:02d}")
        if pf.day_index == inject_day:
            live.apply_cap_change(pf, "X", 100000 + inject_amount, price, c)
        live.generate_signals(pf, closes, c)
    b = pf.symbols["X"]

    same = (abs(a.shares - b.shares) < 1e-6 and
            abs(a.reserve_cash - b.reserve_cash) < 1e-6 and
            abs(a.cost_basis - b.cost_basis) < 1e-6 and
            len(a.pending_ladder) == len(b.pending_ladder))
    print(f"[注资分批] 回测循环 vs 实盘包装"
          f"（{c.portfolio.injection_ladder_tranches} 批 / 间隔 {c.portfolio.injection_ladder_spacing_days} 日）：")
    print(f"        股数 A={a.shares:.4f} B={b.shares:.4f}")
    print(f"        成本 A={a.cost_basis:.2f} B={b.cost_basis:.2f}")
    print(f"        未到期批次 A={len(a.pending_ladder)} B={len(b.pending_ladder)}")
    print(f"        一致 = {'通过' if same else '失败'}")
    return same


def check_defensive_rebalance(cfg, days=900) -> bool:
    """覆盖防御层(B)同源：重构后的 _run_defensive_fund（调用 core.compute_defensive_rebalance）
    必须与"原聚合公式 oracle"逐点一致（守零回归：移进 core 前后组合 NAV/换手/再平衡次数不变）。
    同时验证 core 决策的符号/守恒语义。用合成风险腿 NAV，覆盖周期 与 漂移带 两种触发。"""
    import numpy as np

    rng = np.random.default_rng(11)
    r = rng.normal(0.0006, 0.02, days)
    r[300:340] += (1 - 0.45) ** (1 / 40) - 1          # 中段插一波 -45% 深跌
    risky_nav = 1.0 * np.exp(np.cumsum(r))
    risky_nav = np.concatenate([[1.0], risky_nav])    # nav[0]=1
    grid = list(range(len(risky_nav)))                # 仅用作长度/下标，_run_defensive_fund 不读日期
    flows = [(0, 1_000_000.0), (21, 50_000.0), (252, 50_000.0), (504, 50_000.0)]

    def oracle(w_safe, rebal_days, rebal_band):
        """原始聚合实现（重构前的公式），作为零回归基准。"""
        n = len(risky_nav)
        rr = np.zeros(n)
        for i in range(1, n):
            prev = risky_nav[i - 1]
            rr[i] = (risky_nav[i] / prev - 1.0) if prev > 0 else 0.0
        rs = 0.04 / 252.0
        fbi = {}
        for i, amt in flows:
            fbi[i] = fbi.get(i, 0.0) + amt
        risky_val = safe_val = units = 0.0
        nav = np.zeros(n); equity = np.zeros(n); turnover = 0.0; n_rebal = 0
        P = int(rebal_days) if (rebal_days and rebal_days >= 1) else 0
        for i in range(n):
            if i > 0:
                risky_val *= (1.0 + rr[i]); safe_val *= (1.0 + rs)
            tv_pre = risky_val + safe_val
            nav_b = (tv_pre / units) if units > 0 else 1.0
            amt = fbi.get(i, 0.0)
            if amt:
                units += amt / nav_b
                risky_val += amt * (1.0 - w_safe); safe_val += amt * w_safe
            if i > 0:
                tv = risky_val + safe_val
                cur_w = (safe_val / tv) if tv > 0 else w_safe
                due = bool(P and (i % P == 0))
                drift = bool(rebal_band > 0 and abs(cur_w - w_safe) >= rebal_band)
                if (due or drift) and tv > 0:
                    tgt_risky = tv * (1.0 - w_safe)
                    turnover += abs(tgt_risky - risky_val)
                    risky_val = tgt_risky; safe_val = tv * w_safe; n_rebal += 1
            tv = risky_val + safe_val
            equity[i] = tv
            nav[i] = (tv / units) if units > 0 else (nav[i - 1] if i > 0 else 1.0)
        return nav, equity, turnover, n_rebal

    ok = True
    cases = [(0.0, 21, 0.0), (0.30, 21, 0.0), (0.40, 0, 0.05), (0.40, 21, 0.05), (0.50, 1, 0.0)]
    for w, rd, rb in cases:
        nav_a, eq_a, tn_a, nr_a = oracle(w, rd, rb)
        nav_b, eq_b, _, tn_b, nr_b = _run_defensive_fund(grid, risky_nav, flows, 0.04, w, rd, rb)
        dnav = float(np.max(np.abs(nav_a - nav_b))) if len(nav_a) else 0.0
        deq = float(np.max(np.abs(eq_a - eq_b))) if len(eq_a) else 0.0
        dtn = abs(tn_a - tn_b)
        same = (dnav < 1e-9 and deq < 1e-6 and dtn < 1e-6 and nr_a == nr_b)
        ok = ok and same
        tag = "通过" if same else "失败"
        print(f"  W={w:.0%} days={rd} band={rb:.0%}: ΔNAV={dnav:.2e} ΔEq={deq:.2e} "
              f"Δ换手={dtn:.2e} 再平衡 {nr_a}={nr_b} → {tag}")

    # core 决策语义自检：符号 + 守恒 + band 静默
    m_trim = eng.compute_defensive_rebalance(90.0, 10.0, 0.30, 0.0)   # 安全腿偏低 → 需增厚(>0)
    m_buy = eng.compute_defensive_rebalance(50.0, 50.0, 0.30, 0.0)    # 安全腿偏高 → 需回补(<0)
    m_none = eng.compute_defensive_rebalance(70.0, 30.0, 0.30, 0.05)  # 恰在目标且<band → None
    sem = (m_trim is not None and m_trim > 0 and
           m_buy is not None and m_buy < 0 and
           m_none is None)
    ok = ok and sem
    print(f"  core 决策语义(符号/守恒/band静默): {'通过' if sem else '失败'} "
          f"(trim={m_trim:+.1f} rebuy={m_buy:+.1f} none={m_none})")
    print(f"[防御层B] 重构后 _run_defensive_fund vs 原公式 + core 决策语义：{'通过' if ok else '失败'}")
    return ok


def main() -> int:
    cfg = load_config()
    print("=== us_ratchet 回测/实盘 equivalence 自检 ===")
    ok1 = check_structural(cfg)
    ok2 = check_behavioral(cfg)
    ok3 = check_empty_reserve_touch(cfg)
    ok4 = check_injection_ladder(cfg)
    ok5 = check_defensive_rebalance(cfg)
    all_ok = ok1 and ok2 and ok3 and ok4 and ok5
    print(f"\n总判定: {'✅ 同源一致' if all_ok else '❌ 存在漂移，需排查'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())