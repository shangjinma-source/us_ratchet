"""Versioned nominal trade-price cache for whole-lot execution research."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.helpers import atomic_write_text
from data.ndx_price_basis import (
    RAW_PRICE_BASIS,
    RECOGNIZED_SOURCE_MODES,
    normalize_unadjusted_bars,
)
from data.versioning import file_sha256, manifest_path, write_dataset_manifest


EXECUTION_PRICE_POLICY_ID = "ndx_whole_lot_execution_price_v1"
EXECUTION_PRICE_DATASET_TYPE = "ndx_whole_lot_execution_daily_bars"


class NdxExecutionPriceError(ValueError):
    pass


def execution_cache_path(directory: str | Path, ticker: str) -> Path:
    return Path(directory) / "raw" / f"{str(ticker).upper().strip()}.csv"


def write_execution_cache(
    directory: str | Path,
    ticker: str,
    bars: pd.DataFrame,
    *,
    source_mode: str,
    requested_begin: str,
    requested_end: str,
) -> dict:
    if source_mode not in RECOGNIZED_SOURCE_MODES:
        raise NdxExecutionPriceError(f"unrecognized source mode: {source_mode}")
    symbol = str(ticker).upper().strip()
    normalized = normalize_unadjusted_bars(bars, ticker=symbol)
    path = execution_cache_path(directory, symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = normalized.copy()
    output.index = output.index.strftime("%Y-%m-%d")
    output.index.name = "Date"
    atomic_write_text(path, output.to_csv(index=True))
    source = RECOGNIZED_SOURCE_MODES[source_mode]
    return write_dataset_manifest(
        path,
        dataset_type=EXECUTION_PRICE_DATASET_TYPE,
        dataset_key=symbol,
        source=source["source"],
        source_locator=source["source_locator"],
        row_count=len(normalized),
        data_start=normalized.index.min().strftime("%Y-%m-%d"),
        data_end=normalized.index.max().strftime("%Y-%m-%d"),
        extra={
            "policy_id": EXECUTION_PRICE_POLICY_ID,
            "price_basis": RAW_PRICE_BASIS,
            "corporate_action_adjustment": "none",
            "source_request_mode": source_mode,
            "source_semantics_evidence": source["evidence_strength"],
            "requested_begin": pd.Timestamp(requested_begin).strftime("%Y-%m-%d"),
            "requested_end": pd.Timestamp(requested_end).strftime("%Y-%m-%d"),
            "whole_lot_execution_use_only": True,
            "valuation_use_only": False,
            "return_usage_allowed": False,
            "selection_date_or_later_rows_included": False,
            "return_engine_cache_modified": False,
        },
    )


def load_verified_execution_cache(
    directory: str | Path,
    ticker: str,
    *,
    requested_end: str,
) -> tuple[pd.DataFrame, dict]:
    symbol = str(ticker).upper().strip()
    path = execution_cache_path(directory, symbol)
    sidecar = manifest_path(path)
    if not path.is_file() or not sidecar.is_file():
        raise NdxExecutionPriceError(f"{symbol}: execution cache is missing")
    manifest = json.loads(sidecar.read_text(encoding="utf-8"))
    requested_cutoff = pd.Timestamp(requested_end).normalize()
    manifest_cutoff = pd.to_datetime(manifest.get("requested_end"), errors="coerce")
    checks = {
        "dataset_type": manifest.get("dataset_type") == EXECUTION_PRICE_DATASET_TYPE,
        "dataset_key": manifest.get("dataset_key") == symbol,
        "policy_id": manifest.get("policy_id") == EXECUTION_PRICE_POLICY_ID,
        "price_basis": manifest.get("price_basis") == RAW_PRICE_BASIS,
        "unadjusted": manifest.get("corporate_action_adjustment") == "none",
        "purpose": manifest.get("whole_lot_execution_use_only") is True,
        "not_valuation": manifest.get("valuation_use_only") is False,
        "not_returns": manifest.get("return_usage_allowed") is False,
        "no_future_rows": manifest.get("selection_date_or_later_rows_included") is False,
        "requested_end_covered": pd.notna(manifest_cutoff) and manifest_cutoff >= requested_cutoff,
        "content_sha256": manifest.get("content_sha256") == file_sha256(path),
    }
    failed = sorted(key for key, passed in checks.items() if not passed)
    if failed:
        raise NdxExecutionPriceError(f"{symbol}: execution cache failed checks {failed}")
    frame = normalize_unadjusted_bars(pd.read_csv(path), ticker=symbol)
    if len(frame) != int(manifest.get("row_count") or -1):
        raise NdxExecutionPriceError(f"{symbol}: execution cache row count changed")
    clipped = frame.loc[frame.index <= requested_cutoff].copy()
    if clipped.empty or clipped.index.max() > requested_cutoff:
        raise NdxExecutionPriceError(f"{symbol}: execution cache cutoff failed")
    return clipped, manifest


__all__ = [
    "EXECUTION_PRICE_DATASET_TYPE",
    "EXECUTION_PRICE_POLICY_ID",
    "NdxExecutionPriceError",
    "execution_cache_path",
    "load_verified_execution_cache",
    "write_execution_cache",
]
