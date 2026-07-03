"""实盘信号生成（与回测同源：复用 core.engine 的同一套函数）。

  - init_portfolio     : 首次建仓（各标的 core_ratio 立即买、其余进储备、H 起点）
  - advance_trading_day: 每个新的运行日把交易日序号 +1（同日重复运行幂等）；注资分批的
                         到期判定依赖它，使实盘分批与回测一样按交易日逐批兑现。
  - apply_cap_change   : 抬高某只 cap = 一次注资（立即核心买 + 储备 + 按交易日排分批）
  - generate_signals   : 每日收盘后调用——到期分批核心买入 + 棘轮上调 H + re-arm，
                         输出每标的的限价挂单阶梯
  - compute_defensive  : 每日收盘后（在 generate_signals 之后）调用一次的组合层防御纪律，
                         维持 篮子:安全腿 = (1-W):W 的聚合比，输出篮子各标的买卖 + 安全腿反向单。
                         决策经 core.engine.compute_defensive_rebalance，与回测同源。

阶梯由 core.engine.compute_ladder 产出，与回测成交判定用的是同一函数同一公式
（limit = H × (1 + 档位阈值)），这是 equivalence 的根。
"""
from __future__ import annotations

from dataclasses import dataclass

from core import engine as eng
from core.state import CashFlow, Portfolio, SymbolState


@dataclass
class SymbolSignal:
    ticker: str
    last_close: float
    H: float
    drawdown: float
    reserve_cash: float
    shares: float
    market_value: float
    frozen: bool
    immediate_buys: list   # [(金额, 价, 说明)]
    ladder: list           # core.engine.LadderEntry


@dataclass
class DefensiveOrder:
    """防御层对单个标的的一笔市价指令（实盘照此挂市价/限价即成交单）。"""
    ticker: str
    side: str              # "SELL" / "BUY"
    amount: float          # 美元金额
    shares: float          # 股数（amount / 当日收盘）
    from_reserve: float = 0.0   # 仅 trim：因股票市值不足、从该标的 reserve_cash 抽走的金额
    from_pending_core_cash: float = 0.0  # 仅 trim：必要时取消的待分批核心现金


@dataclass
class DefensiveSignal:
    """组合层防御纪律的当日动作（trim=减仓篮子增厚安全腿 / rebuy=回补篮子减薄安全腿）。
    决策来自 core.engine.compute_defensive_rebalance（与回测同源）。棘轮 H/tier_armed 不受影响。"""
    direction: str         # "trim" / "rebuy"
    move: float            # 带符号金额：>0 风险腿→安全腿；<0 安全腿→风险腿
    basket_value: float    # 触发前篮子整 sleeve 市值 Σ(shares×price)+Σreserve
    safe_value: float      # 触发前安全腿市值 = safe_shares × safe_price
    safe_weight: float     # 触发前安全腿权重 safe_value/(basket+safe)
    target_weight: float   # 目标安全权重 W
    orders: list           # list[DefensiveOrder]，篮子各标的买/卖
    safe_order: DefensiveOrder   # 安全腿(SGOV)反向单


@dataclass
class ScaleUpResult:
    """按目标比 (1-W):W 提高总持仓的结果。"""
    total: float                 # 本次新增总持仓
    basket_portion: float        # (1-W)×total，分摊注资进 8 名篮子
    safe_portion: float          # W×total，加到安全腿
    orders: list                 # [(ticker, delta_cap), ...] 各名注资额
    safe_added_shares: float     # 安全腿新增股数
    safe_ticker: str             # 安全腿标的


def init_portfolio(cfg, prices: dict, safe_price: float | None = None) -> Portfolio:
    """prices: ticker -> 建仓参考价（最新收盘）。
    safe_price 提供且 cfg.safe_leg 存在时，按目标比 W/(1-W) 播种安全腿，使建仓日
    篮子:安全腿 = (1-W):W 即落在目标上（避免首日触发再平衡空转）。"""
    pf = Portfolio(symbols={}, flows=[])
    for s in cfg.symbols:
        st = eng.init_symbol(s.ticker, s.cap_total, prices[s.ticker], cfg)
        pf.symbols[s.ticker] = st
        pf.flows.append(CashFlow(date="init", amount=s.cap_total, note="初始建仓"))
    sl = getattr(cfg, "safe_leg", None)
    if sl is not None and safe_price and safe_price > 0:
        pf.safe_ticker = sl.ticker
        pf.target_safe_weight = sl.target_weight
        # 建仓时篮子整 sleeve 市值 = Σ(核心买入市值 + reserve) = Σcap_total
        basket_value = sum(st.total_value(prices[t]) for t, st in pf.symbols.items())
        safe_target = basket_value * sl.target_weight / (1.0 - sl.target_weight)
        pf.safe_shares = safe_target / safe_price
    return pf


def advance_trading_day(pf: Portfolio, today: str) -> int:
    """把交易日序号推进到“今天”。同一日期重复调用幂等（不重复推进），保证一天只 +1。
    注资分批的 due 与到期判定都以该序号为基准。today: ISO 日期串（如 '2025-06-13'）。
    返回推进后的 day_index。注：按“运行日”近似“交易日”，周末/跳过运行会略有偏差，
    对注资分批的平滑入场无实质影响。"""
    if pf.last_run_date != today:
        pf.day_index += 1
        pf.last_run_date = today
    return pf.day_index


def apply_cap_change(pf: Portfolio, ticker: str, new_cap: float,
                     price: float, cfg) -> float:
    """把某只 cap 调到 new_cap；增量 = 一次注资。返回注资额（≤0=未变/降低不处理）。
    分批以当前 pf.day_index 为起点排 due（与回测同义），后续运行日逐批到期兑现。
    调用前应先 advance_trading_day(pf, today)。"""
    st = pf.symbols[ticker]
    delta = new_cap - st.cap_total
    if delta <= 0:
        st.cap_total = new_cap
        return 0.0
    eng.apply_injection(st, delta, price, pf.day_index, cfg)
    pf.flows.append(CashFlow(date=pf.last_run_date or "init",
                             amount=delta, note=f"注资 {ticker}"))
    return delta


def generate_signals(pf: Portfolio, latest_close: dict, cfg,
                     update_highs: bool = True) -> list[SymbolSignal]:
    """每日收盘后：到期分批核心买入（按 pf.day_index）+ 棘轮上调 H + re-arm，给出当日阶梯。
    注意：不自动记录档位成交（实盘成交需用户回填）。盘中 quote 预览可传
    update_highs=False，只用实时价估值/判断触发，不用盘中价刷新 H 或 re-arm；
    真正落盘仍应在收盘后按日线 close 更新。
    调用前应先 advance_trading_day(pf, today) 推进当日序号。"""
    out = []
    for s in cfg.symbols:
        st = pf.symbols[s.ticker]
        c = latest_close[s.ticker]
        # 到期分批核心买入（cap 调高后的分批注资，按真实交易日逐批兑现）
        imm = []
        bought = eng.process_pending(st, c, pf.day_index)
        if bought > 0:
            imm.append((bought, c, "分批核心买入(到期)"))
        # 棘轮上调 H + 创新高 re-arm（影响次日阶梯）
        if update_highs:
            eng.update_high(st, c, cfg)
        ladder = eng.compute_ladder(st, cfg)
        out.append(SymbolSignal(
            ticker=s.ticker, last_close=c, H=st.H, drawdown=c / st.H - 1,
            reserve_cash=st.reserve_cash, shares=st.shares,
            market_value=st.shares * c, frozen=st.frozen,
            immediate_buys=imm, ladder=ladder,
        ))
    return out


def compute_defensive(pf: Portfolio, latest_close: dict, safe_price: float,
                      cfg, apply: bool = True) -> DefensiveSignal | None:
    """组合层防御纪律（B 方向）——独立于棘轮核心、每日收盘后调一次（在 generate_signals 之后）。

    口径与回测严格同源：
      risky_value = 篮子整 sleeve = Σ(shares×price) + Σreserve_cash + Σpending_core_cash
                    （含 reserve 与待分批核心现金，与回测 risky_nav 同口径）
      safe_value  = pf.safe_shares × safe_price（实盘真实 SGOV 市值）
      决策只经 core.engine.compute_defensive_rebalance(risky, safe, W, exec_band)：
        move>0 → trim：按各标的 total_value(股+reserve) 等比例卖（保持组内漂移=买入持有），
                 单名分摊额超其股票市值时差额先从 reserve_cash 抽，必要时取消待分批核心现金；
                 安全腿等额买入。
        move<0 → rebuy：按各标的 total_value 等比例【买股】回补（不走棘轮阶梯）；安全腿等额卖出。
    apply=True（默认，CLI 用）：把上述动作落到 state（仅改 shares/reserve/safe_shares 量；棘轮 H/tier_armed 不碰）。
    apply=False（预览，dashboard 被动 GET 用）：只算出指令、不改 state，供前端常驻显示，执行由显式动作触发。
    cfg.safe_leg 缺省或 target_safe_weight≤0 或安全腿价≤0 → 返回 None（防御层关闭）。"""
    sl = getattr(cfg, "safe_leg", None)
    if sl is None or pf.target_safe_weight <= 0 or not safe_price or safe_price <= 0:
        return None

    per_total: dict[str, float] = {}
    basket_value = 0.0
    for s in cfg.symbols:
        st = pf.symbols[s.ticker]
        c = latest_close[s.ticker]
        tv = st.total_value(c)
        per_total[s.ticker] = tv
        basket_value += tv

    safe_value = pf.safe_shares * safe_price
    move = eng.compute_defensive_rebalance(
        basket_value, safe_value, pf.target_safe_weight, sl.exec_band)
    if move is None or abs(move) < 1e-9 or basket_value <= 0:
        return None

    total = basket_value + safe_value
    safe_w = safe_value / total if total > 0 else 0.0
    orders: list[DefensiveOrder] = []

    if move > 0:
        # trim：减仓篮子 → 增厚安全腿
        for s in cfg.symbols:
            st = pf.symbols[s.ticker]
            c = latest_close[s.ticker]
            alloc = move * (per_total[s.ticker] / basket_value)
            mv = st.shares * c
            from_shares = min(alloc, mv)
            sh = from_shares / c if c > 0 else 0.0
            cash_need = alloc - from_shares
            from_res = min(cash_need, st.reserve_cash)
            from_pending = min(max(0.0, cash_need - from_res),
                               max(0.0, st.pending_core_cash))
            if apply:
                st.shares -= sh
                if from_res > 1e-12:
                    st.reserve_cash -= from_res
                if from_pending > 1e-12:
                    eng.consume_pending_core_cash(st, from_pending)
            orders.append(DefensiveOrder(ticker=s.ticker, side="SELL", amount=alloc,
                                         shares=sh, from_reserve=from_res,
                                         from_pending_core_cash=from_pending))
        if apply:
            pf.safe_shares += move / safe_price
        safe_order = DefensiveOrder(ticker=pf.safe_ticker, side="BUY",
                                    amount=move, shares=move / safe_price)
        direction = "trim"
    else:
        # rebuy：回补篮子 ← 减薄安全腿（直接买股，不走棘轮补跌阶梯）
        need = -move
        for s in cfg.symbols:
            st = pf.symbols[s.ticker]
            c = latest_close[s.ticker]
            buy = need * (per_total[s.ticker] / basket_value)
            sh = buy / c if c > 0 else 0.0
            if apply:
                st.shares += sh
                st.cost_basis += buy
            orders.append(DefensiveOrder(ticker=s.ticker, side="BUY", amount=buy,
                                         shares=sh, from_reserve=0.0))
        if apply:
            pf.safe_shares -= need / safe_price
        safe_order = DefensiveOrder(ticker=pf.safe_ticker, side="SELL",
                                    amount=need, shares=need / safe_price)
        direction = "rebuy"

    return DefensiveSignal(direction=direction, move=move, basket_value=basket_value,
                           safe_value=safe_value, safe_weight=safe_w,
                           target_weight=pf.target_safe_weight,
                           orders=orders, safe_order=safe_order)


def scale_up_portfolio(pf: Portfolio, total_amount: float, prices: dict,
                       safe_price: float, cfg) -> ScaleUpResult | None:
    """按目标比 (1-W):W 提高总持仓 total_amount（W=pf.target_safe_weight）。
      (1-W)×total：按各名当前 cap_total 比例分摊，对每名做【立即 lump 注资】
                   （核心立即买 + 余进储备，不分批）→ 篮子内逆波动率权重保持不变。
      W×total    ：加到安全腿 SGOV（safe_shares += W×total / safe_price）。
    用 lump 而非分批是刻意的：核心与 SGOV 同步到账，加仓后篮子:安全腿目标比【精确不变】，
    不会因分批延迟到账把比例推歪、触发防御层来回再平衡。
    调用前应先 advance_trading_day。total_amount≤0 或无篮子 → 返回 None。
    注：累计投入(flows)只记篮子侧（与建仓播种 SGOV 不计 flows 的口径一致）。"""
    if total_amount <= 0:
        return None
    cap_sum = sum(st.cap_total for st in pf.symbols.values())
    if cap_sum <= 0:
        return None
    W = pf.target_safe_weight if pf.target_safe_weight > 0 else 0.0
    p = cfg.portfolio
    basket_portion = total_amount * (1.0 - W)
    safe_portion = total_amount * W
    orders: list = []
    for s in cfg.symbols:
        st = pf.symbols[s.ticker]
        if st.frozen:
            continue   # 冻结的标的不加仓
        delta = basket_portion * (st.cap_total / cap_sum)
        if delta <= 0:
            continue
        price = prices[s.ticker]
        # 立即 lump 注资：核心立即买入 + 余额进储备（不走分批，保持 74:26 精确）
        st.cap_total += delta
        st.cum_injected += delta
        core = delta * p.injection_core_ratio
        reserve = delta - core
        st.reserve_cash += reserve
        st.reserve_budget += reserve              # 放大该名后续每档补跌金额
        if core > 0 and price > 0:
            st.shares += core / price
            st.cost_basis += core
        pf.flows.append(CashFlow(date=pf.last_run_date or "init",
                                 amount=delta, note=f"加仓 {s.ticker}"))
        orders.append((s.ticker, delta))
    added_shares = 0.0
    if W > 0 and safe_price and safe_price > 0 and safe_portion > 0:
        added_shares = safe_portion / safe_price
        pf.safe_shares += added_shares
    return ScaleUpResult(total=total_amount, basket_portion=basket_portion,
                         safe_portion=safe_portion, orders=orders,
                         safe_added_shares=added_shares, safe_ticker=pf.safe_ticker)
