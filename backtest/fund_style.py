"""Fixed, read-only style attribution report for a target fund."""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date

import numpy as np
import pandas as pd

from backtest import metrics as M
from data.fetch import get_bars
from data.fund_holdings import get_fund_holding_history
from data.fund_style import get_fund_style_datasets
from data.funds import get_fund_nav
from data.versioning import data_version_payload


REGION_LABELS = {
    "US": "美国上市",
    "CN_A": "中国内地上市",
    "HK": "香港上市",
    "OTHER": "其他上市市场",
}
REPORT_SCHEMA_VERSION = 1
ATTRIBUTION_METHOD_VERSION = "native_daily_risk_weekly_relationship_v1"


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clean_close(series: pd.Series) -> pd.Series:
    out = pd.to_numeric(series, errors="coerce")
    out.index = pd.to_datetime(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index().dropna()
    return out[out > 0].astype(float)


def _drawdown_detail(close: pd.Series) -> dict:
    values = close.to_numpy(dtype=float)
    peaks = np.maximum.accumulate(values)
    drawdowns = 1.0 - values / peaks
    trough_i = int(np.argmax(drawdowns))
    peak_i = int(np.argmax(values[:trough_i + 1]))
    recovery_i = None
    for index in range(trough_i + 1, len(values)):
        if values[index] >= values[peak_i]:
            recovery_i = index
            break
    return {
        "max_drawdown": float(drawdowns[trough_i]),
        "peak_date": close.index[peak_i].strftime("%Y-%m-%d"),
        "trough_date": close.index[trough_i].strftime("%Y-%m-%d"),
        "recovery_date": (
            close.index[recovery_i].strftime("%Y-%m-%d")
            if recovery_i is not None else None
        ),
        "underwater_days": int((close.index[-1] - close.index[peak_i]).days)
        if recovery_i is None else int((close.index[recovery_i] - close.index[peak_i]).days),
    }


def _series_metrics(close: pd.Series) -> dict:
    clean = _clean_close(close)
    if len(clean) < 2:
        raise ValueError("price series has fewer than two observations")
    elapsed_days = int((clean.index[-1] - clean.index[0]).days)
    years = elapsed_days / 365.25
    total_return = float(clean.iloc[-1] / clean.iloc[0] - 1.0)
    cagr = float((clean.iloc[-1] / clean.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else None
    daily = clean.pct_change().replace([np.inf, -np.inf], np.nan).dropna().to_numpy(dtype=float)
    annual_vol = float(np.std(daily, ddof=1) * np.sqrt(252)) if len(daily) > 1 else None
    maxdd = M.max_drawdown(clean.to_numpy(dtype=float))
    return {
        "start": clean.index[0].strftime("%Y-%m-%d"),
        "end": clean.index[-1].strftime("%Y-%m-%d"),
        "observations": len(clean),
        "total_return": total_return,
        "cagr": cagr,
        "annual_volatility": annual_vol,
        "max_drawdown": maxdd,
        "sharpe_zero_rf": M.sharpe(daily),
        "calmar": (cagr / maxdd) if cagr is not None and maxdd > 0 else None,
        "drawdown": _drawdown_detail(clean),
    }


def _annual_returns(series_by_name: dict[str, pd.Series], start: pd.Timestamp,
                    end: pd.Timestamp) -> list[dict]:
    rows = []
    for year in range(int(start.year), int(end.year) + 1):
        item = {"year": year, "partial": year in {int(start.year), int(end.year)}}
        for name, series in series_by_name.items():
            segment = series[(series.index >= max(start, pd.Timestamp(f"{year}-01-01")))
                             & (series.index <= min(end, pd.Timestamp(f"{year}-12-31")))]
            item[name] = (
                float(segment.iloc[-1] / segment.iloc[0] - 1.0)
                if len(segment) >= 2 else None
            )
        rows.append(item)
    return rows


def _weekly_relationships(series_by_name: dict[str, pd.Series], fund_code: str,
                          start: pd.Timestamp, end: pd.Timestamp) -> dict:
    weekly = pd.concat({
        name: series[(series.index >= start) & (series.index <= end)].resample("W-FRI").last()
        for name, series in series_by_name.items()
    }, axis=1).dropna()
    returns = weekly.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    fund_returns = returns[fund_code]
    out = {}
    for name in series_by_name:
        if name == fund_code:
            continue
        pair = pd.concat([fund_returns, returns[name]], axis=1).dropna()
        pair.columns = ["fund", "benchmark"]
        corr = pair["fund"].corr(pair["benchmark"])
        variance = pair["benchmark"].var(ddof=1)
        beta = pair["fund"].cov(pair["benchmark"]) / variance if variance and variance > 0 else None
        alpha = (
            float((pair["fund"] - float(beta) * pair["benchmark"]).mean() * 52)
            if beta is not None else None
        )
        out[name] = {
            "weekly_observations": len(pair),
            "correlation": _finite(corr),
            "beta": _finite(beta),
            "r_squared_single_factor": _finite(corr * corr) if _finite(corr) is not None else None,
            "annualized_alpha_proxy": alpha,
        }
    return out


def _price_version(name: str, close: pd.Series, meta, *,
                   used_start=None, used_end=None) -> dict:
    normalized = _clean_close(close)
    if used_start is not None:
        normalized = normalized[normalized.index >= pd.Timestamp(used_start)]
    if used_end is not None:
        normalized = normalized[normalized.index <= pd.Timestamp(used_end)]
    if normalized.empty:
        raise ValueError(f"{name}: no normalized close data in used range")
    content = normalized.rename("Close").to_csv(index_label="Date", float_format="%.12g")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return {
        "version_id": f"normalized_close:{name}:{digest[:16]}",
        "dataset_type": "normalized_close_series",
        "dataset_key": name,
        "content_sha256": digest,
        "source": getattr(meta, "source", None),
        "retrieval_source": getattr(meta, "source", None),
        "cached": bool(getattr(meta, "cached", False)),
        "row_count": len(normalized),
        "data_start": normalized.index[0].strftime("%Y-%m-%d"),
        "data_end": normalized.index[-1].strftime("%Y-%m-%d"),
        "version_evidence": "sha256_of_normalized_close_series",
    }


def _asset_rows(frame: pd.DataFrame) -> tuple[list[dict], dict[str, float]]:
    rows = []
    equity_by_date = {}
    for record in frame.sort_values("report_date", ascending=False).to_dict("records"):
        stock = _finite(record.get("stock_weight")) or 0.0
        depositary = _finite(record.get("depositary_receipt_weight")) or 0.0
        equity = stock + depositary
        report_date = str(record["report_date"])
        equity_by_date[report_date] = equity
        rows.append({
            "report_date": report_date,
            "stock_weight": _finite(record.get("stock_weight")),
            "depositary_receipt_weight": _finite(record.get("depositary_receipt_weight")),
            "equity_weight": equity,
            "cash_weight": _finite(record.get("cash_weight")),
            "bond_weight": _finite(record.get("bond_weight")),
            "net_assets_cny_100m": _finite(record.get("net_assets_cny_100m")),
        })
    return rows, equity_by_date


def _industry_report(frame: pd.DataFrame, equity_by_date: dict[str, float]) -> dict:
    reports = []
    differences = []
    for report_date, group in frame.groupby("report_date", sort=False):
        ordered = group.sort_values("nav_weight", ascending=False)
        equity_weight = equity_by_date.get(str(report_date))
        total = float(ordered["nav_weight"].sum())
        if equity_weight is not None:
            differences.append(abs(total - equity_weight))
        sectors = [{
            "sector_code": str(row["sector_code"]),
            "sector": str(row["sector"]),
            "nav_weight": float(row["nav_weight"]),
            "equity_share": (
                float(row["nav_weight"] / equity_weight)
                if equity_weight and equity_weight > 0 else None
            ),
        } for _, row in ordered.iterrows()]
        normalized = [item["equity_share"] for item in sectors if item["equity_share"] is not None]
        reports.append({
            "report_date": str(report_date),
            "equity_weight": equity_weight,
            "industry_weight_sum": total,
            "sector_count": len(sectors),
            "sector_hhi": float(sum(value * value for value in normalized)),
            "top_sectors": sectors,
        })
    reports.sort(key=lambda item: item["report_date"], reverse=True)
    latest = reports[0]
    technology = [
        next((sector["nav_weight"] for sector in report["top_sectors"]
              if sector["sector"] == "信息技术"), 0.0)
        for report in reports
    ]
    max_difference = max(differences) if differences else None
    return {
        "standard": "GICS",
        "latest": latest,
        "reports": reports,
        "technology_weight": {
            "latest": technology[0] if technology else None,
            "median": float(np.median(technology)) if technology else None,
            "min": min(technology) if technology else None,
            "max": max(technology) if technology else None,
        },
        "asset_cross_check": {
            "max_abs_difference": max_difference,
            "tolerance": 0.005,
            "passed": bool(max_difference is not None and max_difference <= 0.005),
            "rule": "sum(industry NAV weights) ~= stock + depositary receipt weights",
        },
    }


def _region_and_concentration(history: pd.DataFrame,
                              equity_by_date: dict[str, float]) -> tuple[dict, dict]:
    regions = []
    concentration = []
    prior_top10 = None
    for report_date, group in history.groupby("report_date"):
        report_date = str(report_date)
        ranked = group.sort_values("rank")
        equity = equity_by_date.get(report_date)
        disclosed = float(ranked["nav_weight"].fillna(0).sum())
        coverage = disclosed / equity if equity and equity > 0 else None
        scope = "expanded_holdings" if coverage is not None and coverage >= 0.90 else "partial_holdings"
        nav_weights = {
            key: float(ranked.loc[ranked["asset_class"] == key, "nav_weight"].fillna(0).sum())
            for key in REGION_LABELS
        }
        regions.append({
            "report_date": report_date,
            "scope": scope,
            "reported_security_count": len(ranked),
            "disclosed_nav_weight": disclosed,
            "official_equity_weight": equity,
            "disclosure_coverage": coverage,
            "regions": [{
                "code": key,
                "label": REGION_LABELS[key],
                "nav_weight": nav_weights[key],
                "share_of_disclosed": nav_weights[key] / disclosed if disclosed > 0 else None,
                "share_of_equity": nav_weights[key] / equity if equity and equity > 0 else None,
            } for key in REGION_LABELS],
        })

        top10_frame = ranked[ranked["rank"] <= 10]
        top10_set = {str(value) for value in top10_frame["secid"].dropna()}
        churn = (
            1.0 - len(top10_set & prior_top10) / max(len(top10_set), len(prior_top10))
            if prior_top10 else None
        )
        normalized_weights = (
            ranked["nav_weight"].fillna(0).to_numpy(dtype=float) / disclosed
            if scope == "expanded_holdings" and disclosed > 0 else np.asarray([])
        )
        concentration.append({
            "report_date": report_date,
            "scope": scope,
            "reported_security_count": len(ranked),
            "top1_nav_weight": float(ranked.loc[ranked["rank"] <= 1, "nav_weight"].fillna(0).sum()),
            "top5_nav_weight": float(ranked.loc[ranked["rank"] <= 5, "nav_weight"].fillna(0).sum()),
            "top10_nav_weight": float(top10_frame["nav_weight"].fillna(0).sum()),
            "top10_name_churn_from_prior_report": churn,
            "disclosed_hhi": (
                float(np.sum(normalized_weights ** 2)) if len(normalized_weights) else None
            ),
        })
        prior_top10 = top10_set

    regions.sort(key=lambda item: item["report_date"], reverse=True)
    concentration.sort(key=lambda item: item["report_date"], reverse=True)
    expanded = [item for item in regions if item["scope"] == "expanded_holdings"]
    top10_values = [item["top10_nav_weight"] for item in concentration]
    churn_values = [
        item["top10_name_churn_from_prior_report"] for item in concentration
        if item["top10_name_churn_from_prior_report"] is not None
    ]
    return {
        "classification_basis": (
            "official QDII convention: security exchange; ADR/GDR by depositary listing exchange"
        ),
        "scope_rule": "expanded_holdings when disclosed/equity coverage >= 90%; otherwise partial",
        "latest_disclosure": regions[0] if regions else None,
        "latest_expanded": expanded[0] if expanded else None,
        "reports": regions,
    }, {
        "latest": concentration[0] if concentration else None,
        "reports": concentration,
        "top10_nav_weight_median": float(np.median(top10_values)) if top10_values else None,
        "top10_name_churn_median": float(np.median(churn_values)) if churn_values else None,
    }


def _turnover_report(frame: pd.DataFrame, concentration: dict) -> dict:
    rows = [{
        "report_date": str(record["report_date"]),
        "stock_turnover": float(record["stock_turnover"]),
    } for record in frame.sort_values("report_date", ascending=False).to_dict("records")]
    values = [row["stock_turnover"] for row in rows]
    latest_change = rows[0]["stock_turnover"] - rows[1]["stock_turnover"] if len(rows) > 1 else None
    return {
        "source_frequency": "semiannual_and_annual_report_dates",
        "latest": rows[0] if rows else None,
        "observations": rows,
        "median": float(np.median(values)) if values else None,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "latest_change": latest_change,
        "top10_name_churn_median": concentration.get("top10_name_churn_median"),
    }


def _interpretation(relative: dict, industry: dict, assets: list[dict], region: dict,
                    concentration: dict, turnover: dict) -> dict:
    latest_asset = assets[0]
    latest_industry = industry["latest"]
    top_sector = latest_industry["top_sectors"][0]
    expanded = region.get("latest_expanded") or {}
    region_text = ", ".join(
        f"{item['label']} {item['nav_weight']:.1%}"
        for item in expanded.get("regions", []) if item.get("nav_weight", 0) > 0
    )
    technology = industry.get("technology_weight") or {}
    smh = relative.get("SMH") or {}
    smh_evidence = (
        f"与 SMH 周频相关 {smh['correlation']:.2f}、beta {smh['beta']:.2f}"
        if smh.get("correlation") is not None and smh.get("beta") is not None
        else "当前报告未加载可比的 SMH 周频关系"
    )
    learn = [
        {
            "title": "学习风格包络，不复制证券名单",
            "evidence": (
                f"最新 {top_sector['sector']} 占净值 {top_sector['nav_weight']:.1%}；"
                f"最近完整区域披露为 {region_text or '无可用完整区域数据'}。"
            ),
            "application": "候选池按行业与上市市场暴露设置范围，再独立做点时选股。",
        },
        {
            "title": "把现金缓冲视为风格组成",
            "evidence": (
                f"最新权益仓位 {latest_asset['equity_weight']:.1%}，现金 {latest_asset['cash_weight']:.1%}。"
            ),
            "application": "比较候选时必须同时报告风险腿和防御腿，不能只比较满仓股票篮子。",
        },
        {
            "title": "允许集中，但必须把轮换成本计入",
            "evidence": (
                f"最新前十占净值 {concentration['latest']['top10_nav_weight']:.1%}；"
                f"源端最新换手率 {turnover['latest']['stock_turnover']:.1%}。"
            ),
            "application": "精简持仓可以研究，但需同时验证换手、交易成本和披露延迟。",
        },
        {
            "title": "把风格视为时变状态，不是固定指数替代",
            "evidence": (
                f"信息技术占净值历史为 {technology.get('min', 0):.1%}~"
                f"{technology.get('max', 0):.1%}；{smh_evidence}。"
            ),
            "application": "风格相似度应按报告期和市场阶段复核，不能固化为永久静态权重。",
        },
    ]
    cannot_copy = [
        {
            "title": "披露不是实时组合",
            "reason": "持仓报告存在延迟，且逐期真实发布时间尚不可核验；Q1/Q3 披露覆盖也可能不足。",
        },
        {
            "title": "US 子集不是完整基金",
            "reason": "基金同时包含中国内地、香港、美国上市资产以及现金；只镜像美股会改变区域、行业和回撤结构。",
        },
        {
            "title": "收益差不是纯选股 alpha",
            "reason": "基金人民币净值包含费用和汇率影响；ETF 当前使用拆股调整价格、未额外计入分红，收益差仅作价格行为代理。",
        },
        {
            "title": "归因报告不能替代策略准入",
            "reason": "行业相似或相关性高不代表可交易候选能通过多起点、点时和当前配置守门。",
        },
    ]
    return {"learn": learn, "cannot_copy": cannot_copy}


def run_fund_style_attribution(cfg, fund_code: str = "012922", *,
                               benchmark_tickers=("QQQ", "SMH", "SPY"),
                               start_year: int = 2022, end_year: int | None = None,
                               local_only: bool = True, refresh: bool = False) -> dict:
    code = str(fund_code or "").strip()
    if not (len(code) == 6 and code.isdigit()):
        raise ValueError(f"fund code must be 6 digits: {code!r}")
    final_year = int(date.today().year if end_year is None else end_year)
    first_year = int(start_year)

    nav, nav_meta = get_fund_nav(
        code,
        cfg,
        local_only=bool(local_only),
        refresh=bool(refresh),
    )
    holdings, holdings_meta = get_fund_holding_history(
        code,
        cfg,
        start_year=first_year,
        end_year=final_year,
        local_only=bool(local_only),
    )
    style_data, style_metas = get_fund_style_datasets(
        code,
        cfg,
        start_year=first_year,
        end_year=final_year,
        local_only=bool(local_only),
        refresh=bool(refresh),
    )

    price_cfg = copy.deepcopy(cfg)
    if local_only:
        price_cfg.data.fallback_chain = ["local_cache"]
    series_by_name = {code: _clean_close(nav["Close"])}
    price_metas = {}
    benchmark_errors = {}
    for raw in benchmark_tickers:
        ticker = str(raw).upper().strip()
        try:
            bars, meta = get_bars(ticker, price_cfg)
            close = _clean_close(bars["Close"])
            series_by_name[ticker] = close
            price_metas[ticker] = meta
        except Exception as exc:
            benchmark_errors[ticker] = str(exc)
    required = [str(value).upper().strip() for value in benchmark_tickers]
    missing = [ticker for ticker in required if ticker not in series_by_name]
    if missing:
        raise ValueError(f"missing required style benchmarks: {missing}; errors={benchmark_errors}")

    common = series_by_name[code].index
    for ticker in required:
        common = common.intersection(series_by_name[ticker].index)
    if len(common) < 2:
        raise ValueError("fund and style benchmarks have no sufficient common dates")
    common_start = pd.Timestamp(common.min())
    common_end = pd.Timestamp(common.max())
    benchmark_versions = {
        ticker: _price_version(
            ticker,
            series_by_name[ticker],
            price_metas[ticker],
            used_start=common_start,
            used_end=common_end,
        )
        for ticker in required
    }
    metrics = {
        name: _series_metrics(series[(series.index >= common_start) & (series.index <= common_end)])
        for name, series in series_by_name.items()
    }
    relationships = _weekly_relationships(series_by_name, code, common_start, common_end)
    relative = {}
    for ticker in required:
        fund_metrics = metrics[code]
        benchmark_metrics = metrics[ticker]
        relative[ticker] = {
            "cagr_gap": fund_metrics["cagr"] - benchmark_metrics["cagr"],
            "total_return_gap": fund_metrics["total_return"] - benchmark_metrics["total_return"],
            "volatility_gap": fund_metrics["annual_volatility"] - benchmark_metrics["annual_volatility"],
            "drawdown_relief": benchmark_metrics["max_drawdown"] - fund_metrics["max_drawdown"],
            **relationships[ticker],
        }

    assets, equity_by_date = _asset_rows(style_data["asset_allocation"])
    industry = _industry_report(style_data["industry"], equity_by_date)
    region, concentration = _region_and_concentration(holdings, equity_by_date)
    turnover = _turnover_report(style_data["turnover"], concentration)
    interpretation = _interpretation(relative, industry, assets, region, concentration, turnover)

    data_manifest = {
        "schema_version": 1,
        "fund_nav": data_version_payload(
            nav_meta,
            used_start=common_start.strftime("%Y-%m-%d"),
            used_end=common_end.strftime("%Y-%m-%d"),
        ),
        "holdings_history": data_version_payload(
            holdings_meta,
            used_report_start=str(holdings["report_date"].min()),
            used_report_end=str(holdings["report_date"].max()),
            used_report_count=int(holdings["report_date"].nunique()),
        ),
        "industry": data_version_payload(style_metas["industry"]),
        "asset_allocation": data_version_payload(style_metas["asset_allocation"]),
        "turnover": data_version_payload(style_metas["turnover"]),
        "benchmarks": benchmark_versions,
    }
    version_ids = {
        "fund_nav": data_manifest["fund_nav"].get("version_id"),
        "holdings_history": data_manifest["holdings_history"].get("version_id"),
        "industry": data_manifest["industry"].get("version_id"),
        "asset_allocation": data_manifest["asset_allocation"].get("version_id"),
        "turnover": data_manifest["turnover"].get("version_id"),
        **{f"benchmark_{ticker}": version["version_id"] for ticker, version in benchmark_versions.items()},
    }
    report_identity = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "attribution_method_version": ATTRIBUTION_METHOD_VERSION,
        "data_versions": version_ids,
    }
    report_digest = hashlib.sha256(
        json.dumps(report_identity, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()
    report_id = f"fund_style_attribution:{code}:{report_digest[:16]}"

    return {
        "summary": {
            "research_only": True,
            "does_change_today_advice": False,
            "fund_code": code,
            "report_id": report_id,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "attribution_method_version": ATTRIBUTION_METHOD_VERSION,
            "as_of": common_end.strftime("%Y-%m-%d"),
            "common_range": [common_start.strftime("%Y-%m-%d"), common_end.strftime("%Y-%m-%d")],
            "benchmark_tickers": required,
            "data_versions": version_ids,
            "note": "固定风格归因报告；只描述历史风险收益和披露暴露，不写 config/state。",
        },
        "performance": {
            "return_basis": {
                "fund": "CNY accumulated NAV, net of published fund fees",
                "benchmarks": "normalized split-adjusted close price; distributions not added",
                "currency": "fund CNY NAV versus USD-listed ETF prices; no FX conversion",
                "risk_metrics": "native daily observations inside common date range",
                "relationship_metrics": "weekly Friday-last returns to reduce calendar mismatch",
            },
            "metrics": metrics,
            "relative_to_fund": relative,
            "annual_returns": _annual_returns(series_by_name, common_start, common_end),
            "benchmark_errors": benchmark_errors,
        },
        "asset_allocation": {
            "latest": assets[0],
            "observations": assets,
            "cash_weight": {
                "median": float(np.median([item["cash_weight"] for item in assets if item["cash_weight"] is not None])),
                "min": min(item["cash_weight"] for item in assets if item["cash_weight"] is not None),
                "max": max(item["cash_weight"] for item in assets if item["cash_weight"] is not None),
            },
        },
        "industry": industry,
        "region": region,
        "concentration": concentration,
        "turnover": turnover,
        "interpretation": interpretation,
        "data_quality": {
            "industry_asset_cross_check": industry["asset_cross_check"],
            "region_is_listing_market_not_issuer_revenue_country": True,
            "partial_region_reports_are_not_extrapolated": True,
            "actual_disclosure_publication_dates_available": False,
        },
        "data_manifest": data_manifest,
    }
