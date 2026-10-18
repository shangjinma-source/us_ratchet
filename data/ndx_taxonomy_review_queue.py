"""Build a non-promoting historical taxonomy evidence review queue."""
from __future__ import annotations

from typing import Any

import pandas as pd


class NdxTaxonomyReviewQueueError(ValueError):
    pass


def _required(frame: pd.DataFrame, columns: set[str], label: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise NdxTaxonomyReviewQueueError(f"{label} columns missing: {missing}")


def _ticker_hints(registry: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    hints: dict[str, list[dict[str, str]]] = {}
    for decision in registry.get("decisions") or []:
        if not isinstance(decision, dict) or decision.get("status") != "accepted":
            continue
        for ticker in decision.get("tickers") or []:
            key = str(ticker).strip().upper()
            if key:
                hints.setdefault(key, []).append({
                    "risk_chain": str(decision.get("risk_chain") or "").strip(),
                    "confidence": str(decision.get("confidence") or "").strip(),
                    "evidence_phrase": str(decision.get("evidence_phrase") or "").strip(),
                    "decision_id": str(decision.get("decision_id") or "").strip(),
                })
    return hints


def build_historical_review_queue(
    reviewed_evidence: pd.DataFrame,
    documents: pd.DataFrame,
    current_registry: dict[str, Any],
) -> pd.DataFrame:
    """Join historical SEC evidence to current hints without assigning a chain."""
    _required(
        reviewed_evidence,
        {"evidence_id", "issuer_id", "status", "evidence_available_date", "evidence_excerpt"},
        "reviewed evidence",
    )
    _required(
        documents,
        {
            "job_id", "tickers", "form", "accession_number", "extraction_status",
            "raw_manifest_verified", "raw_sha256", "business_excerpt_sha256",
        },
        "review documents",
    )
    if reviewed_evidence["evidence_id"].duplicated().any():
        raise NdxTaxonomyReviewQueueError("reviewed evidence IDs are not unique")
    docs = documents.copy()
    docs["evidence_id"] = "sec:" + docs["job_id"].astype(str)
    if docs["evidence_id"].duplicated().any():
        raise NdxTaxonomyReviewQueueError("review document evidence IDs are not unique")
    pending = reviewed_evidence[
        reviewed_evidence["status"].astype(str).eq("pending_review")
    ].copy()
    merged = pending.merge(
        docs[
            [
                "evidence_id", "tickers", "form", "accession_number",
                "extraction_status", "raw_manifest_verified", "raw_sha256",
                "business_excerpt_sha256", "section_text_chars",
            ]
        ],
        on="evidence_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if merged["_merge"].ne("both").any():
        raise NdxTaxonomyReviewQueueError("pending evidence is missing its review document")
    merged = merged.drop(columns=["_merge"])
    hints = _ticker_hints(current_registry)
    rows = []
    for row in merged.to_dict("records"):
        tickers = sorted({
            value.strip().upper()
            for value in str(row.get("tickers") or "").split(";")
            if value.strip()
        })
        matched = [hint for ticker in tickers for hint in hints.get(ticker, [])]
        chains = sorted({hint["risk_chain"] for hint in matched if hint["risk_chain"]})
        hint_status = (
            "no_current_hint"
            if not matched
            else "current_hint_conflict"
            if len(chains) != 1
            else "current_hint_available_for_manual_routing_only"
        )
        standard = str(row.get("extraction_status") or "") == "business_section_extracted"
        manifest_ok = str(row.get("raw_manifest_verified") or "").lower() in {"true", "1"}
        reviewable = standard and manifest_ok and bool(str(row.get("evidence_excerpt") or "").strip())
        rows.append({
            "evidence_id": row["evidence_id"],
            "issuer_id": row["issuer_id"],
            "tickers": ";".join(tickers),
            "form": row.get("form", ""),
            "accession_number": row.get("accession_number", ""),
            "evidence_available_date": row.get("evidence_available_date", ""),
            "extraction_status": row.get("extraction_status", ""),
            "raw_manifest_verified": manifest_ok,
            "raw_sha256": row.get("raw_sha256", ""),
            "business_excerpt_sha256": row.get("business_excerpt_sha256", ""),
            "section_text_chars": row.get("section_text_chars", ""),
            "historical_evidence_excerpt": row.get("evidence_excerpt", ""),
            "historical_evidence_reviewable": reviewable,
            "current_hint_status": hint_status,
            "current_hint_risk_chain": chains[0] if len(chains) == 1 else "",
            "current_hint_confidence": ";".join(sorted({hint["confidence"] for hint in matched})),
            "current_hint_evidence_phrases": ";".join(sorted({hint["evidence_phrase"] for hint in matched if hint["evidence_phrase"]})),
            "current_hint_decision_ids": ";".join(sorted({hint["decision_id"] for hint in matched if hint["decision_id"]})),
            "review_status": (
                "manual_historical_source_review_required"
                if reviewable
                else "source_extraction_repair_required"
            ),
            "risk_chain_assignment_performed": False,
            "historical_backfill_from_current_allowed": False,
            "return_data_read": False,
        })
    return pd.DataFrame(rows).sort_values(
        ["historical_evidence_reviewable", "current_hint_status", "tickers"],
        ascending=[False, True, True],
        kind="stable",
    ).reset_index(drop=True)


__all__ = ["NdxTaxonomyReviewQueueError", "build_historical_review_queue"]
