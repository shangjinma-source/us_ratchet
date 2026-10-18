"""Pure decision-date ticker resolution for a future candidate-v3 lineage.

This module is deliberately not wired into the active candidate generator or
task.  It resolves only the identity row used at a decision coordinate.  A
semicolon-delimited taxonomy ticker is accepted only when the repository's
reviewed lifecycle rule binds the same CIK and CUSIP and resolves to the
officially observed ticker on that exact date.

An official constituent observation still has an unknown effective date, so
the result is research input normalization rather than execution-valid identity
authority.  Multiple legitimate securities of one issuer (for example GOOG
and GOOGL) remain in the eligible pool; the portfolio search must continue to
enforce one selected security per issuer.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

import pandas as pd

from data.ndx_security_identity import (
    NdxSecurityIdentityError,
    SecurityLifecycle,
)


class NdxDynamicShadowCandidateIdentityV3Error(ValueError):
    """Raised when decision-date identity normalization is ambiguous."""


_OFFICIAL_REQUIRED = {"ticker"}
_TAXONOMY_REQUIRED = {
    "ticker", "cik", "cusip", "security_id", "issuer_id",
    "selection_date_end", "evidence_available_date",
}
_OUTPUT_PROVENANCE_COLUMNS = {
    "taxonomy_ticker_aliases", "ticker_resolution_status",
    "ticker_lifecycle_rule_id", "ticker_lifecycle_resolved_on_date",
}
_TICKER_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9.\-]*")


def _canonical_date(value: Any, label: str) -> date:
    text = str(value or "").strip()
    try:
        result = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowCandidateIdentityV3Error(f"invalid {label}") from exc
    if text != result.isoformat():
        raise NdxDynamicShadowCandidateIdentityV3Error(f"non-canonical {label}")
    return result


def _optional_date(value: Any, label: str) -> date | None:
    text = str(value or "").strip()
    return None if not text else _canonical_date(text, label)


def _ticker(value: Any, label: str) -> str:
    text = str(value or "").strip().upper()
    if not _TICKER_PATTERN.fullmatch(text):
        raise NdxDynamicShadowCandidateIdentityV3Error(f"invalid {label}: {value!r}")
    return text


def _aliases(value: Any) -> tuple[str, ...]:
    raw = [part.strip() for part in str(value or "").split(";") if part.strip()]
    aliases = tuple(_ticker(part, "taxonomy ticker alias") for part in raw)
    if not aliases or len(set(aliases)) != len(aliases):
        raise NdxDynamicShadowCandidateIdentityV3Error(
            "taxonomy ticker aliases are empty or duplicated"
        )
    return aliases


def _cik(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or int(text) <= 0:
        raise NdxDynamicShadowCandidateIdentityV3Error("taxonomy CIK is invalid")
    return f"{int(text):010d}"


def _nonblank(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise NdxDynamicShadowCandidateIdentityV3Error(f"{label} is blank")
    return text


def _selected_row(
    candidates: pd.DataFrame, *, ticker: str, decision: date,
) -> pd.Series | None:
    if candidates.empty:
        return None
    work = candidates.copy()
    work["_selection_end"] = work["selection_date_end"].map(
        lambda value: _optional_date(value, "taxonomy selection_date_end")
    )
    work["_evidence_available"] = work["evidence_available_date"].map(
        lambda value: _optional_date(value, "taxonomy evidence_available_date")
    )
    work = work.loc[
        work["_selection_end"].notna()
        & work["_selection_end"].le(decision)
        & work["_evidence_available"].notna()
        & work["_evidence_available"].le(decision)
    ]
    if work.empty:
        return None
    latest_selection = work["_selection_end"].max()
    work = work.loc[work["_selection_end"].eq(latest_selection)]
    latest_evidence = work["_evidence_available"].max()
    work = work.loc[work["_evidence_available"].eq(latest_evidence)]
    if len(work) != 1:
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"official ticker resolves to ambiguous latest taxonomy identity: {ticker}"
        )
    return work.iloc[0]


def _resolve_row(
    row: pd.Series,
    *,
    official_ticker: str,
    decision: date,
    lifecycle: SecurityLifecycle,
) -> dict[str, Any]:
    result = row.drop(labels=["_selection_end", "_evidence_available"], errors="ignore").to_dict()
    aliases = _aliases(row["ticker"])
    cik = _cik(row["cik"])
    cusip = _nonblank(row["cusip"], "taxonomy CUSIP").upper()
    security_id = _nonblank(row["security_id"], "taxonomy security_id")
    issuer_id = _nonblank(row["issuer_id"], "taxonomy issuer_id")
    if len(cusip) != 9 or not cusip.isalnum():
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"taxonomy CUSIP is invalid: {official_ticker}"
        )
    if issuer_id != f"issuer:{cik}":
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"taxonomy issuer_id disagrees with CIK: {official_ticker}"
        )
    if security_id != f"security:{cik}:{cusip}":
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"taxonomy security_id disagrees with CIK/CUSIP: {official_ticker}"
        )

    rules_recognizing_ticker = [
        item for item in lifecycle.rules_by_cik.values()
        if official_ticker in item.recognized_tickers
    ]
    if len(rules_recognizing_ticker) > 1:
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"official ticker is ambiguous across lifecycle rules: {official_ticker}"
        )
    recognized_rule = rules_recognizing_ticker[0] if rules_recognizing_ticker else None
    rule = lifecycle.rules_by_cik.get(cik)
    if recognized_rule is not None and recognized_rule.cik != cik:
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"official ticker lifecycle CIK disagrees with taxonomy: {official_ticker}"
        )
    rule_applies = bool(
        len(aliases) > 1
        or rule is not None
        or recognized_rule is not None
    )
    if rule_applies:
        if rule is None:
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"multi-ticker taxonomy identity lacks a reviewed lifecycle: {official_ticker}"
            )
        if cusip != rule.cusip:
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"taxonomy CUSIP disagrees with lifecycle rule: {official_ticker}"
            )
        if official_ticker not in rule.recognized_tickers:
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"official ticker is not recognized by lifecycle rule: {official_ticker}"
            )
        if not set(aliases).issubset(rule.recognized_tickers):
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"taxonomy aliases exceed lifecycle rule: {official_ticker}"
            )
        try:
            resolved = rule.resolve(pd.Timestamp(decision))
        except NdxSecurityIdentityError as exc:
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"lifecycle interval is invalid on decision date: {official_ticker}"
            ) from exc
        if resolved != official_ticker:
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"official ticker conflicts with lifecycle decision-date interval: {official_ticker}"
            )
        status = "REVIEWED_DECISION_DATE_LIFECYCLE"
        rule_id = rule.rule_id
    else:
        if aliases != (official_ticker,):
            raise NdxDynamicShadowCandidateIdentityV3Error(
                f"ticker alias is not covered by a lifecycle rule: {official_ticker}"
            )
        status = "EXACT_OFFICIAL_TICKER_NO_ALIAS"
        rule_id = ""

    result.update({
        "ticker": official_ticker,
        "cik": cik,
        "cusip": cusip,
        "security_id": security_id,
        "issuer_id": issuer_id,
        "taxonomy_ticker_aliases": ";".join(aliases),
        "ticker_resolution_status": status,
        "ticker_lifecycle_rule_id": rule_id,
        "ticker_lifecycle_resolved_on_date": decision.isoformat(),
    })
    return result


def resolve_decision_date_taxonomy_identities(
    official_membership: pd.DataFrame,
    taxonomy_records: pd.DataFrame,
    lifecycle: SecurityLifecycle,
    *,
    decision_date: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve one fully available taxonomy identity per official ticker.

    The function performs no I/O and grants no admission authority.  Missing
    taxonomy evidence remains explicit so the caller can apply its existing
    degraded/fail-closed policy.
    """

    missing_official = sorted(_OFFICIAL_REQUIRED - set(official_membership.columns))
    missing_taxonomy = sorted(_TAXONOMY_REQUIRED - set(taxonomy_records.columns))
    if missing_official or missing_taxonomy:
        raise NdxDynamicShadowCandidateIdentityV3Error(
            f"identity input schema is incomplete: official={missing_official}, taxonomy={missing_taxonomy}"
        )
    if _OUTPUT_PROVENANCE_COLUMNS & set(taxonomy_records.columns):
        raise NdxDynamicShadowCandidateIdentityV3Error(
            "taxonomy input already contains candidate-v3 provenance columns"
        )
    decision = _canonical_date(decision_date, "decision_date")
    official = official_membership.copy()
    official["ticker"] = official["ticker"].map(lambda value: _ticker(value, "official ticker"))
    if official.empty or official["ticker"].duplicated().any():
        raise NdxDynamicShadowCandidateIdentityV3Error(
            "official membership tickers are empty or duplicated"
        )
    records = taxonomy_records.copy()
    records["_aliases"] = records["ticker"].map(_aliases)

    resolved_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    for official_ticker in sorted(official["ticker"]):
        candidates = records.loc[
            records["_aliases"].map(lambda values: official_ticker in values)
        ].drop(columns=["_aliases"])
        selected = _selected_row(candidates, ticker=official_ticker, decision=decision)
        if selected is None:
            missing.append(official_ticker)
            continue
        resolved_rows.append(_resolve_row(
            selected,
            official_ticker=official_ticker,
            decision=decision,
            lifecycle=lifecycle,
        ))

    output_columns = list(taxonomy_records.columns) + [
        "taxonomy_ticker_aliases", "ticker_resolution_status",
        "ticker_lifecycle_rule_id", "ticker_lifecycle_resolved_on_date",
    ]
    resolved = pd.DataFrame(resolved_rows, columns=output_columns)
    if not resolved.empty:
        if resolved["ticker"].duplicated().any():
            raise NdxDynamicShadowCandidateIdentityV3Error("resolved official ticker is duplicated")
        if resolved["security_id"].duplicated().any():
            raise NdxDynamicShadowCandidateIdentityV3Error(
                "one security_id resolved to multiple official tickers"
            )
        if resolved["cusip"].duplicated().any():
            raise NdxDynamicShadowCandidateIdentityV3Error(
                "one CUSIP resolved to multiple official tickers"
            )
        resolved = resolved.sort_values("ticker", kind="stable").reset_index(drop=True)

    issuer_groups = (
        resolved.groupby("issuer_id", sort=True)["security_id"].nunique()
        if not resolved.empty else pd.Series(dtype="int64")
    )
    multi_security_issuers = sorted(issuer_groups.loc[issuer_groups.gt(1)].index.astype(str))
    audit = {
        "schema_version": 1,
        "decision_date": decision.isoformat(),
        "official_security_count": int(len(official)),
        "resolved_security_count": int(len(resolved)),
        "resolved_unique_issuer_count": int(resolved["issuer_id"].nunique()) if not resolved.empty else 0,
        "dynamic_k_upper_bound_is_unique_issuer_count": True,
        "missing_taxonomy_identity_tickers": missing,
        "reviewed_lifecycle_tickers": sorted(
            resolved.loc[
                resolved["ticker_resolution_status"].eq("REVIEWED_DECISION_DATE_LIFECYCLE"),
                "ticker",
            ].astype(str)
        ) if not resolved.empty else [],
        "multi_security_issuer_ids": multi_security_issuers,
        "one_security_per_issuer_must_be_enforced_by_portfolio_search": True,
        "official_membership_effective_date_proved": False,
        "execution_valid_on_date_identity_proved": False,
        "admission_authority": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    return resolved, audit


__all__ = [
    "NdxDynamicShadowCandidateIdentityV3Error",
    "resolve_decision_date_taxonomy_identities",
]
