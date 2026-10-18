"""Compare exact Nasdaq event timing with the quarterly QQQ N-PORT proxy.

This module measures disclosure lag and snapshot-state mismatches only.  It
does not treat QQQ as the exact index, and it never reads prices or returns.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
import yaml


ACTION_AUDIT_COLUMNS = [
    "event_id",
    "event_type",
    "effective_date",
    "source_available_date",
    "action",
    "ticker",
    "comparison_tickers",
    "first_post_event_report_date",
    "first_post_event_available_date",
    "first_post_event_state",
    "first_post_event_expected_state",
    "first_post_event_correct",
    "first_correct_report_date",
    "first_correct_available_date",
    "report_lag_days",
    "availability_lag_days",
    "corrected_lag_days",
    "proxy_status",
    "source_future_data_guard",
    "notes",
]

REPORT_AUDIT_COLUMNS = [
    "report_date",
    "available_date",
    "expected_member_count",
    "proxy_member_count",
    "expected_missing_from_proxy_count",
    "proxy_extra_count",
    "expected_missing_from_proxy",
    "proxy_extra",
    "proxy_extra_details",
    "membership_state_comparison",
    "baseline_source_report_date",
]

EVENT_SUMMARY_COLUMNS = [
    "event_id",
    "event_type",
    "effective_date",
    "action_count",
    "first_post_event_report_date",
    "first_post_event_available_date",
    "first_report_correct_action_count",
    "first_report_mismatch_action_count",
    "unresolved_action_count",
    "max_corrected_lag_days",
    "event_proxy_status",
]

UNRESOLVED_COLUMNS = [
    "report_date",
    "available_date",
    "gap_type",
    "ticker",
    "proxy_weight",
    "proxy_value_usd",
    "proxy_name",
    "proxy_cusip",
    "proxy_mapping_method",
    "evidence_status",
    "details",
]


class NdxEventProxyAuditError(ValueError):
    """Raised when event/proxy audit inputs fail closed."""


def _iso_date(value: object, field: str) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise NdxEventProxyAuditError(f"{field} must be YYYY-MM-DD: {value!r}") from exc


def load_alias_registry(path: str | Path) -> dict:
    source_path = Path(path)
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise NdxEventProxyAuditError(f"cannot read alias registry: {source_path}") from exc
    if not isinstance(payload, dict) or int(payload.get("schema_version") or 0) != 1:
        raise NdxEventProxyAuditError("unsupported alias registry schema")
    groups = payload.get("groups") or []
    if not isinstance(groups, list) or not groups:
        raise NdxEventProxyAuditError("alias registry groups must be non-empty")
    normalized = []
    seen = set()
    for raw in groups:
        if not isinstance(raw, dict):
            raise NdxEventProxyAuditError("alias registry group must be a mapping")
        group_id = str(raw.get("group_id") or "").strip()
        tickers = [str(item).strip().upper() for item in (raw.get("tickers") or [])]
        if not re.fullmatch(r"[a-z0-9_.-]{3,80}", group_id) or len(tickers) < 2:
            raise NdxEventProxyAuditError(f"invalid alias group: {raw!r}")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", ticker) for ticker in tickers):
            raise NdxEventProxyAuditError(f"invalid ticker in alias group {group_id}")
        if len(set(tickers)) != len(tickers) or seen.intersection(tickers):
            raise NdxEventProxyAuditError(f"overlapping or duplicate alias group {group_id}")
        seen.update(tickers)
        normalized.append({
            "group_id": group_id,
            "tickers": tickers,
            "canonical_ticker": tickers[0],
            "evidence_source": str(raw.get("evidence_source") or "").strip(),
            "evidence_available_date": _iso_date(
                raw.get("evidence_available_date"),
                f"{group_id}.evidence_available_date",
            ),
            "notes": str(raw.get("notes") or "").strip(),
        })
    result = dict(payload)
    result["groups"] = normalized
    result["alias_registry_path"] = source_path.as_posix()
    return result


def load_verified_proxy(proxy_path: str | Path, manifest_path: str | Path | None = None) -> tuple[pd.DataFrame, dict]:
    path = Path(proxy_path)
    manifest_file = Path(manifest_path) if manifest_path else path.with_suffix(path.suffix + ".manifest.json")
    if not path.exists() or not manifest_file.exists():
        raise NdxEventProxyAuditError("QQQ N-PORT proxy or manifest is missing")
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise NdxEventProxyAuditError("QQQ N-PORT proxy manifest is invalid") from exc
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if manifest.get("content_sha256") != digest:
        raise NdxEventProxyAuditError("QQQ N-PORT proxy content hash mismatch")
    if manifest.get("dataset_type") != "ndx_point_in_time_constituents":
        raise NdxEventProxyAuditError("QQQ N-PORT proxy dataset type mismatch")
    if manifest.get("dataset_key") != "qqq_nport_public_filings":
        raise NdxEventProxyAuditError("QQQ N-PORT proxy dataset key mismatch")
    if manifest.get("historical_backtest_allowed") is not True:
        raise NdxEventProxyAuditError("QQQ N-PORT proxy is not approved for point-in-time use")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {
        "report_date", "available_date", "ticker", "accession_number",
    }
    if not required.issubset(frame.columns):
        raise NdxEventProxyAuditError(
            f"QQQ N-PORT proxy missing columns: {sorted(required - set(frame.columns))}"
        )
    for column in ["report_date", "available_date"]:
        frame[column] = frame[column].map(lambda value: _iso_date(value, column))
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    if frame["ticker"].eq("").any():
        raise NdxEventProxyAuditError("QQQ N-PORT proxy contains blank tickers")
    grouped = frame.groupby("report_date")
    for report_date, group in grouped:
        if group["available_date"].nunique() != 1:
            raise NdxEventProxyAuditError(f"multiple available dates for report {report_date}")
        if group["ticker"].duplicated().any():
            raise NdxEventProxyAuditError(f"duplicate QQQ ticker in report {report_date}")
    return frame.sort_values(["report_date", "ticker"], kind="stable").reset_index(drop=True), manifest


def _alias_map(alias_registry: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for group in alias_registry["groups"]:
        tickers = list(group["tickers"])
        for ticker in tickers:
            result[ticker] = tickers
    return result


def _canonical_map(alias_registry: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for group in alias_registry["groups"]:
        canonical = group["canonical_ticker"]
        for ticker in group["tickers"]:
            result[ticker] = canonical
    return result


def _json_list(values: set[str] | list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=False)


def audit_event_actions(
    events: pd.DataFrame,
    proxy: pd.DataFrame,
    alias_registry: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return action-level, event-level and report-level proxy diagnostics."""

    if events.empty:
        raise NdxEventProxyAuditError("exact event table is empty")
    required_event_columns = {"event_id", "event_type", "effective_date", "action", "ticker"}
    if not required_event_columns.issubset(events.columns):
        raise NdxEventProxyAuditError(
            f"exact event table missing columns: {sorted(required_event_columns - set(events.columns))}"
        )
    membership_events = events[events["action"].isin(["add", "remove"])].copy()
    if membership_events.empty:
        raise NdxEventProxyAuditError("exact event table has no membership actions")
    membership_events["effective_date"] = membership_events["effective_date"].map(
        lambda value: _iso_date(value, "effective_date")
    )
    if "source_available_date" in membership_events:
        membership_events["source_available_date"] = membership_events["source_available_date"].map(
            lambda value: _iso_date(value, "source_available_date")
        )
    else:
        membership_events["source_available_date"] = membership_events["effective_date"]
    membership_events["ticker"] = membership_events["ticker"].astype(str).str.upper().str.strip()
    alias_map = _alias_map(alias_registry)
    canonical = _canonical_map(alias_registry)
    report_dates = sorted(proxy["report_date"].unique())
    snapshots = {
        report_date: set(proxy.loc[proxy["report_date"].eq(report_date), "ticker"])
        for report_date in report_dates
    }
    snapshot_rows = {
        report_date: {
            canonical.get(str(row["ticker"]).upper(), str(row["ticker"]).upper()): row
            for row in proxy.loc[proxy["report_date"].eq(report_date)].to_dict(orient="records")
        }
        for report_date in report_dates
    }
    available_dates = {
        report_date: str(proxy.loc[proxy["report_date"].eq(report_date), "available_date"].iloc[0])
        for report_date in report_dates
    }
    action_rows = []
    for row in membership_events.to_dict(orient="records"):
        ticker = row["ticker"]
        comparison_tickers = alias_map.get(ticker, [ticker])
        effective_date = row["effective_date"]
        eligible = [report_date for report_date in report_dates if report_date >= effective_date]
        expected_present = row["action"] == "add"
        source_guard = str(row.get("future_data_guard", "")).lower() in {"true", "1"}
        notes = str(row.get("notes") or "")
        if not eligible:
            action_rows.append({
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "effective_date": effective_date,
                "source_available_date": row["source_available_date"],
                "action": row["action"],
                "ticker": ticker,
                "comparison_tickers": _json_list(comparison_tickers),
                "first_post_event_report_date": "",
                "first_post_event_available_date": "",
                "first_post_event_state": "no_report",
                "first_post_event_expected_state": "present" if expected_present else "absent",
                "first_post_event_correct": False,
                "first_correct_report_date": "",
                "first_correct_available_date": "",
                "report_lag_days": "",
                "availability_lag_days": "",
                "corrected_lag_days": "",
                "proxy_status": "no_post_event_report_in_scope",
                "source_future_data_guard": source_guard,
                "notes": notes,
            })
            continue
        first_report = eligible[0]
        states = []
        for report_date in eligible:
            present = bool(snapshots[report_date].intersection(comparison_tickers))
            states.append((report_date, present))
        first_state = states[0][1]
        first_correct = next(
            ((report_date, present) for report_date, present in states if present == expected_present),
            None,
        )
        if first_correct:
            first_correct_report = first_correct[0]
            first_correct_available = available_dates[first_correct_report]
            corrected_lag = (
                pd.Timestamp(first_correct_available) - pd.Timestamp(effective_date)
            ).days
            if first_state == expected_present:
                status = "captured_at_first_post_event_snapshot"
            else:
                status = "quarterly_proxy_lag_until_correct_snapshot"
        else:
            first_correct_report = ""
            first_correct_available = ""
            corrected_lag = ""
            status = "proxy_not_corrected_in_scope"
        action_rows.append({
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "effective_date": effective_date,
            "source_available_date": row["source_available_date"],
            "action": row["action"],
            "ticker": ticker,
            "comparison_tickers": _json_list(comparison_tickers),
            "first_post_event_report_date": first_report,
            "first_post_event_available_date": available_dates[first_report],
            "first_post_event_state": "present" if first_state else "absent",
            "first_post_event_expected_state": "present" if expected_present else "absent",
            "first_post_event_correct": first_state == expected_present,
            "first_correct_report_date": first_correct_report,
            "first_correct_available_date": first_correct_available,
            "report_lag_days": (
                pd.Timestamp(first_report) - pd.Timestamp(effective_date)
            ).days,
            "availability_lag_days": (
                pd.Timestamp(available_dates[first_report]) - pd.Timestamp(effective_date)
            ).days,
            "corrected_lag_days": corrected_lag,
            "proxy_status": status,
            "source_future_data_guard": source_guard,
            "notes": notes,
        })
    action_audit = pd.DataFrame(action_rows, columns=ACTION_AUDIT_COLUMNS)

    event_rows = []
    for event_id, group in action_audit.groupby("event_id", sort=False):
        first_report_values = sorted(set(group["first_post_event_report_date"]) - {""})
        first_available_values = sorted(set(group["first_post_event_available_date"]) - {""})
        mismatches = int((~group["first_post_event_correct"].astype(bool)).sum())
        unresolved = int(group["proxy_status"].isin({
            "no_post_event_report_in_scope", "proxy_not_corrected_in_scope",
        }).sum())
        corrected = pd.to_numeric(group["corrected_lag_days"], errors="coerce").dropna()
        event_rows.append({
            "event_id": event_id,
            "event_type": str(group["event_type"].iloc[0]),
            "effective_date": str(group["effective_date"].min()),
            "action_count": len(group),
            "first_post_event_report_date": first_report_values[0] if first_report_values else "",
            "first_post_event_available_date": first_available_values[0] if first_available_values else "",
            "first_report_correct_action_count": int(group["first_post_event_correct"].astype(bool).sum()),
            "first_report_mismatch_action_count": mismatches,
            "unresolved_action_count": unresolved,
            "max_corrected_lag_days": int(corrected.max()) if not corrected.empty else "",
            "event_proxy_status": (
                "all_actions_correct_at_first_snapshot"
                if mismatches == 0 and unresolved == 0
                else "proxy_action_lag_or_mismatch"
            ),
        })
    event_summary = pd.DataFrame(event_rows, columns=EVENT_SUMMARY_COLUMNS)

    base_report = report_dates[0]
    base_members = {
        canonical.get(ticker, ticker)
        for ticker in snapshots[base_report]
    }
    report_rows = []
    for report_date in report_dates:
        # Rebuild from the fixed baseline for every report.  This keeps the
        # audit deterministic and makes the comparison window explicit:
        # events already represented by the first proxy snapshot are not
        # replayed, while events effective after that snapshot are applied
        # exactly once up to the report being checked.
        expected_members = set(base_members)
        if report_date != base_report:
            for row in membership_events.to_dict(orient="records"):
                if row["effective_date"] <= base_report or row["effective_date"] > report_date:
                    continue
                canonical_ticker = canonical.get(str(row["ticker"]).upper(), str(row["ticker"]).upper())
                if row["action"] == "add":
                    expected_members.add(canonical_ticker)
                elif row["action"] == "remove":
                    expected_members.discard(canonical_ticker)
        actual_members = {
            canonical.get(ticker, ticker)
            for ticker in snapshots[report_date]
        }
        missing = expected_members - actual_members
        extra = actual_members - expected_members
        extra_details = []
        for ticker in sorted(extra):
            row = snapshot_rows[report_date].get(ticker, {})
            extra_details.append({
                "ticker": ticker,
                "name": str(row.get("name") or ""),
                "weight": str(row.get("weight") or ""),
                "value_usd": str(row.get("value_usd") or ""),
                "cusip": str(row.get("cusip") or ""),
                "mapping_method": str(row.get("mapping_method") or ""),
            })
        report_rows.append({
            "report_date": report_date,
            "available_date": available_dates[report_date],
            "expected_member_count": len(expected_members),
            "proxy_member_count": len(actual_members),
            "expected_missing_from_proxy_count": len(missing),
            "proxy_extra_count": len(extra),
            "expected_missing_from_proxy": _json_list(missing),
            "proxy_extra": _json_list(extra),
            "proxy_extra_details": json.dumps(extra_details, ensure_ascii=False, sort_keys=True),
            "membership_state_comparison": "match" if not missing and not extra else "mismatch",
            "baseline_source_report_date": base_report,
        })
    report_audit = pd.DataFrame(report_rows, columns=REPORT_AUDIT_COLUMNS)
    return action_audit, event_summary, report_audit


def audit_metrics(action_audit: pd.DataFrame, event_summary: pd.DataFrame, report_audit: pd.DataFrame) -> dict:
    first_correct = action_audit["first_post_event_correct"].astype(bool)
    corrected_lag = pd.to_numeric(action_audit["corrected_lag_days"], errors="coerce").dropna()
    extra_records = []
    for value in report_audit.get("proxy_extra_details", pd.Series(dtype=str)).tolist():
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = []
        if isinstance(parsed, list):
            extra_records.extend(item for item in parsed if isinstance(item, dict))
    extra_weights = pd.to_numeric(
        pd.Series([item.get("weight", "") for item in extra_records]),
        errors="coerce",
    ).dropna()
    extra_values = pd.to_numeric(
        pd.Series([item.get("value_usd", "") for item in extra_records]),
        errors="coerce",
    ).dropna()
    return {
        "membership_action_count": len(action_audit),
        "event_count": len(event_summary),
        "first_post_event_correct_count": int(first_correct.sum()),
        "first_post_event_mismatch_count": int((~first_correct).sum()),
        "first_post_event_correct_rate": float(first_correct.mean()) if len(action_audit) else 0.0,
        "proxy_lag_action_count": int(
            (action_audit["proxy_status"] == "quarterly_proxy_lag_until_correct_snapshot").sum()
        ),
        "proxy_not_corrected_action_count": int(
            action_audit["proxy_status"].isin({
                "no_post_event_report_in_scope", "proxy_not_corrected_in_scope",
            }).sum()
        ),
        "corrected_lag_days_p50": float(corrected_lag.median()) if not corrected_lag.empty else None,
        "corrected_lag_days_p90": float(corrected_lag.quantile(0.90)) if not corrected_lag.empty else None,
        "corrected_lag_days_max": int(corrected_lag.max()) if not corrected_lag.empty else None,
        "report_state_mismatch_count": int(
            (report_audit["membership_state_comparison"] != "match").sum()
        ),
        "unresolved_proxy_state_mismatch_count": int(
            (report_audit["membership_state_comparison"] != "match").sum()
        ),
        "proxy_extra_occurrence_count": int(len(extra_records)),
        "proxy_extra_ticker_count": int(len({str(item.get('ticker') or '') for item in extra_records if item.get('ticker')})),
        "proxy_extra_weight_total": float(extra_weights.sum()) if not extra_weights.empty else 0.0,
        "proxy_extra_weight_max": float(extra_weights.max()) if not extra_weights.empty else 0.0,
        "proxy_extra_value_usd_total": float(extra_values.sum()) if not extra_values.empty else 0.0,
        "proxy_is_not_exact_index": True,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
    }


def build_unresolved_proxy_gaps(report_audit: pd.DataFrame) -> pd.DataFrame:
    """Expose proxy-only mismatches without promoting them to exact events."""

    rows = []
    for record in report_audit.to_dict(orient="records"):
        if record.get("membership_state_comparison") == "match":
            continue
        try:
            missing = json.loads(str(record.get("expected_missing_from_proxy") or "[]"))
            extra = json.loads(str(record.get("proxy_extra") or "[]"))
            extra_details = json.loads(str(record.get("proxy_extra_details") or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            missing, extra, extra_details = [], [], []
        details_by_ticker = {
            str(item.get("ticker") or ""): item
            for item in extra_details
            if isinstance(item, dict) and item.get("ticker")
        }
        for ticker in missing:
            rows.append({
                "report_date": record["report_date"],
                "available_date": record["available_date"],
                "gap_type": "exact_expected_but_proxy_missing",
                "ticker": ticker,
                "proxy_weight": "",
                "proxy_value_usd": "",
                "proxy_name": "",
                "proxy_cusip": "",
                "proxy_mapping_method": "",
                "evidence_status": "not_promoted_to_exact_event",
                "details": "QQQ N-PORT quarterly state differs; exact Nasdaq event evidence is required.",
            })
        for ticker in extra:
            detail = details_by_ticker.get(str(ticker), {})
            rows.append({
                "report_date": record["report_date"],
                "available_date": record["available_date"],
                "gap_type": "proxy_extra_not_in_exact_event_registry",
                "ticker": ticker,
                "proxy_weight": str(detail.get("weight") or ""),
                "proxy_value_usd": str(detail.get("value_usd") or ""),
                "proxy_name": str(detail.get("name") or ""),
                "proxy_cusip": str(detail.get("cusip") or ""),
                "proxy_mapping_method": str(detail.get("mapping_method") or ""),
                "evidence_status": "not_promoted_to_exact_event",
                "details": "QQQ N-PORT shows a security absent from the reconstructed event state; do not infer an index event from the proxy alone.",
            })
        if not missing and not extra:
            rows.append({
                "report_date": record["report_date"],
                "available_date": record["available_date"],
                "gap_type": "proxy_state_mismatch_unresolved",
                "ticker": "",
                "proxy_weight": "",
                "proxy_value_usd": "",
                "proxy_name": "",
                "proxy_cusip": "",
                "proxy_mapping_method": "",
                "evidence_status": "not_promoted_to_exact_event",
                "details": "Quarterly proxy state mismatch requires source-level review.",
            })
    return pd.DataFrame(rows, columns=UNRESOLVED_COLUMNS)


__all__ = [
    "ACTION_AUDIT_COLUMNS",
    "EVENT_SUMMARY_COLUMNS",
    "UNRESOLVED_COLUMNS",
    "NdxEventProxyAuditError",
    "REPORT_AUDIT_COLUMNS",
    "audit_event_actions",
    "audit_metrics",
    "build_unresolved_proxy_gaps",
    "load_alias_registry",
    "load_verified_proxy",
]
