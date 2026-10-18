"""Versioned unadjusted price evidence for point-in-time NDX valuation research.

The strategy return engine deliberately uses split-adjusted OHLC.  Valuation
research needs a different price basis: the nominal traded close that can be
multiplied by a point-in-time reported share count.  This module keeps the two
datasets separate and never rewrites the return-engine cache.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from core.helpers import atomic_write_text
from data import cn_source
from data.versioning import file_sha256, manifest_path, write_dataset_manifest


RAW_PRICE_CACHE_POLICY_ID = "ndx_unadjusted_price_basis_v1"
PRICE_BASIS_POLICY_ID = "ndx_unadjusted_price_basis_v2"
RAW_PRICE_DATASET_TYPE = "ndx_unadjusted_daily_bars"
RAW_PRICE_BASIS = "unadjusted_nominal_trade_price"
RECOGNIZED_SOURCE_MODES = {
    "eastmoney_fqt_0": {
        "source": "eastmoney",
        "source_locator": "push2his.eastmoney.com fqt=0",
        "evidence_strength": "explicit_unadjusted_request_parameter",
    },
    "sina_raw_daily": {
        "source": "sina",
        "source_locator": "US_MinKService.getDailyK raw response",
        "evidence_strength": "provider_raw_response_plus_split_crosscheck",
    },
}


class NdxPriceBasisError(ValueError):
    pass


@dataclass(frozen=True)
class PriceBasisPolicy:
    maximum_price_age_days: int = 7
    split_ratio_tolerance: float = 0.08
    share_split_lookback_days: int = 240
    minimum_overlap_rows: int = 1

    def validate(self) -> None:
        if self.maximum_price_age_days < 0:
            raise NdxPriceBasisError("maximum_price_age_days must be >= 0")
        if not 0 < self.split_ratio_tolerance < 0.5:
            raise NdxPriceBasisError("split_ratio_tolerance must be in (0, 0.5)")
        if self.share_split_lookback_days < 1:
            raise NdxPriceBasisError("share_split_lookback_days must be >= 1")
        if self.minimum_overlap_rows < 1:
            raise NdxPriceBasisError("minimum_overlap_rows must be >= 1")


def _date_token(value: str | pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _query_token(value: str | pd.Timestamp) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def normalize_unadjusted_bars(
    rows: pd.DataFrame | Iterable[Mapping[str, object]],
    *,
    ticker: str,
) -> pd.DataFrame:
    """Normalize and validate raw nominal OHLC without changing price values."""
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if frame.empty:
        raise NdxPriceBasisError(f"{ticker}: unadjusted source returned no rows")
    rename = {
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    frame = frame.rename(columns=rename)
    if "Date" not in frame.columns:
        if isinstance(frame.index, pd.DatetimeIndex) or frame.index.name == "Date":
            frame = frame.reset_index()
        else:
            raise NdxPriceBasisError(f"{ticker}: raw bars lack Date")
    required = ["Date", "Open", "High", "Low", "Close"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise NdxPriceBasisError(f"{ticker}: raw bars lack columns {missing}")
    if "Volume" not in frame.columns:
        frame["Volume"] = 0.0
    frame = frame[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    if frame["Date"].isna().any():
        raise NdxPriceBasisError(f"{ticker}: raw bars contain invalid dates")
    for column in ("Open", "High", "Low", "Close", "Volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    price = frame[["Open", "High", "Low", "Close"]]
    if not np.isfinite(price.to_numpy(dtype=float)).all():
        raise NdxPriceBasisError(f"{ticker}: raw price contains non-finite values")
    if (price <= 0).any().any():
        raise NdxPriceBasisError(f"{ticker}: raw price contains non-positive values")
    if (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1)).any():
        raise NdxPriceBasisError(f"{ticker}: raw high violates OHLC ordering")
    if (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1)).any():
        raise NdxPriceBasisError(f"{ticker}: raw low violates OHLC ordering")
    if (frame["Volume"].fillna(0) < 0).any():
        raise NdxPriceBasisError(f"{ticker}: raw volume contains negative values")
    frame = frame.sort_values("Date", kind="stable")
    if frame["Date"].duplicated().any():
        raise NdxPriceBasisError(f"{ticker}: raw bars contain duplicate dates")
    return frame.set_index("Date")


def fetch_unadjusted_bars(
    ticker: str,
    *,
    begin: str | pd.Timestamp,
    end: str | pd.Timestamp,
    source_chain: Iterable[str] = ("eastmoney", "sina"),
) -> tuple[pd.DataFrame, str, dict[str, str]]:
    """Fetch raw bars from a source path that explicitly skips adjustment."""
    symbol = str(ticker).upper().strip()
    begin_date = _date_token(begin)
    end_date = _date_token(end)
    errors: dict[str, str] = {}
    for raw_source in source_chain:
        source = str(raw_source).lower().strip()
        try:
            if source == "eastmoney":
                rows = cn_source.fetch_eastmoney_kline(
                    symbol,
                    fqt=0,
                    beg=_query_token(begin_date),
                    end=_query_token(end_date),
                )
                mode = "eastmoney_fqt_0"
            elif source == "sina":
                rows = cn_source.fetch_sina_daily(symbol)
                mode = "sina_raw_daily"
            else:
                raise NdxPriceBasisError(f"unsupported raw source: {source}")
            source_frame = pd.DataFrame(rows)
            date_column = "Date" if "Date" in source_frame.columns else "date"
            if date_column in source_frame.columns:
                parsed_dates = pd.to_datetime(source_frame[date_column], errors="coerce")
                source_frame = source_frame.loc[
                    parsed_dates.between(
                        pd.Timestamp(begin_date),
                        pd.Timestamp(end_date),
                        inclusive="both",
                    )
                ].copy()
            frame = normalize_unadjusted_bars(source_frame, ticker=symbol)
            frame = frame.loc[
                (frame.index >= pd.Timestamp(begin_date))
                & (frame.index <= pd.Timestamp(end_date))
            ]
            if frame.empty:
                raise NdxPriceBasisError(
                    f"{symbol}: {source} has no rows in {begin_date}..{end_date}"
                )
            return frame, mode, errors
        except Exception as exc:
            errors[source] = f"{type(exc).__name__}: {exc}"
    raise NdxPriceBasisError(f"{symbol}: every unadjusted source failed: {errors}")


def raw_cache_path(directory: str | Path, ticker: str) -> Path:
    return Path(directory) / "raw" / f"{str(ticker).upper().strip()}.csv"


def write_unadjusted_cache(
    directory: str | Path,
    ticker: str,
    bars: pd.DataFrame,
    *,
    source_mode: str,
    requested_begin: str,
    requested_end: str,
) -> dict:
    if source_mode not in RECOGNIZED_SOURCE_MODES:
        raise NdxPriceBasisError(f"unrecognized source mode: {source_mode}")
    symbol = str(ticker).upper().strip()
    normalized = normalize_unadjusted_bars(bars, ticker=symbol)
    path = raw_cache_path(directory, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = normalized.copy()
    output.index = output.index.strftime("%Y-%m-%d")
    output.index.name = "Date"
    atomic_write_text(path, output.to_csv(index=True))
    source = RECOGNIZED_SOURCE_MODES[source_mode]
    return write_dataset_manifest(
        path,
        dataset_type=RAW_PRICE_DATASET_TYPE,
        dataset_key=symbol,
        source=source["source"],
        source_locator=source["source_locator"],
        row_count=len(normalized),
        data_start=normalized.index.min().strftime("%Y-%m-%d"),
        data_end=normalized.index.max().strftime("%Y-%m-%d"),
        extra={
            "policy_id": RAW_PRICE_CACHE_POLICY_ID,
            "price_basis": RAW_PRICE_BASIS,
            "corporate_action_adjustment": "none",
            "source_request_mode": source_mode,
            "source_semantics_evidence": source["evidence_strength"],
            "requested_begin": _date_token(requested_begin),
            "requested_end": _date_token(requested_end),
            "valuation_use_only": True,
            "return_engine_cache_modified": False,
        },
    )


def load_verified_unadjusted_cache(
    directory: str | Path,
    ticker: str,
    *,
    requested_begin: str | None = None,
    requested_end: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    symbol = str(ticker).upper().strip()
    path = raw_cache_path(directory, symbol)
    sidecar = manifest_path(path)
    if not path.exists() or not sidecar.exists():
        raise NdxPriceBasisError(f"{symbol}: versioned raw cache is missing")
    try:
        manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxPriceBasisError(f"{symbol}: raw cache manifest is invalid") from exc
    checks = {
        "dataset_type": manifest.get("dataset_type") == RAW_PRICE_DATASET_TYPE,
        "dataset_key": manifest.get("dataset_key") == symbol,
        "policy_id": manifest.get("policy_id") == RAW_PRICE_CACHE_POLICY_ID,
        "price_basis": manifest.get("price_basis") == RAW_PRICE_BASIS,
        "corporate_action_adjustment": (
            manifest.get("corporate_action_adjustment") == "none"
        ),
        "source_request_mode": (
            manifest.get("source_request_mode") in RECOGNIZED_SOURCE_MODES
        ),
        "content_sha256": manifest.get("content_sha256") == file_sha256(path),
    }
    if requested_begin is not None:
        checks["requested_begin"] = manifest.get("requested_begin") == _date_token(
            requested_begin
        )
    if requested_end is not None:
        checks["requested_end"] = manifest.get("requested_end") == _date_token(
            requested_end
        )
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise NdxPriceBasisError(
            f"{symbol}: raw cache manifest failed checks {failed}"
        )
    frame = normalize_unadjusted_bars(pd.read_csv(path), ticker=symbol)
    if int(manifest.get("row_count") or -1) != len(frame):
        raise NdxPriceBasisError(f"{symbol}: raw cache row count changed")
    return frame, manifest


def point_in_time_raw_price_rows(
    plan: pd.DataFrame,
    raw_series: Mapping[str, pd.DataFrame],
    manifests: Mapping[str, Mapping[str, object]],
    *,
    adjusted_series: Mapping[str, pd.DataFrame] | None = None,
    policy: PriceBasisPolicy | None = None,
) -> pd.DataFrame:
    selected_policy = policy or PriceBasisPolicy()
    selected_policy.validate()
    required = {"selection_date", "ticker"}
    if not required.issubset(plan.columns):
        raise NdxPriceBasisError(f"price plan lacks {sorted(required - set(plan.columns))}")
    adjusted = adjusted_series or {}
    optional = [
        "price_ticker",
        "ticker_alias_applied",
        "ticker_lifecycle_rule_id",
        "ticker_lifecycle_status",
        "security_cusip",
        "ticker_lifecycle_evidence_url",
    ]
    columns = ["selection_date", "ticker"] + [
        column for column in optional if column in plan.columns
    ]
    output = []
    for row in plan[columns].itertuples(index=False):
        selection_date = pd.Timestamp(row.selection_date).normalize()
        ticker = str(row.ticker).upper().strip()
        price_ticker = str(getattr(row, "price_ticker", ticker)).upper().strip()
        frame = raw_series.get(price_ticker)
        manifest = dict(manifests.get(price_ticker) or {})
        item = {
            "selection_date": selection_date.strftime("%Y-%m-%d"),
            "ticker": ticker,
            "price_ticker": price_ticker,
            "ticker_alias_applied": bool(
                getattr(row, "ticker_alias_applied", price_ticker != ticker)
            ),
            "ticker_lifecycle_rule_id": str(
                getattr(row, "ticker_lifecycle_rule_id", "") or ""
            ),
            "ticker_lifecycle_status": str(
                getattr(row, "ticker_lifecycle_status", "") or ""
            ),
            "security_cusip": str(getattr(row, "security_cusip", "") or ""),
            "ticker_lifecycle_evidence_url": str(
                getattr(row, "ticker_lifecycle_evidence_url", "") or ""
            ),
            "price_status": "missing",
            "price_ready": False,
            "price_basis_ready": False,
            "price": np.nan,
            "price_date": "",
            "price_age_days": np.nan,
            "price_future_data_guard_passed": True,
            "historical_price_basis": RAW_PRICE_BASIS,
            "source": manifest.get("source"),
            "source_request_mode": manifest.get("source_request_mode"),
            "source_semantics_evidence": manifest.get("source_semantics_evidence"),
            "raw_price_version_id": manifest.get("version_id"),
            "raw_price_sha256": manifest.get("content_sha256"),
            "adjusted_close_same_date": np.nan,
            "adjusted_to_raw_ratio": np.nan,
            "adjusted_alignment_status": "not_checked",
            "adjusted_reference_ticker": "",
        }
        if frame is None or frame.empty:
            output.append(item)
            continue
        close = pd.to_numeric(frame.loc[frame.index < selection_date, "Close"], errors="coerce")
        close = close[np.isfinite(close) & (close > 0)]
        if close.empty:
            item["price_status"] = "no_strict_prior_price"
            output.append(item)
            continue
        price_date = pd.Timestamp(close.index[-1]).normalize()
        price = float(close.iloc[-1])
        age_days = int((selection_date - price_date).days)
        future_guard = bool(price_date < selection_date)
        basis_ready = (
            manifest.get("price_basis") == RAW_PRICE_BASIS
            and manifest.get("corporate_action_adjustment") == "none"
            and manifest.get("source_request_mode") in RECOGNIZED_SOURCE_MODES
        )
        status = "ready" if age_days <= selected_policy.maximum_price_age_days else "stale"
        item.update({
            "price_status": status,
            "price_ready": bool(status == "ready" and future_guard and basis_ready),
            "price_basis_ready": bool(basis_ready),
            "price": price,
            "price_date": price_date.strftime("%Y-%m-%d"),
            "price_age_days": age_days,
            "price_future_data_guard_passed": future_guard,
        })
        adjusted_ticker = price_ticker if price_ticker in adjusted else ticker
        adjusted_frame = adjusted.get(adjusted_ticker)
        item["adjusted_reference_ticker"] = (
            adjusted_ticker if adjusted_frame is not None else ""
        )
        if adjusted_frame is not None and price_date in adjusted_frame.index:
            adjusted_close = float(adjusted_frame.at[price_date, "Close"])
            if np.isfinite(adjusted_close) and adjusted_close > 0:
                item["adjusted_close_same_date"] = adjusted_close
                item["adjusted_to_raw_ratio"] = adjusted_close / price
                item["adjusted_alignment_status"] = "same_date_ratio_available"
            else:
                item["adjusted_alignment_status"] = "same_date_adjusted_invalid"
        elif adjusted_frame is not None:
            item["adjusted_alignment_status"] = "same_date_adjusted_missing"
        output.append(item)
    rows = pd.DataFrame(output)
    if rows.duplicated(["selection_date", "ticker"]).any():
        raise NdxPriceBasisError("point-in-time raw price rows are not unique")
    return rows.sort_values(["selection_date", "ticker"], kind="stable").reset_index(
        drop=True
    )


def raw_split_events(
    raw_series: Mapping[str, pd.DataFrame],
    *,
    policy: PriceBasisPolicy | None = None,
) -> pd.DataFrame:
    selected_policy = policy or PriceBasisPolicy()
    selected_policy.validate()
    output = []
    for ticker, frame in sorted(raw_series.items()):
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna().sort_index()
        for position in range(1, len(close)):
            prior = float(close.iloc[position - 1])
            current = float(close.iloc[position])
            if prior <= 0 or current <= 0:
                continue
            event = cn_source.match_split_event(
                current / prior,
                selected_policy.split_ratio_tolerance,
            )
            if event is None:
                continue
            output.append({
                "ticker": str(ticker).upper(),
                "prior_date": pd.Timestamp(close.index[position - 1]).strftime("%Y-%m-%d"),
                "event_date": pd.Timestamp(close.index[position]).strftime("%Y-%m-%d"),
                "prior_close": prior,
                "close": current,
                "raw_price_ratio": current / prior,
                "split_factor": int(event["factor"]),
                "split_kind": event["kind"],
            })
    columns = [
        "ticker", "prior_date", "event_date", "prior_close", "close",
        "raw_price_ratio", "split_factor", "split_kind",
    ]
    if not output:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(output, columns=columns).sort_values(
        ["ticker", "event_date"], kind="stable"
    ).reset_index(drop=True)


def crosscheck_share_split_events(
    share_events: pd.DataFrame,
    price_events: pd.DataFrame,
    *,
    policy: PriceBasisPolicy | None = None,
) -> pd.DataFrame:
    selected_policy = policy or PriceBasisPolicy()
    selected_policy.validate()
    required = {
        "ticker", "prior_selection_date", "selection_date", "nearest_split_ratio",
        "split_like",
    }
    if not required.issubset(share_events.columns):
        raise NdxPriceBasisError(
            f"share events lack {sorted(required - set(share_events.columns))}"
        )
    events = price_events.copy()
    if not events.empty:
        events["event_date"] = pd.to_datetime(events["event_date"])
    output = []
    for row in share_events.itertuples(index=False):
        ticker = str(row.ticker).upper()
        selection_date = pd.Timestamp(row.selection_date).normalize()
        lookback = selection_date - pd.Timedelta(
            days=selected_policy.share_split_lookback_days
        )
        candidates = events[
            events["ticker"].eq(ticker)
            & events["event_date"].gt(lookback)
            & events["event_date"].le(selection_date)
        ] if not events.empty else events
        expected = float(row.nearest_split_ratio)
        matched = None
        error = np.nan
        if not candidates.empty:
            ranked = candidates.assign(
                factor_error=(candidates["split_factor"].astype(float) - expected).abs()
                / expected
            ).sort_values(["factor_error", "event_date"], kind="stable")
            matched = ranked.iloc[0]
            error = float(matched["factor_error"])
        split_like = bool(row.split_like)
        if not split_like:
            status = "share_change_not_integer_split"
        elif matched is None:
            status = "expected_raw_split_missing"
        elif error <= selected_policy.split_ratio_tolerance:
            status = "matched"
        else:
            status = "raw_split_factor_mismatch"
        output.append({
            "ticker": ticker,
            "prior_selection_date": _date_token(row.prior_selection_date),
            "selection_date": _date_token(row.selection_date),
            "share_split_like": split_like,
            "expected_split_factor": expected,
            "matched_raw_event_date": (
                pd.Timestamp(matched["event_date"]).strftime("%Y-%m-%d")
                if matched is not None else ""
            ),
            "matched_raw_split_factor": (
                float(matched["split_factor"]) if matched is not None else np.nan
            ),
            "factor_relative_error": error,
            "crosscheck_status": status,
        })
    return pd.DataFrame(output).sort_values(
        ["ticker", "selection_date"], kind="stable"
    ).reset_index(drop=True)
