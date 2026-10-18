"""Fail-closed disposition of known NDX event evidence gaps.

This module does not infer index membership and never reads prices, returns, or
backtest output.  It only verifies that the two known event gaps are explicitly
scoped and remain blocked until stronger evidence is available.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Mapping

import pandas as pd


SCOPE_COLUMNS = [
    "case_id",
    "issue_type",
    "ticker",
    "source_event_id",
    "effective_date",
    "proxy_report_date",
    "evidence_available_date",
    "proxy_available_date",
    "blocked_selection_start",
    "blocked_selection_end",
    "scope_lock",
    "status",
    "promotion_allowed",
    "evidence_match",
    "observed_weight",
    "observed_value_usd",
    "observed_cusip",
    "spin_off_parent_ticker",
    "distribution_date",
    "regular_way_start_date",
    "exact_addition_supported",
    "exact_removal_date_supported",
    "evidence_status",
    "source_locator",
    "rule_source_locator",
    "ndx_policy_source_locator",
    "trading_source_locator",
    "resolution_required",
]


class NdxEventGapDispositionError(ValueError):
    """Raised when an event-gap disposition cannot be verified fail-closed."""


def _iso_date(value: object, field: str, *, allow_blank: bool = False) -> str:
    text = str(value or "").strip()
    if not text and allow_blank:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise NdxEventGapDispositionError(
            f"{field} must be YYYY-MM-DD: {value!r}"
        ) from exc


def _float(value: object, field: str, *, allow_blank: bool = False) -> float | None:
    text = str(value or "").strip()
    if not text and allow_blank:
        return None
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise NdxEventGapDispositionError(f"{field} must be numeric: {value!r}") from exc


def _single_row(frame: pd.DataFrame, mask: pd.Series, description: str) -> dict[str, Any]:
    matched = frame.loc[mask]
    if len(matched) != 1:
        raise NdxEventGapDispositionError(
            f"expected exactly one {description} row, found {len(matched)}"
        )
    return matched.iloc[0].to_dict()


def validate_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the immutable, research-only disposition configuration."""

    if int(config.get("schema_version") or 0) != 1:
        raise NdxEventGapDispositionError("unsupported event-gap disposition schema")
    if config.get("dataset_key") != "ndx_event_gap_disposition_v1":
        raise NdxEventGapDispositionError("event-gap disposition dataset key mismatch")
    for key, expected in {
        "research_only": True,
        "historical_backtest_allowed": False,
        "v11_plan_registration_allowed": True,
        "v11_execution_allowed": False,
    }.items():
        if config.get(key) is not expected:
            raise NdxEventGapDispositionError(
                f"event-gap disposition must set {key}={expected!r}"
            )
    cases = config.get("cases")
    if not isinstance(cases, list) or not cases:
        raise NdxEventGapDispositionError("event-gap disposition cases must be non-empty")
    seen = set()
    normalized_cases = []
    for raw in cases:
        if not isinstance(raw, dict):
            raise NdxEventGapDispositionError("event-gap disposition case must be a mapping")
        case = dict(raw)
        case_id = str(case.get("case_id") or "").strip()
        if not case_id or case_id in seen:
            raise NdxEventGapDispositionError(f"duplicate or blank case_id: {case_id!r}")
        seen.add(case_id)
        if case.get("scope_lock") not in {
            "exclude_effective_day_until_source_available",
            "proxy_extra_is_not_membership_evidence",
            "exact_addition_supported_removal_unresolved",
        }:
            raise NdxEventGapDispositionError(f"unsupported scope lock for {case_id}")
        if case.get("status") not in {
            "locked_blocker", "unresolved_proxy_only", "partial_exact_event_locked"
        }:
            raise NdxEventGapDispositionError(f"unsupported status for {case_id}")
        if case.get("promotion_allowed") is not False:
            raise NdxEventGapDispositionError(
                f"promotion must remain false for {case_id}"
            )
        case["effective_date"] = _iso_date(
            case.get("effective_date"), "effective_date", allow_blank=True
        )
        case["proxy_report_date"] = _iso_date(
            case.get("proxy_report_date"), "proxy_report_date", allow_blank=True
        )
        case["evidence_available_date"] = _iso_date(
            case.get("evidence_available_date"), "evidence_available_date"
        )
        case["proxy_available_date"] = _iso_date(
            case.get("proxy_available_date"), "proxy_available_date", allow_blank=True
        )
        case["blocked_selection_start"] = _iso_date(
            case.get("blocked_selection_start"), "blocked_selection_start"
        )
        case["blocked_selection_end"] = _iso_date(
            case.get("blocked_selection_end"), "blocked_selection_end"
        )
        if case["blocked_selection_start"] > case["blocked_selection_end"]:
            raise NdxEventGapDispositionError(
                f"blocked selection range is reversed for {case_id}"
            )
        if not str(case.get("resolution_required") or "").strip():
            raise NdxEventGapDispositionError(
                f"resolution_required is required for {case_id}"
            )
        if case.get("status") == "partial_exact_event_locked":
            case["distribution_date"] = _iso_date(
                case.get("distribution_date"), "distribution_date"
            )
            case["regular_way_start_date"] = _iso_date(
                case.get("regular_way_start_date"), "regular_way_start_date"
            )
            if case.get("exact_addition_supported") is not True:
                raise NdxEventGapDispositionError(
                    f"partial exact event must confirm addition for {case_id}"
                )
            if case.get("exact_removal_date_supported") is not False:
                raise NdxEventGapDispositionError(
                    f"partial exact event must retain unresolved removal for {case_id}"
                )
            for source_field in (
                "source_locator", "rule_source_locator",
                "ndx_policy_source_locator", "trading_source_locator",
            ):
                if not str(case.get(source_field) or "").startswith("https://"):
                    raise NdxEventGapDispositionError(
                        f"official source URL is required for {case_id}: {source_field}"
                    )
        normalized_cases.append(case)
    result = dict(config)
    result["cases"] = normalized_cases
    return result


def build_scope_rows(
    config: Mapping[str, Any],
    *,
    exact_gaps: pd.DataFrame,
    exact_source_audit: pd.DataFrame,
    proxy_gaps: pd.DataFrame,
) -> pd.DataFrame:
    """Match configured gap cases to verified exact/proxy audit rows."""

    normalized = validate_config(config)
    rows = []
    for case in normalized["cases"]:
        case_id = str(case["case_id"])
        issue_type = str(case.get("issue_type") or "")
        ticker = str(case.get("ticker") or "").upper()
        observed_weight = ""
        observed_value = ""
        observed_cusip = ""
        evidence_match = False
        if issue_type == "source_available_after_effective_date":
            event_id = str(case.get("source_event_id") or "")
            gap = _single_row(
                exact_gaps,
                exact_gaps["gap_type"].eq(issue_type)
                & exact_gaps["event_id"].eq(event_id),
                f"exact event gap {case_id}",
            )
            source = _single_row(
                exact_source_audit,
                exact_source_audit["event_id"].eq(event_id),
                f"exact source audit {case_id}",
            )
            try:
                required_tickers = json.loads(str(source.get("required_tickers") or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                required_tickers = []
            evidence_match = (
                ticker in {str(value).upper() for value in required_tickers}
                and str(source.get("effective_date") or "") == case["effective_date"]
                and str(source.get("source_available_date") or "")
                == case["evidence_available_date"]
                and str(gap.get("event_id") or "") == event_id
            )
        elif issue_type == "proxy_extra_not_in_exact_event_registry":
            gap = _single_row(
                proxy_gaps,
                proxy_gaps["gap_type"].eq(issue_type)
                & proxy_gaps["ticker"].str.upper().eq(ticker),
                f"proxy gap {case_id}",
            )
            observed_weight = str(gap.get("proxy_weight") or "")
            observed_value = str(gap.get("proxy_value_usd") or "")
            observed_cusip = str(gap.get("proxy_cusip") or "")
            expected_weight = _float(case.get("expected_proxy_weight"), "expected_proxy_weight")
            expected_value = _float(case.get("expected_proxy_value_usd"), "expected_proxy_value_usd")
            evidence_match = (
                str(gap.get("report_date") or "") == case["proxy_report_date"]
                and str(gap.get("available_date") or "") == case["proxy_available_date"]
                and str(gap.get("proxy_cusip") or "") == str(case.get("expected_proxy_cusip") or "")
                and abs(float(observed_weight) - float(expected_weight)) <= 1e-12
                and abs(float(observed_value) - float(expected_value)) <= 0.01
            )
        else:
            raise NdxEventGapDispositionError(
                f"unsupported issue_type for {case_id}: {issue_type!r}"
            )
        rows.append({
            "case_id": case_id,
            "issue_type": issue_type,
            "ticker": ticker,
            "source_event_id": str(case.get("source_event_id") or ""),
            "effective_date": case["effective_date"],
            "proxy_report_date": case["proxy_report_date"],
            "evidence_available_date": case["evidence_available_date"],
            "proxy_available_date": case["proxy_available_date"],
            "blocked_selection_start": case["blocked_selection_start"],
            "blocked_selection_end": case["blocked_selection_end"],
            "scope_lock": case["scope_lock"],
            "status": case["status"],
            "promotion_allowed": False,
            "evidence_match": bool(evidence_match),
            "observed_weight": observed_weight,
            "observed_value_usd": observed_value,
            "observed_cusip": observed_cusip,
            "spin_off_parent_ticker": str(case.get("spin_off_parent_ticker") or ""),
            "distribution_date": str(case.get("distribution_date") or ""),
            "regular_way_start_date": str(case.get("regular_way_start_date") or ""),
            "exact_addition_supported": case.get("exact_addition_supported", ""),
            "exact_removal_date_supported": case.get("exact_removal_date_supported", ""),
            "evidence_status": str(case.get("evidence_status") or ""),
            "source_locator": str(case.get("source_locator") or ""),
            "rule_source_locator": str(case.get("rule_source_locator") or ""),
            "ndx_policy_source_locator": str(case.get("ndx_policy_source_locator") or ""),
            "trading_source_locator": str(case.get("trading_source_locator") or ""),
            "resolution_required": str(case["resolution_required"]),
        })
    result = pd.DataFrame(rows, columns=SCOPE_COLUMNS)
    if not result.empty and not result["evidence_match"].astype(bool).all():
        failed = result.loc[~result["evidence_match"].astype(bool), "case_id"].tolist()
        raise NdxEventGapDispositionError(
            f"event-gap evidence mismatch for cases: {failed}"
        )
    return result


def disposition_summary(scope: pd.DataFrame) -> dict[str, Any]:
    if scope.empty:
        raise NdxEventGapDispositionError("event-gap scope cannot be empty")
    locked = scope["status"].isin({
        "locked_blocker", "unresolved_proxy_only", "partial_exact_event_locked"
    })
    scope_lock_complete = bool(
        scope["evidence_match"].astype(bool).all()
        and locked.all()
        and (~scope["promotion_allowed"].astype(bool)).all()
    )
    return {
        "case_count": int(len(scope)),
        "evidence_match_count": int(scope["evidence_match"].astype(bool).sum()),
        "locked_case_count": int(locked.sum()),
        "partial_exact_addition_count": int(
            scope["status"].eq("partial_exact_event_locked").sum()
        ),
        "unresolved_removal_date_count": int(
            (scope["exact_addition_supported"].eq(True)
             & scope["exact_removal_date_supported"].eq(False)).sum()
        ),
        "scope_lock_complete": scope_lock_complete,
        "historical_backtest_allowed": False,
        "v11_plan_registration_allowed": True,
        "v11_execution_allowed": False,
        "return_data_read": False,
        "price_data_used": False,
        "backtest_results_used": False,
    }


__all__ = [
    "SCOPE_COLUMNS",
    "NdxEventGapDispositionError",
    "build_scope_rows",
    "disposition_summary",
    "validate_config",
]
