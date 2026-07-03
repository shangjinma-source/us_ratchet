"""组合 / 标的状态。回测与实盘共用同一套 state，确保信号同源。

可序列化（to_dict / from_dict），第 6 步落盘持久化与手动 patch 直接用。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class TierFire:
    """一次档位触发记录，用于贡献拆解。"""
    date: str
    tier_index: int
    threshold: float
    limit_price: float
    fill_price: float
    amount: float
    shares: float


@dataclass
class TacticalFill:
    """一次战术固定限价成交记录，独立于深跌棘轮档位。"""
    date: str
    limit_price: float
    fill_price: float
    amount: float
    shares: float
    basis_price: float = 0.0
    live_price: float = 0.0
    regime: str = ""
    reason: str = ""
    note: str = ""


@dataclass
class SymbolState:
    ticker: str
    cap_total: float
    shares: float = 0.0
    reserve_cash: float = 0.0           # 实际干火药
    reserve_budget: float = 0.0         # 当前周期档位定额基准（re-arm 快照 + 注资累加）
    H: float = 0.0                      # 自建仓以来最高（按 high_basis）
    tier_armed: list = field(default_factory=list)   # 每档是否已装填
    cost_basis: float = 0.0             # 累计买入金额（成本基础）
    cum_injected: float = 0.0           # 累计注入本金（含初始）
    entry_date: str = ""                # 人工校准的聚合买入日期（用于重算 H / 展示）
    entry_price: float = 0.0            # 人工校准的聚合买入均价
    pending_ladder: list = field(default_factory=list)  # [(due_index, amount), ...]
    pending_core_cash: float = 0.0      # 已注入、已排分批但尚未成交的核心现金
    frozen: bool = False                # 人工剔除冻结：停止一切加仓
    fires: list = field(default_factory=list)           # list[TierFire]
    tactical_fills: list = field(default_factory=list)   # list[TacticalFill]

    def market_value(self, price: float) -> float:
        return self.shares * price

    def total_value(self, price: float) -> float:
        return self.shares * price + self.reserve_cash + self.pending_core_cash

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SymbolState":
        fires = [TierFire(**f) for f in d.get("fires", [])]
        tactical_fills = [TacticalFill(**f) for f in d.get("tactical_fills", [])]
        pending = [tuple(x) for x in d.get("pending_ladder", [])]
        pending_core_cash = d.get("pending_core_cash")
        if pending_core_cash is None:
            pending_core_cash = sum(float(x[1]) for x in pending)
        d = {**d, "fires": fires,
             "tactical_fills": tactical_fills,
             "pending_ladder": pending,
             "pending_core_cash": float(pending_core_cash or 0.0)}
        return cls(**d)


@dataclass
class CashFlow:
    """一笔现金流：date 为 ISO 字符串，amount 为正（注入本金）。"""
    date: str
    amount: float
    note: str = ""


@dataclass
class Portfolio:
    symbols: dict          # ticker -> SymbolState
    flows: list            # list[CashFlow]，累计注资账（含初始建仓）
    day_index: int = 0     # 实盘交易日序号：每个新运行日 +1（见 live.advance_trading_day），
                           # 注资分批的 due 与到期判定以此为基准。回测不用此字段（用循环下标 i）。
    last_run_date: str = ""  # 上次推进 day_index 的日期(ISO)，用于同日重复运行幂等
    # --- 组合层防御腿（B 方向）。target_safe_weight=0 → 防御层关闭（旧 state 反序列化即此默认，零回归）---
    safe_ticker: str = "SGOV"        # 安全腿标的（超短债 ETF）
    safe_shares: float = 0.0         # 安全腿持有股数（实盘真实持有，引擎读其市值=股数×最新收盘）
    target_safe_weight: float = 0.0  # 安全资产目标权重 W（建仓时由 cfg.safe_leg 播种）

    def total_value(self, prices: dict) -> float:
        return sum(s.total_value(prices[t]) for t, s in self.symbols.items())

    def total_invested(self, prices: dict) -> float:
        return sum(s.market_value(prices[t]) for t, s in self.symbols.items())

    def total_reserve(self) -> float:
        return sum(s.reserve_cash for s in self.symbols.values())

    def total_pending_core_cash(self) -> float:
        return sum(s.pending_core_cash for s in self.symbols.values())

    def total_contributed(self) -> float:
        return sum(f.amount for f in self.flows)
