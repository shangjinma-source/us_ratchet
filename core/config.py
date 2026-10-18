"""配置加载与校验。

零硬编码：所有策略 / 数据参数来自 config.yaml。
每只标的仅声明 cap_total，weight / core_target / reserve_quota 在此推导。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from core.helpers import resolve, project_root

KNOWN_PROVIDERS = {"eastmoney", "sina", "local_cache", "yfinance", "stooq"}
HIGH_DEFS = {"since_inception", "ath", "rolling"}
HIGH_BASES = {"close", "high"}


class ConfigError(ValueError):
    pass


@dataclass
class ProxyConfig:
    enabled: bool = False
    url: str = "http://127.0.0.1:7890"
    bypass_for_data_hosts: bool = True


@dataclass
class ValidationConfig:
    split_continuity_jump_pct: float = 0.35
    max_provider_divergence_pct: float = 0.03


@dataclass
class DataConfig:
    fallback_chain: list[str]
    auto_adjust: bool
    start_date: str
    end_date: Optional[str]
    cache_dir: str
    proxy: ProxyConfig
    validation: ValidationConfig
    fqt: int = 1
    auto_split_adjust: bool = True
    split_detect_tol: float = 0.06


@dataclass
class RearmConfig:
    mode: str = "new_high"
    new_high_epsilon_pct: float = 0.005
    hysteresis_same_day_block: bool = True


@dataclass
class TierConfig:
    thresholds: list[float]
    deploy_ratios: list[float]


@dataclass
class PortfolioConfig:
    core_ratio: float
    injection_core_ratio: float
    inject_skip_core_near_high: bool
    high_definition: str
    high_basis: str
    rolling_window_days: int
    rearm: RearmConfig
    tiers: TierConfig
    manual_override_default: str
    injection_mode: str = "lump_core"            # lump_core / all_reserve / ladder_core
    injection_ladder_trigger_ratio: float = 0.50  # 0.65Δ 超过当前核心仓位此比例 → 自动分批
    injection_ladder_tranches: int = 4
    injection_ladder_spacing_days: int = 5


@dataclass
class Symbol:
    ticker: str
    cap_total: float
    weight: float = 0.0          # 推导
    core_target: float = 0.0     # 推导
    reserve_quota: float = 0.0   # 推导


@dataclass
class SafeLeg:
    """组合层防御腿（B 方向）：真实持有的超短债 ETF。配置缺省 → 防御层关闭。
    实盘据此维持 篮子:安全腿 = (1-target_weight):target_weight 的聚合比；
    回测安全腿走固定收益近似，决策同经 core.engine.compute_defensive_rebalance（同源）。"""
    ticker: str = "SGOV"
    target_weight: float = 0.26   # 安全资产目标权重 W
    exec_band: float = 0.15       # 执行带：安全腿权重偏离目标 ≥ 此值才再平衡（与回测 --rebal-band 同口径）


@dataclass
class TacticalOrderConfig:
    """每日战术挂单提示层。

    只用于前端/实盘提示，不参与深跌棘轮回测成交；目的是把“牛市回踩可买”和
    “熊市保留弹药”从 H 回撤档位里拆出来。
    """
    enabled: bool = True
    ma_short: int = 5
    ma_mid: int = 20
    ma_trend: int = 50
    ma_long: int = 200
    atr_window: int = 14
    bull_atr_mult: float = 0.6
    neutral_atr_mult: float = 1.0
    bear_atr_mult: float = 1.8
    bull_reserve_ratio: float = 0.20
    neutral_reserve_ratio: float = 0.12
    bear_reserve_ratio: float = 0.0
    min_discount_pct: float = 0.003
    market_gate_enabled: bool = True
    market_gate_tickers: tuple[str, ...] = ("QQQ", "SPY")


@dataclass
class ExecutionConfig:
    """Broker/execution constraints shared by live advice, buy plans, and research metadata."""
    venue: str = "汇丰银行"
    currency: str = "USD"
    lot_size: float = 1.0
    allow_fractional: bool = False
    cash_input_net_of_reserve: bool = True
    fee_bps: float = 0.0
    min_fee: float = 0.0
    buy_plan_compact_target: int = 4


@dataclass
class ResearchAdmissionConfig:
    """Fail-closed risk budget for research candidates; never drives live orders."""
    target_benchmark: str = "012922"
    min_rolling_windows: int = 12
    min_target_win_rate: float = 0.50
    min_target_excess_p50: float = 0.0
    max_target_dd_cost_p50: float = 0.03
    max_target_dd_cost_bad_tail: float = 0.05
    min_incumbent_xirr_margin_p50: float = -0.001
    min_incumbent_xirr_margin_p10: float = -0.02
    max_incumbent_dd_cost_p50: float = 0.005
    max_incumbent_dd_cost_p90: float = 0.02


@dataclass
class AppConfig:
    data: DataConfig
    portfolio: PortfolioConfig
    symbols: list[Symbol]
    safe_leg: Optional[SafeLeg] = None     # None = 不启用防御腿（向后兼容旧 config）
    tactical_orders: TacticalOrderConfig = field(default_factory=TacticalOrderConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    research_admission: ResearchAdmissionConfig = field(default_factory=ResearchAdmissionConfig)
    cache_dir: Path = field(default=None)  # 解析后的绝对路径


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _resolve_config_path(path: str | Path) -> Path:
    """在多个候选位置查找配置，兼容 config.yaml 放在 config/ 下或项目根/当前目录。"""
    p = Path(path)
    if p.is_absolute():
        return p
    root = project_root()
    cwd = Path.cwd()
    candidates = [
        root / p,                 # config/config.yaml（约定位置）
        root / p.name,            # 项目根下的 config.yaml
        cwd / p,                  # 相对当前工作目录
        cwd / p.name,             # 当前目录下的 config.yaml
    ]
    seen, ordered = set(), []
    for c in candidates:
        c = c.resolve()
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    for c in ordered:
        if c.exists():
            return c
    tried = "\n  ".join(str(c) for c in ordered)
    raise ConfigError(f"找不到配置文件 '{path}'，已尝试:\n  {tried}")


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    path = _resolve_config_path(path)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # ---- data ----
    d = raw.get("data", {})
    proxy = ProxyConfig(**{**ProxyConfig().__dict__, **(d.get("proxy") or {})})
    valid = ValidationConfig(**{**ValidationConfig().__dict__, **(d.get("validation") or {})})
    chain = d.get("fallback_chain") or []
    _require(chain, "data.fallback_chain 不能为空")
    unknown = set(chain) - KNOWN_PROVIDERS
    _require(not unknown, f"未知 provider: {unknown}；支持 {KNOWN_PROVIDERS}")
    data = DataConfig(
        fallback_chain=list(chain),
        auto_adjust=bool(d.get("auto_adjust", True)),
        start_date=str(d.get("start_date", "2015-01-01")),
        end_date=d.get("end_date"),
        cache_dir=str(d.get("cache_dir", "data/cache")),
        proxy=proxy,
        validation=valid,
        fqt=int(d.get("fqt", 1)),
        auto_split_adjust=bool(d.get("auto_split_adjust", True)),
        split_detect_tol=float(d.get("split_detect_tol", 0.06)),
    )

    # ---- portfolio ----
    p = raw.get("portfolio", {})
    core_ratio = float(p.get("core_ratio", 0.65))
    _require(0 < core_ratio <= 1, "core_ratio 必须在 (0, 1]")
    inj = float(p.get("injection_core_ratio", core_ratio))
    _require(0 <= inj <= 1, "injection_core_ratio 必须在 [0, 1]")

    hdef = str(p.get("high_definition", "since_inception"))
    _require(hdef in HIGH_DEFS, f"high_definition 须为 {HIGH_DEFS}")
    hbasis = str(p.get("high_basis", "close"))
    _require(hbasis in HIGH_BASES, f"high_basis 须为 {HIGH_BASES}")

    rearm = RearmConfig(**{**RearmConfig().__dict__, **(p.get("rearm") or {})})
    _require(rearm.mode in {"new_high", "recover_band", "time_decay"},
             "rearm.mode 须为 new_high / recover_band / time_decay")

    t = p.get("drawdown_tiers", {})
    thresholds = [float(x) for x in t.get("thresholds", [])]
    ratios = [float(x) for x in t.get("deploy_ratios", [])]
    _require(thresholds, "drawdown_tiers.thresholds 不能为空")
    _require(len(thresholds) == len(ratios),
             "thresholds 与 deploy_ratios 长度必须一致")
    _require(all(x < 0 for x in thresholds), "所有回撤档阈值必须为负")
    _require(all(thresholds[i] > thresholds[i + 1] for i in range(len(thresholds) - 1)),
             "回撤档阈值必须严格递减（如 -0.10, -0.20, ...）")
    _require(all(r >= 0 for r in ratios), "deploy_ratios 不能为负")
    _require(sum(ratios) <= 1.0 + 1e-9,
             f"deploy_ratios 之和({sum(ratios):.3f})不应超过 1（占该股储备配额比例）")

    inj_mode = str(p.get("injection_mode", "lump_core"))
    _require(inj_mode in {"lump_core", "all_reserve", "ladder_core"},
             "injection_mode 须为 lump_core / all_reserve / ladder_core")

    portfolio = PortfolioConfig(
        core_ratio=core_ratio,
        injection_core_ratio=inj,
        inject_skip_core_near_high=bool(p.get("inject_skip_core_near_high", False)),
        high_definition=hdef,
        high_basis=hbasis,
        rolling_window_days=int(p.get("rolling_window_days", 252)),
        rearm=rearm,
        tiers=TierConfig(thresholds=thresholds, deploy_ratios=ratios),
        manual_override_default=str((p.get("manual_override") or {}).get("default_action", "freeze")),
        injection_mode=inj_mode,
        injection_ladder_trigger_ratio=float(p.get("injection_ladder_trigger_ratio", 0.50)),
        injection_ladder_tranches=int(p.get("injection_ladder_tranches", 4)),
        injection_ladder_spacing_days=int(p.get("injection_ladder_spacing_days", 5)),
    )

    # ---- symbols + 推导 ----
    syms_raw = raw.get("symbols", [])
    _require(syms_raw, "symbols 不能为空")
    symbols = [Symbol(ticker=str(s["ticker"]).upper(), cap_total=float(s["cap_total"]))
               for s in syms_raw]
    tickers = [s.ticker for s in symbols]
    _require(len(tickers) == len(set(tickers)), f"标的重复: {tickers}")
    _require(all(s.cap_total > 0 for s in symbols), "每只 cap_total 必须 > 0")
    total_cap = sum(s.cap_total for s in symbols)
    for s in symbols:
        s.weight = s.cap_total / total_cap
        s.core_target = s.cap_total * core_ratio
        s.reserve_quota = s.cap_total * (1 - core_ratio)

    # ---- safe_leg（防御腿，可选）----
    sl_raw = raw.get("safe_leg")
    safe_leg = None
    if sl_raw:
        sl_ticker = str(sl_raw.get("ticker", "SGOV")).upper()
        sl_w = float(sl_raw.get("target_weight", 0.26))
        sl_band = float(sl_raw.get("exec_band", 0.15))
        _require(bool(sl_ticker), "safe_leg.ticker 不能为空")
        _require(0 < sl_w < 1, "safe_leg.target_weight 必须在 (0, 1)")
        _require(sl_band >= 0, "safe_leg.exec_band 不能为负")
        safe_leg = SafeLeg(ticker=sl_ticker, target_weight=sl_w, exec_band=sl_band)

    # ---- tactical_orders（每日战术挂单提示层，可选）----
    tact_raw = raw.get("tactical_orders") or {}
    tactical_orders = TacticalOrderConfig(
        **{**TacticalOrderConfig().__dict__, **tact_raw}
    )
    _require(tactical_orders.ma_short > 0 and tactical_orders.ma_mid > 0
             and tactical_orders.ma_trend > 0 and tactical_orders.ma_long > 0,
             "tactical_orders 均线窗口必须 > 0")
    _require(tactical_orders.atr_window > 0, "tactical_orders.atr_window 必须 > 0")
    _require(0 <= tactical_orders.bull_reserve_ratio <= 1
             and 0 <= tactical_orders.neutral_reserve_ratio <= 1
             and 0 <= tactical_orders.bear_reserve_ratio <= 1,
             "tactical_orders reserve_ratio 必须在 [0,1]")
    _require(tactical_orders.bull_atr_mult >= 0
             and tactical_orders.neutral_atr_mult >= 0
             and tactical_orders.bear_atr_mult >= 0,
             "tactical_orders atr_mult 不能为负")
    _require(0 <= tactical_orders.min_discount_pct < 0.10,
             "tactical_orders.min_discount_pct 必须在 [0,0.10)")
    gate_tickers = tactical_orders.market_gate_tickers
    if isinstance(gate_tickers, str):
        gate_tickers = [x for x in gate_tickers.replace(",", " ").split() if x]
    tactical_orders.market_gate_tickers = tuple(str(x).upper().strip() for x in gate_tickers if str(x).strip())
    _require(bool(tactical_orders.market_gate_tickers),
             "tactical_orders.market_gate_tickers 不能为空")

    # ---- execution（券商/整股执行约束）----
    exec_raw = raw.get("execution") or {}
    execution = ExecutionConfig(**{**ExecutionConfig().__dict__, **exec_raw})
    execution.venue = str(execution.venue or "汇丰银行")
    execution.currency = str(execution.currency or "USD").upper()
    execution.lot_size = float(execution.lot_size)
    execution.fee_bps = float(execution.fee_bps)
    execution.min_fee = float(execution.min_fee)
    execution.buy_plan_compact_target = int(execution.buy_plan_compact_target)
    _require(execution.lot_size > 0, "execution.lot_size 必须 > 0")
    _require(execution.fee_bps >= 0, "execution.fee_bps 不能为负")
    _require(execution.min_fee >= 0, "execution.min_fee 不能为负")
    _require(execution.buy_plan_compact_target > 0,
             "execution.buy_plan_compact_target 必须 > 0")

    # ---- research_admission（只读研究准入，不进入执行层）----
    admission_raw = raw.get("research_admission") or {}
    research_admission = ResearchAdmissionConfig(
        **{**ResearchAdmissionConfig().__dict__, **admission_raw}
    )
    research_admission.target_benchmark = str(
        research_admission.target_benchmark or "012922"
    ).upper().strip()
    research_admission.min_rolling_windows = int(research_admission.min_rolling_windows)
    for field_name in (
        "min_target_win_rate",
        "min_target_excess_p50",
        "max_target_dd_cost_p50",
        "max_target_dd_cost_bad_tail",
        "min_incumbent_xirr_margin_p50",
        "min_incumbent_xirr_margin_p10",
        "max_incumbent_dd_cost_p50",
        "max_incumbent_dd_cost_p90",
    ):
        setattr(research_admission, field_name, float(getattr(research_admission, field_name)))
    _require(bool(research_admission.target_benchmark),
             "research_admission.target_benchmark 不能为空")
    _require(research_admission.min_rolling_windows >= 6,
             "research_admission.min_rolling_windows 必须 >= 6")
    _require(0 <= research_admission.min_target_win_rate <= 1,
             "research_admission.min_target_win_rate 必须在 [0, 1]")
    _require(research_admission.max_target_dd_cost_p50 >= 0,
             "research_admission.max_target_dd_cost_p50 不能为负")
    _require(research_admission.max_target_dd_cost_bad_tail >= 0,
             "research_admission.max_target_dd_cost_bad_tail 不能为负")
    _require(research_admission.max_incumbent_dd_cost_p50 >= 0,
             "research_admission.max_incumbent_dd_cost_p50 不能为负")
    _require(research_admission.max_incumbent_dd_cost_p90 >= 0,
             "research_admission.max_incumbent_dd_cost_p90 不能为负")

    cfg = AppConfig(data=data, portfolio=portfolio, symbols=symbols,
                    safe_leg=safe_leg, tactical_orders=tactical_orders,
                    execution=execution, research_admission=research_admission)
    cfg.cache_dir = resolve(data.cache_dir)
    return cfg
