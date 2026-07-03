"""数据 provider：每个负责抓单只标的日线并归一化为统一 schema。

主源 eastmoney（前复权）→ 备援 sina（不复权）→ local_cache。
yahoo/stooq 类保留（换环境可用），但不在默认链里——国内访问被限流。

统一 schema 由 fetch._normalize 处理；provider 只管取回 DataFrame。
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from core.helpers import proxy_env
from data import cn_source

log = logging.getLogger("us_ratchet")


class ProviderError(Exception):
    pass


class BaseProvider:
    name = "base"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        raise NotImplementedError


def _rows_to_df(rows: list, ticker: str, src: str) -> pd.DataFrame:
    if not rows:
        raise ProviderError(f"{src} 返回空数据: {ticker}")
    df = pd.DataFrame(rows)
    df = df.rename(columns={"date": "Date", "open": "Open", "high": "High",
                            "low": "Low", "close": "Close", "volume": "Volume"})
    return df


class EastmoneyProvider(BaseProvider):
    """东财 push2his 日K，带复权（fqt 来自 config，默认 1=前复权）。主源。"""
    name = "eastmoney"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        beg = (cfg.data.start_date or "1990-01-01").replace("-", "")
        end = (cfg.data.end_date.replace("-", "") if cfg.data.end_date else "20500101")
        fqt = getattr(cfg.data, "fqt", 1)
        rows = cn_source.fetch_eastmoney_kline(ticker, fqt=fqt, beg=beg, end=end)
        return _rows_to_df(rows, ticker, "eastmoney")


class SinaProvider(BaseProvider):
    """新浪美股日K。原始数据**不复权**，本 provider 自动做前复权（拆股检测），
    使其等价于东财 fqt=1。东财历史在部分网络被掐死时，这是可靠的主源。"""
    name = "sina"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        rows = cn_source.fetch_sina_daily(ticker)
        if not rows:
            raise ProviderError(f"sina 返回空数据: {ticker}")
        # 自动前复权
        if getattr(cfg.data, "auto_split_adjust", True):
            tol = getattr(cfg.data, "split_detect_tol", 0.06)
            rows, splits = cn_source.split_adjust(rows, tol)
            if splits:
                desc = ", ".join(f"{d}≈{k}" for d, k in splits)
                log.info("%s 新浪自复权：检测到拆股 %s", ticker, desc)
        df = _rows_to_df(rows, ticker, "sina")
        if cfg.data.start_date:
            df = df[df["Date"] >= cfg.data.start_date]
        if cfg.data.end_date:
            df = df[df["Date"] <= cfg.data.end_date]
        if df.empty:
            raise ProviderError(f"sina 截断后为空: {ticker}")
        return df


class LocalCacheProvider(BaseProvider):
    name = "local_cache"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        path = cfg.cache_dir / f"{ticker}.csv"
        if not path.exists():
            raise ProviderError(f"本地缓存不存在: {path}")
        df = pd.read_csv(path)
        if df.empty:
            raise ProviderError(f"本地缓存为空: {path}")
        return df


class YFinanceProvider(BaseProvider):
    """保留：换到无限流环境可用。不在默认链。"""
    name = "yfinance"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as e:
            raise ProviderError("未安装 yfinance") from e
        d = cfg.data
        with proxy_env(d.proxy):
            df = yf.download(ticker, start=d.start_date, end=d.end_date,
                             auto_adjust=d.auto_adjust, progress=False, threads=False)
        if df is None or df.empty:
            raise ProviderError(f"yfinance 返回空数据: {ticker}")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df


class StooqProvider(BaseProvider):
    """保留：换环境可用。不在默认链。"""
    name = "stooq"
    BASE = "https://stooq.com/q/d/l/"

    def fetch(self, ticker: str, cfg) -> pd.DataFrame:
        import requests
        d = cfg.data
        params = {"s": f"{ticker.lower()}.us", "i": "d"}
        if d.start_date:
            params["d1"] = d.start_date.replace("-", "")
        if d.end_date:
            params["d2"] = d.end_date.replace("-", "")
        with proxy_env(d.proxy):
            resp = requests.get(self.BASE, params=params, timeout=30)
        if resp.status_code != 200 or not resp.text.strip():
            raise ProviderError(f"stooq HTTP {resp.status_code}: {ticker}")
        text = resp.text.strip()
        if text.lower().startswith("<") or "no data" in text.lower():
            raise ProviderError(f"stooq 无数据: {ticker}")
        df = pd.read_csv(io.StringIO(text))
        if df.empty or "Date" not in df.columns:
            raise ProviderError(f"stooq 解析失败: {ticker}")
        return df


REGISTRY = {
    EastmoneyProvider.name: EastmoneyProvider,
    SinaProvider.name: SinaProvider,
    LocalCacheProvider.name: LocalCacheProvider,
    YFinanceProvider.name: YFinanceProvider,
    StooqProvider.name: StooqProvider,
}
