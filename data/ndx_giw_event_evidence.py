"""Normalize user-supplied official Nasdaq GIW corporate-action exports.

The importer preserves candidate evidence rows but never decides that a row is
an NDX addition/removal and never changes the exact-event registry.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


class NdxGiwEventEvidenceError(ValueError):
    pass


REQUIRED_FIELDS = ("effective_date", "reason", "issue_symbol", "index_symbol")
OPTIONAL_FIELDS = (
    "index_name", "description", "new_issue_symbol", "company_name",
    "new_company_name", "comments", "current_sedol", "new_sedol",
)


def _key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


ALIASES = {
    "effective_date": {"effectivedate", "effective"},
    "reason": {"reason", "actionreason"},
    "issue_symbol": {"issuesymbol", "symbol", "oldsymbol"},
    "index_symbol": {"indexsymbol", "index"},
    "index_name": {"indexname"},
    "description": {"description"},
    "new_issue_symbol": {"newissuesymbol", "newsymbol"},
    "company_name": {"companyname", "oldname"},
    "new_company_name": {"newcompanyname", "newname"},
    "comments": {"comments", "comment"},
    "current_sedol": {"currentsedol", "oldsedol"},
    "new_sedol": {"newsedol"},
}


def _read_export(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        raise NdxGiwEventEvidenceError(f"GIW export is missing: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path, dtype=str, keep_default_na=False)
        if suffix in {".csv", ".txt"}:
            return pd.read_csv(path, dtype=str, keep_default_na=False)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise NdxGiwEventEvidenceError(f"cannot parse GIW export: {path}") from exc
    raise NdxGiwEventEvidenceError("GIW export must be CSV, TXT, XLSX, or XLS")


def _column_map(frame: pd.DataFrame) -> dict[str, str]:
    keyed = {_key(column): str(column) for column in frame.columns}
    result = {}
    for field, aliases in ALIASES.items():
        matches = [keyed[key] for key in aliases if key in keyed]
        if len(matches) > 1:
            raise NdxGiwEventEvidenceError(
                f"ambiguous GIW columns for {field}: {matches}"
            )
        if matches:
            result[field] = matches[0]
    missing = [field for field in REQUIRED_FIELDS if field not in result]
    if missing:
        raise NdxGiwEventEvidenceError(
            f"GIW export missing required fields: {missing}"
        )
    return result


def _date_text(value: object) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"/Date\((\d+)\)/", text)
    if match:
        parsed = pd.to_datetime(int(match.group(1)), unit="ms", utc=True)
    else:
        parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        raise NdxGiwEventEvidenceError(f"invalid EffectiveDate: {value!r}")
    return pd.Timestamp(parsed).date().isoformat()


def normalize_giw_export(
    path: Path,
    *,
    index_symbol: str = "NDX",
    ticker: str = "GRAL",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return exact GIW rows for an index/ticker without interpreting actions."""
    source = _read_export(path)
    if source.empty:
        raise NdxGiwEventEvidenceError("GIW export is empty")
    mapping = _column_map(source)
    normalized = pd.DataFrame(index=source.index)
    for field in (*REQUIRED_FIELDS, *OPTIONAL_FIELDS):
        column = mapping.get(field)
        normalized[field] = source[column].astype(str).str.strip() if column else ""
    normalized["effective_date"] = normalized["effective_date"].map(_date_text)
    for field in ("issue_symbol", "new_issue_symbol", "index_symbol"):
        normalized[field] = normalized[field].str.upper()
    normalized.insert(0, "source_row_number", source.index.astype(int) + 2)
    target_index = str(index_symbol).strip().upper()
    target_ticker = str(ticker).strip().upper()
    selected = normalized.loc[
        normalized["index_symbol"].eq(target_index)
        & (
            normalized["issue_symbol"].eq(target_ticker)
            | normalized["new_issue_symbol"].eq(target_ticker)
        )
    ].copy()
    if selected.empty:
        raise NdxGiwEventEvidenceError(
            f"no {target_index}/{target_ticker} corporate-action rows in GIW export"
        )
    selected = selected.sort_values(
        ["effective_date", "source_row_number"], kind="stable"
    ).reset_index(drop=True)
    summary = {
        "source_row_count": int(len(source)),
        "matched_row_count": int(len(selected)),
        "index_symbol": target_index,
        "ticker": target_ticker,
        "effective_dates": selected["effective_date"].drop_duplicates().tolist(),
        "manual_action_classification_required": True,
        "exact_removal_date_promoted": False,
        "historical_backtest_allowed": False,
        "v11_execution_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
    }
    return selected, summary


__all__ = [
    "NdxGiwEventEvidenceError",
    "OPTIONAL_FIELDS",
    "REQUIRED_FIELDS",
    "normalize_giw_export",
]
