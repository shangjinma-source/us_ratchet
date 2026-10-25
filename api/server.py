"""FastAPI 后端：单页前端 + 回测曲线 + 实盘状态/阶梯 + 加本金/建仓/回填。

运行（PyCharm 终端）:
    python -m api.server
    # 然后浏览器打开 http://127.0.0.1:8010
数据抓取与回测复用 core/backtest 逻辑；价格在内存缓存，避免每次请求都打数据源。
"""
from __future__ import annotations

import csv
import copy
import hashlib
import io
import json
import logging
import re
import time
from threading import Lock
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Body
from fastapi.responses import FileResponse, JSONResponse

from core.config import load_config, Symbol
from core.helpers import atomic_write_text, setup_logging, resolve
from core import engine as eng
from core import live
from core.admission import AdmissionProfile, apply_admissions
from core.persist import (
    ADVICE_SNAPSHOT_PATH,
    advice_snapshot_log,
    advice_snapshot_storage,
    audit_log,
    backup_state,
    iter_advice_snapshots,
    load_advice_snapshots,
    load_portfolio,
    save_portfolio,
)
from core.state import CashFlow, Portfolio, SymbolState, TierFire, TacticalFill
from core.state_readiness import state_clock_readiness
from core.broker_account import (
    BROKER_ACCOUNT_PATH,
    backup_broker_account,
    load_broker_account,
    save_broker_account,
    broker_account_fingerprint,
    update_broker_position,
    BrokerAccountError,
)
from backtest.engine import (
    run_nav_panel,
    run_rolling_start_panel,
    run_trend_gate_ab,
    run_crash_sleeve_ab,
    run_param_scan_ab,
    run_injection_mode_ab,
    run_tactical_overlay_ab,
    _align_prices,
)
from backtest.fund_mirror import run_fund_mirror_research, run_fund_quarterly_mirror_research
from backtest.fund_style import run_fund_style_attribution
from backtest.universe import cached_universe, run_universe_research
from backtest.preference import run_preference_portfolio_research
from backtest.preference_walkforward import (
    run_preference_rebalance_research,
    run_preference_walkforward_research,
)
from backtest.live_gate import run_preference_live_gate
from backtest.ndx_competition import run_ndx_competition_research
from backtest.ndx_incumbent_frontier import (
    NdxIncumbentFrontierError,
    read_verified_incumbent_curve_bundle,
)
from backtest.ndx_style_crowding import (
    NdxStyleCrowdingError,
    read_verified_style_crowding_bundle,
)
from backtest.ndx_cash_history_dashboard import read_cash_history_evidence
from backtest.ndx_modern_new_cash_inputs_dashboard_view import (
    load_modern_new_cash_inputs_view, FLAGS as MODERN_NEW_CASH_INPUT_FLAGS,
)
from backtest.ndx_marginal_dashboard import (
    NdxMarginalDashboardError,
    read_verified_marginal_dashboard,
)
from backtest.parallel_deployment import build_parallel_deployment_plan
from backtest.state_catchup import (
    StateCatchupError,
    build_exact_session_close_panel,
    replay_session_catchup,
)
from backtest.candidate_registry import build_candidate_registry, build_static_candidate_registry
from data.candidate_pool import CandidatePoolError, build_current_candidate_registry
from data.fetch import get_bars
from data.quotes import fetch_sina_quotes
from data.current_portfolio_preview import (
    PreviewSourceError, read_current_portfolio_preview, read_current_portfolio_bars,
)
from data.current_cash_portfolio_research import (
    ResearchExpiredError, ProjectionBudgetExceededError,
)
from api.current_quantity_research_v2 import create_router as create_quantity_research_router
from data.current_quantity_v2_service_factory import create_service as create_quantity_research_service
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY, LazyPullbackCapStore
from api.current_quantity_v2_intraday import create_router as create_quantity_intraday_router
from data.current_quantity_v2_intraday_factory import create_reference_service
from data.current_quantity_v2_current_cash_factory import create_services as create_current_cash_services
from data.current_quantity_v2_bounded_unit_review import BoundedPublicUnitReview
from os import environ as server_environment
from data.current_quantity_v2_monthly_composition import create_services as create_quantity_monthly_services
from api.current_quantity_v2_monthly_research import create_router as create_quantity_monthly_research_router
from api.current_quantity_v2_difference import create_router as create_quantity_difference_router
from api.current_quantity_v2_paper import create_router as create_quantity_paper_router
from data.current_strategy_validation import (
    StrategyValidationSourceError, read_current_strategy_validation,
)
from datetime import date, datetime, timedelta, timezone

setup_logging(logging.WARNING)
app = FastAPI(title="us_ratchet")
from api.strategy_error_boundary_v1 import StrategyErrorBoundary
app.add_middleware(StrategyErrorBoundary)
from api.verified_daily_comparison import router as verified_daily_comparison_router
app.include_router(verified_daily_comparison_router)
from api.strategy_server_mount_v6 import mount_strategy_routes
_strategy_runtime_root = Path(__file__).resolve().parents[1]
from api.strategy_followup_summary_v1 import create_router as create_followup_summary_router
app.include_router(create_followup_summary_router(_strategy_runtime_root))
mount_strategy_routes(app=app, root=_strategy_runtime_root, environment=server_environment)
from api.optional_quantity_research_mount import (
    legacy_quantity_research_configured, unconfigured_quantity_research_router,
)
if legacy_quantity_research_configured(root=_strategy_runtime_root, environment=server_environment):
    # Server-owned research configuration; HTTP clients supply only entered_cash.
    _current_quantity_research = create_quantity_research_service(
        root=Path(__file__).resolve().parents[1],
        descriptor_path="tmp/tri98_runtime_execution_admission_20261016_v10/descriptor.json",
        descriptor_sha256="aef2c3680d0b2652cf9d141d829a5760193c21581cb948fee0f8e471543e6fce",
    )
    _current_quantity_research = VerifiedSnapshotBundleService(_current_quantity_research, source_withdrawals=SOURCE_WITHDRAWALS)
    app.include_router(create_quantity_research_router(service=_current_quantity_research))
    _current_quantity_intraday = create_reference_service(
        root=Path(__file__).resolve().parents[1], snapshot_service=_current_quantity_research,
    )
    app.include_router(create_quantity_intraday_router(service=_current_quantity_intraday))
    # One server-owned paper pool. Construction does not fetch quotes or create a DB.
    _current_quantity_pullback_caps = LazyPullbackCapStore(
        Path(__file__).resolve().parents[1] / 'data' / 'quantity_v2_pullback' / 'entry_caps.sqlite3',
        clock=lambda: datetime.now(timezone.utc).isoformat(),
        max_history_rows=512, max_history_bytes=128 * 1024 * 1024,
    )
    _current_quantity_cash = create_current_cash_services(
        root=Path(__file__).resolve().parents[1], snapshot_service=_current_quantity_research,
        identity_manifest_path="tmp/tri98_runtime_execution_admission_20261016_v10/identity_manifest.json",
        server_account_id="current-quantity-v2-paper-pool",
        database_path=Path(__file__).resolve().parents[1] / "data" / "quantity_v2_paper" / "paper.sqlite3",
        observation_directory=Path(__file__).resolve().parents[1] / "data" / "quantity_v2_observations",
        pullback_policy=EXPERIMENTAL_POLICY,
        pullback_cap_store=_current_quantity_pullback_caps,
        unit_review_reader=BoundedPublicUnitReview(),
        execution_month_mandate={
            "path": "tmp/tri98_runtime_execution_admission_20261016_v10/initial_execution_month.json",
            "sha256": "e319d0b8e2035fc58ed9c71cef041cb20fb2ce6b5bdea5a5702fd6c80163689c",
        },
    )
    # Monthly inputs are explicit server configuration, never inferred from October data.
    _current_quantity_monthly = create_quantity_monthly_services(
        root=Path(__file__).resolve().parents[1], paper_service=_current_quantity_cash['paper'],
        storage_root=Path(__file__).resolve().parents[1] / 'data' / 'quantity_v2_monthly',
        config_path=server_environment.get('QUANTITY_V2_MONTHLY_CONFIG_PATH'),
        config_sha256=server_environment.get('QUANTITY_V2_MONTHLY_CONFIG_SHA256'),
        execution_review_mode=server_environment.get('QUANTITY_V2_EXECUTION_REVIEW_MODE','DERIVED_PAPER_BOUNDED'),
        pullback_policy=EXPERIMENTAL_POLICY,
        pullback_cap_store=_current_quantity_pullback_caps,
    )
    _current_quantity_cash['paper'] = _current_quantity_monthly['paper']
    app.include_router(create_quantity_monthly_research_router(service=_current_quantity_monthly['research']))
    app.include_router(create_quantity_difference_router(service=_current_quantity_cash['preview']))
    app.include_router(create_quantity_paper_router(service=_current_quantity_cash['paper']))
    from api.current_quantity_v2_simulation_status import create_router as create_automatic_simulation_router
    app.include_router(create_automatic_simulation_router(
        database_path=Path(__file__).resolve().parents[1] / 'data' / 'quantity_v2_isolated_trial_20261016' / 'simulation.sqlite3',
        simulation_id='tri98-pullback-conditional-trial-20261016',initial_cash='20000'))
else:
    app.include_router(unconfigured_quantity_research_router())
from api.current_research_paper import router as current_research_paper_router
app.include_router(current_research_paper_router)
from api.current_research_intraday_paper import router as current_research_intraday_paper_router
app.include_router(current_research_intraday_paper_router)
CFG = load_config()
STATE_PATH = "data/state.json"
_broker_write_lock = Lock()
WEB = Path(__file__).resolve().parents[1] / "web" / "index.html"

_px_cache: dict = {}          # {"dates":..., "px":...}
_bt_cache: dict = {}          # {monthly: result_dict}
_roll_cache: dict = {}        # {(monthly, min_years, state_mtime): result_dict}
_trend_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_crash_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_param_cache: dict = {}       # {(monthly, state_mtime): result_dict}
_inject_mode_cache: dict = {} # {(monthly, state_mtime): result_dict}
_tactical_cache: dict = {}    # {(monthly, state_mtime): result_dict}
_research_candidate_cache: dict = {}  # {(monthly, include_heavy, state_mtime, ...): result_dict}
_ndx_competition_cache: dict = {}
_ndx_style_crowding_cache: dict = {}
_ndx_marginal_dashboard_cache: dict = {}
_safe_cache: dict = {}        # {"price": SGOV 最新收盘}
_bars_cache: dict = {}        # ticker -> OHLCV DataFrame
_quote_cache: dict = {}       # {key: (ts, quotes)}
QUOTE_TTL_SEC = 12
BACKTEST_BASELINES = {"012922", "QQQ", "SPY"}


def _clean_backtest_date(value: str | None, field: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"{field} must be YYYY-MM-DD") from e
    return value


def _clean_backtest_baseline(value: str | None) -> str:
    baseline = (value or "012922").strip().upper()
    return baseline if baseline in BACKTEST_BASELINES else "012922"

ADMISSION_PROFILES = {
    "trend_reduction": AdmissionProfile(
        name="trend_reduction",
        benchmark="长期持有",
        x_field="xirr_vs_hold",
        dd_field="dd_relief_vs_hold",
        market_mode="downshift",
        live_block="涉及主动降低风险仓位；当前纪律不允许市场层主动卖出或减仓。",
    ),
    "trend_execution": AdmissionProfile(
        name="trend_execution",
        benchmark="纯棘轮",
        x_field="xirr_vs_risk",
        dd_field="dd_relief_vs_risk",
        rolling_x_field="xirr_vs_hold",
        rolling_dd_field="dd_relief_vs_hold",
        market_mode="downshift",
    ),
    "crash_sleeve": AdmissionProfile(
        name="crash_sleeve",
        benchmark="纯棘轮",
        x_field="xirr_vs_risk",
        dd_field="dd_relief_vs_risk",
        market_mode="crash",
        live_block="缺少独立 crash cash 实盘账户和成交回填，不能直接进入今日建议。",
    ),
    "param_scan": AdmissionProfile(
        name="param_scan",
        benchmark="当前参数",
        x_field="xirr_vs_current",
        dd_field="dd_relief_vs_current",
        market_mode="structural",
    ),
    "injection_mode": AdmissionProfile(
        name="injection_mode",
        benchmark="当前注资模式",
        x_field="xirr_vs_current",
        dd_field="dd_relief_vs_current",
        market_mode="structural",
    ),
    "tactical_overlay": AdmissionProfile(
        name="tactical_overlay",
        benchmark="关闭战术单",
        x_field="xirr_vs_baseline",
        dd_field="dd_relief_vs_baseline",
        min_dd=-0.001,
        market_mode="tactical",
    ),
}


def _state_mtime_ns() -> int:
    p = resolve(STATE_PATH)
    return p.stat().st_mtime_ns if p.exists() else 0


def _fund_data_token(code: str = "012922") -> tuple:
    """Invalidate research caches when versioned fund data changes."""
    fund_code = str(code or "012922").strip()
    root = Path(CFG.cache_dir)
    paths = [
        root / "funds" / f"{fund_code}.csv",
        root / "funds" / f"{fund_code}.csv.manifest.json",
        root / "fund_holdings" / f"{fund_code}_history.csv",
        root / "fund_holdings" / f"{fund_code}_history.csv.manifest.json",
    ]
    token = []
    for path in paths:
        try:
            stat = path.stat()
            token.append((path.name, int(stat.st_mtime_ns), int(stat.st_size)))
        except OSError:
            token.append((path.name, 0, 0))
    return tuple(token)


def _ndx_competition_report_path() -> Path:
    return (
        Path(CFG.cache_dir)
        / "research"
        / "ndx_competition_validation_source_final.json"
    )


def _ndx_competition_report_token() -> tuple:
    path = _ndx_competition_report_path()
    try:
        stat = path.stat()
        return (path.name, int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        return (path.name, 0, 0)


def _ndx_portfolio_curves_path() -> Path:
    return resolve(
        Path(CFG.cache_dir)
        / "research"
        / "ndx_lab"
        / "ndx_incumbent_composition_sensitivity_v8g"
        / "analysis"
        / "sensitivity"
        / "portfolio_curves.json"
    )


def _ndx_style_crowding_path() -> Path:
    return resolve(
        Path(CFG.cache_dir)
        / "research"
        / "ndx_style_crowding_v1"
        / "manifest.json"
    )


def _ndx_marginal_dashboard_paths() -> tuple[Path, Path, Path, Path]:
    cache = Path(CFG.cache_dir)
    return (
        resolve(cache / "research" / "ndx_marginal_stage1_v1"),
        resolve(cache / "research" / "ndx_marginal_forward_v1"),
        resolve(
            cache
            / "candidate_pools"
            / "ndx_taxonomy_v2"
            / "incumbent_overlay"
            / "reviewed"
            / "evidence_reviewed.csv"
        ),
        resolve(
            cache
            / "candidate_pools"
            / "ndx_history"
            / "event_gap_disposition"
            / "manifest.json"
        ),
    )


def _load_ndx_portfolio_curves(curves_path: str | Path | None = None) -> dict:
    path = Path(curves_path) if curves_path is not None else _ndx_portfolio_curves_path()
    manifest_path = path.parents[2] / "manifest.json"
    return read_verified_incumbent_curve_bundle(path, manifest_path)


def _reweight_symbols(symbols) -> None:
    total = sum(s.cap_total for s in symbols)
    if total <= 0:
        return
    for s in symbols:
        s.weight = s.cap_total / total
        s.core_target = s.cap_total * CFG.portfolio.core_ratio
        s.reserve_quota = s.cap_total * (1 - CFG.portfolio.core_ratio)


def _symbols_from_portfolio(pf: Portfolio) -> list[Symbol]:
    symbols = [
        Symbol(ticker=t, cap_total=float(st.cap_total))
        for t, st in sorted(pf.symbols.items())
        if float(st.cap_total) > 0
    ]
    _reweight_symbols(symbols)
    return symbols


def _cfg_for_portfolio(pf: Portfolio):
    c = copy.deepcopy(CFG)
    c.symbols = _symbols_from_portfolio(pf)
    if getattr(c, "safe_leg", None) is not None and pf.target_safe_weight > 0:
        c.safe_leg.target_weight = float(pf.target_safe_weight)
        c.safe_leg.ticker = pf.safe_ticker
    return c


def _backtest_cfg():
    """仪表板回测优先跟随当前 state 的本金配置；无 state 时回退 config.yaml。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return copy.deepcopy(CFG)
    return _cfg_for_portfolio(pf)


def _history_high_since(ticker: str, buy_date: str) -> float:
    try:
        d0 = date.fromisoformat(str(buy_date)[:10])
    except ValueError as e:
        raise ValueError("买入日期必须为 YYYY-MM-DD") from e
    if d0 > date.today():
        raise ValueError("买入日期不能晚于今天")
    df, _ = get_bars(ticker, CFG)
    idx_dates = df.index.date
    d2 = df[idx_dates >= d0]
    if d2.empty:
        raise ValueError(f"{ticker} 在 {buy_date} 之后没有可用行情")
    col = "High" if CFG.portfolio.high_basis == "high" and "High" in d2.columns else "Close"
    return float(d2[col].max())


def _initial_high_since_buy(ticker: str, buy_date: str, buy_price: float) -> tuple[float, dict]:
    """Calculate H for a real broker position, tolerating same-day buys before daily bars land."""
    try:
        return _history_high_since(ticker, buy_date), {"source": "daily_history"}
    except ValueError as e:
        msg = str(e)
        try:
            d0 = date.fromisoformat(str(buy_date)[:10])
        except ValueError:
            raise
        if "没有可用行情" not in msg or d0 < date.today() - timedelta(days=1):
            raise
        q = _quotes_for([ticker]).get(str(ticker).upper())
        live_price = float(q.price) if q and getattr(q, "price", 0) and q.price > 0 else None
        h = max([float(buy_price)] + ([live_price] if live_price else []))
        return h, {
            "source": "intraday_fallback",
            "reason": msg,
            "live_price": round(live_price, 4) if live_price else None,
        }


_TRADE_LINE_RE = re.compile(
    r"(?P<date>\d{4}[-/]?\d{2}[-/]?\d{2}).*?"
    r"(?:成交|买入|BUY|Buy|buy)?\s*"
    r"(?P<ticker>[A-Za-z]{1,8})\s*"
    r"(?P<shares>\d+(?:\.\d+)?)\s*(?:股|shares?|SHARES?)?.*?"
    r"(?P<price>\d+(?:\.\d+)?)\s*(?:美元|美金|USD|usd|元)?"
)


def _normalize_trade_date(raw: str) -> str:
    s = str(raw).strip().replace("/", "-")
    if re.fullmatch(r"\d{8}", s):
        s = f"{s[:4]}-{s[4:6]}-{s[6:]}"
    try:
        d = date.fromisoformat(s[:10])
    except ValueError as e:
        raise ValueError(f"成交日期无效: {raw}") from e
    if d > date.today():
        raise ValueError(f"成交日期不能晚于今天: {raw}")
    return d.isoformat()


def _parse_trade_text(text: str) -> list[dict]:
    trades = []
    parts = re.split(r"[\n;；]+", str(text or ""))
    for part in parts:
        line = part.strip()
        if not line:
            continue
        if not re.search(r"\d{4}[-/]?\d{2}[-/]?\d{2}", line):
            continue
        m = _TRADE_LINE_RE.search(line)
        if not m:
            raise ValueError(f"无法解析成交记录: {line}")
        trades.append({
            "date": _normalize_trade_date(m.group("date")),
            "ticker": m.group("ticker").upper(),
            "shares": float(m.group("shares")),
            "price": float(m.group("price")),
            "raw": line,
        })
    return trades


def _norm_header(raw: str) -> str:
    return re.sub(r"[\s_\-./()（）]+", "", str(raw or "").strip().lower())


def _num(raw, default: float | None = None) -> float | None:
    if raw is None:
        return default
    s = str(raw).strip()
    if not s:
        return default
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[$,\s股美元美金]", "", s.replace("，", ""))
    try:
        val = float(s)
    except ValueError:
        return default
    return -val if neg else val


def _csv_rows(text: str) -> list[dict]:
    raw = str(text or "").strip()
    if not raw:
        return []
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    header = lines[0]
    if not any(sep in header for sep in [",", "\t", ";", "，"]):
        return []
    normalized_header = {_norm_header(x) for x in re.split(r"[,;\t，]", header)}
    if not normalized_header.intersection({"ticker", "symbol", "代码", "证券代码", "标的", "股票代码"}):
        return []
    sample = raw.replace("，", ",")
    try:
        dialect = csv.Sniffer().sniff(sample[:2048], delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(sample), dialect=dialect)
    out = []
    for row in reader:
        mapped = {_norm_header(k): (v.strip() if isinstance(v, str) else v)
                  for k, v in (row or {}).items()}
        if any(v not in (None, "") for v in mapped.values()):
            out.append(mapped)
    return out


def _pick(row: dict, aliases: set[str]):
    for key in aliases:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


_TICKER_FIELDS = {"ticker", "symbol", "代码", "证券代码", "标的", "股票代码"}
_DATE_FIELDS = {"date", "tradedate", "transactiondate", "成交日期", "交易日期", "日期"}
_SHARE_FIELDS = {"shares", "share", "qty", "quantity", "持仓数量", "数量", "股数", "成交数量"}
_PRICE_FIELDS = {"price", "avgprice", "averageprice", "avgcost", "costprice",
                 "成交价", "成交价格", "均价", "成本价", "平均成本", "买入价"}
_COST_FIELDS = {"cost", "costbasis", "amount", "netamount", "成交金额", "成本", "总成本", "金额"}


def _parse_trade_csv(text: str) -> list[dict]:
    rows = []
    for row in _csv_rows(text):
        ticker = str(_pick(row, _TICKER_FIELDS) or "").upper().strip()
        date_raw = _pick(row, _DATE_FIELDS)
        shares = _num(_pick(row, _SHARE_FIELDS))
        price = _num(_pick(row, _PRICE_FIELDS))
        if not ticker and date_raw is None and shares is None and price is None:
            continue
        if not ticker or date_raw is None or shares is None or price is None:
            raise ValueError(f"CSV 成交流水缺少 date/ticker/shares/price 字段: {row}")
        rows.append({
            "date": _normalize_trade_date(date_raw),
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "raw": row,
        })
    return rows


def _snapshot_rows_from_body(body: dict) -> list[dict]:
    rows = []
    for row in _csv_rows(str(body.get("text", ""))):
        ticker = str(_pick(row, _TICKER_FIELDS) or "").upper().strip()
        shares = _num(_pick(row, _SHARE_FIELDS))
        price = _num(_pick(row, _PRICE_FIELDS))
        cost = _num(_pick(row, _COST_FIELDS))
        date_raw = _pick(row, _DATE_FIELDS)
        if not ticker and shares is None and price is None and cost is None:
            continue
        if not ticker or shares is None:
            raise ValueError(f"CSV 持仓快照缺少 ticker/shares 字段: {row}")
        if cost is None:
            if price is None:
                raise ValueError(f"{ticker} 缺少均价/成本字段")
            cost = float(shares) * float(price)
        if price is None:
            if float(shares) <= 0:
                raise ValueError(f"{ticker} 股数必须 > 0")
            price = float(cost) / float(shares)
        rows.append({
            "date": _normalize_trade_date(date_raw) if date_raw else None,
            "ticker": ticker,
            "shares": float(shares),
            "price": float(price),
            "cost": float(cost),
            "raw": row,
        })
    if body.get("positions"):
        for p in body.get("positions") or []:
            ticker = str(p.get("ticker", "")).upper().strip()
            shares = _num(p.get("shares"))
            price = _num(p.get("price") if p.get("price") is not None else p.get("avg_price"))
            cost = _num(p.get("cost") if p.get("cost") is not None else p.get("cost_basis"))
            if cost is None and shares is not None and price is not None:
                cost = float(shares) * float(price)
            if price is None and shares and cost is not None:
                price = float(cost) / float(shares)
            rows.append({
                "date": _normalize_trade_date(p.get("date")) if p.get("date") else None,
                "ticker": ticker,
                "shares": float(shares or 0),
                "price": float(price or 0),
                "cost": float(cost or 0),
                "raw": p,
            })
    if not rows:
        raise ValueError("请提供 CSV 持仓快照（至少包含 ticker/shares/avg price 或 cost）")
    for row in rows:
        if not row["ticker"]:
            raise ValueError("持仓快照缺少 ticker")
        if row["shares"] <= 0 or row["price"] <= 0 or row["cost"] <= 0:
            raise ValueError(f"{row['ticker']} 的股数、均价和成本必须 > 0")
    return rows


def _trade_rows_from_body(body: dict) -> list[dict]:
    rows = []
    for tr in body.get("trades") or []:
        try:
            row = {
                "date": _normalize_trade_date(tr.get("date", "")),
                "ticker": str(tr.get("ticker", "")).upper().strip(),
                "shares": float(tr.get("shares", 0)),
                "price": float(tr.get("price", 0)),
                "raw": tr,
            }
        except (TypeError, ValueError) as e:
            raise ValueError(f"成交记录字段无效: {tr}") from e
        rows.append(row)
    if body.get("text"):
        text = str(body.get("text", ""))
        csv_rows = _parse_trade_csv(text)
        rows.extend(csv_rows if csv_rows else _parse_trade_text(text))
    if not rows:
        raise ValueError("请提供至少一笔成交记录")
    for row in rows:
        if not row["ticker"]:
            raise ValueError("成交记录缺少 ticker")
        if row["shares"] <= 0 or row["price"] <= 0:
            raise ValueError(f"{row['ticker']} 的股数和价格必须 > 0")
    return rows


def _replacement_map_from_body(body: dict) -> dict[str, str]:
    repl: dict[str, str] = {}
    raw = body.get("replace") or {}
    if isinstance(raw, dict):
        for old, new in raw.items():
            old_t = str(old).upper().strip()
            new_t = str(new).upper().strip()
            if old_t and new_t:
                repl[old_t] = new_t
    txt = str(body.get("replace_text", "") or "")
    for part in re.split(r"[\n,，;；\s]+", txt):
        item = part.strip()
        if not item:
            continue
        if "->" in item:
            old, new = item.split("->", 1)
        elif "=" in item:
            old, new = item.split("=", 1)
        else:
            continue
        old_t = old.upper().strip()
        new_t = new.upper().strip()
        if old_t and new_t:
            repl[old_t] = new_t
    return repl


def _group_trade_rows(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        g = grouped.setdefault(row["ticker"], {
            "ticker": row["ticker"],
            "shares": 0.0,
            "cost": 0.0,
            "first_date": row["date"],
            "last_date": row["date"],
            "trades": [],
        })
        g["shares"] += row["shares"]
        g["cost"] += row["shares"] * row["price"]
        g["first_date"] = min(g["first_date"], row["date"])
        g["last_date"] = max(g["last_date"], row["date"])
        g["trades"].append(row)
    for g in grouped.values():
        g["avg_price"] = g["cost"] / g["shares"]
    return grouped


def _group_snapshot_rows(rows: list[dict]) -> dict[str, dict]:
    grouped: dict[str, dict] = {}
    for row in rows:
        g = grouped.setdefault(row["ticker"], {
            "ticker": row["ticker"],
            "shares": 0.0,
            "cost": 0.0,
            "first_date": row.get("date"),
            "last_date": row.get("date"),
            "rows": [],
        })
        g["shares"] += row["shares"]
        g["cost"] += row["cost"]
        dates = [d for d in [g.get("first_date"), row.get("date")] if d]
        if dates:
            g["first_date"] = min(dates)
            g["last_date"] = max(dates)
        g["rows"].append(row)
    for g in grouped.values():
        if g["shares"] <= 0:
            raise ValueError(f"{g['ticker']} 股数必须 > 0")
        g["avg_price"] = g["cost"] / g["shares"]
    return grouped


def _sync_diff(pf: Portfolio, grouped: dict[str, dict], repl: dict[str, str],
               mode: str) -> list[dict]:
    old_by_new = {new: old for old, new in repl.items()}
    diff = []
    for ticker, g in grouped.items():
        old_ticker = old_by_new.get(ticker)
        source_ticker = ticker if ticker in pf.symbols else old_ticker
        source = pf.symbols.get(source_ticker) if source_ticker else None
        old_shares = float(source.shares) if source else 0.0
        old_cost = float(source.cost_basis) if source else 0.0
        old_avg = old_cost / old_shares if old_shares > 0 else None
        diff.append({
            "ticker": ticker,
            "mode": mode,
            "status": "replace" if old_ticker else ("update" if source else "new"),
            "replaced_from": old_ticker if old_ticker != ticker else None,
            "old_shares": round(old_shares, 6),
            "new_shares": round(float(g["shares"]), 6),
            "delta_shares": round(float(g["shares"]) - old_shares, 6),
            "old_cost_basis": round(old_cost, 2),
            "new_cost_basis": round(float(g["cost"]), 2),
            "delta_cost_basis": round(float(g["cost"]) - old_cost, 2),
            "old_avg_price": round(old_avg, 4) if old_avg is not None else None,
            "new_avg_price": round(float(g["avg_price"]), 4),
            "first_date": g.get("first_date") or (source.entry_date if source else None),
            "needs_date": bool(mode == "snapshot" and source is None and not g.get("first_date")),
        })
    missing = sorted(t for t in pf.symbols.keys()
                     if t not in grouped and t not in repl.keys())
    for ticker in missing:
        st = pf.symbols[ticker]
        avg = st.cost_basis / st.shares if st.shares > 0 else None
        diff.append({
            "ticker": ticker,
            "mode": mode,
            "status": "missing_in_import",
            "replaced_from": None,
            "old_shares": round(float(st.shares), 6),
            "new_shares": 0.0,
            "delta_shares": round(-float(st.shares), 6),
            "old_cost_basis": round(float(st.cost_basis), 2),
            "new_cost_basis": 0.0,
            "delta_cost_basis": round(-float(st.cost_basis), 2),
            "old_avg_price": round(avg, 4) if avg is not None else None,
            "new_avg_price": None,
            "first_date": st.entry_date,
            "needs_date": False,
        })
    return diff


def _rebuild_flows_from_symbols(pf: Portfolio) -> None:
    pf.flows = [
        CashFlow(date=(st.entry_date or pf.last_run_date or "init"),
                 amount=float(st.cum_injected),
                 note=f"当前持仓 {ticker}")
        for ticker, st in pf.symbols.items()
    ]


def _prices():
    if not _px_cache:
        dates, px, _ = _align_prices(CFG)
        _px_cache["dates"], _px_cache["px"] = dates, px
    return _px_cache["dates"], _px_cache["px"]


def _bars_for(ticker: str, cfg=None):
    key = str(ticker).upper()
    if key not in _bars_cache:
        df, _ = get_bars(key, cfg or CFG)
        _bars_cache[key] = df
    return _bars_cache[key]


def _daily_closes(cfg=None):
    """按传入 universe 获取日线最后收盘；支持 state 中新增的非 config 标的。"""
    c = cfg or CFG
    out = {}
    for s in c.symbols:
        df = _bars_for(s.ticker, c)
        out[s.ticker] = float(df["Close"].iloc[-1])
    return out


def _state_session_catchup(pf, cfg, latest_closed_iso: str):
    """Replay every complete cross-ticker session without mutating live state."""
    if not pf.last_run_date:
        raise StateCatchupError("state has no last_run_date")
    frames = {
        str(symbol.ticker).upper(): _bars_for(symbol.ticker, cfg)
        for symbol in cfg.symbols
    }
    panel, audit = build_exact_session_close_panel(
        cfg,
        frames,
        snapshot_as_of=pf.last_run_date,
        latest_session=latest_closed_iso,
    )
    proposed, ledger = replay_session_catchup(
        pf,
        cfg,
        snapshot_as_of=pf.last_run_date,
        session_closes=panel,
    )
    audit = {
        **audit,
        "day_index_before": int(pf.day_index),
        "day_index_after": int(proposed.day_index),
        "immediate_buy_session_count": sum(
            1 for row in ledger if row.get("immediate_buys")
        ),
        "immediate_buy_count": sum(
            len(lines)
            for row in ledger
            for lines in (row.get("immediate_buys") or {}).values()
        ),
    }
    return proposed, ledger, audit


def _latest_closed_session_date(cfg=None) -> date | None:
    """Return the latest common complete daily-bar date for the risk sleeve.

    Calendar ``date.today()`` can fall inside the US session while local OHLC
    data still ends at the previous close.  State mutations must never label
    that unfinished session as settled.
    """
    c = cfg or CFG
    dates = []
    for s in c.symbols:
        df = _bars_for(s.ticker, c)
        if df is None or df.empty:
            continue
        try:
            last = df.index[-1]
            last_date = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10])
            dates.append(last_date)
        except (AttributeError, TypeError, ValueError):
            continue
    return min(dates) if dates else None


def _daily_bar_freshness_payload(cfg, price_meta: dict | None, market: dict | None) -> dict:
    """Audit whether signal OHLC has caught up with the represented quote session.

    Quotes remain display/trigger inputs only.  This payload makes a lagging
    daily-close basis explicit instead of silently presenting it as today's
    tactical conclusion.
    """
    risk_tickers = [str(s.ticker).upper() for s in cfg.symbols]
    tc = getattr(cfg, "tactical_orders", None)
    gate_tickers = [
        str(t).upper() for t in (getattr(tc, "market_gate_tickers", ()) or ())
    ]
    required = list(dict.fromkeys(risk_tickers + gate_tickers))
    rows = []
    for ticker in required:
        try:
            frame = _bars_for(ticker, cfg)
            last = frame.index[-1]
            last_date = last.date() if hasattr(last, "date") else date.fromisoformat(str(last)[:10])
            rows.append({"ticker": ticker, "last_daily_bar": last_date.isoformat(), "error": ""})
        except Exception as exc:
            rows.append({"ticker": ticker, "last_daily_bar": None, "error": str(exc)})

    quote_items = [
        item for item in ((price_meta or {}).get("items") or {}).values()
        if item.get("mode") == "quote" and item.get("market_time")
    ]
    if quote_items:
        parsed_quote_sessions = [
            _snapshot_market_date({
                "as_of": (price_meta or {}).get("as_of") or date.today().isoformat(),
                "market": {"items": [item]},
            })[0]
            for item in quote_items
        ]
        parsed_quote_sessions = [value for value in parsed_quote_sessions if value]
        quote_session = max(parsed_quote_sessions) if parsed_quote_sessions else None
        quote_session_source = "latest_market_time" if quote_session else "unparsed_market_time"
    else:
        quote_session, quote_session_source = None, "no_quote_session"
    quote_iso = quote_session.isoformat() if quote_session else None
    lagging = [
        row["ticker"] for row in rows
        if quote_iso and (not row["last_daily_bar"] or row["last_daily_bar"] < quote_iso)
    ]
    common_risk = min(
        (row["last_daily_bar"] for row in rows if row["ticker"] in risk_tickers and row["last_daily_bar"]),
        default=None,
    )
    status = (
        "DAILY_BARS_LAG_QUOTE_SESSION" if lagging else
        "CURRENT_TO_QUOTE_SESSION" if quote_iso else
        "NO_QUOTE_SESSION_COMPARISON"
    )
    note = (
        f"最新报价代表美股 {quote_iso} 会话，但策略日线尚未覆盖：{', '.join(lagging)}。"
        f"战术/市场 gate 仍严格使用已收盘日线（共同风险腿截至 {common_risk or '未知'}），"
        "因此当前 WAIT/挂单结论不是按最新报价会话收盘数据重算。请先刷新日线后再判断，系统不会用盘中价替代日线信号。"
        if lagging else
        f"策略所需日线已覆盖最新报价会话 {quote_iso}。" if quote_iso else
        "当前没有可识别的报价会话，只报告本地日线日期。"
    )
    return {
        "status": status,
        "quote_session_date": quote_iso,
        "quote_session_source": quote_session_source,
        "common_risk_daily_bar_date": common_risk,
        "market_gate_signal_dates": {
            str(item.get("ticker") or "").upper(): item.get("as_of")
            for item in (market or {}).get("items") or []
        },
        "lagging_tickers": lagging,
        "required_ticker_count": len(required),
        "rows": rows,
        "note": note,
    }


def _safe_daily_price(cfg=None):
    """安全腿(SGOV)日线最后收盘。无 safe_leg 配置 → None（防御层关闭）。"""
    c = cfg or CFG
    sl = getattr(c, "safe_leg", None)
    if sl is None:
        return None
    key = sl.ticker
    if key not in _safe_cache:
        df, _ = get_bars(sl.ticker, c)
        _safe_cache[key] = float(df["Close"].iloc[-1])
    return _safe_cache[key]


def _quote_tickers(cfg, include_safe: bool = True) -> list[str]:
    tickers = [s.ticker for s in (cfg or CFG).symbols]
    sl = getattr(cfg or CFG, "safe_leg", None)
    if include_safe and sl is not None:
        tickers.append(sl.ticker)
    tc = getattr(cfg or CFG, "tactical_orders", None)
    for ticker in getattr(tc, "market_gate_tickers", ()) if tc is not None else ():
        tickers.append(ticker)
    return sorted({str(t).upper() for t in tickers if t})


def _quotes_for(tickers: list[str]) -> dict:
    key = tuple(sorted({str(t).upper() for t in tickers if t}))
    if not key:
        return {}
    now = time.time()
    cached = _quote_cache.get(key)
    if cached and now - cached["ts"] <= QUOTE_TTL_SEC:
        return cached["quotes"]
    try:
        quotes = fetch_sina_quotes(key)
    except Exception as e:
        logging.getLogger("us_ratchet").warning("盘中报价失败: %s", e)
        quotes = {}
    _quote_cache[key] = {"ts": now, "quotes": quotes}
    return quotes


def _latest_prices(cfg=None, include_safe: bool = True):
    """盘中价格优先；失败逐只回退到日线最后收盘。

    返回 (prices, meta)。meta 里保留每只标的的价格源和时间，供前端显式展示。
    """
    c = cfg or CFG
    prices = _daily_closes(c)
    daily_price = dict(prices)
    tickers = _quote_tickers(c, include_safe=include_safe)
    quotes = _quotes_for(tickers)
    items = {}
    quote_times = []
    fallback = []

    for tk in tickers:
        q = quotes.get(tk)
        if q and q.price > 0:
            prices[tk] = float(q.price)
            if q.quote_time:
                quote_times.append(q.quote_time)
            items[tk] = {
                "ticker": tk,
                "source": q.source,
                "mode": "quote",
                "price": round(float(q.price), 4),
                "previous_close": round(float(q.previous_close), 4) if q.previous_close else None,
                "change": round(float(q.change), 4) if q.change is not None else None,
                "change_pct": round(float(q.change_pct) / 100.0, 6) if q.change_pct is not None else None,
                "quote_time": q.quote_time,
                "market_time": q.market_time,
            }
        elif tk in daily_price:
            fallback.append(tk)
            items[tk] = {
                "ticker": tk,
                "source": "daily_close",
                "mode": "daily_close",
                "price": round(float(daily_price[tk]), 4),
                "previous_close": round(float(daily_price[tk]), 4),
                "change": None,
                "change_pct": None,
                "quote_time": "",
                "market_time": "",
            }

    meta = {
        "mode": "quote" if any(x.get("mode") == "quote" for x in items.values()) else "daily_close",
        "source": "sina_quote" if any(x.get("mode") == "quote" for x in items.values()) else "daily_close",
        "as_of": max(quote_times) if quote_times else "",
        "quote_count": sum(1 for x in items.values() if x.get("mode") == "quote"),
        "fallback": fallback,
        "ttl_sec": QUOTE_TTL_SEC,
        "items": items,
        "note": "盘中价用于估值和今日建议预览；H/re-arm 仍以收盘落盘为准。",
    }
    return prices, meta


def _latest_closes(cfg=None):
    """兼容旧调用：返回盘中价优先的最新价格。"""
    return _latest_prices(cfg, include_safe=False)[0]


def _safe_price(cfg=None):
    """兼容旧调用：安全腿盘中价优先，失败回退日线收盘。"""
    c = cfg or CFG
    sl = getattr(c, "safe_leg", None)
    if sl is None:
        return None
    prices, _ = _latest_prices(c, include_safe=True)
    return prices.get(sl.ticker) or _safe_daily_price(c)


def _mean_tail(series, n: int) -> float | None:
    if n <= 0 or len(series) < n:
        return None
    return float(series.tail(n).mean())


def _atr_tail(df, n: int) -> float | None:
    if n <= 0 or len(df) < n + 1:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev_close).abs(), (low - prev_close).abs()))
    val = tr.tail(n).mean()
    return float(val) if np.isfinite(val) else None


def _market_regime(last_close: float, ma20: float | None, ma50: float | None,
                   ma200: float | None) -> str:
    if ma20 is None or ma50 is None:
        return "UNKNOWN"
    if last_close >= ma20 and ma20 >= ma50 and (ma200 is None or ma50 >= ma200):
        return "BULL"
    if last_close < ma50 or (ma200 is not None and last_close < ma200):
        return "BEAR"
    return "NEUTRAL"


def _regime_label(regime: str) -> str:
    return {
        "BULL": "牛市",
        "NEUTRAL": "震荡",
        "BEAR": "熊市/破趋势",
        "UNKNOWN": "未知",
    }.get(regime, str(regime or "UNKNOWN"))


def _regime_rank(regime: str) -> int:
    return {"BULL": 0, "NEUTRAL": 1, "UNKNOWN": 1, "BEAR": 2}.get(regime, 1)


def _worse_regime(a: str, b: str | None) -> str:
    if not b:
        return a
    return a if _regime_rank(a) >= _regime_rank(b) else b


def _market_stats(ticker: str, cfg, tc, latest_price: float | None = None,
                  price_info: dict | None = None) -> dict:
    df = _bars_for(ticker, cfg)
    close = df["Close"]
    daily_last = float(close.iloc[-1])
    live_last = float(latest_price) if latest_price and latest_price > 0 else daily_last
    ma5 = _mean_tail(close, tc.ma_short)
    ma20 = _mean_tail(close, tc.ma_mid)
    ma50 = _mean_tail(close, tc.ma_trend)
    ma200 = _mean_tail(close, tc.ma_long)
    atr = _atr_tail(df, tc.atr_window)
    # Market gating is a daily-close decision.  Intraday quotes can briefly
    # cross MA50 and make a live order flicker between NEUTRAL and BEAR while
    # the underlying closed-bar regime is unchanged.
    regime = _market_regime(daily_last, ma20, ma50, ma200)
    return {
        "ticker": ticker,
        "as_of": close.index[-1].strftime("%Y-%m-%d"),
        "source": (price_info or {}).get("source", "daily_close"),
        "mode": (price_info or {}).get("mode", "daily_close"),
        "price_source": (price_info or {}).get("source", "daily_close"),
        "quote_time": (price_info or {}).get("quote_time", ""),
        "market_time": (price_info or {}).get("market_time", ""),
        "last": round(live_last, 2),
        "signal_price": round(daily_last, 2),
        "signal_price_source": "daily_close",
        "regime": regime,
        "label": _regime_label(regime),
        "ma5": round(ma5, 2) if ma5 else None,
        "ma20": round(ma20, 2) if ma20 else None,
        "ma50": round(ma50, 2) if ma50 else None,
        "ma200": round(ma200, 2) if ma200 else None,
        "atr": round(atr, 2) if atr else None,
        "above_ma50": bool(ma50 is not None and daily_last >= ma50),
        "above_ma200": bool(ma200 is not None and daily_last >= ma200),
    }


def _market_phase_payload(cfg, latest_prices: dict | None = None,
                          price_meta: dict | None = None) -> dict | None:
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None or not getattr(tc, "market_gate_enabled", False):
        return None
    items = []
    errors = {}
    for ticker in getattr(tc, "market_gate_tickers", ("QQQ", "SPY")):
        tk = str(ticker).upper()
        try:
            info = ((price_meta or {}).get("items") or {}).get(tk, {})
            items.append(_market_stats(tk, cfg, tc,
                                       (latest_prices or {}).get(tk), info))
        except Exception as e:
            errors[tk] = str(e)
    regimes = [x["regime"] for x in items if x.get("regime") != "UNKNOWN"]
    if not regimes:
        regime = "UNKNOWN"
    elif any(r == "BEAR" for r in regimes):
        regime = "BEAR"
    elif all(r == "BULL" for r in regimes):
        regime = "BULL"
    else:
        regime = "NEUTRAL"
    rule = {
        "BULL": "允许牛市回踩小额战术挂单；深跌棘轮照常装填。",
        "NEUTRAL": "战术买入降到震荡标准；只接受更深的 20日线/ATR 缓冲价。",
        "BEAR": "暂停浅层战术买入；保留储备金给深跌棘轮或后续再平衡。",
        "UNKNOWN": "市场层数据不足；仅按个股状态给出建议。",
    }[regime]
    return {
        "enabled": True,
        "regime": regime,
        "label": _regime_label(regime),
        "rule": rule,
        "method": "QQQ/SPY：收盘价、MA20/MA50/MA200；任一破趋势则按更保守阶段处理。",
        "as_of": max((x.get("quote_time") or x["as_of"] for x in items), default=None),
        "items": items,
        "errors": errors,
    }


def _admission_market(cfg) -> dict:
    """Daily-close market phase used only to annotate research admission."""
    try:
        market = _market_phase_payload(cfg)
    except Exception as e:
        return {
            "enabled": False,
            "regime": "UNKNOWN",
            "label": "未知",
            "rule": "市场阶段取数失败；研究准入不因未知阶段放大信号。",
            "error": str(e),
        }
    return market or {
        "enabled": False,
        "regime": "UNKNOWN",
        "label": "未知",
        "rule": "市场层未启用。",
    }


def _tactical_order(ticker: str, st, live_price: float, cfg, market: dict | None = None,
                    price_info: dict | None = None) -> dict:
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None or not getattr(tc, "enabled", False):
        return {"enabled": False, "action": "WAIT", "text": "战术挂单层未启用"}
    if st.frozen:
        return {"enabled": True, "action": "FROZEN", "text": "冻结：不做战术挂单"}
    if st.reserve_cash <= 0:
        return {"enabled": True, "action": "WAIT", "text": "无储备金，不做战术挂单"}

    try:
        df = _bars_for(ticker, cfg)
    except Exception as e:
        return {"enabled": True, "action": "WAIT", "text": f"战术挂单无法取数: {e}"}

    close = df["Close"]
    daily_ref = float(close.iloc[-1])
    basis_price = float((price_info or {}).get("previous_close") or daily_ref)
    ma5 = _mean_tail(close, tc.ma_short)
    ma20 = _mean_tail(close, tc.ma_mid)
    ma50 = _mean_tail(close, tc.ma_trend)
    ma200 = _mean_tail(close, tc.ma_long)
    atr = _atr_tail(df, tc.atr_window)
    if ma20 is None or ma50 is None or atr is None:
        return {"enabled": True, "action": "WAIT", "text": "战术挂单数据窗口不足"}

    # 限价生成必须使用稳定锚点；实时价只做触发判断，避免盘中 quote 下跌时限价跟着下移。
    stock_regime = _market_regime(basis_price, ma20, ma50, ma200)
    market_regime = market.get("regime") if market and market.get("enabled") else None
    regime = _worse_regime(stock_regime, market_regime)
    gate_note = None
    if market_regime and regime != stock_regime:
        if regime == "BEAR":
            gate_note = f"市场层{_regime_label(market_regime)}：暂停浅层战术买入"
        elif regime == "NEUTRAL":
            gate_note = f"市场层{_regime_label(market_regime)}：牛市信号降为震荡标准"

    cap = basis_price * (1 - tc.min_discount_pct)
    if regime == "BULL":
        ratio = tc.bull_reserve_ratio
        anchor = max(x for x in [ma5, ma20, basis_price - tc.bull_atr_mult * atr] if x is not None)
        reason = f"牛市：5/20日回踩或 {tc.bull_atr_mult:g}ATR 小回落"
    elif regime == "NEUTRAL":
        ratio = tc.neutral_reserve_ratio
        anchor = min(ma20, basis_price - tc.neutral_atr_mult * atr)
        reason = f"震荡：20日线下方并留 {tc.neutral_atr_mult:g}ATR 缓冲"
    else:
        ratio = tc.bear_reserve_ratio
        anchor = min(ma50, basis_price - tc.bear_atr_mult * atr)
        reason = "熊市/破趋势：默认不做浅层战术买入，保留弹药给深跌棘轮"
    if gate_note:
        reason = f"{gate_note}；{reason}"

    daily_limit = min(anchor, cap)
    amount = min(st.reserve_cash, st.reserve_cash * ratio)
    budget_basis = {"source": "strategy_state_reserve_cash",
                    "reserve_cash_usd": float(st.reserve_cash),
                    "reserve_ratio": float(ratio), "raw_budget_usd": float(amount),
                    "current_cash_not_consumed": True}
    execution_context = _tactical_execution_context(amount, daily_limit, cfg)
    execution_context["budget_basis"] = budget_basis
    if amount <= 0:
        return {
            "enabled": True, "regime": regime, "action": "WAIT", "text": reason,
            "limit": round(float(daily_limit), 2), "trigger": round(float(daily_limit), 2),
            "amount": 0,
            "live_price": round(float(live_price), 2),
            "basis_price": round(float(basis_price), 2),
            "daily_ref": round(float(daily_ref), 2),
            "limit_fixed": True,
            "limit_basis": "previous_close_or_daily_close",
            "stock_regime": stock_regime, "market_regime": market_regime,
            "market_gate_applied": bool(gate_note),
            "execution_context": execution_context,
            "metrics": {"ma5": round(ma5, 2) if ma5 else None,
                        "ma20": round(ma20, 2) if ma20 else None,
                        "ma50": round(ma50, 2) if ma50 else None,
                        "ma200": round(ma200, 2) if ma200 else None,
                        "atr": round(atr, 2) if atr else None},
        }

    triggered = live_price <= daily_limit
    limit = daily_limit
    shares = amount / limit if limit > 0 else 0.0
    text = (f"已触发今日固定限价 ${limit:.2f}，建议买入约 ${amount:,.0f}"
            if triggered else f"今日固定战术限价 ${limit:.2f}，金额 ${amount:,.0f}")
    return {
        "enabled": True, "regime": regime,
        "action": "BUY_NOW" if triggered else "PLACE_LIMIT",
        "text": text, "reason": reason,
        "limit": round(limit, 2), "trigger": round(limit, 2),
        "live_price": round(float(live_price), 2),
        "basis_price": round(float(basis_price), 2),
        "daily_ref": round(float(daily_ref), 2),
        "limit_fixed": True,
        "limit_basis": "previous_close_or_daily_close",
        "amount": round(amount, 0), "shares": round(shares, 3),
        "stock_regime": stock_regime, "market_regime": market_regime,
        "market_gate_applied": bool(gate_note),
        "execution_context": execution_context,
        "metrics": {"ma5": round(ma5, 2) if ma5 else None,
                    "ma20": round(ma20, 2) if ma20 else None,
                    "ma50": round(ma50, 2) if ma50 else None,
                    "ma200": round(ma200, 2) if ma200 else None,
                    "atr": round(atr, 2) if atr else None},
    }


def _symbol_advice(sig, tactical=None):
    immediate = [{"amount": round(a, 0), "price": round(p, 2), "reason": why}
                 for a, p, why in sig.immediate_buys]
    triggered = [
        {"tier": e.tier_index, "threshold": e.threshold,
         "limit": round(e.limit_price, 2), "amount": round(e.amount, 0),
         "shares": round(e.shares, 3)}
        for e in sig.ladder
        if sig.last_close <= e.limit_price
    ]
    next_order = None
    if sig.ladder:
        e = sig.ladder[0]
        next_order = {"tier": e.tier_index, "threshold": e.threshold,
                      "limit": round(e.limit_price, 2),
                      "amount": round(e.amount, 0),
                      "shares": round(e.shares, 3)}
    if sig.frozen:
        return {"action": "FROZEN", "text": "冻结：不自动买入", "immediate": immediate,
                "triggered": triggered, "next_order": next_order}
    if immediate:
        total = sum(x["amount"] for x in immediate)
        return {"action": "BUY_NOW", "text": f"分批到期，建议买入约 ${total:,.0f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    if triggered:
        total = sum(x["amount"] for x in triggered)
        return {"action": "BUY_NOW", "text": f"现价低于触发价，建议买入约 ${total:,.0f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    if tactical and tactical.get("action") in {"BUY_NOW", "PLACE_LIMIT"}:
        return {**tactical, "immediate": immediate, "triggered": triggered,
                "next_order": next_order}
    if next_order:
        prefix = "战术单等待" if tactical else "等待"
        return {"action": "WAIT",
                "text": f"{prefix}；长期极深预挂 ${next_order['limit']:.2f}",
                "immediate": immediate, "triggered": triggered, "next_order": next_order}
    return {"action": "WAIT", "text": "无活跃买入建议", "immediate": immediate,
            "triggered": triggered, "next_order": next_order}


def _defensive_payload(dfn):
    """把 DefensiveSignal 序列化给前端（None → 不触发）。"""
    if dfn is None:
        return None
    return {
        "direction": dfn.direction, "move": round(dfn.move, 0),
        "basket_value": round(dfn.basket_value, 0), "safe_value": round(dfn.safe_value, 0),
        "safe_weight": round(dfn.safe_weight, 4), "target_weight": round(dfn.target_weight, 4),
        "orders": [{"ticker": o.ticker, "side": o.side, "amount": round(o.amount, 0),
                    "shares": round(o.shares, 3), "from_reserve": round(o.from_reserve, 0),
                    "from_pending_core_cash": round(o.from_pending_core_cash, 0)}
                   for o in dfn.orders],
        "safe_order": {"ticker": dfn.safe_order.ticker, "side": dfn.safe_order.side,
                       "amount": round(dfn.safe_order.amount, 0),
                       "shares": round(dfn.safe_order.shares, 3)},
    }


def _apply_tactical_fill(pf: Portfolio, body: dict, cfg) -> dict:
    ticker = str(body.get("ticker", "")).upper().strip()
    if not ticker or ticker not in pf.symbols:
        raise ValueError(f"状态不存在或无此标的 {ticker}")
    st = pf.symbols[ticker]
    if st.frozen:
        raise ValueError(f"{ticker} 已冻结，不应回填战术成交")
    if st.reserve_cash <= 0:
        raise ValueError(f"{ticker} 无储备金可用于战术成交")

    prices, price_meta = _latest_prices(cfg, include_safe=True)
    info = ((price_meta or {}).get("items") or {}).get(ticker, {})
    market = _market_phase_payload(cfg, prices, price_meta)
    live_price = float(prices.get(ticker) or 0)
    tactical = _tactical_order(ticker, st, live_price, cfg, market, info)
    suggested_amount = float(tactical.get("amount") or 0.0)
    suggested_limit = float(tactical.get("limit") or 0.0)

    amount = float(body.get("amount") or suggested_amount or 0.0)
    price = float(body.get("price") or suggested_limit or 0.0)
    if amount <= 0:
        raise ValueError("战术成交金额必须 > 0")
    if price <= 0:
        raise ValueError("战术成交价必须 > 0")
    amount = min(amount, float(st.reserve_cash))
    shares = amount / price

    fill_date = str(body.get("date") or date.today().isoformat()).strip()
    fill_date = _normalize_trade_date(fill_date)
    note = str(body.get("note", "") or "").strip()

    st.shares += shares
    st.cost_basis += amount
    st.reserve_cash -= amount
    fill = TacticalFill(
        date=fill_date,
        limit_price=float(suggested_limit or price),
        fill_price=price,
        amount=amount,
        shares=shares,
        basis_price=float(tactical.get("basis_price") or 0.0),
        live_price=float(tactical.get("live_price") or live_price or 0.0),
        regime=str(tactical.get("regime") or ""),
        reason=str(tactical.get("reason") or ""),
        note=note,
    )
    st.tactical_fills.append(fill)
    return {
        "ticker": ticker,
        "date": fill.date,
        "amount": round(amount, 2),
        "shares": round(shares, 6),
        "fill_price": round(price, 4),
        "limit_price": round(fill.limit_price, 4),
        "reserve_left": round(st.reserve_cash, 2),
        "regime": fill.regime,
        "reason": fill.reason,
        "note": fill.note,
    }


def _tactical_rule_label(cfg) -> str:
    tc = getattr(cfg, "tactical_orders", None)
    if tc is None or not getattr(tc, "enabled", False):
        return "战术限价关闭"
    return (f"{tc.ma_short}/{tc.ma_mid}+ATR 固定限价；牛市 {tc.bull_atr_mult:g}ATR，"
            f"震荡 {tc.neutral_atr_mult:g}ATR，熊市 {tc.bear_atr_mult:g}ATR")


def _execution_constraints_payload(cfg) -> dict:
    ex = getattr(cfg, "execution", None)
    venue = getattr(ex, "venue", "汇丰银行")
    lot_size = float(getattr(ex, "lot_size", 1.0) or 1.0)
    allow_fractional = bool(getattr(ex, "allow_fractional", False))
    compact_target = int(getattr(ex, "buy_plan_compact_target", 4) or 4)
    return {
        "venue": venue,
        "currency": str(getattr(ex, "currency", "USD") or "USD").upper(),
        "lot_size": lot_size,
        "allow_fractional": allow_fractional,
        "cash_input_net_of_reserve": bool(getattr(ex, "cash_input_net_of_reserve", True)),
        "fee_bps": float(getattr(ex, "fee_bps", 0.0) or 0.0),
        "min_fee": float(getattr(ex, "min_fee", 0.0) or 0.0),
        "buy_plan_compact_target": compact_target,
        "rounding_rule": "whole_lot_floor" if not allow_fractional else "fractional_allowed",
        "summary": (
            f"{venue}；最小交易单位 {lot_size:g} 股；"
            + ("允许碎股；" if allow_fractional else "不交易碎股；")
            + "输入购买力已扣除保留现金。"
        ),
    }


def _tactical_execution_context(amount: float, limit: float | None, cfg) -> dict:
    """Annotate whether the strategy budget can fund the broker's minimum lot.

    The tactical signal remains a strategy signal.  This metadata only prevents
    a fractional internal amount from being mistaken for an executable HSBC
    whole-share order.
    """
    constraints = _execution_constraints_payload(cfg)
    value = float(amount or 0.0)
    price = float(limit or 0.0)
    lot_size = float(constraints.get("lot_size") or 1.0)
    allow_fractional = bool(constraints.get("allow_fractional"))
    unit_notional = price * lot_size if price > 0 else 0.0
    whole_lot_ready = bool(
        value > 0
        and price > 0
        and (allow_fractional or value + 0.01 >= unit_notional)
    )
    if value <= 0 or price <= 0:
        status = "NO_TACTICAL_BUDGET"
        note = "当前市况没有可动用的浅层战术预算。"
    elif not whole_lot_ready:
        status = "SUB_LOT_OBSERVATION"
        note = (
            f"策略预算约 ${value:,.0f}，低于最小交易单位约 ${unit_notional:,.0f}；"
            "汇丰不支持碎股时，这是限价观察价，不是按该预算可直接执行的整股订单。"
        )
    else:
        status = "EXECUTABLE_AT_CONSTRAINTS"
        note = "策略预算达到当前交易单位约束；实际股数仍须经过现金与真实缺口计划。"
    return {
        "status": status,
        "strategy_budget": round(value, 2),
        "minimum_lot_notional": round(unit_notional, 2) if unit_notional > 0 else None,
        "lot_size": lot_size,
        "allow_fractional": allow_fractional,
        "whole_lot_ready": whole_lot_ready,
        "note": note,
    }


def _config_health_payload(cfg, safe: dict | None, market: dict | None,
                           execution: dict | None) -> dict:
    p = cfg.portfolio
    sl = getattr(cfg, "safe_leg", None)
    tc = getattr(cfg, "tactical_orders", None)
    tier_text = "/".join(f"{x:.0%}" for x in p.tiers.thresholds)
    deploy_text = "/".join(f"{x:.0%}" for x in p.tiers.deploy_ratios)
    stages = []
    stages.append({
        "name": "核心棘轮",
        "status": "active",
        "summary": (
            f"core_ratio {p.core_ratio:.0%}；回撤档 {tier_text}；部署 {deploy_text}。"
        ),
    })
    if sl is not None:
        weight = (safe or {}).get("weight")
        if safe:
            stages.append({
                "name": "防御层",
                "status": "active",
                "summary": (
                    f"{sl.ticker} 目标 W={sl.target_weight:.0%}，执行带 ±{sl.exec_band:.0%}"
                    + (f"；当前 {float(weight):.1%}。" if weight is not None else "。")
                ),
            })
        else:
            stages.append({
                "name": "防御层",
                "status": "ignored_legacy_config",
                "summary": (
                    f"券商快照未持有 {sl.ticker}；旧 safe_leg 目标仅保留兼容审计，"
                    "不计入真实账户、不生成防御动作。"
                ),
            })
    else:
        stages.append({"name": "防御层", "status": "off", "summary": "未启用 safe_leg。"})
    stages.append({
        "name": "战术限价",
        "status": "active" if tc is not None and getattr(tc, "enabled", False) else "off",
        "summary": _tactical_rule_label(cfg),
    })
    stages.append({
        "name": "研究隔离",
        "status": "locked",
        "summary": "研究候选不读取到 /api/state；未人工确认前不写 config.yaml。",
    })
    stages.append({
        "name": "执行约束",
        "status": "active",
        "summary": _execution_constraints_payload(cfg)["summary"],
    })
    actionable = int((execution or {}).get("actionable_count") or 0)
    market_label = (market or {}).get("label") or "未知"
    summary = (
        f"当前配置仍是实盘基线；市场阶段 {market_label}；"
        f"今日可执行项 {actionable} 条。"
    )
    return {
        "status": "active_incumbent",
        "summary": summary,
        "does_use_research_candidate": False,
        "checks": stages,
        "next_review": "只有候选库进入 config_candidate，并完成今日建议差异检查后，才考虑人工替换配置。",
    }


def _position_gap_payload(syms: list[dict], live_cfg, configured_cfg=None) -> dict:
    """Build the account-truth allocation gaps used by the share planner.

    ``state.cap_total`` is the live strategy target because ``_cfg_for_portfolio``
    also uses it for signals and backtests.  Book-only shares stay visible for
    audit, but never reduce the real account gap.
    """
    configured_caps = {
        str(s.ticker).upper(): float(s.cap_total)
        for s in getattr(configured_cfg, "symbols", []) or []
    }
    live_caps = {
        str(s.ticker).upper(): float(s.cap_total)
        for s in getattr(live_cfg, "symbols", []) or []
    }

    def amount(value) -> float:
        try:
            out = float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, out) if np.isfinite(out) else 0.0

    rows = []
    for s in syms:
        ticker = str(s.get("ticker") or "").upper()
        if not ticker:
            continue
        is_real = bool(s.get("is_real_position", bool(s.get("entry_date"))))
        is_reported_closed = bool(s.get("reported_closed")) and not is_real
        if is_real:
            position_kind = "real_position"
            position_label = "真实持仓"
        elif is_reported_closed:
            position_kind = "reported_closed"
            position_label = "已清仓待新信号"
        else:
            position_kind = "pending_entry"
            position_label = "待建仓"
        target = amount(live_caps.get(ticker, s.get("cap_total")))
        real_market_value = amount(s.get("real_market_value")) if is_real else 0.0
        real_cost_basis = amount(s.get("real_cost_basis")) if is_real else 0.0
        real_shares = amount(s.get("real_shares")) if is_real else 0.0
        book_market_value = amount(s.get("book_market_value", s.get("market_value")))
        book_cost_basis = amount(s.get("book_cost_basis", s.get("cost_basis")))
        book_shares = amount(s.get("book_shares", s.get("shares")))
        gap = max(0.0, target - real_market_value)
        configured_target = configured_caps.get(ticker)
        rows.append({
            "ticker": ticker,
            "position_kind": position_kind,
            "position_label": position_label,
            "position_status": s.get("position_status") or ("real" if is_real else "book_only"),
            "reported_closed": is_reported_closed,
            "reported_closed_as_of": s.get("reported_closed_as_of"),
            "reported_closed_note": s.get("reported_closed_note"),
            "core_deployment_eligible": not is_reported_closed,
            "entry_date": s.get("entry_date"),
            "target_amount": round(target, 2),
            "target_source": "state.cap_total",
            "configured_reference_target": (
                round(float(configured_target), 2) if configured_target is not None else None
            ),
            "target_diff_from_config": (
                round(target - float(configured_target), 2) if configured_target is not None else None
            ),
            "real_shares": round(real_shares, 6),
            "real_market_value": round(real_market_value, 2),
            "real_cost_basis": round(real_cost_basis, 2),
            "book_shares_ignored": round(book_shares, 6) if not is_real else 0.0,
            "book_market_value_ignored": round(book_market_value, 2) if not is_real else 0.0,
            "book_cost_basis_ignored": round(book_cost_basis, 2) if not is_real else 0.0,
            "gap_amount": round(gap, 2),
            "gap_ratio": round(gap / target, 6) if target > 0 else 0.0,
            "has_gap": gap > 0.01,
            "frozen": bool(s.get("frozen")),
        })

    rows.sort(key=lambda row: (
        -float(row["gap_ratio"]),
        -float(row["gap_amount"]),
        row["ticker"],
    ))
    class_ranks = {"real_position": 0, "pending_entry": 0, "reported_closed": 0}
    for rank, row in enumerate(rows, start=1):
        row["gap_rank"] = rank
        kind = row["position_kind"]
        class_ranks[kind] += 1
        row["class_gap_rank"] = class_ranks[kind]

    real_rows = [row for row in rows if row["position_kind"] == "real_position"]
    pending_rows = [row for row in rows if row["position_kind"] == "pending_entry"]
    reported_closed_rows = [row for row in rows if row["position_kind"] == "reported_closed"]
    account_fingerprint = "|".join(
        f"{row['ticker']}:{row['position_kind']}:{row['target_amount']:.2f}:"
        f"{row['real_shares']:.6f}:{row['real_cost_basis']:.2f}:{row['entry_date'] or ''}"
        for row in sorted(rows, key=lambda item: item["ticker"])
    )
    return {
        "version": 1,
        "account_fingerprint": account_fingerprint,
        "target_rule": (
            "当前实盘目标取 state.cap_total；config.yaml cap_total 仅作配置参考，不参与本次缺口扣减。"
        ),
        "holding_rule": (
            "独立券商持仓快照中的 real_market_value 计入真实已持；策略账股数、市值和成本不参与扣减。"
        ),
        "ranking_rule": (
            "同一执行信号层先检查当前现金能否买一个交易单位，再按真实缺口比例、缺口金额排序；"
            "ticker 只用于确定性并列排序。"
        ),
        "share_rule": (
            "建议股数不得超过本次可动用现金、单名上限或真实缺口；整股一手超过缺口时返回 0 股。"
        ),
        "real_position_count": len(real_rows),
        "pending_entry_count": len(pending_rows),
        "reported_closed_count": len(reported_closed_rows),
        "real_tickers": [row["ticker"] for row in real_rows],
        "pending_entry_tickers": [row["ticker"] for row in pending_rows],
        "reported_closed_tickers": [row["ticker"] for row in reported_closed_rows],
        "totals": {
            "target_amount": round(sum(float(row["target_amount"]) for row in rows), 2),
            "real_market_value": round(sum(float(row["real_market_value"]) for row in rows), 2),
            "gap_amount": round(sum(float(row["gap_amount"]) for row in rows), 2),
            "book_market_value_ignored": round(
                sum(float(row["book_market_value_ignored"]) for row in rows), 2
            ),
        },
        "rows": rows,
    }


def _account_readiness_payload(syms: list[dict], safe: dict | None,
                               position_gaps: dict | None = None,
                               broker_only: list[dict] | None = None) -> dict:
    active = []
    confirmed = []
    unconfirmed = []
    reported_closed = []
    for s in syms:
        is_confirmed = bool(s.get("is_real_position", bool(s.get("entry_date"))))
        is_reported_closed = bool(s.get("reported_closed")) and not is_confirmed
        has_position = (
            float(s.get("book_shares", s.get("shares")) or 0.0) > 1e-9
            or float(s.get("book_cost_basis", s.get("cost_basis")) or 0.0) > 1e-9
        )
        if not has_position:
            continue
        row = {
            "ticker": s.get("ticker"),
            "shares": s.get("real_shares") if is_confirmed else 0.0,
            "market_value": s.get("real_market_value") if is_confirmed else 0.0,
            "cost_basis": s.get("real_cost_basis") if is_confirmed else 0.0,
            "book_shares": s.get("book_shares", s.get("shares")),
            "book_market_value": s.get("book_market_value", s.get("market_value")),
            "book_cost_basis": s.get("book_cost_basis", s.get("cost_basis")),
            "position_status": s.get("position_status"),
            "reserve": s.get("reserve"),
            "entry_date": s.get("entry_date"),
            "entry_price": s.get("entry_price"),
            "reported_closed": is_reported_closed,
            "reported_closed_as_of": s.get("reported_closed_as_of"),
            "reported_closed_note": s.get("reported_closed_note"),
        }
        active.append(row)
        if is_confirmed:
            confirmed.append(row)
        elif is_reported_closed:
            reported_closed.append(row)
        else:
            unconfirmed.append(row)
    for item in broker_only or []:
        row = {
            "ticker": item.get("ticker"), "shares": item.get("shares"),
            "market_value": item.get("market_value"), "cost_basis": item.get("cost_basis"),
            "book_shares": 0.0, "book_market_value": 0.0, "book_cost_basis": 0.0,
            "position_status": "broker_only_off_strategy", "reserve": 0.0,
            "entry_date": None, "entry_price": item.get("average_cost"),
            "broker_only": True,
        }
        active.append(row)
        confirmed.append(row)
    reserve_total = sum(float(s.get("reserve") or 0.0) for s in syms)
    pending_total = sum(float(s.get("pending_core_cash") or 0.0) for s in syms)
    confirmed_tickers = ", ".join(str(x["ticker"]) for x in confirmed) or "无"
    unconfirmed_tickers = ", ".join(str(x["ticker"]) for x in unconfirmed[:8])
    if len(unconfirmed) > 8:
        unconfirmed_tickers += f" 等{len(unconfirmed)}个"
    reported_closed_tickers = ", ".join(
        str(x["ticker"]) for x in reported_closed
    ) or "无"
    summary = (
        f"按独立券商快照识别，当前真实持仓 {len(confirmed)} 个（{confirmed_tickers}）。"
        + (
            f"另有 {len(unconfirmed)} 个无买入日的账本持仓（{unconfirmed_tickers}），"
            "买入计划中视为待建仓/未确认。"
            if unconfirmed else ""
        )
        + (
            f"另有 {len(reported_closed)} 个用户已报告清仓的旧策略账本标的"
            f"（{reported_closed_tickers}），等待新入场信号，不作为普通待建仓或机械回补对象。"
            if reported_closed else ""
        )
    )
    return {
        "status": "cash_needed" if confirmed else "needs_broker_confirmation",
        "summary": summary,
        "state_position_count": len(active),
        "state_positions": active,
        "confirmed_position_count": len(confirmed),
        "confirmed_positions": confirmed,
        "unconfirmed_position_count": len(unconfirmed),
        "unconfirmed_positions": unconfirmed,
        "reported_closed_count": len(reported_closed),
        "reported_closed_positions": reported_closed,
        "safe_position": safe,
        "reserve_book_cash": round(reserve_total, 0),
        "pending_core_cash": round(pending_total, 0),
        "needs_cash_input": True,
        "position_rule": "券商快照是实际持仓真相；策略账仅用于目标、H、储备与组合研究。",
        "position_gaps": position_gaps or {},
        "cash_source": (
            "券商可用现金未从 state 自动读取；reserve_cash 是策略账本里的储备配额，"
            "不等同于券商账户真实可动用现金。"
        ),
        "next_step": "生成正式买入股数前请输入本次可动用现金；实际持仓变化请同步券商快照。",
    }


def _broker_account_payload(closes: dict[str, float]) -> dict:
    account = load_broker_account(resolve(BROKER_ACCOUNT_PATH))
    if not account:
        return {"available": False, "positions": [], "by_ticker": {}, "broker_only": []}
    positions = []
    for source in account["positions"]:
        ticker = source["ticker"]
        price_source = "strategy_latest_price"
        price = closes.get(ticker)
        if not price:
            try:
                frame = _bars_for(ticker, CFG)
                price = float(frame["Close"].iloc[-1])
                price_source = "broker_only_latest_daily_close"
            except Exception:
                price = float(source["observed_price"])
                price_source = "broker_snapshot_observed_price"
        shares = int(source["shares"])
        average_cost = float(source["average_cost"])
        positions.append({
            **source,
            "price": price,
            "price_source": price_source,
            "market_value": shares * price,
            "cost_basis": shares * average_cost,
        })
    total = sum(row["market_value"] for row in positions)
    for row in positions:
        row["account_weight"] = row["market_value"] / total if total > 0 else 0.0
    by_ticker = {row["ticker"]: row for row in positions}
    account_fingerprint = broker_account_fingerprint(account)
    return {
        "available": True,
        "snapshot_as_of": account["snapshot_as_of"],
        "snapshot_clock": account["snapshot_clock"],
        "source_note": account["source_note"],
        "deployable_cash_usd": account.get("deployable_cash_usd", 0.0),
        "deployable_cash_session_date": account.get("deployable_cash_session_date", ""),
        "deployable_cash_persistence": account.get(
            "deployable_cash_persistence", "session"
        ),
        "positions_confirmed_session_date": account.get(
            "positions_confirmed_session_date", ""
        ),
        "account_fingerprint": account_fingerprint,
        "deployable_cash_note": account.get("deployable_cash_note", ""),
        "reported_closed_positions": account.get("reported_closed_positions", []),
        "positions": positions,
        "by_ticker": by_ticker,
        "total_market_value": total,
        "total_cost_basis": sum(row["cost_basis"] for row in positions),
    }


def _date_only(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _quality_close_at(df, pos: int) -> float | None:
    if pos < 0 or pos >= len(df):
        return None
    try:
        v = float(df["Close"].iloc[pos])
    except Exception:
        return None
    return v if np.isfinite(v) and v > 0 else None


def _bar_num(row, key: str) -> float | None:
    try:
        v = float(row.get(key))
    except Exception:
        return None
    return v if np.isfinite(v) and v > 0 else None


def _fill_quality_row(ticker: str, fill: TacticalFill, df, prev_fill_date: date | None) -> dict:
    fill_date = _date_only(fill.date)
    idx = None
    if fill_date is not None:
        dates = [d.date() for d in df.index]
        for i, d in enumerate(dates):
            if d >= fill_date:
                idx = i
                break
    if idx is None:
        return {
            "ticker": ticker,
            "date": fill.date,
            "error": "成交日期之后没有可用日线",
            "amount": round(float(fill.amount), 0),
            "fill_price": round(float(fill.fill_price), 4),
            "limit_price": round(float(fill.limit_price), 4),
        }

    bar = df.iloc[idx]
    prev_close = _quality_close_at(df, idx - 1)
    fill_price = float(fill.fill_price)
    open_px = _bar_num(bar, "Open")
    low_px = _bar_num(bar, "Low")
    close_px = _bar_num(bar, "Close")
    close20 = _quality_close_at(df, idx + 20)
    close60 = _quality_close_at(df, idx + 60)
    repeat_days = None
    if prev_fill_date is not None and fill_date is not None:
        repeat_days = (fill_date - prev_fill_date).days

    def rel(base):
        if base is None or base <= 0 or fill_price <= 0:
            return None
        return fill_price / base - 1.0

    return {
        "ticker": ticker,
        "date": fill.date,
        "bar_date": df.index[idx].strftime("%Y-%m-%d"),
        "amount": round(float(fill.amount), 0),
        "shares": round(float(fill.shares), 3),
        "limit_price": round(float(fill.limit_price), 4),
        "fill_price": round(fill_price, 4),
        "basis_price": round(float(fill.basis_price), 4) if fill.basis_price else None,
        "prev_close": round(prev_close, 4) if prev_close is not None else None,
        "open": round(open_px, 4) if open_px is not None else None,
        "low": round(low_px, 4) if low_px is not None else None,
        "close": round(close_px, 4) if close_px is not None else None,
        "discount_vs_prev_close": rel(prev_close),
        "fill_vs_open": rel(open_px),
        "fill_vs_low": rel(low_px),
        "fill_vs_close": rel(close_px),
        "return_20d": (close20 / fill_price - 1.0) if close20 and fill_price > 0 else None,
        "return_60d": (close60 / fill_price - 1.0) if close60 and fill_price > 0 else None,
        "repeat_days": repeat_days,
        "regime": fill.regime,
        "reason": fill.reason,
        "note": fill.note,
    }


def _avg(nums: list[float | None]) -> float | None:
    vals = [float(x) for x in nums if x is not None and np.isfinite(float(x))]
    return float(np.mean(vals)) if vals else None


def _tactical_quality_payload(pf: Portfolio, cfg) -> dict:
    prices, price_meta = _latest_prices(cfg, include_safe=True)
    market = _market_phase_payload(cfg, prices, price_meta)
    rows: list[dict] = []
    by_symbol: list[dict] = []
    current_limits: list[dict] = []

    for sym in cfg.symbols:
        ticker = sym.ticker
        st = pf.symbols.get(ticker)
        if st is None:
            continue
        try:
            df = _bars_for(ticker, cfg)
        except Exception as e:
            by_symbol.append({
                "ticker": ticker,
                "fill_count": 0,
                "assessment": "取数失败",
                "note": str(e),
            })
            continue

        fills = sorted(getattr(st, "tactical_fills", []) or [], key=lambda f: str(f.date))
        prev_date = None
        symbol_rows = []
        for fill in fills:
            row = _fill_quality_row(ticker, fill, df, prev_date)
            rows.append(row)
            symbol_rows.append(row)
            parsed = _date_only(fill.date)
            if parsed is not None:
                prev_date = parsed

        info = ((price_meta or {}).get("items") or {}).get(ticker, {})
        live_price = float(prices.get(ticker) or 0)
        tactical = _tactical_order(ticker, st, live_price, cfg, market, info)
        latest_bar = df.iloc[-1]
        latest_low = _bar_num(latest_bar, "Low")
        latest_close = _bar_num(latest_bar, "Close")
        limit = float(tactical.get("limit") or 0.0)
        unfilled = None
        if tactical.get("action") == "PLACE_LIMIT" and limit > 0:
            touched = latest_low is not None and latest_low <= limit
            unfilled = {
                "ticker": ticker,
                "limit": round(limit, 4),
                "latest_low": round(latest_low, 4) if latest_low is not None else None,
                "latest_close": round(latest_close, 4) if latest_close is not None else None,
                "touched_by_latest_daily_low": bool(touched),
                "gap_to_low": (latest_low / limit - 1.0) if latest_low and limit > 0 else None,
                "close_vs_limit": (latest_close / limit - 1.0) if latest_close and limit > 0 else None,
                "opportunity_cost_note": (
                    "最近日线 low 已触及限价但没有对应回填，需核对券商是否成交。"
                    if touched else "最近日线 low 仍高于限价，未成交主要是限价偏深。"
                ),
            }
            current_limits.append(unfilled)

        avg_discount = _avg([r.get("discount_vs_prev_close") for r in symbol_rows])
        avg_vs_low = _avg([r.get("fill_vs_low") for r in symbol_rows])
        avg_r20 = _avg([r.get("return_20d") for r in symbol_rows])
        avg_r60 = _avg([r.get("return_60d") for r in symbol_rows])
        avg_repeat = _avg([r.get("repeat_days") for r in symbol_rows])
        fill_count = len(symbol_rows)
        if fill_count == 0 and unfilled and (unfilled.get("close_vs_limit") or 0) > 0.05:
            assessment = "偏保守"
            note = "尚无战术成交，当前限价离收盘价较远，可能买不到。"
        elif avg_discount is not None and avg_discount > -0.005:
            assessment = "偏激进"
            note = "成交价相对前收折价不足，接近追价。"
        elif avg_vs_low is not None and avg_vs_low > 0.035:
            assessment = "可优化"
            note = "成交价离当日低点较远，后续看是否可提高耐心。"
        elif avg_r20 is not None and avg_r20 < -0.03:
            assessment = "需复核"
            note = "成交后 20 日表现偏弱，可能买早了。"
        elif fill_count > 0:
            assessment = "正常"
            note = "有成交记录，折价和后续表现未显示明显异常。"
        else:
            assessment = "样本不足"
            note = "还没有足够战术成交样本。"

        by_symbol.append({
            "ticker": ticker,
            "fill_count": fill_count,
            "fill_amount": round(sum(float(r.get("amount") or 0.0) for r in symbol_rows), 0),
            "avg_discount_vs_prev_close": avg_discount,
            "avg_fill_vs_low": avg_vs_low,
            "avg_return_20d": avg_r20,
            "avg_return_60d": avg_r60,
            "avg_repeat_days": avg_repeat,
            "assessment": assessment,
            "note": note,
            "current_unfilled": unfilled,
        })

    recent_rows = sorted(rows, key=lambda r: (str(r.get("date") or ""), str(r.get("ticker") or "")), reverse=True)
    filled_rows = [r for r in rows if not r.get("error")]
    avg_discount = _avg([r.get("discount_vs_prev_close") for r in filled_rows])
    avg_r20 = _avg([r.get("return_20d") for r in filled_rows])
    avg_r60 = _avg([r.get("return_60d") for r in filled_rows])
    touched_unfilled = sum(1 for x in current_limits if x.get("touched_by_latest_daily_low"))
    conservative_unfilled = sum(1 for x in current_limits if (x.get("gap_to_low") or 0) > 0.02)
    if not filled_rows:
        verdict = "样本不足：还没有战术成交记录。"
    elif avg_discount is not None and avg_discount > -0.005:
        verdict = "偏激进：平均折价不足，需观察是否接近追价。"
    elif conservative_unfilled >= max(2, len(current_limits) // 2):
        verdict = "偏保守：较多当前限价明显低于最近日线 low，可能买不到。"
    else:
        verdict = "当前样本未显示需要替换战术规则；继续按现行 5/20+ATR 观察。"

    return {
        "research_only": True,
        "does_change_today_advice": False,
        "as_of": date.today().isoformat(),
        "price_as_of": (price_meta or {}).get("as_of"),
        "summary": {
            "fill_count": len(filled_rows),
            "symbol_count": len(by_symbol),
            "current_unfilled_count": len(current_limits),
            "touched_unfilled_count": touched_unfilled,
            "avg_discount_vs_prev_close": avg_discount,
            "avg_return_20d": avg_r20,
            "avg_return_60d": avg_r60,
            "verdict": verdict,
            "rule_comparison": "当前 5/20+ATR 仍来自 tactical_overlay_ab 的最佳实盘配置；本页只做实盘成交质量反馈。",
            "limitation": "没有持久化未成交订单流水；未成交机会成本仅基于当前可挂限价和最近日线 low/close 粗估。",
        },
        "by_symbol": sorted(by_symbol, key=lambda x: (x.get("assessment") == "正常", x.get("ticker") or "")),
        "recent_fills": recent_rows[:20],
        "current_unfilled": current_limits,
    }


_MONTH_ABBR = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _snapshot_market_date(snapshot: dict, ticker: str | None = None) -> tuple[date | None, str]:
    """Infer the US market session date represented by a generated advice snapshot."""
    as_of = _date_only(snapshot.get("as_of")) or _date_only(snapshot.get("ts"))

    candidates: list[str] = []
    if ticker:
        for row in snapshot.get("symbols") or []:
            if str(row.get("ticker") or "").upper() == str(ticker).upper():
                candidates.extend([row.get("market_time"), row.get("quote_time")])
                break
    for item in (snapshot.get("market") or {}).get("items") or []:
        candidates.extend([item.get("market_time"), item.get("quote_time")])
    candidates.extend([
        (snapshot.get("price_meta") or {}).get("as_of"),
        snapshot.get("as_of"),
        snapshot.get("ts"),
    ])

    for raw in candidates:
        text = str(raw or "").strip()
        if not text:
            continue
        m = re.search(
            r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\b",
            text,
            flags=re.IGNORECASE,
        )
        if m:
            month = _MONTH_ABBR.get(m.group(1).upper()[:3])
            day = int(m.group(2))
            year = (as_of or date.today()).year
            try:
                d = date(year, month, day)
                if as_of and (d - as_of).days > 180:
                    d = date(year - 1, month, day)
                elif as_of and (as_of - d).days > 180:
                    d = date(year + 1, month, day)
                return d, "market_time"
            except (TypeError, ValueError):
                pass
        m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
        if m:
            d = _date_only(m.group(1))
            if d:
                return d, "iso"
    return as_of, "snapshot_as_of" if as_of else "unknown"


def _bar_index_on_or_after(df, target: date | None) -> int | None:
    if target is None:
        return None
    for i, d in enumerate(df.index):
        if d.date() >= target:
            return i
    return None


def _safe_rel(num: float | None, base: float | None) -> float | None:
    if num is None or base is None or base <= 0:
        return None
    return num / base - 1.0


def _snapshot_symbol_row(snapshot: dict, ticker: str) -> dict:
    t = str(ticker or "").upper()
    for row in snapshot.get("symbols") or []:
        if str(row.get("ticker") or "").upper() == t:
            return row
    return {}


def _golden_pit_candidates(snapshot: dict, include_deep: bool) -> list[dict]:
    allowed_sources = {"tactical_limit"}
    if include_deep:
        allowed_sources.add("ratchet_next")
    rows = []
    for item in ((snapshot.get("execution") or {}).get("items") or []):
        if item.get("source") not in allowed_sources:
            continue
        if item.get("side") != "BUY" or item.get("action") not in {"PLACE_LIMIT", "BUY_NOW"}:
            continue
        limit = _round_num(item.get("limit") or item.get("trigger"), 4)
        if limit is None or limit <= 0:
            continue
        rows.append(item)
    return rows


def _golden_pit_row(snapshot: dict, item: dict, cfg) -> dict:
    ticker = str(item.get("ticker") or "").upper()
    session_date, session_source = _snapshot_market_date(snapshot, ticker)
    limit = _round_num(item.get("limit") or item.get("trigger"), 4)
    live_price = _round_num(item.get("live_price"), 4)
    symbol_snapshot = _snapshot_symbol_row(snapshot, ticker)
    tactical = symbol_snapshot.get("tactical") or {}
    out = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_ts": snapshot.get("ts"),
        "ticker": ticker,
        "source": item.get("source"),
        "level": item.get("level") or item.get("execution_level"),
        "action": item.get("action"),
        "status": item.get("status"),
        "session_date": session_date.isoformat() if session_date else None,
        "session_date_source": session_source,
        "limit": limit,
        "live_price": live_price,
        "amount": item.get("amount"),
        "market_regime": (snapshot.get("market") or {}).get("regime"),
        "market_label": (snapshot.get("market") or {}).get("label"),
        "stock_regime": tactical.get("stock_regime"),
        "tactical_regime": tactical.get("regime"),
        "reason": item.get("reason") or tactical.get("reason"),
        "error": "",
    }
    if not ticker or not limit:
        out["error"] = "缺少 ticker 或限价"
        return out

    try:
        df = _bars_for(ticker, cfg)
    except Exception as e:
        out["error"] = f"取数失败: {e}"
        return out

    idx = _bar_index_on_or_after(df, session_date)
    if idx is None:
        out.update({
            "verdict": "PENDING",
            "label": "等待日线",
            "note": "快照对应交易日之后暂无日线，等待数据源落盘后再计算触及和反弹。",
            "lookahead_complete": False,
        })
        return out

    bar = df.iloc[idx]
    open_px = _bar_num(bar, "Open")
    high_px = _bar_num(bar, "High")
    low_px = _bar_num(bar, "Low")
    close_px = _bar_num(bar, "Close")
    prev_close = _quality_close_at(df, idx - 1)
    close1 = _quality_close_at(df, idx + 1)
    close5 = _quality_close_at(df, idx + 5)
    close20 = _quality_close_at(df, idx + 20)
    touched = bool(low_px is not None and low_px <= limit)
    missed_gap = (low_px / limit - 1.0) if low_px is not None and limit > 0 and not touched else 0.0

    rebound_1d_from_low = _safe_rel(close1, low_px)
    rebound_5d_from_low = _safe_rel(close5, low_px)
    rebound_20d_from_low = _safe_rel(close20, low_px)
    ret_1d_from_limit = _safe_rel(close1, limit)
    ret_5d_from_limit = _safe_rel(close5, limit)
    ret_20d_from_limit = _safe_rel(close20, limit)
    day_rebound_from_low = _safe_rel(close_px, low_px)
    close_vs_limit = _safe_rel(close_px, limit)
    live_vs_limit = _safe_rel(live_price, limit)

    if close20 is None:
        verdict = "PENDING"
        label = "等待后续日线"
        note = "20日观察窗口尚未完整，先只记录触及和当日表现。"
    elif touched and (ret_5d_from_limit or 0) >= 0.03:
        verdict = "TOUCHED_REBOUNDED"
        label = "触及后反弹"
        note = "限价曾被日线 low 触及，后续反弹为正；若未成交需核对券商订单。"
    elif (not touched) and missed_gap <= 0.02 and (rebound_5d_from_low or 0) >= 0.03:
        verdict = "NEAR_MISS_REBOUNDED"
        label = "接近但没买到"
        note = "当日 low 距限价不远且后续反弹，适合作为黄金坑观察样本。"
    elif (not touched) and missed_gap > 0.05 and (rebound_5d_from_low or 0) >= 0.03:
        verdict = "LIMIT_TOO_DEEP"
        label = "限价偏深"
        note = "当日 low 仍明显高于限价但后续反弹，说明当前限价可能买不到这类回调。"
    elif touched and (ret_5d_from_limit or 0) < 0:
        verdict = "TOUCHED_WEAK"
        label = "触及后走弱"
        note = "触及后短期仍弱，不应事后归因为黄金坑。"
    else:
        verdict = "NO_CLEAR_EDGE"
        label = "无明显黄金坑"
        note = "触及/反弹证据不足，暂不支持调整规则。"

    out.update({
        "bar_date": df.index[idx].strftime("%Y-%m-%d"),
        "open": round(open_px, 4) if open_px is not None else None,
        "high": round(high_px, 4) if high_px is not None else None,
        "low": round(low_px, 4) if low_px is not None else None,
        "close": round(close_px, 4) if close_px is not None else None,
        "prev_close": round(prev_close, 4) if prev_close is not None else None,
        "touched_limit": touched,
        "missed_gap": missed_gap,
        "live_vs_limit": live_vs_limit,
        "close_vs_limit": close_vs_limit,
        "day_rebound_from_low": day_rebound_from_low,
        "return_1d_from_limit": ret_1d_from_limit,
        "return_5d_from_limit": ret_5d_from_limit,
        "return_20d_from_limit": ret_20d_from_limit,
        "rebound_1d_from_low": rebound_1d_from_low,
        "rebound_5d_from_low": rebound_5d_from_low,
        "rebound_20d_from_low": rebound_20d_from_low,
        "lookahead_complete": close20 is not None,
        "verdict": verdict,
        "label": label,
        "note": note,
    })
    return out


def _golden_pit_review_payload(cfg, limit: int = 200, include_deep: bool = False) -> dict:
    output_limit = max(0, min(int(limit or 0), 500))
    journal_snapshot_count = 0
    candidate_snapshot_keys: set[str] = set()
    raw_candidate_count = 0
    first_snapshot_ts = None
    last_snapshot_ts = None
    # Keep only the latest snapshot for each session/ticker/source/limit key.
    # The journal can contain hundreds of identical dashboard refreshes per day;
    # deduplicating before OHLC replay keeps the full-history scan cheap.
    dedup_inputs: dict[tuple, tuple[dict, dict]] = {}
    errors = []
    for snap in iter_advice_snapshots():
        journal_snapshot_count += 1
        snapshot_ts = str(snap.get("ts") or "")
        if first_snapshot_ts is None:
            first_snapshot_ts = snapshot_ts or None
        last_snapshot_ts = snapshot_ts or last_snapshot_ts
        if snap.get("error"):
            errors.append(snap)
            continue
        candidates = _golden_pit_candidates(snap, include_deep=include_deep)
        if candidates:
            candidate_snapshot_keys.add(
                str(snap.get("snapshot_id") or snapshot_ts or journal_snapshot_count)
            )
        raw_candidate_count += len(candidates)
        for item in candidates:
            ticker = str(item.get("ticker") or "").upper()
            limit_price = _round_num(item.get("limit") or item.get("trigger"), 4)
            session_date, _ = _snapshot_market_date(snap, ticker)
            key = (
                session_date.isoformat() if session_date else snap.get("as_of") or snapshot_ts,
                ticker,
                item.get("source"),
                limit_price,
            )
            dedup_inputs[key] = (snap, item)

    dedup: dict[tuple, dict] = {}
    for key, (snap, item) in dedup_inputs.items():
        row = _golden_pit_row(snap, item, cfg)
        dedup[key] = row

    rows = sorted(
        dedup.values(),
        key=lambda r: (str(r.get("bar_date") or r.get("session_date") or ""),
                       str(r.get("snapshot_ts") or ""), str(r.get("ticker") or "")),
        reverse=True,
    )
    valid_rows = [r for r in rows if not r.get("error")]
    touched_rows = [r for r in valid_rows if r.get("touched_limit")]
    missed_rows = [r for r in valid_rows if not r.get("touched_limit")]
    near_miss_rows = [r for r in valid_rows if r.get("verdict") == "NEAR_MISS_REBOUNDED"]
    too_deep_rows = [r for r in valid_rows if r.get("verdict") == "LIMIT_TOO_DEEP"]
    positive_5d_rows = [
        r for r in valid_rows
        if r.get("return_5d_from_limit") is not None and float(r["return_5d_from_limit"]) > 0
    ]
    if not valid_rows:
        verdict = "样本不足：还没有可复盘的建议快照。"
    elif too_deep_rows and len(too_deep_rows) >= max(2, len(valid_rows) // 3):
        verdict = "初步偏保守：多条快照显示限价离当日 low 较远且随后反弹。"
    elif near_miss_rows:
        verdict = "存在接近未成交样本：适合后续做黄金坑观察层 A/B。"
    elif touched_rows and len(positive_5d_rows) >= max(1, len(touched_rows) // 2):
        verdict = "已有触及后反弹样本：优先核对真实订单是否成交。"
    else:
        verdict = "暂未看到稳定的黄金坑证据；继续积累快照。"

    bar_dates = sorted(
        str(r.get("bar_date")) for r in valid_rows if r.get("bar_date")
    )

    return {
        "research_only": True,
        "does_change_today_advice": False,
        "as_of": date.today().isoformat(),
        "snapshot_limit": output_limit,
        "include_deep": bool(include_deep),
        "summary": {
            "snapshot_count": journal_snapshot_count,
            "candidate_snapshot_count": len(candidate_snapshot_keys),
            "raw_candidate_count": raw_candidate_count,
            "candidate_count": len(rows),
            "valid_count": len(valid_rows),
            "touched_count": len(touched_rows),
            "missed_count": len(missed_rows),
            "near_miss_rebounded_count": len(near_miss_rows),
            "limit_too_deep_count": len(too_deep_rows),
            "avg_missed_gap": _avg([r.get("missed_gap") for r in missed_rows]),
            "avg_rebound_5d_from_low": _avg([r.get("rebound_5d_from_low") for r in valid_rows]),
            "avg_return_5d_from_limit": _avg([r.get("return_5d_from_limit") for r in valid_rows]),
            "verdict": verdict,
            "method": "全量流式扫描建议日志；按交易日/标的/来源/限价去重后，用对应交易日 OHLC 和后续 1/5/20 日收盘复盘触及、错过距离和反弹。",
            "scan_scope": "full_advice_snapshot_journal",
            "oldest_snapshot_ts": first_snapshot_ts,
            "latest_snapshot_ts": last_snapshot_ts,
            "oldest_bar_date": bar_dates[0] if bar_dates else None,
            "latest_bar_date": bar_dates[-1] if bar_dates else None,
        },
        "snapshot_storage": advice_snapshot_storage(),
        "rows": rows[:min(output_limit, 100)] if output_limit else [],
        "errors": errors[:20],
    }


def _execution_payload(symbols: list[dict], defensive: dict | None, price_meta: dict | None) -> dict:
    """统一生成今日可执行建议；研究层规则不得在这里改变实盘动作。"""
    items: list[dict] = []
    position_context = {
        str(s.get("ticker") or "").upper(): {
            "position_status": s.get("position_status"),
            "is_real_position": bool(s.get("is_real_position", bool(s.get("entry_date")))),
            "reported_closed": bool(s.get("reported_closed")),
        }
        for s in symbols
        if s.get("ticker")
    }

    def add_item(priority: int, source: str, ticker: str, action: str, side: str,
                 label: str, amount: float | None = None, shares: float | None = None,
                 limit: float | None = None, live_price: float | None = None,
                 trigger: float | None = None, threshold: float | None = None,
                 status: str = "active", reason: str = "", text: str = "",
                 execution_context: dict | None = None):
        ticker_key = str(ticker or "").upper()
        context = position_context.get(ticker_key)
        is_real_position = bool((context or {}).get("is_real_position"))
        is_reported_closed = bool((context or {}).get("reported_closed")) and not is_real_position
        is_risk_buy = side == "BUY" and context is not None
        share_plan_eligible = (
            not is_risk_buy
            or (
                not is_reported_closed
                and (is_real_position or source == "tactical_limit")
            )
        )
        position_intent = None
        if is_risk_buy:
            position_intent = "ADD" if is_real_position else "OPEN"
        items.append({
            "priority": priority,
            "source": source,
            "ticker": ticker,
            "action": action,
            "side": side,
            "label": label,
            "amount": round(float(amount), 0) if amount is not None else None,
            "shares": round(float(shares), 3) if shares is not None else None,
            "limit": round(float(limit), 2) if limit is not None else None,
            "live_price": round(float(live_price), 2) if live_price is not None else None,
            "trigger": round(float(trigger), 2) if trigger is not None else None,
            "threshold": round(float(threshold), 4) if threshold is not None else None,
            "status": status,
            "reason": reason,
            "text": text,
            "explanation": "",
            "position_status": (context or {}).get("position_status"),
            "account_scope": (
                "real_position" if is_real_position else "pending_entry"
                if context is not None and not is_reported_closed else "reported_closed"
                if is_reported_closed else "portfolio"
            ),
            "position_intent": position_intent,
            "share_plan_eligible": share_plan_eligible,
            "execution_context": execution_context or {},
        })

    for s in symbols:
        ticker = s.get("ticker", "")
        advice = s.get("advice") or {}
        tactical = s.get("tactical") or {}

        if s.get("frozen") or advice.get("action") == "FROZEN":
            add_item(
                priority=85, source="symbol_wait", ticker=ticker,
                action="FROZEN", side="NONE", label="冻结",
                live_price=s.get("last_close"), status="wait",
                text=advice.get("text", "冻结：不自动买入"),
            )
            continue

        for im in advice.get("immediate") or []:
            add_item(
                priority=10, source="pending_core", ticker=ticker,
                action="BUY_NOW", side="BUY", label="分批核心到期",
                amount=im.get("amount"), live_price=im.get("price"),
                reason=im.get("reason", ""), text="待分批核心现金到期，按今日执行价买入。",
            )

        for tr in advice.get("triggered") or []:
            add_item(
                priority=20, source="ratchet_trigger", ticker=ticker,
                action="BUY_NOW", side="BUY", label=f"深跌棘轮档 {tr.get('tier')}",
                amount=tr.get("amount"), shares=tr.get("shares"), limit=tr.get("limit"),
                trigger=tr.get("limit"), threshold=tr.get("threshold"),
                text="现价已低于已装填档位限价，属于主策略即时买入。",
            )

        has_primary_buy = bool(advice.get("immediate") or advice.get("triggered"))
        if (not has_primary_buy and tactical.get("action") in {"BUY_NOW", "PLACE_LIMIT"}
                and tactical.get("amount")):
            is_now = tactical.get("action") == "BUY_NOW"
            add_item(
                priority=30 if is_now else 50, source="tactical_limit", ticker=ticker,
                action=tactical.get("action"), side="BUY",
                label="战术固定限价",
                amount=tactical.get("amount"), shares=tactical.get("shares"),
                limit=tactical.get("limit"), live_price=tactical.get("live_price"),
                trigger=tactical.get("trigger"), status="triggered" if is_now else "pending",
                reason=tactical.get("reason", ""), text=tactical.get("text", ""),
                execution_context=tactical.get("execution_context"),
            )

        next_order = advice.get("next_order")
        has_triggered_ladder = bool(advice.get("triggered"))
        if next_order and not has_triggered_ladder:
            add_item(
                priority=70, source="ratchet_next", ticker=ticker,
                action="PLACE_LIMIT", side="BUY", label=f"深跌棘轮档 {next_order.get('tier')}",
                amount=next_order.get("amount"), shares=next_order.get("shares"),
                limit=next_order.get("limit"), trigger=next_order.get("limit"),
                threshold=next_order.get("threshold"), status="pending",
                text="深跌棘轮的下一档限价，可作为预先挂单参考。",
            )

        if not advice.get("immediate") and not advice.get("triggered") and not next_order \
                and tactical.get("action") not in {"BUY_NOW", "PLACE_LIMIT"}:
            add_item(
                priority=90, source="symbol_wait", ticker=ticker,
                action=advice.get("action", "WAIT"), side="NONE", label="无动作",
                live_price=s.get("last_close"), status="wait",
                reason=tactical.get("reason", ""), text=advice.get("text", "无活跃买入建议"),
            )

    if defensive:
        direction = defensive.get("direction")
        safe_order = defensive.get("safe_order") or {}
        label = "防御层减风险" if direction == "trim" else "防御层回补风险"
        add_item(
            priority=5, source="defensive_safe", ticker=safe_order.get("ticker", ""),
            action="REBALANCE", side=safe_order.get("side", ""), label=label,
            amount=safe_order.get("amount"), shares=safe_order.get("shares"),
            status="needs_confirm",
            text="防御层偏离执行带，需要点击确认后才会落盘。",
        )
        for o in defensive.get("orders") or []:
            add_item(
                priority=6, source="defensive_basket", ticker=o.get("ticker", ""),
                action="REBALANCE", side=o.get("side", ""), label=label,
                amount=o.get("amount"), shares=o.get("shares"),
                status="needs_confirm",
                text="防御层篮子侧再平衡指令。",
            )

    items.sort(key=lambda x: (x["priority"], x["ticker"], x["source"]))

    def execution_level(item: dict) -> dict:
        source = item.get("source")
        action = item.get("action")
        if source in {"defensive_safe", "defensive_basket"}:
            return {"label": "需确认", "note": "防御层再平衡预览，确认后才落盘。"}
        if source == "pending_core":
            return {"label": "核心到期", "note": "既有分批核心现金到期，优先级高于挂单参考。"}
        if source == "ratchet_trigger":
            return {"label": "深跌触发", "note": "已跌破棘轮档位限价，属于主策略即时买入。"}
        if source == "tactical_limit" and action == "BUY_NOW":
            return {"label": "战术触发", "note": "盘中价已触发当前固定战术限价。"}
        if source == "tactical_limit":
            return {"label": "战术预挂", "note": "当前固定战术限价，可预先挂单。"}
        if source == "ratchet_next":
            return {"label": "长期深跌预挂", "note": "下一档极深棘轮限价，不属于今日战术挂单。"}
        if action == "FROZEN":
            return {"label": "冻结", "note": "冻结标的不自动买入。"}
        return {"label": "观察", "note": "当前无可执行动作。"}

    def explain_item(item: dict) -> str:
        source = item.get("source")
        ticker = item.get("ticker") or "该标的"
        if source == "pending_core":
            return f"{ticker} 的分批核心现金到期，属于既有注资计划兑现，不是研究层新增买入。"
        if source == "ratchet_trigger":
            return (
                f"{ticker} 已跌到已装填深跌棘轮档位；限价来自 H×(1+回撤阈值)，"
                "只买不主动卖。"
            )
        if source == "tactical_limit":
            return (
                f"{ticker} 使用当前 config 的固定战术限价；限价由前收/日线 MA/ATR 锚定，"
                "盘中价只判断是否触发。"
            )
        if source == "ratchet_next":
            return (
                f"{ticker} 尚未触发深跌档位；这里显示下一档可预挂限价，"
                "不是今日战术限价，也不是立即追价买入。"
            )
        if source in {"defensive_safe", "defensive_basket"}:
            return "防御层偏离执行带，需要人工确认后才会落盘；棘轮 H 和档位状态不因此重置。"
        if source == "symbol_wait":
            return f"{ticker} 没有核心到期、深跌触发或战术买入信号，继续观察。"
        return item.get("text") or item.get("reason") or "按当前实盘配置生成。"

    for it in items:
        lvl = execution_level(it)
        it["execution_level"] = lvl["label"]
        it["sort_note"] = lvl["note"]
        it["explanation"] = explain_item(it)
        if it.get("source") == "tactical_limit":
            note = (it.get("execution_context") or {}).get("note")
            if note:
                it["explanation"] += f" {note}"
        if it.get("side") == "BUY" and not it.get("share_plan_eligible", True):
            if it.get("account_scope") == "reported_closed":
                it["explanation"] += (
                    " 用户已报告该标的清仓；旧账本信号只作审计，须经新的入场生命周期确认后才能重新进入股数计划。"
                )
            else:
                it["explanation"] += (
                    " 该标的不在独立券商快照中，此账本型分批/棘轮信号不进入真实账户股数计划。"
                )

    def item_counts(rows: list[dict]) -> dict:
        out = {"buy_now": 0, "place_limit": 0, "rebalance": 0, "wait": 0}
        for row in rows:
            action = row.get("action")
            if action == "BUY_NOW":
                out["buy_now"] += 1
            elif action == "PLACE_LIMIT":
                out["place_limit"] += 1
            elif action == "REBALANCE":
                out["rebalance"] += 1
            else:
                out["wait"] += 1
        return out

    strategy_counts = item_counts(items)
    account_items = [
        item for item in items
        if item.get("side") != "BUY" or item.get("share_plan_eligible", True)
    ]
    deep_reference_items = [item for item in account_items if item.get("source") == "ratchet_next"]
    today_items = [item for item in account_items if item.get("source") != "ratchet_next"]
    counts = item_counts(today_items)
    excluded_book_signal_count = len(items) - len(account_items)

    account_signal_count = counts["buy_now"] + counts["place_limit"] + counts["rebalance"]
    strategy_actionable = (
        strategy_counts["buy_now"] + strategy_counts["place_limit"]
        + strategy_counts["rebalance"]
    )
    lot_size = float(_execution_constraints_payload(CFG).get("lot_size") or 1.0)

    def whole_lot_buy_ready(item: dict) -> bool:
        if item.get("side") != "BUY" or item.get("action") not in {"BUY_NOW", "PLACE_LIMIT"}:
            return False
        context = item.get("execution_context") or {}
        if isinstance(context, dict) and context.get("whole_lot_ready") is not None:
            return bool(context.get("whole_lot_ready"))
        if float(item.get("shares") or 0.0) + 1e-9 >= lot_size:
            return True
        price = float(item.get("limit") or item.get("live_price") or 0.0)
        amount = float(item.get("amount") or 0.0)
        return price > 0 and amount + 0.01 >= price * lot_size

    whole_lot_buy_actionable_count = sum(1 for item in today_items if whole_lot_buy_ready(item))
    actionable = whole_lot_buy_actionable_count + counts["rebalance"]
    whole_share_reference_count = sum(
        1 for item in account_items
        if item.get("side") == "BUY"
        and item.get("action") in {"BUY_NOW", "PLACE_LIMIT"}
        and float(item.get("shares") or 0.0) >= 1.0
    )
    if actionable:
        summary = (f"今日执行层：立即买入 {counts['buy_now']} 条，战术/长期深跌限价 "
                   f"{counts['place_limit']} 条，防御再平衡 {counts['rebalance']} 条。")
    elif account_signal_count:
        summary = (
            f"今日执行层：有 {account_signal_count} 条账户范围策略信号，但均未满足汇丰整股/真实缺口约束；"
            "无可执行买入草案。"
        )
    else:
        summary = "今日执行层：无立即买入、无防御再平衡；仅保留观察。"
    return {
        "as_of": (price_meta or {}).get("as_of"),
        "mode": (price_meta or {}).get("mode", "daily_close"),
        "counts": counts,
        "strategy_counts": strategy_counts,
        "deep_reference_count": len(deep_reference_items),
        "excluded_book_signal_count": excluded_book_signal_count,
        "actionable_count": actionable,
        "strategy_actionable_count": strategy_actionable,
        "account_signal_count": account_signal_count,
        "whole_lot_buy_actionable_count": whole_lot_buy_actionable_count,
        "non_executable_signal_count": max(0, account_signal_count - actionable),
        "whole_share_reference_count": whole_share_reference_count,
        "summary": summary,
        "items": items,
        "explanation": {
            "summary": summary,
            "rule_stack": [
                "待分批核心：按既有注资计划到期买入。",
                "深跌棘轮：按 H 与回撤档位触发，只买不主动卖。",
                "战术限价：使用当前 config 的 5/20+ATR 固定限价，盘中价不改变锚点。",
                "防御层：只在安全腿偏离执行带时预览再平衡，确认后才落盘。",
            ],
            "research_boundary": "研究层结果不会自动进入今日执行建议。",
        },
        "research_note": "MA门控、崩盘sleeve、参数扫描、注资模式A/B和战术挂单A/B仍是研究层；未显式接入前不会改变今日建议。",
    }


def _round_num(value, ndigits: int = 4):
    try:
        if value is None:
            return None
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v, ndigits) if np.isfinite(v) else None


def _advice_snapshot_from_state(payload: dict) -> dict:
    """Build a compact, append-only /api/state evidence snapshot.

    Keep this payload small enough for 30-second dashboard refreshes, but rich
    enough to reconstruct why a buy did or did not appear at the time.
    """
    price_meta = payload.get("price_meta") or {}
    price_items = price_meta.get("items") or {}
    market = payload.get("market") or {}
    execution = payload.get("execution") or {}
    account = payload.get("account_readiness") or {}
    constraints = payload.get("execution_constraints") or _execution_constraints_payload(CFG)

    execution_items = []
    for item in execution.get("items") or []:
        execution_items.append({
            "priority": item.get("priority"),
            "level": item.get("execution_level"),
            "source": item.get("source"),
            "ticker": item.get("ticker"),
            "action": item.get("action"),
            "side": item.get("side"),
            "status": item.get("status"),
            "amount": item.get("amount"),
            "shares": item.get("shares"),
            "limit": item.get("limit"),
            "live_price": item.get("live_price"),
            "trigger": item.get("trigger"),
            "threshold": item.get("threshold"),
            "reason": item.get("reason"),
            "text": item.get("text"),
            "explanation": item.get("explanation"),
            "position_status": item.get("position_status"),
            "account_scope": item.get("account_scope"),
            "position_intent": item.get("position_intent"),
            "share_plan_eligible": item.get("share_plan_eligible"),
            "execution_context": item.get("execution_context") or {},
        })

    buy_plan_candidates = [
        {
            "ticker": item.get("ticker"),
            "source": item.get("source"),
            "action": item.get("action"),
            "status": item.get("status"),
            "amount": item.get("amount"),
            "shares": item.get("shares"),
            "limit": item.get("limit"),
            "live_price": item.get("live_price"),
            "execution_level": item.get("execution_level"),
            "position_status": item.get("position_status"),
            "account_scope": item.get("account_scope"),
            "position_intent": item.get("position_intent"),
            "share_plan_eligible": item.get("share_plan_eligible"),
            "execution_context": item.get("execution_context") or {},
        }
        for item in execution.get("items") or []
        if item.get("side") == "BUY"
        and item.get("source") != "ratchet_next"
        and item.get("action") in {"BUY_NOW", "PLACE_LIMIT"}
        and item.get("share_plan_eligible", True)
    ]

    symbol_rows = []
    for s in payload.get("symbols") or []:
        ticker = str(s.get("ticker") or "").upper()
        pinfo = price_items.get(ticker) or {}
        tactical = s.get("tactical") or {}
        metrics = tactical.get("metrics") or {}
        advice = s.get("advice") or {}
        live_price = _round_num(tactical.get("live_price") or s.get("last_close"), 4)
        tactical_limit = _round_num(tactical.get("limit"), 4)
        distance_to_tactical = None
        if live_price and tactical_limit and tactical_limit > 0:
            distance_to_tactical = round(live_price / tactical_limit - 1.0, 6)
        symbol_rows.append({
            "ticker": ticker,
            "price": _round_num(s.get("last_close"), 4),
            "previous_close": _round_num(s.get("previous_close") or pinfo.get("previous_close"), 4),
            "price_source": s.get("price_source") or s.get("source") or pinfo.get("source"),
            "quote_time": s.get("quote_time") or pinfo.get("quote_time"),
            "market_time": s.get("market_time") or pinfo.get("market_time"),
            "H": _round_num(s.get("H"), 4),
            "drawdown": _round_num(s.get("drawdown"), 6),
            "reserve": s.get("reserve"),
            "pending_core_cash": s.get("pending_core_cash"),
            "cap_total": s.get("cap_total"),
            "position_status": s.get("position_status"),
            "real_shares": s.get("real_shares"),
            "real_market_value": s.get("real_market_value"),
            "real_cost_basis": s.get("real_cost_basis"),
            "book_shares": s.get("book_shares"),
            "book_market_value": s.get("book_market_value"),
            "entry_date": s.get("entry_date"),
            "tier_armed": s.get("tier_armed"),
            "tactical": {
                "enabled": tactical.get("enabled"),
                "action": tactical.get("action"),
                "triggered": tactical.get("action") == "BUY_NOW",
                "limit": tactical_limit,
                "trigger": _round_num(tactical.get("trigger"), 4),
                "live_price": live_price,
                "distance_to_limit": distance_to_tactical,
                "amount": tactical.get("amount"),
                "shares": tactical.get("shares"),
                "basis_price": _round_num(tactical.get("basis_price"), 4),
                "daily_ref": _round_num(tactical.get("daily_ref"), 4),
                "regime": tactical.get("regime"),
                "stock_regime": tactical.get("stock_regime"),
                "market_regime": tactical.get("market_regime"),
                "market_gate_applied": tactical.get("market_gate_applied"),
                "execution_context": tactical.get("execution_context") or {},
                "reason": tactical.get("reason"),
                "ma5": _round_num(metrics.get("ma5"), 4),
                "ma20": _round_num(metrics.get("ma20"), 4),
                "ma50": _round_num(metrics.get("ma50"), 4),
                "ma200": _round_num(metrics.get("ma200"), 4),
                "atr": _round_num(metrics.get("atr"), 4),
            },
            "ratchet": {
                "triggered": advice.get("triggered") or [],
                "next_order": advice.get("next_order"),
                "immediate": advice.get("immediate") or [],
            },
        })

    market_items = []
    for item in market.get("items") or []:
        market_items.append({
            "ticker": item.get("ticker"),
            "label": item.get("label"),
            "regime": item.get("regime"),
            "last": item.get("last"),
            "signal_price": item.get("signal_price"),
            "signal_price_source": item.get("signal_price_source"),
            "ma20": item.get("ma20"),
            "ma50": item.get("ma50"),
            "ma200": item.get("ma200"),
            "atr": item.get("atr"),
            "source": item.get("source"),
            "quote_time": item.get("quote_time"),
            "market_time": item.get("market_time"),
        })

    return {
        "version": 2,
        "snapshot_id": f"{payload.get('as_of') or date.today().isoformat()}-{int(time.time() * 1000)}",
        "type": "api_state_advice_snapshot",
        "as_of": payload.get("as_of"),
        "state_last_run_date": payload.get("state_last_run_date"),
        "preview_day_index": payload.get("preview_day_index"),
        "needs_daily_update": payload.get("needs_daily_update"),
        "state_freshness": payload.get("state_freshness") or {},
        "price_meta": {
            "mode": price_meta.get("mode"),
            "source": price_meta.get("source"),
            "as_of": price_meta.get("as_of"),
            "quote_count": price_meta.get("quote_count"),
            "fallback": price_meta.get("fallback") or [],
        },
        "market": {
            "enabled": market.get("enabled"),
            "label": market.get("label"),
            "regime": market.get("regime"),
            "rule": market.get("rule"),
            "as_of": market.get("as_of"),
            "items": market_items,
        },
        "execution": {
            "summary": execution.get("summary"),
            "counts": execution.get("counts") or {},
            "strategy_counts": execution.get("strategy_counts") or {},
            "excluded_book_signal_count": execution.get("excluded_book_signal_count"),
            "actionable_count": execution.get("actionable_count"),
            "items": execution_items,
        },
        "buy_plan_draft": {
            "backend_cash_input_known": False,
            "execution_venue": constraints.get("venue"),
            "lot_size": constraints.get("lot_size"),
            "allow_fractional": constraints.get("allow_fractional"),
            "cash_input_net_of_reserve": constraints.get("cash_input_net_of_reserve"),
            "fee_bps": constraints.get("fee_bps"),
            "min_fee": constraints.get("min_fee"),
            "candidates": buy_plan_candidates,
            "note": "后端只记录可复算草案候选；本次可动用现金仍来自浏览器输入，P4 正式计划器再服务端化。",
        },
        "execution_constraints": constraints,
        "account": {
            "summary": account.get("summary"),
            "position_rule": account.get("position_rule"),
            "confirmed_position_count": account.get("confirmed_position_count"),
            "unconfirmed_position_count": account.get("unconfirmed_position_count"),
            "confirmed_positions": account.get("confirmed_positions") or [],
            "unconfirmed_positions": account.get("unconfirmed_positions") or [],
            "reserve_book_cash": account.get("reserve_book_cash"),
            "pending_core_cash": account.get("pending_core_cash"),
            "safe_position": account.get("safe_position"),
            "position_gaps": account.get("position_gaps") or {},
        },
        "symbols": symbol_rows,
        "safe": payload.get("safe"),
        "totals": payload.get("totals") or {},
    }


@app.get("/")
def index():
    return FileResponse(WEB)


@app.post("/api/refresh")
def refresh():
    _px_cache.clear()
    _bt_cache.clear()
    _roll_cache.clear()
    _trend_cache.clear()
    _crash_cache.clear()
    _param_cache.clear()
    _inject_mode_cache.clear()
    _tactical_cache.clear()
    _research_candidate_cache.clear()
    _ndx_competition_cache.clear()
    _ndx_style_crowding_cache.clear()
    _ndx_marginal_dashboard_cache.clear()
    _safe_cache.clear()
    _bars_cache.clear()
    _quote_cache.clear()
    return {"ok": True}


@app.get("/api/backtest")
def api_backtest(
    monthly: float = 3000.0,
    start: str = "2022-01-11",
    end: str = "",
    baseline_ticker: str = "012922",
):
    try:
        start_date = _clean_backtest_date(start, "start")
        end_date = _clean_backtest_date(end, "end")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if start_date and end_date and start_date > end_date:
        return JSONResponse({"error": "start must be earlier than or equal to end"}, status_code=400)
    baseline = _clean_backtest_baseline(baseline_ticker)
    bt_cfg = _backtest_cfg()
    if start_date:
        bt_cfg.data.start_date = start_date
    if end_date:
        bt_cfg.data.end_date = end_date
    key = (
        round(monthly, 2), start_date, end_date, baseline,
        _state_mtime_ns(), _fund_data_token("012922"),
    )
    if key in _bt_cache:
        return _bt_cache[key]
    try:
        res = run_nav_panel(bt_cfg, monthly=monthly,
                            safe_weight=(bt_cfg.safe_leg.target_weight
                                         if bt_cfg.safe_leg else 0.0),
                            safe_annual=0.04, rebal_days=21,
                            rebal_band=0.0,
                            benchmark_tickers=("QQQ", "SPY", "012922"),
                            baseline_ticker=baseline)
    except Exception as e:
        return JSONResponse({"error": f"回测失败: {e}"}, status_code=500)

    # 下采样到 ~400 点
    dates = res["grid"]
    n = len(dates)
    step = max(1, n // 400)
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    dlabels = [dates[i].strftime("%Y-%m-%d") for i in idx]

    def curve(arr):
        out = []
        for i in idx:
            v = float(arr[i])
            out.append(round(v, 4) if np.isfinite(v) else None)
        return out

    def first_valid_index(arr):
        for i, v in enumerate(arr):
            try:
                fv = float(v)
            except Exception:
                continue
            if np.isfinite(fv) and fv > 0:
                return i
        return None

    def display_curves():
        """Chart-only view: mid-history benchmarks start at the strategy NAV level.

        Metrics remain untouched.  This prevents a 2022-inception benchmark from
        being visually compared as if it had compounded since 2015.
        """
        strategy_item = res["curves"].get(res["strategy_label"])
        if not strategy_item:
            return {name: curve(item["nav"]) for name, item in res["curves"].items()}, {}
        strategy_nav = np.asarray(strategy_item["nav"], dtype=float)
        chart = {}
        meta = {}
        for name, item in res["curves"].items():
            nav = np.asarray(item["nav"], dtype=float)
            shown = nav.copy()
            start_i = first_valid_index(shown)
            if start_i is not None and start_i > 0:
                base_nav = float(shown[start_i])
                anchor_nav = float(strategy_nav[start_i])
                if np.isfinite(base_nav) and base_nav > 0 and np.isfinite(anchor_nav) and anchor_nav > 0:
                    shown[start_i:] = shown[start_i:] * (anchor_nav / base_nav)
                    meta[name] = {
                        "start": dates[start_i].strftime("%Y-%m-%d"),
                        "anchor": res["strategy_label"],
                        "anchor_nav": round(anchor_nav, 4),
                        "original_nav": round(base_nav, 4),
                        "scale": round(anchor_nav / base_nav, 6),
                    }
            chart[name] = curve(shown)
        return chart, meta

    order = list(res["curves"].keys())
    summary = {name: item["metrics"] for name, item in res["curves"].items()}
    chart_series, rebased = display_curves()
    out = {
        "dates": dlabels,
        "series": {name: curve(item["nav"]) for name, item in res["curves"].items()},
        "chart_series": chart_series,
        "summary": summary,
        "order": order,
        "baseline": res["baseline_label"],
        "strategy_label": res["strategy_label"],
        "contributed": res["contributed"],
        "range": [dlabels[0], dlabels[-1]],
        "tier_contrib": res.get("tier_contrib", {}),
        "meta": {
            "unit": "NAV",
            "request": {
                "monthly": monthly,
                "start": start_date,
                "end": end_date,
                "baseline_ticker": baseline,
            },
            "safe_weight": res["safe_weight"],
            "safe_annual": res["safe_annual"],
            "execution_constraints": _execution_constraints_payload(bt_cfg),
            "execution_note": (
                "主回测保持经济净值/NAV口径，允许份额化表达以衡量策略本身；"
                "汇丰整股约束已作为实盘口径元数据输出，整数股成交回放需另做专门 A/B 后才能接入。"
            ),
            "benchmark_errors": res.get("benchmark_errors", {}),
            "data_versions": res.get("data_versions", {}),
            "chart_rebased": rebased,
            "chart_note": "Chart uses the selected backtest window. If a benchmark starts after the window start, only the chart is rebased from its first valid date; metrics keep the real cash-flow path.",
        },
    }
    _bt_cache[key] = out
    return out


@app.get("/api/rolling_starts")
def api_rolling_starts(monthly: float = 3000.0, min_years: float = 3.0):
    bt_cfg = _backtest_cfg()
    min_years = max(1.0, float(min_years))
    key = (
        round(monthly, 2), round(min_years, 2),
        _state_mtime_ns(), _fund_data_token("012922"),
    )
    if key in _roll_cache:
        return _roll_cache[key]
    try:
        res = run_rolling_start_panel(
            bt_cfg, monthly=monthly, min_years=min_years,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0,
            benchmark_tickers=("QQQ", "SPY", "012922"), baseline_ticker="012922")
    except Exception as e:
        return JSONResponse({"error": f"滚动回测失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    out = {
        "summary": res.get("summary", {}),
        "rows": rows,
        "strategy_label": res.get("strategy_label"),
        "range": [rows[0]["start"], rows[-1]["start"]] if rows else None,
        "meta": {
            "unit": "NAV",
            "safe_weight": res.get("safe_weight"),
            "safe_annual": res.get("safe_annual"),
            "benchmark_errors": res.get("benchmark_errors", {}),
            "data_versions": res.get("data_versions", {}),
        },
    }
    _roll_cache[key] = out
    return out


@app.get("/api/trend_ab")
def api_trend_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _trend_cache:
        return _trend_cache[key]
    try:
        res = run_trend_gate_ab(
            bt_cfg, monthly=monthly,
            ma_days=(5, 20, 50, 200),
            floors=(0.75, 0.50, 0.0),
            band=0.0, cost=0.001,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"趋势门控 A/B 失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    execution_rows = res.get("execution_rows", [])
    summary = dict(res.get("summary", {}) or {})
    market = _admission_market(bt_cfg)
    summary["admission"] = {
        "trend_reduction": apply_admissions(
            rows, ADMISSION_PROFILES["trend_reduction"], market),
        "trend_execution": apply_admissions(
            execution_rows, ADMISSION_PROFILES["trend_execution"], market),
    }
    out = {
        "summary": summary,
        "baselines": res.get("baselines", {}),
        "rows": rows,
        "execution_rows": execution_rows,
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "market": market,
        "meta": {"unit": "NAV", "research_only": True},
    }
    _trend_cache[key] = out
    return out


@app.get("/api/crash_sleeve")
def api_crash_sleeve(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _crash_cache:
        return _crash_cache[key]
    try:
        res = run_crash_sleeve_ab(
            bt_cfg, monthly=monthly,
            sleeve_weights=(0.10, 0.15),
            thresholds=(0.20, 0.30, 0.40),
            deploy_ratios=(0.30, 0.40, 1.00),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0,
            benchmark_tickers=("QQQ", "SPY"))
    except Exception as e:
        return JSONResponse({"error": f"崩盘 sleeve A/B 失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    summary = dict(res.get("summary", {}) or {})
    market = _admission_market(bt_cfg)
    summary["admission"] = apply_admissions(
        rows, ADMISSION_PROFILES["crash_sleeve"], market)
    out = {
        "summary": summary,
        "baselines": res.get("baselines", {}),
        "rows": rows,
        "correlation": res.get("correlation", {}),
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "market": market,
        "meta": {
            "unit": "NAV",
            "research_only": True,
            "benchmark_errors": res.get("benchmark_errors", {}),
        },
    }
    _crash_cache[key] = out
    return out


@app.get("/api/param_scan")
def api_param_scan(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _param_cache:
        return _param_cache[key]
    try:
        res = run_param_scan_ab(
            bt_cfg, monthly=monthly,
            core_ratios=(0.75, 0.85, 0.90, 0.95),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"参数扫描失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    summary = dict(res.get("summary", {}) or {})
    market = _admission_market(bt_cfg)
    summary["admission"] = apply_admissions(
        rows, ADMISSION_PROFILES["param_scan"], market)
    out = {
        "summary": summary,
        "baselines": res.get("baselines", {}),
        "rows": rows,
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "market": market,
        "meta": {"unit": "NAV", "research_only": True},
    }
    _param_cache[key] = out
    return out


@app.get("/api/injection_ab")
def api_injection_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _inject_mode_cache:
        return _inject_mode_cache[key]
    try:
        res = run_injection_mode_ab(
            bt_cfg, monthly=monthly,
            modes=("lump_core", "ladder_core", "all_reserve"),
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21, rebal_band=0.0)
    except Exception as e:
        return JSONResponse({"error": f"注资模式 A/B 失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    summary = dict(res.get("summary", {}) or {})
    market = _admission_market(bt_cfg)
    summary["admission"] = apply_admissions(
        rows, ADMISSION_PROFILES["injection_mode"], market)
    out = {
        "summary": summary,
        "baselines": res.get("baselines", {}),
        "rows": rows,
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "market": market,
        "meta": {"unit": "NAV", "research_only": True},
    }
    _inject_mode_cache[key] = out
    return out


@app.get("/api/tactical_ab")
def api_tactical_ab(monthly: float = 3000.0):
    bt_cfg = _backtest_cfg()
    key = (round(monthly, 2), _state_mtime_ns())
    if key in _tactical_cache:
        return _tactical_cache[key]
    try:
        res = run_tactical_overlay_ab(
            bt_cfg, monthly=monthly,
            safe_weight=(bt_cfg.safe_leg.target_weight if bt_cfg.safe_leg else 0.0),
            safe_annual=0.04, rebal_days=21,
            rebal_band=(bt_cfg.safe_leg.exec_band if bt_cfg.safe_leg else 0.0),
            rolling_step_months=12)
    except Exception as e:
        return JSONResponse({"error": f"战术挂单 A/B 失败: {e}"}, status_code=500)

    rows = res.get("rows", [])
    summary = dict(res.get("summary", {}) or {})
    market = _admission_market(bt_cfg)
    summary["admission"] = apply_admissions(
        rows, ADMISSION_PROFILES["tactical_overlay"], market)
    out = {
        "summary": summary,
        "baselines": res.get("baselines", {}),
        "rows": rows,
        "range": [res["grid"][0].strftime("%Y-%m-%d"), res["grid"][-1].strftime("%Y-%m-%d")]
        if len(res.get("grid", [])) else None,
        "contributed": res.get("contributed"),
        "market": market,
        "meta": {"unit": "NAV", "research_only": True},
    }
    _tactical_cache[key] = out
    return out


@app.get("/api/universe_candidates")
def api_universe_candidates():
    return {
        "tickers": cached_universe(CFG.cache_dir),
        "source": "data/cache",
        "note": "默认排除 QQQ/SPY/SGOV/SMH/XSD；显式传入 /api/universe_research?tickers=... 可覆盖。",
    }


@app.get("/api/candidate_pool")
def api_candidate_pool(include_all: bool = True):
    """Versioned current NDX/QQQ competition pool; never a historical universe."""
    try:
        payload = build_current_candidate_registry(CFG)
        if not include_all:
            payload = dict(payload)
            payload["candidates"] = [
                row for row in payload.get("candidates", [])
                if "strategy_target_pool" in (row.get("scopes") or [])
            ]
        return payload
    except CandidatePoolError as exc:
        return JSONResponse(
            {"error": f"候选池快照不可用: {exc}"},
            status_code=503,
        )


@app.get("/api/ndx_competition")
def api_ndx_competition(refresh: bool = False):
    """Validated NDX individual-security competition; QQQ is benchmark-only."""
    report_path = _ndx_competition_report_path()
    cache_key = (
        False,
        int(report_path.stat().st_mtime_ns) if report_path.exists() else 0,
    )
    if not refresh and cache_key in _ndx_competition_cache:
        return _ndx_competition_cache[cache_key]

    payload = None
    loaded_from_disk = False
    if not refresh and report_path.exists():
        try:
            candidate = json.loads(report_path.read_text(encoding="utf-8"))
            summary = candidate.get("summary") or {}
            price_version = (
                (candidate.get("data_manifest") or {}).get("price_universe") or {}
            )
            if (
                summary.get("method") == "ndx_point_in_time_active_competition"
                and summary.get("qqq_role") == "benchmark_only_not_candidate"
                and price_version.get("content_sha256")
            ):
                payload = candidate
                loaded_from_disk = True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            payload = None

    if payload is None:
        bt_cfg = _backtest_cfg()
        bt_cfg.data.start_date = "2022-01-11"
        try:
            payload = run_ndx_competition_research(
                bt_cfg,
                target_benchmark="012922",
                min_years=1.5,
                lookback_years=2.0,
                min_history_years=0.5,
                top_ns="10",
                weight_modes="source_weight",
                safe_weights="0,0.26",
                rebalance_months="6,12",
                max_weights="0.25,0.35",
                trade_cost_bps=10.0,
                step_months=1,
                local_only=True,
                include_samples=False,
            )
            atomic_write_text(
                report_path,
                json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            )
        except Exception as exc:
            return JSONResponse(
                {"error": f"纳指100个股竞争回测失败: {exc}"},
                status_code=500,
            )

    payload = copy.deepcopy(payload)
    payload["report_cache"] = {
        "path": str(report_path),
        "loaded_from_disk": loaded_from_disk,
        "refresh_requested": bool(refresh),
    }
    final_key = (
        False,
        int(report_path.stat().st_mtime_ns) if report_path.exists() else 0,
    )
    _ndx_competition_cache.clear()
    _ndx_competition_cache[final_key] = payload
    return payload


@app.get("/api/ndx_portfolio_curves")
def api_ndx_portfolio_curves():
    """Read-only hash-bound NDX curve evidence; never starts an HTTP backtest."""
    try:
        return _load_ndx_portfolio_curves()
    except NdxIncumbentFrontierError as exc:
        return {
            "schema_version": 1,
            "available": False,
            "research_only": True,
            "reason": f"纳指100组合曲线证据不可用: {exc}",
        }


@app.get("/api/ndx_style_crowding")
def api_ndx_style_crowding():
    """Read-only hash-verified style/crowding evidence; never runs research."""
    manifest_path = _ndx_style_crowding_path()
    cache_key = int(manifest_path.stat().st_mtime_ns) if manifest_path.exists() else 0
    if cache_key and cache_key in _ndx_style_crowding_cache:
        return copy.deepcopy(_ndx_style_crowding_cache[cache_key])
    try:
        payload = read_verified_style_crowding_bundle(manifest_path.parent)
    except (NdxStyleCrowdingError, OSError, ValueError) as exc:
        return JSONResponse(
            {
                "available": False,
                "research_only": True,
                "promotion_allowed": False,
                "reason": f"纳指100风格/拥挤度诊断不可用: {exc}",
            },
            status_code=503,
        )
    payload = copy.deepcopy(payload)
    payload["report_cache"] = {
        "path": str(manifest_path.parent),
        "loaded_from_disk": True,
        "refresh_requested": False,
    }
    _ndx_style_crowding_cache.clear()
    _ndx_style_crowding_cache[cache_key] = payload
    return copy.deepcopy(payload)


@app.get("/api/ndx_marginal_allocation")
def api_ndx_marginal_allocation():
    """Read-only legacy monitoring, cash history and complete modern saved inputs."""
    try:
        modern_inputs = dict(load_modern_new_cash_inputs_view(), available=True, research_only=True)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        modern_inputs = {
            "schema": "MODERN_DYNAMIC_NEW_CASH_DASHBOARD_VIEW_V1",
            "status": "SOURCE_INPUTS_UNAVAILABLE_BLOCKED",
            "available": False, "research_only": True,
            "reason": f"现代动态组合来源输入不可用: {exc}",
            "coordinates_preserved": [], "lanes": [], "tracks": [],
            "current_new_money": None, "current_account": None, "plan_rows": [],
            **MODERN_NEW_CASH_INPUT_FLAGS,
        }
    try:
        cash_evidence = read_cash_history_evidence()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        cash_evidence = {"available": False, "research_only": True,
                         "candidate_admission_allowed": False,
                         "reason": f"已封现金历史证据不可用: {exc}"}
    try:
        stage1_dir, forward_dir, overlay_path, event_gap_manifest_path = _ndx_marginal_dashboard_paths()
        manifest_paths = [
            stage1_dir / "manifest.json",
            forward_dir / "latest_evaluation" / "manifest.json",
            forward_dir / "cohort_index.jsonl",
            overlay_path,
            event_gap_manifest_path,
        ]
        cache_key = tuple(
            (int(path.stat().st_mtime_ns), int(path.stat().st_size))
            if path.exists() else (0, 0)
            for path in manifest_paths
        )
        if cache_key in _ndx_marginal_dashboard_cache:
            cached = copy.deepcopy(_ndx_marginal_dashboard_cache[cache_key])
            cached["portfolio_optimization_cash_evidence"] = cash_evidence
            cached["modern_dynamic_new_cash_inputs"] = modern_inputs
            return cached
        payload = read_verified_marginal_dashboard(
            stage1_dir=stage1_dir,
            forward_dir=forward_dir,
            overlay_path=overlay_path,
            event_gap_manifest_path=event_gap_manifest_path,
        )
    except (NdxMarginalDashboardError, OSError, ValueError, KeyError) as exc:
        return JSONResponse(
            {
                "available": False,
                "research_only": True,
                "candidate_admission_allowed": False,
                "reason": f"纳指100新增资金边际配置证据不可用: {exc}",
                "portfolio_optimization_cash_evidence": cash_evidence,
                "modern_dynamic_new_cash_inputs": modern_inputs,
            },
            status_code=200 if cash_evidence.get("available") or modern_inputs.get("available") else 503,
        )
    payload["portfolio_optimization_cash_evidence"] = cash_evidence
    payload["modern_dynamic_new_cash_inputs"] = modern_inputs
    payload["report_cache"] = {
        "stage1_path": stage1_dir.as_posix(),
        "forward_path": forward_dir.as_posix(),
        "loaded_from_disk": True,
        "refresh_requested": False,
    }
    _ndx_marginal_dashboard_cache.clear()
    _ndx_marginal_dashboard_cache[cache_key] = payload
    return copy.deepcopy(payload)


@app.get("/api/universe_research")
def api_universe_research(tickers: str = "", total_cap: float = 37000.0,
                          monthly: float = 3000.0, top_n: int = 8,
                          max_weight: float = 0.22, min_weight: float = 0.04,
                          max_pair_corr: float = 0.92,
                          min_years: float = 2.0,
                          drawdown_budget: float = 0.35,
                          local_only: bool = True,
                          include_backtest: bool = True):
    """候选美股池诊断/动态篮子建议。研究层，不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    if not str(tickers or "").strip():
        tickers = ",".join(cached_universe(bt_cfg.cache_dir))
    try:
        return run_universe_research(
            bt_cfg, tickers,
            total_cap=float(total_cap),
            monthly=float(monthly),
            top_n=max(1, min(20, int(top_n))),
            min_history_years=max(0.5, float(min_years)),
            max_weight=max(0.05, min(0.60, float(max_weight))),
            min_weight=max(0.0, min(0.20, float(min_weight))),
            max_pair_corr=max(0.50, min(0.99, float(max_pair_corr))),
            drawdown_budget=max(0.05, min(0.80, float(drawdown_budget))),
            local_only=bool(local_only),
            include_backtest=bool(include_backtest),
        )
    except Exception as e:
        return JSONResponse({"error": f"候选池研究失败: {e}"}, status_code=500)


@app.get("/api/preference_portfolio_research")
def api_preference_portfolio_research(tickers: str = "", groups: str = "",
                                      total_cap: float = 37000.0,
                                      monthly: float = 3000.0,
                                      target_benchmark: str = "012922",
                                      min_years: float = 3.0,
                                      safe_weights: str = "0,0.14,0.26",
                                      include_voltarget: bool = False,
                                      voltarget_top_k: int = 4,
                                      local_only: bool = True):
    """自选美股池/分组组合 A/B。研究层，不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    if not str(tickers or "").strip() and not str(groups or "").strip():
        tickers = ",".join(cached_universe(bt_cfg.cache_dir))
    try:
        return run_preference_portfolio_research(
            bt_cfg,
            tickers=tickers,
            groups=groups,
            total_cap=float(total_cap),
            monthly=float(monthly),
            local_only=bool(local_only),
            min_years=max(1.0, float(min_years)),
            safe_weights=safe_weights,
            include_voltarget=bool(include_voltarget),
            voltarget_top_k=max(0, min(12, int(voltarget_top_k))),
            target_benchmark=str(target_benchmark or "012922").upper(),
        )
    except Exception as e:
        return JSONResponse({"error": f"自选组合研究失败: {e}"}, status_code=500)


@app.get("/api/fund_mirror_research")
def api_fund_mirror_research(fund_code: str = "012922",
                             report_date: str = "",
                             total_cap: float = 37000.0,
                             monthly: float = 3000.0,
                             target_benchmark: str = "012922",
                             min_years: float = 3.0,
                             top_n: int = 10,
                             safe_weights: str = "0,0.14,0.26,0.40",
                             core_ratios: str = "0.90,0.95",
                             include_equal: bool = True,
                             local_only: bool = False):
    """镜像目标基金最新披露 US 持仓做研究；不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    try:
        return run_fund_mirror_research(
            bt_cfg,
            fund_code=str(fund_code or "012922"),
            report_date=(report_date or None),
            total_cap=float(total_cap),
            monthly=float(monthly),
            target_benchmark=str(target_benchmark or "012922").upper(),
            min_years=max(1.0, float(min_years)),
            top_n=max(1, min(30, int(top_n))),
            safe_weights=safe_weights,
            core_ratios=core_ratios,
            include_equal=bool(include_equal),
            local_only=bool(local_only),
        )
    except Exception as e:
        return JSONResponse({"error": f"基金持仓镜像研究失败: {e}"}, status_code=500)


@app.get("/api/fund_style_attribution")
def api_fund_style_attribution(fund_code: str = "012922",
                               benchmarks: str = "QQQ,SMH,SPY",
                               start_year: int = 2022,
                               end_year: int = 0,
                               local_only: bool = True,
                               refresh: bool = False):
    """固定基金风格归因报告；只读，不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    benchmark_tickers = tuple(
        value.strip().upper() for value in str(benchmarks or "").split(",")
        if value.strip()
    )
    try:
        return run_fund_style_attribution(
            bt_cfg,
            fund_code=str(fund_code or "012922"),
            benchmark_tickers=benchmark_tickers or ("QQQ", "SMH", "SPY"),
            start_year=max(1990, int(start_year)),
            end_year=(int(end_year) if int(end_year) > 0 else None),
            local_only=bool(local_only) and not bool(refresh),
            refresh=bool(refresh),
        )
    except Exception as e:
        return JSONResponse({"error": f"基金风格归因失败: {e}"}, status_code=500)


@app.get("/api/fund_quarterly_mirror_research")
def api_fund_quarterly_mirror_research(fund_code: str = "012922",
                                       total_cap: float = 37000.0,
                                       monthly: float = 3000.0,
                                       target_benchmark: str = "012922",
                                       min_years: float = 3.0,
                                       start_year: int = 2021,
                                       end_year: int = 0,
                                       top_ns: str = "4,6,8",
                                       weight_modes: str = "fund_weight,capped_fund_weight,score_risk",
                                       safe_weights: str = "0.26,0.34,0.40",
                                       core_ratios: str = "0.90,0.95",
                                       max_weight: float = 0.30,
                                       min_weight: float = 0.04,
                                       availability_delay_days: int = 30,
                                       rebalance_months: int = 3,
                                       rebalance_same_report: bool = False,
                                       trade_cost_bps: float = 10.0,
                                       step_months: int = 3,
                                       max_windows: int = 0,
                                       local_only: bool = False,
                                       include_samples: bool = False):
    """按历史季度披露点时镜像目标基金 US 持仓；研究层，不改今日建议。"""
    bt_cfg = _backtest_cfg()
    try:
        return run_fund_quarterly_mirror_research(
            bt_cfg,
            fund_code=str(fund_code or "012922"),
            total_cap=float(total_cap),
            monthly=float(monthly),
            target_benchmark=str(target_benchmark or "012922").upper(),
            min_years=max(1.0, float(min_years)),
            start_year=(int(start_year) if int(start_year) > 0 else None),
            end_year=(int(end_year) if int(end_year) > 0 else None),
            top_ns=top_ns,
            weight_modes=weight_modes,
            safe_weights=safe_weights,
            core_ratios=core_ratios,
            max_weight=max(0.05, min(1.0, float(max_weight))),
            min_weight=max(0.0, min(0.25, float(min_weight))),
            availability_delay_days=max(0, min(120, int(availability_delay_days))),
            rebalance_months=max(1, min(12, int(rebalance_months))),
            rebalance_same_report=bool(rebalance_same_report),
            trade_cost_bps=max(0.0, min(200.0, float(trade_cost_bps))),
            step_months=max(1, min(12, int(step_months))),
            max_windows=max(0, int(max_windows)),
            local_only=bool(local_only),
            include_samples=bool(include_samples),
        )
    except Exception as e:
        return JSONResponse({"error": f"季度持仓点时镜像研究失败: {e}"}, status_code=500)


@app.get("/api/preference_walkforward")
def api_preference_walkforward(tickers: str = "", groups: str = "",
                               total_cap: float = 37000.0,
                               monthly: float = 3000.0,
                               target_benchmark: str = "012922",
                               min_years: float = 3.0,
                               lookback_years: float = 3.0,
                               min_history_years: float = 2.0,
                               safe_weights: str = "0,0.26",
                               modes: str = "",
                               step_months: int = 1,
                               max_windows: int = 0,
                               local_only: bool = True,
                               include_samples: bool = False):
    """点时动态篮子 walk-forward。研究层，不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    if not str(tickers or "").strip() and not str(groups or "").strip():
        tickers = ",".join(cached_universe(bt_cfg.cache_dir))
    try:
        return run_preference_walkforward_research(
            bt_cfg,
            tickers=tickers,
            groups=groups,
            total_cap=float(total_cap),
            monthly=float(monthly),
            target_benchmark=str(target_benchmark or "012922").upper(),
            min_years=max(1.0, float(min_years)),
            lookback_years=max(0.5, float(lookback_years)),
            min_history_years=max(0.5, float(min_history_years)),
            safe_weights=safe_weights,
            modes=(modes or None),
            step_months=max(1, min(12, int(step_months))),
            max_windows=max(0, int(max_windows)),
            local_only=bool(local_only),
            include_samples=bool(include_samples),
        )
    except Exception as e:
        return JSONResponse({"error": f"点时动态篮子回放失败: {e}"}, status_code=500)


@app.get("/api/preference_rebalance")
def api_preference_rebalance(tickers: str = "", groups: str = "",
                             total_cap: float = 37000.0,
                             monthly: float = 3000.0,
                             target_benchmark: str = "012922",
                             min_years: float = 3.0,
                             lookback_years: float = 3.0,
                             min_history_years: float = 2.0,
                             safe_weights: str = "0,0.26",
                             modes: str = "",
                             rebalance_months: str = "6,12",
                             trade_cost_bps: float = 10.0,
                             step_months: int = 1,
                             max_windows: int = 0,
                             local_only: bool = True,
                             include_samples: bool = False):
    """低频主动重选/调仓成本回放。研究层，不改 state/config/今日建议。"""
    bt_cfg = _backtest_cfg()
    if not str(tickers or "").strip() and not str(groups or "").strip():
        tickers = ",".join(cached_universe(bt_cfg.cache_dir))
    try:
        return run_preference_rebalance_research(
            bt_cfg,
            tickers=tickers,
            groups=groups,
            total_cap=float(total_cap),
            monthly=float(monthly),
            target_benchmark=str(target_benchmark or "012922").upper(),
            min_years=max(1.0, float(min_years)),
            lookback_years=max(0.5, float(lookback_years)),
            min_history_years=max(0.5, float(min_history_years)),
            safe_weights=safe_weights,
            modes=(modes or None),
            rebalance_months=rebalance_months,
            trade_cost_bps=max(0.0, float(trade_cost_bps)),
            step_months=max(1, min(12, int(step_months))),
            max_windows=max(0, int(max_windows)),
            local_only=bool(local_only),
            include_samples=bool(include_samples),
        )
    except Exception as e:
        return JSONResponse({"error": f"低频主动重选回放失败: {e}"}, status_code=500)


@app.get("/api/preference_live_gate")
def api_preference_live_gate(tickers: str = "", groups: str = "",
                             total_cap: float = 37000.0,
                             monthly: float = 3000.0,
                             target_benchmark: str = "012922",
                             min_years: float = 3.0,
                             safe_weights: str = "0,0.14,0.26",
                             include_voltarget: bool = False,
                             voltarget_top_k: int = 4,
                             local_only: bool = True,
                             include_research: bool = False):
    """Read-only gate before any dynamic basket can touch live advice."""
    bt_cfg = _backtest_cfg()
    incumbent_basis = (
        "state_cap_total"
        if load_portfolio(resolve(STATE_PATH)) is not None
        else "config_yaml"
    )
    if not str(tickers or "").strip() and not str(groups or "").strip():
        tickers = ",".join(cached_universe(bt_cfg.cache_dir))
    try:
        return run_preference_live_gate(
            bt_cfg,
            tickers=tickers,
            groups=groups,
            total_cap=float(total_cap),
            monthly=float(monthly),
            target_benchmark=str(target_benchmark or "012922").upper(),
            min_years=max(1.0, float(min_years)),
            safe_weights=safe_weights,
            include_voltarget=bool(include_voltarget),
            voltarget_top_k=max(0, min(12, int(voltarget_top_k))),
            local_only=bool(local_only),
            market=_admission_market(bt_cfg),
            incumbent_basis=incumbent_basis,
            include_research=bool(include_research),
        )
    except Exception as e:
        return JSONResponse({"error": f"动态篮子实盘准入预检失败: {e}"}, status_code=500)


def _source_result(label: str, fn):
    try:
        res = fn()
    except Exception as e:
        return None, f"{label}: {e}"
    if isinstance(res, JSONResponse):
        try:
            text = res.body.decode("utf-8", errors="replace")
        except Exception:
            text = repr(res)
        return None, f"{label}: {text}"
    return res, None


@app.get("/api/research_candidates")
def api_research_candidates(tickers: str = "", groups: str = "",
                            monthly: float = 3000.0,
                            total_cap: float = 37000.0,
                            target_benchmark: str = "012922",
                            min_years: float = 3.0,
                            compute: bool = False,
                            include_dynamic: bool = True,
                            include_heavy: bool = False,
                            include_voltarget: bool = True,
                            local_only: bool = True):
    """只读策略研发台账；统一治理候选阶段，不写 config/state。"""
    bt_cfg = _backtest_cfg()
    key = (
        round(float(monthly), 2), round(float(total_cap), 2),
        str(target_benchmark or "012922").upper(), round(float(min_years), 2),
        bool(compute), bool(include_dynamic), bool(include_heavy), bool(include_voltarget),
        bool(local_only), str(tickers or ""), str(groups or ""), _state_mtime_ns(),
        _fund_data_token(str(target_benchmark or "012922")),
        _ndx_competition_report_token(),
    )
    if key in _research_candidate_cache:
        return _research_candidate_cache[key]

    market = _admission_market(bt_cfg)
    if not compute:
        ndx_competition, _ = _source_result(
            "ndx_competition", lambda: api_ndx_competition(refresh=False)
        )
        out = build_static_candidate_registry(
            ndx_competition=ndx_competition,
            market=market,
            as_of=date.today().isoformat(),
        )
        _research_candidate_cache[key] = out
        return out

    source_errors: dict[str, str] = {}

    param_scan, err = _source_result("param_scan", lambda: api_param_scan(monthly=monthly))
    if err:
        source_errors["param_scan"] = err
    injection_ab, err = _source_result("injection_ab", lambda: api_injection_ab(monthly=monthly))
    if err:
        source_errors["injection_ab"] = err
    tactical_ab, err = _source_result("tactical_ab", lambda: api_tactical_ab(monthly=monthly))
    if err:
        source_errors["tactical_ab"] = err

    preference_gate = None
    if include_dynamic:
        preference_gate, err = _source_result(
            "preference_live_gate",
            lambda: api_preference_live_gate(
                tickers=tickers, groups=groups, total_cap=total_cap, monthly=monthly,
                target_benchmark=target_benchmark, min_years=min_years,
                safe_weights="0,0.14,0.26", include_voltarget=include_voltarget,
                local_only=local_only, include_research=False,
            ),
        )
        if err:
            source_errors["preference_live_gate"] = err

    preference_walkforward = preference_rebalance = fund_mirror = fund_quarterly = None
    ndx_competition = None
    if include_heavy:
        preference_walkforward, err = _source_result(
            "preference_walkforward",
            lambda: api_preference_walkforward(
                tickers=tickers, groups=groups, total_cap=total_cap, monthly=monthly,
                target_benchmark=target_benchmark, min_years=min_years,
                safe_weights="0,0.26", local_only=local_only, include_samples=False,
            ),
        )
        if err:
            source_errors["preference_walkforward"] = err
        preference_rebalance, err = _source_result(
            "preference_rebalance",
            lambda: api_preference_rebalance(
                tickers=tickers, groups=groups, total_cap=total_cap, monthly=monthly,
                target_benchmark=target_benchmark, min_years=min_years,
                safe_weights="0,0.26", local_only=local_only, include_samples=False,
            ),
        )
        if err:
            source_errors["preference_rebalance"] = err
        fund_mirror, err = _source_result(
            "fund_mirror_research",
            lambda: api_fund_mirror_research(
                fund_code=target_benchmark, total_cap=total_cap, monthly=monthly,
                target_benchmark=target_benchmark, min_years=min_years,
                top_n=10, local_only=local_only,
            ),
        )
        if err:
            source_errors["fund_mirror_research"] = err
        fund_quarterly, err = _source_result(
            "fund_quarterly_mirror_research",
            lambda: api_fund_quarterly_mirror_research(
                fund_code=target_benchmark, total_cap=total_cap, monthly=monthly,
                target_benchmark=target_benchmark, min_years=min_years,
                local_only=local_only, include_samples=False,
            ),
        )
        if err:
            source_errors["fund_quarterly_mirror_research"] = err
        ndx_competition, err = _source_result(
            "ndx_competition", lambda: api_ndx_competition(refresh=False)
        )
        if err:
            source_errors["ndx_competition"] = err

    out = build_candidate_registry(
        preference_gate=preference_gate,
        tactical_ab=tactical_ab,
        param_scan=param_scan,
        injection_ab=injection_ab,
        preference_walkforward=preference_walkforward,
        preference_rebalance=preference_rebalance,
        fund_mirror=fund_mirror,
        fund_quarterly=fund_quarterly,
        ndx_competition=ndx_competition,
        source_errors=source_errors,
        market=market,
        include_heavy=include_heavy,
        as_of=date.today().isoformat(),
    )
    _research_candidate_cache[key] = out
    return out


def _broker_safe_position(safe_ticker, broker_by_ticker):
    """Return the real safe-leg position, never the legacy strategy-book shares."""
    return (broker_by_ticker or {}).get(str(safe_ticker).upper())


def _state_payload(pf):
    cfg = _cfg_for_portfolio(pf)
    latest_closed_date = _latest_closed_session_date(cfg)
    latest_closed_iso = (latest_closed_date or date.today()).isoformat()
    preview_date = date.today().isoformat()
    closes, price_meta = _latest_prices(cfg, include_safe=True)
    broker_account = _broker_account_payload(closes)
    broker_by_ticker = broker_account.get("by_ticker") or {}
    reported_closed_by_ticker = {
        str(row.get("ticker") or "").upper(): row
        for row in broker_account.get("reported_closed_positions") or []
        if row.get("ticker")
    }
    safe_px = None
    if getattr(cfg, "safe_leg", None) is not None:
        safe_px = closes.get(cfg.safe_leg.ticker) or _safe_daily_price(cfg)
    needs_daily_update = pf.last_run_date != latest_closed_iso
    clock_readiness = state_clock_readiness(pf, latest_closed_iso)
    preview = copy.deepcopy(pf)
    catchup_ledger: list[dict] = []
    catchup_preview = {
        "status": "CURRENT" if not needs_daily_update else "STATE_CATCHUP_BLOCKED",
        "snapshot_as_of": pf.last_run_date,
        "latest_session": latest_closed_iso,
        "session_count": 0,
        "day_index_before": int(pf.day_index),
        "day_index_after": int(pf.day_index),
        "immediate_buy_session_count": 0,
        "immediate_buy_count": 0,
    }
    if needs_daily_update and clock_readiness["safe_to_apply_daily_update"]:
        try:
            preview, catchup_ledger, catchup_preview = _state_session_catchup(
                pf, cfg, latest_closed_iso
            )
            catchup_preview["status"] = (
                "HISTORICAL_ACTION_RECONCILIATION_REQUIRED"
                if catchup_preview.get("immediate_buy_count") else
                "EXACT_SESSION_CATCHUP_PREVIEW_READY"
            )
        except StateCatchupError as exc:
            catchup_preview["error"] = str(exc)
    elif needs_daily_update:
        catchup_preview["error"] = "state chronology is not safe for session catch-up"
    # 被动状态页使用盘中 quote 估值，但不把盘中价用于 H/re-arm 预览，避免开盘阶段误刷新策略高点。
    signals = live.generate_signals(preview, closes, cfg, update_highs=False)
    market = _market_phase_payload(cfg, closes, price_meta)
    daily_bar_freshness = _daily_bar_freshness_payload(cfg, price_meta, market)
    # 防御层必须以独立券商快照为真实持仓来源；旧 state.safe_shares 仅保留审计。
    broker_safe_position = _broker_safe_position(pf.safe_ticker, broker_by_ticker)
    if broker_safe_position:
        preview.safe_shares = float(broker_safe_position["shares"])
    # 被动 GET 只预览（apply=False，不改持仓），执行走 /api/rebalance。
    dfn = (
        live.compute_defensive(preview, closes, safe_px, cfg, apply=False)
        if broker_safe_position else None
    )
    thr = cfg.portfolio.tiers.thresholds
    syms = []
    tot_mv = tot_res = tot_pending = tot_cost = tot_injected = 0.0
    real_mv = real_cost = 0.0
    book_only_mv = book_only_cost = 0.0
    for sig in signals:
        st = preview.symbols[sig.ticker]
        info = ((price_meta or {}).get("items") or {}).get(sig.ticker, {})
        tactical = _tactical_order(sig.ticker, st, sig.last_close, cfg, market, info)
        advice = _symbol_advice(sig, tactical)
        avg_price = (st.cost_basis / st.shares) if st.shares > 0 else None
        broker_position = broker_by_ticker.get(sig.ticker)
        is_real_position = broker_position is not None
        reported_closed_record = reported_closed_by_ticker.get(sig.ticker)
        is_reported_closed = bool(reported_closed_record) and not is_real_position
        real_shares = float(broker_position["shares"]) if broker_position else 0.0
        real_market_value = real_shares * sig.last_close if is_real_position else 0.0
        real_cost_basis = float(broker_position["cost_basis"]) if is_real_position else 0.0
        if is_real_position:
            real_mv += real_market_value
            real_cost += real_cost_basis
        else:
            book_only_mv += sig.market_value
            book_only_cost += st.cost_basis
        tot_mv += sig.market_value
        tot_res += sig.reserve_cash
        tot_pending += st.pending_core_cash
        tot_cost += st.cost_basis
        tot_injected += st.cum_injected
        tactical_fills = getattr(st, "tactical_fills", []) or []
        tactical_fill_amount = sum(float(f.amount) for f in tactical_fills)
        syms.append({
            **info,
            "ticker": sig.ticker, "last_close": round(sig.last_close, 2),
            "H": round(sig.H, 2), "drawdown": round(sig.drawdown, 4),
            "position_status": (
                "broker_real" if is_real_position else
                "broker_reported_closed" if is_reported_closed else
                "strategy_book_only"
            ),
            "is_real_position": is_real_position,
            "reported_closed": is_reported_closed,
            "reported_closed_as_of": (
                reported_closed_record.get("reported_as_of") if reported_closed_record else None
            ),
            "reported_closed_note": (
                reported_closed_record.get("note") if reported_closed_record else None
            ),
            "reserve": round(sig.reserve_cash, 0), "shares": round(sig.shares, 3),
            "book_shares": round(sig.shares, 3),
            "real_shares": round(real_shares, 3),
            "pending_core_cash": round(st.pending_core_cash, 0),
            "market_value": round(sig.market_value, 0), "cost_basis": round(st.cost_basis, 0),
            "book_market_value": round(sig.market_value, 0),
            "book_cost_basis": round(st.cost_basis, 0),
            "real_market_value": round(real_market_value, 0),
            "real_cost_basis": round(real_cost_basis, 0),
            "avg_price": round(avg_price, 4) if avg_price is not None else None,
            "book_avg_price": round(avg_price, 4) if avg_price is not None else None,
            "real_avg_price": round(float(broker_position["average_cost"]), 4) if is_real_position else None,
            "entry_date": st.entry_date,
            "entry_price": round(st.entry_price, 4) if st.entry_price else None,
            "cap_total": round(st.cap_total, 0), "cum_injected": round(st.cum_injected, 0),
            "frozen": st.frozen, "tier_armed": st.tier_armed, "thresholds": thr,
            "tactical_fill_count": len(tactical_fills),
            "tactical_fill_amount": round(tactical_fill_amount, 0),
            "tactical_fills": [
                {"date": f.date, "amount": round(f.amount, 0),
                 "fill_price": round(f.fill_price, 2), "limit_price": round(f.limit_price, 2),
                 "shares": round(f.shares, 3), "regime": f.regime, "note": f.note}
                for f in tactical_fills[-5:]
            ],
            "advice": advice,
            "tactical": tactical,
            "immediate_buys": [{"amount": round(a, 0), "price": round(p, 2), "reason": why}
                               for a, p, why in sig.immediate_buys],
            "ladder": [{"tier": e.tier_index, "threshold": e.threshold,
                        "limit": round(e.limit_price, 2), "amount": round(e.amount, 0),
                        "shares": round(e.shares, 3)} for e in sig.ladder],
            "pnl": round(sig.market_value - st.cost_basis, 0),
            "book_pnl": round(sig.market_value - st.cost_basis, 0),
            "real_pnl": round(real_market_value - real_cost_basis, 0),
        })
    strategy_tickers = set(preview.symbols)
    broker_only = [
        row for row in broker_account.get("positions", [])
        if row["ticker"] not in strategy_tickers and row["ticker"] != pf.safe_ticker
    ]
    real_mv += sum(float(row["market_value"]) for row in broker_only)
    real_cost += sum(float(row["cost_basis"]) for row in broker_only)
    broker_account["broker_only"] = broker_only
    broker_account["legacy_strategy_safe_leg"] = {
        "ticker": pf.safe_ticker,
        "state_shares": float(pf.safe_shares),
        "state_target_weight": float(pf.target_safe_weight),
        "broker_position_held": bool(broker_safe_position),
        "ignored_as_real_position": not bool(broker_safe_position),
    }
    broker_account.pop("by_ticker", None)
    safe_shares = float(broker_safe_position["shares"]) if broker_safe_position else 0.0
    safe_value = (safe_shares * safe_px) if safe_px else 0.0
    total_value = tot_mv + tot_res + tot_pending + safe_value
    safe = None
    if pf.target_safe_weight > 0 and safe_px and broker_safe_position:
        safe_info = ((price_meta or {}).get("items") or {}).get(pf.safe_ticker, {})
        safe = {"ticker": pf.safe_ticker, "shares": round(safe_shares, 3),
                "price": round(safe_px, 2), "value": round(safe_value, 0),
                "source": safe_info.get("source", "daily_close"),
                "mode": safe_info.get("mode", "daily_close"),
                "price_source": safe_info.get("source", "daily_close"),
                "quote_time": safe_info.get("quote_time", ""),
                "market_time": safe_info.get("market_time", ""),
                "target_weight": round(pf.target_safe_weight, 4),
                "weight": round(safe_value / total_value, 4) if total_value > 0 else 0.0,
                "exec_band": round(getattr(CFG.safe_leg, "exec_band", 0.0), 4)}
    defensive = _defensive_payload(dfn)
    execution = _execution_payload(syms, defensive, price_meta)
    execution_constraints = _execution_constraints_payload(cfg)
    config_health = _config_health_payload(cfg, safe, market, execution)
    position_gaps = _position_gap_payload(syms, cfg, CFG)
    account_readiness = _account_readiness_payload(syms, safe, position_gaps, broker_only)
    state_as_of = preview_date
    data_lag_days = (
        max(0, (date.today() - latest_closed_date).days)
        if latest_closed_date is not None else None
    )
    catchup_ready = catchup_preview["status"] in {
        "CURRENT", "EXACT_SESSION_CATCHUP_PREVIEW_READY",
    }
    state_freshness = {
        "status": (
            "STATE_CATCHUP_BLOCKED" if needs_daily_update and not catchup_ready else
            "DAILY_UPDATE_REQUIRED" if needs_daily_update else
            "CURRENT"
        ),
        "state_last_run_date": pf.last_run_date,
        "preview_date": state_as_of,
        "latest_closed_session_date": latest_closed_iso,
        "data_lag_days": data_lag_days,
        "needs_daily_update": needs_daily_update,
        "execution_is_preview": needs_daily_update,
        "state_clock_readiness": clock_readiness,
        "session_catchup": catchup_preview,
        "note": (
            "state 含有晚于状态时钟的持仓事件；日更新已安全阻断，须先完成真实账户对账。"
            if not clock_readiness["safe_to_apply_daily_update"]
            else f"逐会话状态预览失败：{catchup_preview.get('error')}。系统拒绝把缺失会话压成一次推进。"
            if needs_daily_update and not catchup_ready
            else f"最新完整风险腿日线为 {latest_closed_iso}；当前 {state_as_of} 仍可能处于美股盘中，"
            f"已逐一预览 {catchup_preview.get('session_count', 0)} 个完整会话；未经显式日更新不会写入 state。"
            if needs_daily_update
            else f"state 已推进到最新完整日线 {latest_closed_iso}；仍须按执行约束和用户确认落单。"
        ),
    }
    execution["state_freshness"] = state_freshness
    return {
        "initialized": True, "symbols": syms, "safe": safe, "market": market,
        "broker_account": broker_account,
        "price_meta": price_meta,
        "daily_bar_freshness": daily_bar_freshness,
        "execution_session_date": (
            daily_bar_freshness.get("quote_session_date") or latest_closed_iso
        ),
        "execution_constraints": execution_constraints,
        "as_of": state_as_of,
        "latest_closed_session_date": latest_closed_iso,
        "state_last_run_date": pf.last_run_date,
        "preview_day_index": preview.day_index,
        "needs_daily_update": needs_daily_update,
        "state_freshness": state_freshness,
        "state_catchup_preview": {
            **catchup_preview,
            "historical_action_sessions": [
                row["session_date"] for row in catchup_ledger if row.get("immediate_buys")
            ],
            "live_state_written": False,
            "orders_created": False,
        },
        "defensive": defensive,
        "execution": execution,
        "config_health": config_health,
        "account_readiness": account_readiness,
        "explanation": {
            "summary": execution.get("summary"),
            "market_state": {
                "label": (market or {}).get("label"),
                "regime": (market or {}).get("regime"),
                "rule": (market or {}).get("rule"),
            },
            "today_advice_impact": "今日建议只来自当前实盘配置；研究候选不改变动作。",
            "why_current_config": config_health.get("summary"),
            "research_boundary": "研究层必须先通过 A/B、多起点、点时验证、当前配置对照和今日 diff。",
        },
        "totals": {"market_value": round(tot_mv, 0), "reserve": round(tot_res, 0),
                   "pending_core_cash": round(tot_pending, 0),
                   "cost_basis": round(tot_cost, 0),
                   "contributed": round(tot_injected, 0),
                   "basket_value": round(tot_mv + tot_res + tot_pending, 0),
                   "safe_value": round(safe_value, 0),
                   "total_value": round(total_value, 0),
                   "pnl": round(tot_mv - tot_cost, 0),
                   "real_market_value": round(real_mv, 0),
                   "real_cost_basis": round(real_cost, 0),
                   "real_pnl": round(real_mv - real_cost, 0),
                   "real_total_value": round(real_mv + safe_value, 0),
                   "book_only_market_value": round(book_only_mv, 0),
                   "book_only_cost_basis": round(book_only_cost, 0),
                   "book_only_pnl": round(book_only_mv - book_only_cost, 0)},
    }


@app.get("/api/state")
def api_state():
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        caps = {s.ticker: s.cap_total for s in CFG.symbols}
        return {"initialized": False, "caps": caps,
                "core_ratio": CFG.portfolio.core_ratio,
                "execution_constraints": _execution_constraints_payload(CFG)}
    try:
        payload = _state_payload(pf)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    try:
        rec = advice_snapshot_log(_advice_snapshot_from_state(payload))
        payload["advice_snapshot"] = {
            "logged": True,
            "ts": rec.get("ts"),
            "snapshot_id": rec.get("snapshot_id"),
            "path": ADVICE_SNAPSHOT_PATH,
        }
    except Exception as e:
        logging.getLogger("us_ratchet").warning("建议快照写入失败: %s", e)
        payload["advice_snapshot"] = {"logged": False, "error": str(e)}
    return payload


def _parallel_deployment_readiness(
    payload: dict,
    *,
    requested_cash_usd: float,
    broker_confirmed: bool,
    account_fingerprint: str,
) -> dict:
    """Bind a review-ready draft to exact state, data, account and cash inputs."""
    blockers: list[dict] = []
    state_freshness = payload.get("state_freshness") or {}
    daily_bars = payload.get("daily_bar_freshness") or {}
    broker = payload.get("broker_account") or {}
    execution_session = str(payload.get("execution_session_date") or "")
    latest_closed = str(payload.get("latest_closed_session_date") or "")
    if state_freshness.get("status") != "CURRENT":
        blockers.append({
            "code": "STATE_CATCHUP_REQUIRED",
            "observed": state_freshness.get("status"),
        })
    bar_status = str(daily_bars.get("status") or "")
    common_bar = str(daily_bars.get("common_risk_daily_bar_date") or "")
    if bar_status == "DAILY_BARS_LAG_QUOTE_SESSION" or common_bar != latest_closed:
        blockers.append({
            "code": "DAILY_BARS_NOT_EXECUTION_READY",
            "observed": bar_status,
            "common_risk_daily_bar_date": common_bar,
            "latest_closed_session_date": latest_closed,
        })
    if not broker.get("available"):
        blockers.append({"code": "BROKER_SNAPSHOT_REQUIRED"})
    confirmed_session = str(broker.get("positions_confirmed_session_date") or "")
    if not execution_session or confirmed_session != execution_session:
        blockers.append({
            "code": "BROKER_POSITION_SESSION_CONFIRMATION_REQUIRED",
            "confirmed_session": confirmed_session,
            "execution_session": execution_session,
        })
    server_fingerprint = str(broker.get("account_fingerprint") or "")
    if not account_fingerprint or account_fingerprint != server_fingerprint:
        blockers.append({
            "code": "BROKER_ACCOUNT_FINGERPRINT_MISMATCH",
            "expected": server_fingerprint,
        })
    if not broker_confirmed:
        blockers.append({"code": "BROKER_CONFIRMATION_REQUIRED"})
    declared_cash = float(broker.get("deployable_cash_usd") or 0.0)
    requested_cash = float(requested_cash_usd or 0.0)
    if abs(requested_cash - declared_cash) > 0.01:
        blockers.append({
            "code": "DECLARED_CASH_MISMATCH",
            "declared_cash_usd": round(declared_cash, 2),
            "requested_cash_usd": round(requested_cash, 2),
        })
    cash_persistence = str(broker.get("deployable_cash_persistence") or "session")
    cash_session = str(broker.get("deployable_cash_session_date") or "")
    if cash_persistence != "until_user_update" and cash_session != execution_session:
        blockers.append({
            "code": "DEPLOYABLE_CASH_SESSION_CONFIRMATION_REQUIRED",
            "cash_session": cash_session,
            "execution_session": execution_session,
        })
    return {
        "status": "READY" if not blockers else "BLOCKED",
        "ready": not blockers,
        "execution_session_date": execution_session,
        "state_status": state_freshness.get("status"),
        "daily_bar_status": bar_status,
        "positions_confirmed_session_date": confirmed_session,
        "account_fingerprint": server_fingerprint,
        "declared_cash_usd": round(declared_cash, 2),
        "cash_persistence": cash_persistence,
        "blockers": blockers,
    }


@app.get("/api/parallel_deployment")
def api_parallel_deployment(
    cash_usd: float = 0.0,
    broker_confirmed: bool = False,
    account_fingerprint: str = "",
):
    """Build a read-only scheduled deployment draft independent of tactical signals."""
    try:
        requested_cash = float(cash_usd)
    except (TypeError, ValueError):
        requested_cash = float("nan")
    if not np.isfinite(requested_cash) or requested_cash < 0:
        return JSONResponse({
            "error": "cash_usd 必须是有限且不小于 0 的美元金额。",
            "status": "INVALID_CASH_INPUT",
            "promotion_allowed": False,
            "orders_created": False,
            "config_or_state_write": False,
        }, status_code=422)
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未初始化策略状态。"}, status_code=409)
    try:
        payload = _state_payload(pf)
        gap_model = (payload.get("account_readiness") or {}).get("position_gaps") or {}
        prices = {
            str(row.get("ticker") or "").upper(): float(
                row.get("price") or row.get("previous_close") or 0.0
            )
            for row in payload.get("symbols") or []
        }
        constraints = payload.get("execution_constraints") or {}
        broker = payload.get("broker_account") or {}
        deployment_readiness = _parallel_deployment_readiness(
            payload,
            requested_cash_usd=requested_cash,
            broker_confirmed=broker_confirmed,
            account_fingerprint=account_fingerprint,
        )
        reported_exits = [
            str(row.get("ticker") or "").upper()
            for row in broker.get("reported_closed_positions") or []
        ]
        result = build_parallel_deployment_plan(
            gap_model.get("rows") or [],
            prices,
            cash_usd=requested_cash,
            broker_confirmed=deployment_readiness["ready"],
            broker_snapshot_as_of=broker.get("snapshot_as_of"),
            broker_account_fingerprint=broker.get("account_fingerprint"),
            excluded_tickers=reported_exits,
            max_names=int(constraints.get("buy_plan_compact_target") or 4),
            lot_size=int(float(constraints.get("lot_size") or 1)),
            fee_bps=float(constraints.get("fee_bps") or 0.0),
            min_fee=float(constraints.get("min_fee") or 0.0),
        )
    except Exception as exc:
        return JSONResponse({"error": f"生成定期部署草案失败: {exc}"}, status_code=500)

    tactical_contexts = [
        (row.get("tactical") or {}).get("execution_context") or {}
        for row in payload.get("symbols") or []
    ]
    tactical_status_counts: dict[str, int] = {}
    for context in tactical_contexts:
        status = str(context.get("status") or "UNKNOWN")
        tactical_status_counts[status] = tactical_status_counts.get(status, 0) + 1
    tc = getattr(CFG, "tactical_orders", None)
    result["tactical_dead_zone_diagnostic"] = {
        "market_regime": (payload.get("market") or {}).get("regime"),
        "market_label": (payload.get("market") or {}).get("label"),
        "market_gate_enabled": bool(getattr(tc, "market_gate_enabled", False)),
        "bear_reserve_ratio": float(getattr(tc, "bear_reserve_ratio", 0.0) or 0.0),
        "tactical_status_counts": tactical_status_counts,
        "today_actionable_count": int((payload.get("execution") or {}).get("actionable_count") or 0),
        "interpretation": (
            "战术通道在 BEAR 下预算为零；定期部署通道不改写该信号，"
            "而是依据当前已批准目标缺口分期使用用户明确输入的现金。"
        ),
    }
    result["data_as_of"] = payload.get("as_of")
    result["execution_session_date"] = payload.get("execution_session_date")
    result["position_gap_totals"] = gap_model.get("totals") or {}
    result["declared_deployable_cash"] = {
        "amount_usd": float(broker.get("deployable_cash_usd") or 0.0),
        "execution_session_date": broker.get("deployable_cash_session_date"),
        "persistence": broker.get("deployable_cash_persistence", "session"),
        "note": broker.get("deployable_cash_note"),
        "used_only_when_request_cash_matches_user_input": True,
    }
    result["deployment_readiness"] = deployment_readiness
    result["cash_pool"] = {
        "schema": "FULL_INPUT_CASH_POOL_V2",
        "currency": "USD",
        "input_pool_usd": requested_cash,
        "input_pool_basis": "FULL_CURRENT_MANUAL_USD_INPUT",
        "reserve_added_usd": 0.0,
        "allocated_notional_usd": round(sum(
            float(row.get("notional") or 0.0) for row in result.get("lines") or []
        ), 2),
        "estimated_fees_usd": round(sum(
            float(row.get("estimated_fee") or 0.0) for row in result.get("lines") or []
        ), 2),
        "draft_cash_used_usd": result.get("cash_deployed", 0.0),
        "cash_unallocated_usd": result.get("cash_remaining", requested_cash),
        "target_scope": "CURRENT_APPROVED_ABSOLUTE_TARGET_GAP_ONLY",
        "capital_growth_status": "REQUESTED_NOT_IMPLEMENTED",
        "dynamic_optimizer_admitted": False,
        "posttrade_risk_validation": "NOT_AVAILABLE_IN_THIS_DRAFT",
        "execution_authorized": False,
    }
    pool = result["cash_pool"]
    # Legacy line components and total costs are rounded separately. Expose
    # that difference rather than silently changing the fee or allocator.
    pool["display_rounding_adjustment_usd"] = round(
        float(pool["draft_cash_used_usd"])
        - pool["allocated_notional_usd"] - pool["estimated_fees_usd"], 2,
    )
    pool["cash_reconciliation_adjustment_usd"] = (
        requested_cash - float(pool["draft_cash_used_usd"])
        - float(pool["cash_unallocated_usd"])
    )
    if not deployment_readiness["ready"] and result.get("lines"):
        result["status"] = "EXECUTION_READINESS_BLOCKED"
        result["promotion_allowed"] = False
        result["account_confirmation_note"] = (
            "状态时钟、日线、券商会话、账户指纹与声明现金尚未同时通过；"
            "草案仅供诊断，不能视为可执行。"
        )
    result["read_only_guards"] = {
        "advice_snapshot_logged": False,
        "orders_created": False,
        "config_or_state_write": False,
        "live_change_requires_separate_today_diff_and_user_approval": True,
    }
    return result


@app.get("/api/advice_snapshots")
def api_advice_snapshots(limit: int = 50):
    """Read recent generated advice snapshots; this endpoint never mutates state."""
    try:
        rows = load_advice_snapshots(limit=limit)
    except Exception as e:
        return JSONResponse({"error": f"读取建议快照失败: {e}"}, status_code=500)
    return {
        "path": ADVICE_SNAPSHOT_PATH,
        "storage": advice_snapshot_storage(),
        "count": len(rows),
        "limit": max(0, min(int(limit or 0), 500)),
        "items": rows,
        "note": "快照来自 /api/state 成功生成时的只读追加日志；不写 config.yaml 或 data/state.json。",
    }


@app.get("/static/selected_stock_charts.js")
def selected_stock_charts_script():
    return FileResponse(WEB.parent / "selected_stock_charts.js", media_type="application/javascript")


@app.get("/static/current_research_intraday_paper.js")
def current_research_intraday_paper_script():
    return FileResponse(WEB.parent / "current_research_intraday_paper.js", media_type="application/javascript")


@app.get("/static/current_research_paper.js")
def current_research_paper_script():
    return FileResponse(WEB.parent / "current_research_paper.js", media_type="application/javascript")


@app.get("/static/current_research_paper_performance.js")
def current_research_paper_performance_script():
    return FileResponse(WEB.parent / "current_research_paper_performance.js", media_type="application/javascript")


@app.get("/static/current_research_intraday.js")
def current_research_intraday_script():
    return FileResponse(WEB.parent / "current_research_intraday.js", media_type="application/javascript")


@app.get("/static/current_quantity_v2_intraday.js")
def current_quantity_v2_intraday_script():
    return FileResponse(WEB.parent / "current_quantity_v2_intraday.js", media_type="application/javascript")


@app.get('/static/strategy_account.js')
def strategy_account_script():
    return FileResponse(WEB.parent / 'strategy_account.js', media_type='application/javascript')

@app.get('/static/strategy_monthly_target_charts.js')
def strategy_monthly_target_charts_script():
    return FileResponse(WEB.parent / 'strategy_monthly_target_charts.js', media_type='application/javascript')

@app.get('/static/strategy_monthly_target.js')
def strategy_monthly_target_script():
    return FileResponse(WEB.parent / 'strategy_monthly_target.js', media_type='application/javascript')

@app.get('/static/strategy_daily_controller.js')
def strategy_daily_controller_script():
    return FileResponse(WEB.parent / 'strategy_daily_controller.js', media_type='application/javascript')

@app.get('/static/strategy_daily_mount.js')
def strategy_daily_mount_script():
    return FileResponse(WEB.parent / 'strategy_daily_mount.js', media_type='application/javascript')

@app.get('/static/strategy_capital_controller.js')
def strategy_capital_controller_script():
    return FileResponse(WEB.parent / 'strategy_capital_controller.js', media_type='application/javascript')

@app.get('/static/strategy_capital_mount.js')
def strategy_capital_mount_script():
    return FileResponse(WEB.parent / 'strategy_capital_mount.js', media_type='application/javascript')


@app.get("/static/current_quantity_v2_paper.js")
def current_quantity_v2_paper_script():
    return FileResponse(WEB.parent / "current_quantity_v2_paper.js", media_type="application/javascript")


@app.get('/static/automatic_simulation.js')
def automatic_simulation_script():
    return FileResponse(WEB.parent / 'automatic_simulation.js', media_type='application/javascript')


@app.get("/api/current_portfolio_preview")
def api_current_portfolio_preview():
    try:
        return read_current_portfolio_preview()
    except PreviewSourceError:
        return JSONResponse({"status": "UNAVAILABLE", "research_only": True,
                             "execution_blocked": True, "error": "已保存研究快照不可用或校验失败"}, status_code=503)


@app.get("/api/current_strategy_validation")
def api_current_strategy_validation():
    try:
        return read_current_strategy_validation()
    except StrategyValidationSourceError:
        return JSONResponse({"status": "UNAVAILABLE", "research_only": True,
                             "execution_blocked": True, "independent_oos": False,
                             "error": "已封存研究验证结果不可用或校验失败"}, status_code=503)


@app.get("/api/current_portfolio_preview/bars")
def api_current_portfolio_preview_bars(ticker: str, interval: str = "day", bars: int = 90):
    try:
        return read_current_portfolio_bars(ticker, interval, bars)
    except PreviewSourceError:
        return JSONResponse({"status": "UNAVAILABLE", "reason": "已保存 OHLC 来源不可用或校验失败"}, status_code=503)
    except ValueError as error:
        return JSONResponse({"status": "INVALID", "reason": str(error)}, status_code=400)


@app.get("/api/golden_pit_review")
def api_golden_pit_review(limit: int = 200, include_deep: bool = False):
    """Replay advice snapshots against later OHLC data; research-only."""
    try:
        return _golden_pit_review_payload(CFG, limit=limit, include_deep=include_deep)
    except Exception as e:
        return JSONResponse({"error": f"黄金坑复盘失败: {e}"}, status_code=500)


@app.get("/api/tactical_quality")
def api_tactical_quality():
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return {"initialized": False, "summary": {"verdict": "尚未建仓，暂无战术成交质量。"}}
    try:
        return {"initialized": True, **_tactical_quality_payload(pf, _cfg_for_portfolio(pf))}
    except Exception as e:
        return JSONResponse({"error": f"战术成交质量评估失败: {e}"}, status_code=500)


@app.post("/api/daily_update")
def api_daily_update():
    """显式落盘今日状态：推进交易日、处理到期分批、刷新 H/re-arm。"""
    return JSONResponse({
        "error": "直接 daily_update 写入已停用；请先生成 today diff/rollback，并使用一次性显式批准契约。",
        "approval_workflow": "scripts/state_daily_update_approval.py",
        "state_written": False,
        "orders_created": False,
    }, status_code=409)


@app.post("/api/init")
def api_init():
    if load_portfolio(resolve(STATE_PATH)) is not None:
        return JSONResponse({"error": "已存在状态，拒绝覆盖。如需重建请删除 data/state.json"}, status_code=400)
    try:
        closes = _latest_closes(CFG)
        safe_px = _safe_price(CFG)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    pf = live.init_portfolio(CFG, closes, safe_px)   # safe_px 提供 → 同时播种 SGOV 安全腿至目标比
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("init", {"caps": {t: s.cap_total for t, s in pf.symbols.items()},
                       "safe": {"ticker": pf.safe_ticker, "shares": pf.safe_shares,
                                "target_weight": pf.target_safe_weight}}, "前端建仓")
    return _state_payload(pf)


@app.post("/api/rebalance")
def api_rebalance():
    """显式执行防御层再平衡（把预览指令落到 state：改 shares/reserve/safe_shares）。
    被动 GET /api/state 只预览不执行；用户确认后调本接口落盘。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        closes = _latest_closes(cfg)
        safe_px = _safe_price(cfg)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    if safe_px is None or pf.target_safe_weight <= 0:
        return JSONResponse({"error": "未启用安全腿（config 无 safe_leg 或未播种）"}, status_code=400)
    latest_closed_date = _latest_closed_session_date(cfg)
    if latest_closed_date is None:
        return JSONResponse({"error": "没有可确认的完整风险腿日线，拒绝执行"}, status_code=409)
    live.advance_trading_day(pf, latest_closed_date.isoformat())
    dfn = live.compute_defensive(pf, closes, safe_px, cfg, apply=True)   # 真正落 state
    if dfn is None:
        return {"rebalanced": False, "msg": "当前在执行带内，无需再平衡"}
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("rebalance", {"direction": dfn.direction, "move": round(dfn.move, 0),
                            "safe_weight_before": round(dfn.safe_weight, 4)}, "前端执行防御层再平衡")
    payload = _state_payload(pf)
    payload["rebalanced"] = True
    payload["executed"] = _defensive_payload(dfn)
    return payload


@app.post("/api/inject")
def api_inject(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper()
    new_cap = float(body.get("new_cap", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker not in pf.symbols:
        return JSONResponse({"error": f"无此标的 {ticker}"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    closes = _latest_closes(cfg)
    backup_state(resolve(STATE_PATH))
    latest_closed_date = _latest_closed_session_date(cfg)
    if latest_closed_date is None:
        return JSONResponse({"error": "没有可确认的完整风险腿日线，拒绝执行"}, status_code=409)
    live.advance_trading_day(pf, latest_closed_date.isoformat())   # 注资前推进最新完整日线
    delta = live.apply_cap_change(pf, ticker, new_cap, closes[ticker], cfg)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("inject", {"ticker": ticker, "new_cap": new_cap, "delta": delta}, "前端加本金")
    payload = _state_payload(pf)
    payload["injected_delta"] = round(delta, 0)
    return payload


@app.post("/api/scale_up")
def api_scale_up(body: dict = Body(...)):
    """按 74:26 提高总持仓 $amount：(1-W)×amount 分摊注资进 8 名（lump），W×amount 加 SGOV。
    保持篮子内逆波动率权重 + 篮子:安全腿目标比精确不变。"""
    amount = float(body.get("amount", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if amount <= 0:
        return JSONResponse({"error": "金额必须 > 0"}, status_code=400)
    if pf.target_safe_weight <= 0:
        return JSONResponse({"error": "未启用安全腿，无法按 74:26 加仓（请用「加本金」逐只）"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        closes = _latest_closes(cfg)
        safe_px = _safe_price(cfg)
    except Exception as e:
        return JSONResponse({"error": f"取最新价失败: {e}"}, status_code=500)
    if safe_px is None:
        return JSONResponse({"error": "取安全腿价失败"}, status_code=500)
    backup_state(resolve(STATE_PATH))
    latest_closed_date = _latest_closed_session_date(cfg)
    if latest_closed_date is None:
        return JSONResponse({"error": "没有可确认的完整风险腿日线，拒绝执行"}, status_code=409)
    live.advance_trading_day(pf, latest_closed_date.isoformat())
    res = live.scale_up_portfolio(pf, amount, closes, safe_px, cfg)
    if res is None:
        return JSONResponse({"error": "加仓失败（金额或组合状态无效）"}, status_code=400)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("scale_up", {"total": amount, "basket": res.basket_portion,
                           "safe": res.safe_portion}, "前端按74:26提高总持仓")
    payload = _state_payload(pf)
    payload["scale_up"] = {
        "total": round(res.total, 0),
        "basket_portion": round(res.basket_portion, 0),
        "safe_portion": round(res.safe_portion, 0),
        "orders": [{"ticker": t, "delta": round(d, 0)} for t, d in res.orders],
        "safe_ticker": res.safe_ticker,
        "safe_added_shares": round(res.safe_added_shares, 3),
    }
    return payload


@app.post("/api/fill")
def api_fill(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper()
    tier = int(body.get("tier", -1))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    st = pf.symbols[ticker]
    cfg = _cfg_for_portfolio(pf)
    thr = cfg.portfolio.tiers.thresholds
    if not (0 <= tier < len(thr)) or not st.tier_armed[tier]:
        return JSONResponse({"error": "档位无效或未装填"}, status_code=400)
    limit = st.H * (1 + thr[tier])
    ladder = {e.tier_index: e for e in eng.compute_ladder(st, cfg)}
    amount = float(body.get("amount") or (ladder[tier].amount if tier in ladder else 0))
    price = float(body.get("price") or limit)
    amount = min(amount, st.reserve_cash)
    if amount <= 0 or price <= 0:
        return JSONResponse({"error": "金额/价格无效"}, status_code=400)
    sh = amount / price
    st.shares += sh; st.cost_basis += amount; st.reserve_cash -= amount
    st.tier_armed[tier] = False
    st.fires.append(TierFire(date=date.today().isoformat(), tier_index=tier, threshold=thr[tier],
                             limit_price=limit, fill_price=price, amount=amount, shares=sh))
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("fill", {"ticker": ticker, "tier": tier, "price": price, "amount": amount}, "前端回填成交")
    return _state_payload(pf)


@app.post("/api/tactical_fill")
def api_tactical_fill(body: dict = Body(...)):
    """回填战术固定限价成交：只写 tactical_fills，不关闭深跌棘轮档位。"""
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    cfg = _cfg_for_portfolio(pf)
    try:
        detail = _apply_tactical_fill(pf, body, cfg)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("tactical_fill", detail, "前端回填战术固定限价成交")
    payload = _state_payload(pf)
    payload["tactical_fill"] = detail
    return payload


@app.post("/api/add_symbol")
def api_add_symbol(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper().strip()
    buy_date = str(body.get("buy_date", "")).strip()
    try:
        buy_price = float(body.get("buy_price", 0))
        shares = float(body.get("shares", 0))
        reserve_cash = float(body.get("reserve_cash", 0) or 0)
    except (TypeError, ValueError):
        return JSONResponse({"error": "股数/买入价/储备金必须为数字"}, status_code=400)
    if not ticker:
        return JSONResponse({"error": "请填写 ticker"}, status_code=400)
    if buy_price <= 0 or shares <= 0 or reserve_cash < 0:
        return JSONResponse({"error": "股数和买入价必须 > 0，储备金不能为负"}, status_code=400)
    if not buy_date:
        return JSONResponse({"error": "请填写买入日期"}, status_code=400)
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker in pf.symbols:
        return JSONResponse({"error": f"{ticker} 已在当前持仓中，请用校准持仓或加本金"}, status_code=400)
    try:
        h, h_meta = _initial_high_since_buy(ticker, buy_date, buy_price)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    cost_basis = shares * buy_price
    cap_total = cost_basis + reserve_cash
    st = SymbolState(
        ticker=ticker,
        cap_total=cap_total,
        shares=shares,
        reserve_cash=reserve_cash,
        reserve_budget=reserve_cash,
        H=h,
        tier_armed=[True] * len(CFG.portfolio.tiers.thresholds),
        cost_basis=cost_basis,
        cum_injected=cap_total,
        entry_date=buy_date[:10],
        entry_price=buy_price,
    )
    backup_state(resolve(STATE_PATH))
    pf.symbols[ticker] = st
    pf.flows.append(CashFlow(date=buy_date[:10], amount=cap_total, note=f"新增持仓 {ticker}"))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("add_symbol",
              {"ticker": ticker, "buy_date": st.entry_date, "buy_price": buy_price,
               "shares": shares, "reserve_cash": reserve_cash,
               "cap_total": round(cap_total, 2), "H": round(h, 4), "H_meta": h_meta},
              "前端新增持仓")
    return _state_payload(pf)


@app.post("/api/remove_symbol")
def api_remove_symbol(body: dict = Body(...)):
    ticker = str(body.get("ticker", "")).upper().strip()
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    if ticker not in pf.symbols:
        return JSONResponse({"error": f"当前持仓中没有 {ticker}"}, status_code=400)
    if len(pf.symbols) <= 1:
        return JSONResponse({"error": "至少保留一只风险腿标的"}, status_code=400)
    old = pf.symbols[ticker].to_dict()
    backup_state(resolve(STATE_PATH))
    del pf.symbols[ticker]
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("remove_symbol", {"ticker": ticker, "old": old}, "前端删除持仓")
    return _state_payload(pf)


@app.post("/api/sync_trades")
def api_sync_trades(body: dict = Body(...)):
    """按券商已成交流水或持仓快照覆盖当前聚合持仓。

    mode=trades：同一 ticker 多笔成交会聚合为真实股数和加权均价；默认保留该标的已有储备金。
    mode=snapshot：CSV 至少包含 ticker/shares/avg_price 或 cost；新标的需要 date/buy_date。
    preview=true 时只返回差异，不落盘。replace/replace_text 用于 GOOGL=GOOG
    这种从旧 ticker 迁移到新 ticker 的场景。
    """
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None:
        return JSONResponse({"error": "尚未建仓"}, status_code=400)
    try:
        mode = str(body.get("mode", "trades") or "trades").lower()
        if mode in {"snapshot", "positions", "position"}:
            mode = "snapshot"
            rows = _snapshot_rows_from_body(body)
            grouped = _group_snapshot_rows(rows)
        else:
            mode = "trades"
            rows = _trade_rows_from_body(body)
            grouped = _group_trade_rows(rows)
        repl = _replacement_map_from_body(body)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    preserve_reserve = bool(body.get("preserve_reserve", True))
    reset_tiers = bool(body.get("reset_tiers", True))
    sync_cap = bool(body.get("sync_cap", True))
    old_by_new = {new: old for old, new in repl.items()}
    changed = []
    diff = _sync_diff(pf, grouped, repl, mode)
    if bool(body.get("preview", False)):
        return {
            "preview": True,
            "mode": mode,
            "rows": len(rows),
            "diff": diff,
            "blocked": [d for d in diff if d.get("needs_date")],
            "note": "预览不落盘；确认同步后才会备份并改写 data/state.json。",
        }
    blocked = [d for d in diff if d.get("needs_date")]
    if blocked:
        names = ", ".join(d["ticker"] for d in blocked)
        return JSONResponse({"error": f"持仓快照新增标的需要买入日期: {names}"}, status_code=400)

    try:
        for ticker, g in grouped.items():
            old_ticker = old_by_new.get(ticker)
            if old_ticker and old_ticker != ticker and ticker in pf.symbols:
                return JSONResponse({"error": f"{ticker} 已存在，无法同时从 {old_ticker} 替换"}, status_code=400)
            source_ticker = ticker if ticker in pf.symbols else old_ticker
            source = pf.symbols.get(source_ticker) if source_ticker else None
            reserve = (float(source.reserve_cash) + float(source.pending_core_cash)
                       if (source and preserve_reserve) else 0.0)
            buy_date = g.get("first_date") or (source.entry_date if source else None)
            if not buy_date:
                return JSONResponse({"error": f"{ticker} 缺少买入日期，无法重算 H"}, status_code=400)
            h, h_meta = _initial_high_since_buy(ticker, buy_date, float(g["avg_price"]))
            old_snapshot = source.to_dict() if source else None

            if source is None:
                st = SymbolState(ticker=ticker, cap_total=0.0)
            else:
                st = copy.deepcopy(source)
                st.ticker = ticker
            st.shares = float(g["shares"])
            st.cost_basis = float(g["cost"])
            st.entry_date = str(buy_date)[:10]
            st.entry_price = float(g["avg_price"])
            st.H = h
            st.reserve_cash = reserve
            st.reserve_budget = reserve
            st.pending_ladder = []
            st.pending_core_cash = 0.0
            if reset_tiers:
                st.tier_armed = [True] * len(CFG.portfolio.tiers.thresholds)
            if sync_cap:
                st.cum_injected = st.cost_basis + st.reserve_cash + st.pending_core_cash
                st.cap_total = st.cum_injected

            if old_ticker and old_ticker in pf.symbols and old_ticker != ticker:
                del pf.symbols[old_ticker]
            pf.symbols[ticker] = st
            changed.append({
                "ticker": ticker,
                "replaced_from": old_ticker if old_ticker != ticker else None,
                "shares": round(st.shares, 6),
                "avg_price": round(st.entry_price, 4),
                "cost_basis": round(st.cost_basis, 2),
                "reserve_cash": round(st.reserve_cash, 2),
                "cap_total": round(st.cap_total, 2),
                "H": round(st.H, 4),
                "H_meta": h_meta,
                "first_date": st.entry_date,
                "old": old_snapshot,
            })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    backup_state(resolve(STATE_PATH))
    _rebuild_flows_from_symbols(pf)
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("sync_trades", {"mode": mode, "rows": rows, "replace": repl, "changed": changed},
              "按券商导入同步当前持仓")
    payload = _state_payload(pf)
    payload["synced"] = changed
    payload["sync_diff"] = diff
    return payload


@app.post("/api/sync_broker_snapshot")
def api_sync_broker_snapshot(body: dict = Body(...)):
    with _broker_write_lock:
        return _sync_broker_snapshot_unlocked(body)


def _sync_broker_snapshot_unlocked(body: dict):
    """Replace only broker account truth; never mutate the strategy book."""
    if type(body.get("preview", False)) is not bool:
        return JSONResponse({"error": "preview 必须为布尔值"}, status_code=400)
    try:
        rows = _snapshot_rows_from_body(body)
        grouped = _group_snapshot_rows(rows)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    loaded_account = load_broker_account(resolve(BROKER_ACCOUNT_PATH))
    fingerprint = broker_account_fingerprint(loaded_account) if loaded_account else "BROKER_ACCOUNT_ABSENT"
    if not body.get("preview", False) and body.get("expected_account_fingerprint") != fingerprint:
        return JSONResponse({"error": "券商持仓已变化或尚未预览，请重新检查差异"}, status_code=409)
    current = loaded_account or {"positions": []}
    old = {row["ticker"]: row for row in current.get("positions") or []}
    diff = []
    for ticker, group in sorted(grouped.items()):
        previous = old.get(ticker)
        old_shares = float(previous["shares"]) if previous else 0.0
        old_avg = float(previous["average_cost"]) if previous else None
        diff.append({
            "ticker": ticker, "mode": "snapshot",
            "status": "update" if previous else "new",
            "replaced_from": None,
            "old_shares": old_shares, "new_shares": float(group["shares"]),
            "delta_shares": float(group["shares"]) - old_shares,
            "old_cost_basis": old_shares * old_avg if old_avg is not None else 0.0,
            "new_cost_basis": float(group["cost"]),
            "delta_cost_basis": float(group["cost"]) - (old_shares * old_avg if old_avg is not None else 0.0),
            "old_avg_price": old_avg, "new_avg_price": float(group["avg_price"]),
            "first_date": None, "needs_date": False,
        })
    for ticker, previous in sorted(old.items()):
        if ticker not in grouped:
            diff.append({
                "ticker": ticker, "mode": "snapshot", "status": "missing_in_import",
                "replaced_from": None, "old_shares": float(previous["shares"]),
                "new_shares": 0.0, "delta_shares": -float(previous["shares"]),
                "old_cost_basis": float(previous["shares"]) * float(previous["average_cost"]),
                "new_cost_basis": 0.0,
                "delta_cost_basis": -float(previous["shares"]) * float(previous["average_cost"]),
                "old_avg_price": float(previous["average_cost"]), "new_avg_price": None,
                "first_date": None, "needs_date": False,
            })
    if bool(body.get("preview", False)):
        return {
            "preview": True, "committed": False, "mode": "snapshot", "rows": len(rows), "diff": diff,
            "account_fingerprint": fingerprint,
            "blocked": [],
            "note": "预览不落盘；确认后仅替换 data/broker_positions.json，不修改策略 state。",
        }
    snapshot = {
        "schema_version": 1,
        "snapshot_as_of": str(body.get("snapshot_as_of") or date.today().isoformat())[:10],
        "snapshot_clock": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_note": str(body.get("source_note") or "前端券商持仓快照同步"),
        "deployable_cash_usd": float(
            body.get("deployable_cash_usd", current.get("deployable_cash_usd", 0.0)) or 0.0
        ),
        "deployable_cash_session_date": str(
            body.get(
                "deployable_cash_session_date",
                current.get("deployable_cash_session_date", ""),
            ) or ""
        )[:10],
        "deployable_cash_persistence": str(
            body.get(
                "deployable_cash_persistence",
                current.get("deployable_cash_persistence", "session"),
            ) or "session"
        ),
        "positions_confirmed_session_date": str(
            body.get(
                "positions_confirmed_session_date",
                current.get("positions_confirmed_session_date", ""),
            ) or ""
        )[:10],
        "deployable_cash_note": str(
            body.get("deployable_cash_note", current.get("deployable_cash_note", "")) or ""
        ),
        "reported_closed_positions": body.get(
            "reported_closed_positions", current.get("reported_closed_positions", [])
        ),
        "positions": [
            {
                "ticker": ticker, "shares": int(group["shares"]),
                "average_cost": float(group["avg_price"]),
                "observed_price": float(group["avg_price"]),
            }
            for ticker, group in sorted(grouped.items())
        ],
    }
    from core.broker_account import validate_broker_account
    snapshot = validate_broker_account(snapshot)
    committed_fingerprint = broker_account_fingerprint(snapshot)
    backup_broker_account(resolve(BROKER_ACCOUNT_PATH))
    save_broker_account(snapshot, resolve(BROKER_ACCOUNT_PATH))
    # The account is committed. Auxiliary failures cannot undo this replacement.
    warnings = []
    try:
        audit_log(
            "sync_broker_snapshot",
            {"snapshot_as_of": snapshot["snapshot_as_of"], "positions": snapshot["positions"], "diff": diff},
            "前端同步独立券商持仓；策略 state 未修改",
        )
    except Exception:
        logging.getLogger("us_ratchet").exception("Broker snapshot committed; audit failed")
        warnings.append({"code": "BROKER_AUDIT_FAILED", "message": "持仓已保存，但审计日志写入失败"})
    try:
        pf = load_portfolio(resolve(STATE_PATH))
        payload = _state_payload(pf) if pf is not None else {"initialized": False}
        if not isinstance(payload, dict):
            raise TypeError("state payload must be a mapping")
    except Exception:
        logging.getLogger("us_ratchet").exception("Broker snapshot committed; state refresh failed")
        warnings.append({"code": "BROKER_STATE_REFRESH_FAILED", "message": "持仓已保存，但页面数据刷新失败，请仅刷新页面"})
        payload = {}
    payload.update(committed=True, account_fingerprint=committed_fingerprint,
                   diff=diff, warnings=warnings, broker_snapshot_synced=snapshot["positions"], sync_diff=diff)
    return payload


@app.post("/api/update_broker_position")
def api_update_broker_position(body: dict = Body(...)):
    """Record one broker position without recalculating strategy state or orders."""
    with _broker_write_lock:
        try:
            current = load_broker_account(resolve(BROKER_ACCOUNT_PATH))
            if current is None:
                raise BrokerAccountError("请先导入一份券商持仓快照")
            fingerprint = broker_account_fingerprint(current)
            if body.get("account_fingerprint") != fingerprint:
                return JSONResponse({"error": "持仓已变化，请刷新后重新录入"}, status_code=409)
            if type(body.get("preview", False)) is not bool:
                raise BrokerAccountError("preview must be boolean")
            snapshot, difference = update_broker_position(current, body)
        except (BrokerAccountError, TypeError, ValueError) as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        unchanged = snapshot == current
        preview = body.get("preview", False)
        resulting_fingerprint = fingerprint if preview else broker_account_fingerprint(snapshot)
        warnings = []
        if not preview and not unchanged:
            backup_broker_account(resolve(BROKER_ACCOUNT_PATH))
            save_broker_account(snapshot, resolve(BROKER_ACCOUNT_PATH))
            try:
                audit_log("update_broker_position", {"diff": difference}, "用户录入券商当前总持仓")
            except Exception:
                logging.getLogger("us_ratchet").exception("Broker position committed; audit failed")
                warnings.append({"code": "BROKER_AUDIT_FAILED", "message": "持仓已保存，但审计日志写入失败"})
        return {
            "preview": preview, "unchanged": unchanged, "diff": [difference],
            "committed": not preview and not unchanged, "warnings": warnings,
            "account_fingerprint": resulting_fingerprint,
            "note": "只更新本标的券商持仓；现金和其它持仓的确认日期保持原值。",
        }


@app.post("/api/set_position")
def api_set_position(body: dict = Body(...)):
    """按真实聚合买入信息校准当前持仓。

    buy_date 用来重算自买入以来的 H；buy_price/shares 用来重算成本。
    sync_cap=True 时，把 cap_total/cum_injected 同步为 成本+当前储备，使回测面板跟随新本金权重。
    """
    ticker = str(body.get("ticker", "")).upper()
    buy_date = str(body.get("buy_date", "")).strip()
    sync_cap = bool(body.get("sync_cap", False))
    try:
        buy_price = float(body.get("buy_price", 0))
        shares = float(body.get("shares", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "股数/买入价必须为数字"}, status_code=400)
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    if not buy_date:
        return JSONResponse({"error": "请填写买入日期"}, status_code=400)
    if buy_price <= 0 or shares <= 0:
        return JSONResponse({"error": "股数和买入价必须 > 0"}, status_code=400)
    try:
        h, h_meta = _initial_high_since_buy(ticker, buy_date, buy_price)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    st = pf.symbols[ticker]
    old = {"shares": st.shares, "cost_basis": st.cost_basis, "H": st.H,
           "cap_total": st.cap_total, "cum_injected": st.cum_injected}
    st.shares = shares
    st.cost_basis = shares * buy_price
    st.H = h
    st.entry_date = buy_date[:10]
    st.entry_price = buy_price
    if not st.fires:
        st.reserve_budget = st.reserve_cash
    if sync_cap:
        st.cum_injected = st.cost_basis + st.reserve_cash + st.pending_core_cash
        st.cap_total = st.cum_injected

    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("set_position",
              {"ticker": ticker, "buy_date": st.entry_date, "buy_price": buy_price,
               "shares": shares, "sync_cap": sync_cap, "old": old,
               "new": {"cost_basis": round(st.cost_basis, 2), "H": round(st.H, 4),
                       "cap_total": round(st.cap_total, 2),
                       "cum_injected": round(st.cum_injected, 2)},
               "H_meta": h_meta},
              "前端校准当前持仓")
    payload = _state_payload(pf)
    payload["set_position"] = {"ticker": ticker, "H_meta": h_meta}
    return payload


@app.post("/api/set_cost")
def api_set_cost(body: dict = Body(...)):
    """修正某标的的成本：cost_basis = 当前股数 × 真实平均成本价。
    成本仅影响「盈亏」展示，不参与任何棘轮/防御层信号——纯显示修正，安全。"""
    ticker = str(body.get("ticker", "")).upper()
    avg_price = float(body.get("avg_price", 0))
    pf = load_portfolio(resolve(STATE_PATH))
    if pf is None or ticker not in pf.symbols:
        return JSONResponse({"error": "状态不存在或无此标的"}, status_code=400)
    if avg_price <= 0:
        return JSONResponse({"error": "平均成本价必须 > 0"}, status_code=400)
    st = pf.symbols[ticker]
    old_cost = st.cost_basis
    st.cost_basis = st.shares * avg_price
    st.entry_price = avg_price
    backup_state(resolve(STATE_PATH))
    save_portfolio(pf, resolve(STATE_PATH))
    _bt_cache.clear()
    audit_log("set_cost", {"ticker": ticker, "avg_price": avg_price,
                           "old_cost": round(old_cost, 2), "new_cost": round(st.cost_basis, 2)},
              "前端修正成本")
    return _state_payload(pf)


def main():
    import argparse
    import os
    import uvicorn
    ap = argparse.ArgumentParser(description="us_ratchet 服务")
    ap.add_argument("--host", default=os.environ.get("US_RATCHET_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("US_RATCHET_PORT", "8010")))
    args = ap.parse_args()
    print(f"\n>>> 打开浏览器访问 http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
