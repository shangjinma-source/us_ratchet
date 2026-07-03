"""抓取编排：多源降级链 + 归一化 + 复权校验 + 写穿缓存。

get_bars(ticker, cfg) 按 fallback_chain 依次尝试，第一个成功者返回；
非缓存源成功后写穿本地缓存（Windows 原子写）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text
from data.providers import REGISTRY, ProviderError
from data import cn_source

log = logging.getLogger("us_ratchet")

CANON_COLS = ["Open", "High", "Low", "Close", "Volume"]


class DataError(Exception):
    pass


@dataclass
class FetchMeta:
    ticker: str
    source: str
    rows: int
    start: str
    end: str
    errors: dict = field(default_factory=dict)      # provider -> 失败原因
    suspicious_jumps: list = field(default_factory=list)  # [(date, ratio), ...] 疑似未复权
    cached: bool = False


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """归一化为统一 schema：DatetimeIndex(Date, 升序) + 五列。"""
    df = df.copy()
    # 索引归一
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")
    else:
        df.index = pd.to_datetime(df.index)
        df.index.name = "Date"
    # 列名归一（首字母大写匹配）
    rename = {c: c.capitalize() for c in df.columns}
    df = df.rename(columns=rename)
    missing = [c for c in CANON_COLS if c not in df.columns]
    if missing:
        # Volume 缺失可补 0；价列缺失则失败
        if missing == ["Volume"]:
            df["Volume"] = 0
        else:
            raise DataError(f"缺少必要列: {missing}（现有 {list(df.columns)}）")
    df = df[CANON_COLS].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def _basic_validate(df: pd.DataFrame, ticker: str) -> None:
    if df.empty:
        raise DataError(f"{ticker}: 归一化后为空")
    if not df.index.is_monotonic_increasing:
        raise DataError(f"{ticker}: 日期非升序")
    price = df[["Open", "High", "Low", "Close"]]
    if price.isna().any().any():
        raise DataError(f"{ticker}: 价列含 NaN")
    if (price <= 0).any().any():
        raise DataError(f"{ticker}: 价列含非正值")


def _find_suspicious_jumps(df: pd.DataFrame, jump_pct: float) -> list:
    """相邻收盘价跳变超过阈值 → 疑似未复权的拆股（复权后不应有此跳变）。
    返回 (date, signed_pct)；保留符号以便区分下跌拆股 vs 真实上涨。"""
    pct = df["Close"] / df["Close"].shift(1) - 1
    hits = pct[pct.abs() > jump_pct]
    return [(d.strftime("%Y-%m-%d"), float(p)) for d, p in hits.items()]


def _write_cache(ticker: str, df: pd.DataFrame, cfg) -> None:
    path: Path = cfg.cache_dir / f"{ticker}.csv"
    out = df.copy()
    out.index = out.index.strftime("%Y-%m-%d")
    atomic_write_text(path, out.to_csv(index_label="Date"))
    log.info("写穿缓存: %s (%d 行)", path, len(df))


def get_bars(ticker: str, cfg) -> tuple[pd.DataFrame, FetchMeta]:
    errors: dict = {}
    for name in cfg.data.fallback_chain:
        provider = REGISTRY[name]()
        try:
            raw = provider.fetch(ticker, cfg)
            df = _normalize(raw)
            _basic_validate(df, ticker)
            jumps = _find_suspicious_jumps(df, cfg.data.validation.split_continuity_jump_pct)
            meta = FetchMeta(
                ticker=ticker, source=name, rows=len(df),
                start=df.index[0].strftime("%Y-%m-%d"),
                end=df.index[-1].strftime("%Y-%m-%d"),
                errors=errors, suspicious_jumps=jumps,
                cached=(name == "local_cache"),
            )
            if name != "local_cache":
                _write_cache(ticker, df, cfg)
            log.info("%s ← %s | %s..%s | %d 行 | 疑似跳变 %d 处",
                     ticker, name, meta.start, meta.end, meta.rows, len(jumps))
            # 复权后仍出现"干净拆股比例"的跳变 → 说明有拆股没被复权处理（异常）
            tol = getattr(cfg.data, "split_detect_tol", 0.06)
            unadj = [(d, p) for d, p in jumps if cn_source.is_clean_split_jump(1 + p, tol)]
            if unadj:
                log.warning("⚠ %s 检出 %d 处疑似未复权拆股跳变（应已复权，请核对）: %s",
                            ticker, len(unadj), unadj[:3])
            return df, meta
        except (ProviderError, DataError) as e:
            errors[name] = repr(e)
            log.warning("%s 源 %s 失败: %s", ticker, name, e)
        except Exception as e:  # 网络/解析等未预期错误也降级
            errors[name] = repr(e)
            log.warning("%s 源 %s 异常降级: %s", ticker, name, e)
    raise DataError(f"{ticker}: 所有数据源失败 -> {errors}")


def cross_provider_check(ticker: str, cfg, a: str = "eastmoney", b: str = "sina") -> dict:
    """跨源复权一致性：对比两源重叠日期的收盘价相对偏差中位数。
    用于校验复权口径，不进热路径。"""
    out = {"ticker": ticker, "ok": False, "reason": "", "median_div": None, "max_div": None}
    try:
        da = _normalize(REGISTRY[a]().fetch(ticker, cfg))
        db = _normalize(REGISTRY[b]().fetch(ticker, cfg))
    except Exception as e:
        out["reason"] = f"取数失败: {e}"
        return out
    joined = da[["Close"]].join(db[["Close"]], lsuffix=f"_{a}", rsuffix=f"_{b}", how="inner")
    if joined.empty:
        out["reason"] = "无重叠日期"
        return out
    div = (joined[f"Close_{a}"] / joined[f"Close_{b}"] - 1).abs()
    out["median_div"] = float(div.median())
    out["max_div"] = float(div.max())
    tol = cfg.data.validation.max_provider_divergence_pct
    out["ok"] = out["median_div"] <= tol
    out["reason"] = ("一致" if out["ok"]
                     else f"中位偏差 {out['median_div']:.2%} > 容忍 {tol:.2%}（复权口径可能不同）")
    return out
