"""Fail-closed point-in-time projection for original-eight execution attribution.

This module does not create taxonomy history and must not be used to select
securities or label returns.  It only projects independently reviewed SEC
evidence that was already public at a requested execution-attribution date.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd


INCUMBENT_TICKERS = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")
REQUIRED_COLUMNS = {
    "ticker", "security_id", "issuer_id", "risk_chain", "effective_from",
    "effective_to", "evidence_source_type", "evidence_locator",
    "evidence_available_date", "status",
}


class NdxIncumbentPitAttributionError(ValueError):
    """Raised when the attribution-only point-in-time projection is unsafe."""


def build_incumbent_pit_attribution(
    reviewed_evidence: pd.DataFrame,
    selection_dates: Iterable[str],
    *,
    source_manifest: Mapping[str, object],
) -> pd.DataFrame:
    """Project reviewed evidence without changing its historical-backfill policy."""

    summary = source_manifest.get("summary") or {}
    if source_manifest.get("manifest_type") != "ndx_incumbent_overlay_reviewed_bundle":
        raise NdxIncumbentPitAttributionError("unexpected reviewed overlay manifest")
    if source_manifest.get("historical_backfill_allowed") is not False:
        raise NdxIncumbentPitAttributionError("source overlay backfill policy changed")
    if not isinstance(summary, Mapping) or summary.get("historical_backfill_allowed") is not False:
        raise NdxIncumbentPitAttributionError("source overlay summary backfill policy changed")
    if any(source_manifest.get(key) is not False for key in (
        "return_data_read", "price_data_used", "backtest_results_used",
    )):
        raise NdxIncumbentPitAttributionError("source overlay is not return-independent")
    missing = REQUIRED_COLUMNS - set(reviewed_evidence.columns)
    if missing:
        raise NdxIncumbentPitAttributionError(f"reviewed evidence missing columns: {sorted(missing)}")

    evidence = reviewed_evidence.copy()
    evidence["ticker"] = evidence["ticker"].astype(str).str.upper().str.strip()
    evidence = evidence.loc[evidence["ticker"].isin(INCUMBENT_TICKERS)].copy()
    counts = evidence.groupby("ticker").size().to_dict()
    if set(counts) != set(INCUMBENT_TICKERS) or any(value != 1 for value in counts.values()):
        raise NdxIncumbentPitAttributionError("original-eight evidence must be complete and unique")
    if not evidence["status"].astype(str).str.lower().eq("accepted").all():
        raise NdxIncumbentPitAttributionError("original-eight evidence is not fully accepted")
    if not evidence["evidence_source_type"].astype(str).eq("sec_filing_business_description").all():
        raise NdxIncumbentPitAttributionError("non-SEC evidence cannot enter attribution projection")
    if not evidence["evidence_locator"].astype(str).str.startswith("https://www.sec.gov/Archives/").all():
        raise NdxIncumbentPitAttributionError("SEC evidence locator is invalid")
    if evidence[["security_id", "issuer_id", "risk_chain"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any():
        raise NdxIncumbentPitAttributionError("identity or risk-chain field is blank")
    if evidence["security_id"].duplicated().any() or evidence["issuer_id"].duplicated().any():
        raise NdxIncumbentPitAttributionError("original-eight identity is ambiguous")

    for column in ("effective_from", "effective_to", "evidence_available_date"):
        evidence[column + "_parsed"] = pd.to_datetime(evidence[column], errors="coerce").dt.normalize()
    if evidence[["effective_from_parsed", "evidence_available_date_parsed"]].isna().any().any():
        raise NdxIncumbentPitAttributionError("required evidence dates are invalid")

    dates = pd.to_datetime(list(selection_dates), errors="coerce").normalize()
    if len(dates) == 0 or dates.isna().any() or dates.duplicated().any():
        raise NdxIncumbentPitAttributionError("selection dates must be non-empty, valid and unique")
    rows = []
    for selection in sorted(dates):
        for row in evidence.sort_values("ticker", kind="stable").to_dict("records"):
            if row["evidence_available_date_parsed"] > selection:
                raise NdxIncumbentPitAttributionError(
                    f"future evidence at {selection.date()}: {row['ticker']}"
                )
            if row["effective_from_parsed"] > selection:
                raise NdxIncumbentPitAttributionError(
                    f"future effective classification at {selection.date()}: {row['ticker']}"
                )
            effective_to = row["effective_to_parsed"]
            if pd.notna(effective_to) and effective_to < selection:
                raise NdxIncumbentPitAttributionError(
                    f"expired classification at {selection.date()}: {row['ticker']}"
                )
            rows.append({
                "selection_date": selection.date().isoformat(),
                "ticker": row["ticker"],
                "security_id": row["security_id"],
                "issuer_id": row["issuer_id"],
                "risk_chain": row["risk_chain"],
                "effective_from": row["effective_from"],
                "effective_to": row["effective_to"],
                "evidence_available_date": row["evidence_available_date"],
                "evidence_source_type": row["evidence_source_type"],
                "evidence_locator": row["evidence_locator"],
                "status": "accepted_for_execution_attribution",
                "attribution_role": "ORIGINAL_8_EXECUTION_RISK_CHAIN_ONLY",
                "candidate_selection_allowed": False,
                "return_labeling_allowed": False,
                "historical_backfill_created": False,
            })
    return pd.DataFrame(rows)

