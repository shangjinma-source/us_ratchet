"""共享信号引擎（回测与实盘同源的唯一信号来源）。

纯函数、无 I/O。回测驱动器与实盘驱动器都调用这里：
  - update_high     : 棘轮上调 H + 创新高 re-arm
  - apply_injection : 注资拆分（立即核心 / 分批 / 全储备）
  - process_pending : 执行到期的分批核心买入
  - compute_ladder  : 由当前 H + 已装填档位算出限价挂单阶梯（实盘照挂、回测判成交都用它）
  - fire_tiers      : 回测成交模型——当日 low ≤ limit 则触发，成交价 min(open, limit)
  - compute_defensive_rebalance : 组合层防御纪律——由风险腿/安全腿当前市值算出"该挪多少"
                       的带符号再平衡金额（实盘据此对篮子+安全腿挂单、回测据此调拨两腿，同源）

「阶梯」由 compute_ladder 唯一产出 → 实盘挂的限价与回测成交判定的限价完全一致；
"再平衡金额"由 compute_defensive_rebalance 唯一产出 → 实盘防御层动作与回测组合层调拨完全一致。
这两处是回测/实盘 equivalence 的根。
"""
from __future__ import annotations

from dataclasses import dataclass

from core.state import SymbolState, TierFire


@dataclass
class LadderEntry:
    tier_index: int
    threshold: float
    limit_price: float
    amount: float
    shares: float
    armed: bool


def _buy(state: SymbolState, amount: float, price: float) -> float:
    """以 price 买入 amount 金额，返回成交股数；更新股数与成本基础。"""
    if amount <= 0 or price <= 0:
        return 0.0
    sh = amount / price
    state.shares += sh
    state.cost_basis += amount
    return sh


def consume_pending_core_cash(state: SymbolState, amount: float) -> float:
    """取消/转出已排分批但未成交的核心现金，并同步缩减待执行分批。"""
    need = max(0.0, float(amount or 0.0))
    available = max(0.0, float(getattr(state, "pending_core_cash", 0.0) or 0.0))
    take = min(need, available)
    if take <= 1e-12:
        return 0.0

    state.pending_core_cash = max(0.0, available - take)
    remaining = take
    still = []
    for due, amt in state.pending_ladder:
        amt = float(amt)
        if remaining <= 1e-12:
            still.append((due, amt))
            continue
        used = min(amt, remaining)
        left = amt - used
        remaining -= used
        if left > 1e-9:
            still.append((due, left))
    state.pending_ladder = still
    return take


def init_symbol(ticker: str, cap_total: float, price: float, cfg) -> SymbolState:
    """初始建仓：core_ratio 立即买核心，其余进储备。H 以建仓价起。"""
    p = cfg.portfolio
    st = SymbolState(ticker=ticker, cap_total=cap_total,
                     tier_armed=[True] * len(p.tiers.thresholds),
                     H=price)
    st.cum_injected += cap_total
    core_now = cap_total * p.core_ratio
    _buy(st, core_now, price)
    st.reserve_cash += cap_total * (1 - p.core_ratio)
    st.reserve_budget = st.reserve_cash
    return st


def update_high(state: SymbolState, ref_price: float, cfg) -> bool:
    """棘轮上调 H；创新高（超过旧 H × (1+eps)）则全部 re-arm 并刷新预算快照。
    返回是否发生 re-arm。ref_price 由调用方按 high_basis 传入（close 或 high）。"""
    p = cfg.portfolio
    eps = p.rearm.new_high_epsilon_pct
    if ref_price > state.H * (1 + eps):
        state.H = ref_price
        state.tier_armed = [True] * len(p.tiers.thresholds)
        state.reserve_budget = state.reserve_cash   # 新周期预算 = 当前干火药
        return True
    # H 单调不降：即使未达 eps 也至少抬到 ref_price（避免 eps 造成 H 滞后）
    if ref_price > state.H:
        state.H = ref_price
    return False


def apply_injection(state: SymbolState, delta: float, price: float,
                    today_index: int, cfg) -> None:
    """注资拆分。delta 为本次新增本金（= 抬高 cap 的增量）。"""
    if delta <= 0 or state.frozen:
        return
    p = cfg.portfolio
    state.cum_injected += delta
    state.cap_total += delta

    if p.injection_mode == "all_reserve":
        state.reserve_cash += delta
        state.reserve_budget += delta
        return

    core_part = delta * p.injection_core_ratio
    res_part = delta - core_part

    # 接近 ATH 保护开关：核心份转入储备（默认关）
    if p.inject_skip_core_near_high and price >= state.H * (1 - 0.01):
        res_part += core_part
        core_part = 0.0

    state.reserve_cash += res_part
    state.reserve_budget += res_part   # 注资放大后续每档加仓金额

    if core_part <= 0:
        return

    # size 闸：核心份相对现有核心仓位过大 → 分批；否则立即买
    cur_core_val = state.shares * price
    ladder = (p.injection_mode == "ladder_core") or \
             (cur_core_val > 0 and core_part > p.injection_ladder_trigger_ratio * cur_core_val)
    if ladder:
        n = max(1, p.injection_ladder_tranches)
        each = core_part / n
        state.pending_core_cash += core_part
        for k in range(n):
            due = today_index + p.injection_ladder_spacing_days * (k + 1)
            state.pending_ladder.append((due, each))
    else:
        _buy(state, core_part, price)


def process_pending(state: SymbolState, price: float, today_index: int) -> float:
    """执行所有到期的分批核心买入，返回当日买入金额。"""
    if not state.pending_ladder or state.frozen:
        return 0.0
    use_cash_book = float(getattr(state, "pending_core_cash", 0.0) or 0.0) > 1e-9
    bought, still = 0.0, []
    for due, amt in state.pending_ladder:
        amt = float(amt)
        if today_index >= due:
            buy_amt = amt
            if use_cash_book:
                available = max(0.0, float(state.pending_core_cash or 0.0))
                buy_amt = min(amt, available)
                state.pending_core_cash = max(0.0, available - buy_amt)
                leftover = amt - buy_amt
                if leftover > 1e-6:
                    still.append((due, leftover))
            if buy_amt > 1e-9:
                _buy(state, buy_amt, price)
                bought += buy_amt
        else:
            still.append((due, amt))
    state.pending_ladder = still
    return bought


def compute_ladder(state: SymbolState, cfg) -> list[LadderEntry]:
    """由当前 H + 已装填档位算出限价挂单阶梯。冻结或无装填档位则空。
    金额受 reserve_cash 约束，阶梯总额不超过当前干火药。"""
    p = cfg.portfolio
    out: list[LadderEntry] = []
    if state.frozen:
        return out
    remaining = state.reserve_cash
    for i, thr in enumerate(p.tiers.thresholds):
        if not state.tier_armed[i]:
            continue
        limit = state.H * (1 + thr)
        amt = min(p.tiers.deploy_ratios[i] * state.reserve_budget, remaining)
        if amt <= 0 or limit <= 0:
            continue
        out.append(LadderEntry(tier_index=i, threshold=thr, limit_price=limit,
                               amount=amt, shares=amt / limit, armed=True))
        remaining -= amt
    return out


def fire_tiers(state: SymbolState, bar_open: float, bar_low: float,
               date_str: str, cfg) -> list[TierFire]:
    """回测成交模型：当日 low ≤ limit 视为成交，成交价 min(open, limit)。
    跳空击穿多档 → 当日一并触发（按从浅到深顺序，受 reserve_cash 约束）。"""
    p = cfg.portfolio
    fires: list[TierFire] = []
    if state.frozen:
        return fires
    for i, thr in enumerate(p.tiers.thresholds):
        if not state.tier_armed[i]:
            continue
        limit = state.H * (1 + thr)
        if bar_low <= limit:
            amt = min(p.tiers.deploy_ratios[i] * state.reserve_budget, state.reserve_cash)
            if amt <= 0:
                # 暂时无弹药：保持装填，等注资补回储备后仍可在该档成交。
                # 与 compute_ladder 同义（只读、amt<=0 跳过、不改状态）→ 回测/实盘同源。
                continue
            fill = min(bar_open, limit)        # 跳空低开取更优开盘价
            sh = _buy(state, amt, fill)
            state.reserve_cash -= amt
            state.tier_armed[i] = False
            f = TierFire(date=date_str, tier_index=i, threshold=thr,
                         limit_price=limit, fill_price=fill, amount=amt, shares=sh)
            state.fires.append(f)
            fires.append(f)
    return fires


def freeze_symbol(state: SymbolState) -> None:
    """人工剔除 = 冻结：停止一切加仓，核心永不自动卖，持仓保留。"""
    state.frozen = True
    if getattr(state, "pending_core_cash", 0.0) > 0:
        state.reserve_cash += state.pending_core_cash
        state.reserve_budget += state.pending_core_cash
        state.pending_core_cash = 0.0
    state.pending_ladder = []
    state.tier_armed = [False] * len(state.tier_armed)


# ===========================================================================
# 组合层防御纪律（B 方向）——独立于棘轮核心"只买不卖"的一条单独纪律。
# 棘轮核心永不主动卖；防御层负责"维持安全资产目标权重"：篮子涨出目标 → 减回安全腿，
# 篮子跌出目标 → 从安全腿回补篮子。决策只此一处（compute_defensive_rebalance），
# 回测在组合层据此调拨风险腿/安全腿两个聚合值，实盘据此把这笔带符号金额摊到各标的
# 下真实买/卖单、对安全腿(超短债 ETF)反向操作 → 同源。
# ===========================================================================
def compute_defensive_rebalance(risky_value: float, safe_value: float,
                                target_safe_weight: float,
                                rebal_band: float = 0.0) -> float | None:
    """防御层再平衡的唯一决策来源（纯函数、无 I/O、无状态）。

    给定风险腿/安全腿当前市值与目标安全资产权重，返回需要【从风险腿挪到安全腿】的
    带符号金额（组合总额守恒：safe += 返回值、risky -= 返回值）：
        >0 → 减仓风险腿、增厚安全腿（trim：卖篮子买安全腿）
        <0 → 回补风险腿、减薄安全腿（rebuy：卖安全腿买篮子）
        =0 → 恰在目标（仍是一次"动作"，是否记次由调用方定）
    rebal_band > 0：仅当安全腿权重偏离目标 ≥ band（漂移触发）才返回金额，否则 None
                    （交易次数远少于无条件再平衡，机械化最划算——实盘默认走这条）。
    rebal_band <= 0：无条件按目标拉回（始终返回带符号金额）。

    与 compute_ladder 同一设计：决策集中一处，回测/实盘共调 → 防御层 equivalence 的根。
    """
    tv = risky_value + safe_value
    if tv <= 0:
        return None
    cur_w = safe_value / tv
    if rebal_band > 0 and abs(cur_w - target_safe_weight) < rebal_band:
        return None
    target_safe = tv * target_safe_weight
    return target_safe - safe_value
