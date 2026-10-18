"""Current point-in-time readiness and whole-lot math for v11 stage 1.

This module does not rank candidates or read return series.  It exposes every
current NDX security and fails closed while quality scores, valuation guards,
fresh OOS, or exact-event eligibility are unavailable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from data.versioning import file_sha256


class NdxMarginalStage1Error(ValueError):
    pass


INCUMBENTS = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")
ALLOWED_SHARES = (0.0, 0.05, 0.10, 0.15)


def verify_sidecar(
    path: Path,
    *,
    require_return_proof: bool = True,
    expected_return_data_read: bool = False,
) -> dict[str, Any]:
    sidecar = path.with_name(path.name + ".manifest.json")
    if not path.exists() or not sidecar.exists():
        raise NdxMarginalStage1Error(f"missing input or sidecar: {path}")
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    actual = file_sha256(path)
    if payload.get("content_sha256") != actual:
        raise NdxMarginalStage1Error(f"content hash mismatch: {path}")
    if require_return_proof and payload.get("return_data_read") is not expected_return_data_read:
        raise NdxMarginalStage1Error(
            f"input return_data_read identity mismatch: {path}"
        )
    if not require_return_proof and payload.get("dataset_type") != "security_candidate_registry":
        raise NdxMarginalStage1Error(f"unrecognized membership registry: {path}")
    return {"path": path.as_posix(), "sha256": actual, "version_id": payload.get("version_id"), "rows": payload.get("row_count")}


def load_current_inputs(taxonomy_path: Path, quality_path: Path, valuation_path: Path, registry_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    versions = {
        "taxonomy": verify_sidecar(taxonomy_path),
        "quality": verify_sidecar(quality_path),
        "valuation": verify_sidecar(valuation_path),
        "registry": verify_sidecar(registry_path, require_return_proof=False),
    }
    taxonomy = pd.read_csv(taxonomy_path)
    quality = pd.read_csv(quality_path)
    valuation = pd.read_csv(valuation_path)
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry = pd.DataFrame([
        {
            "ticker": row.get("ticker"),
            "name": row.get("name"),
            "ndx_current": bool(row.get("ndx_current")),
            "liquidity_status": (row.get("liquidity") or {}).get("status"),
            "broker_tradability_status": (row.get("broker_tradability") or {}).get("status"),
        }
        for row in registry_payload.get("candidates", [])
        if row.get("ndx_current") is True
    ])
    frame = taxonomy.merge(quality, on="ticker", how="left", suffixes=("", "_quality"))
    keep = ["ticker", "price", "price_date", "price_ready", "valuation_score_generated", "valuation_score_allowed", "valuation_blockers"]
    frame = frame.merge(valuation[keep], on="ticker", how="left")
    frame = frame.merge(registry, on="ticker", how="left")
    if len(frame) != 101 or frame["security_id"].nunique() != 101:
        raise NdxMarginalStage1Error("current security universe must contain exactly 101 unique securities")
    selection = pd.to_datetime(frame["effective_from"], errors="coerce")
    available = pd.to_datetime(frame["evidence_available_date"], errors="coerce")
    if (available > selection).fillna(False).any():
        raise NdxMarginalStage1Error("taxonomy future-data guard failed")
    price_date = pd.to_datetime(frame["price_date"], errors="coerce")
    observation = pd.Timestamp("2026-07-13")
    if (price_date >= observation).fillna(False).any():
        raise NdxMarginalStage1Error("price_date must be strictly before the 2026-07-13 selection date")
    return frame, versions


def build_candidate_readiness(frame: pd.DataFrame, *, config: Mapping[str, Any]) -> pd.DataFrame:
    incumbent_issuers = set(frame.loc[frame["ticker"].isin(INCUMBENTS), "issuer_id"].astype(str))
    # TSM is an incumbent covered by the separate SEC overlay, but is not a
    # current Nasdaq-100 constituent.  It remains frozen in the eight-name
    # baseline and must not be injected into the 101-security candidate pool.
    missing_incumbents = set(INCUMBENTS).difference(set(frame["ticker"]))
    if missing_incumbents != {"TSM"}:
        raise NdxMarginalStage1Error(
            f"unexpected current-NDX incumbent coverage: {sorted(missing_incumbents)}"
        )
    rows = []
    for row in frame.to_dict("records"):
        ticker = str(row["ticker"]).upper()
        blockers: list[str] = []
        role = "challenger"
        if ticker in INCUMBENTS:
            role = "incumbent_frozen"
            blockers.append("INCUMBENT_FROZEN_NOT_A_NEW_CANDIDATE")
        elif str(row.get("issuer_id")) in incumbent_issuers:
            blockers.append("ISSUER_ALREADY_PRESENT_IN_INCUMBENT")
        if row.get("status") != "accepted":
            blockers.append("RISK_CHAIN_UNCLASSIFIED_OR_UNACCEPTED")
        if not bool(row.get("price_ready")) or pd.isna(row.get("price")):
            blockers.append("STRICT_PRIOR_PRICE_NOT_READY")
        if not bool(row.get("quality_factor_input_ready")):
            blockers.append("QUALITY_INPUT_NOT_READY")
        if not bool(row.get("quality_score_generated")):
            blockers.append("QUALITY_SCORE_NOT_GENERATED")
        if not bool(row.get("valuation_score_generated")):
            blockers.append("VALUATION_OVERPAY_GUARD_NOT_READY")
        blockers.extend(["FRESH_OOS_NOT_AVAILABLE", "EXACT_NDX_EVENT_EXECUTION_BLOCKED", "HSBC_TRADABILITY_UNVERIFIED"])
        rows.append({
            "security_id": row.get("security_id"), "issuer_id": row.get("issuer_id"), "ticker": ticker,
            "name": row.get("name"), "role": role, "selection_date": "2026-07-13",
            "ticker_lifecycle_status": "current_ticker_as_of_selection",
            "security_effective_from": row.get("effective_from"),
            "security_effective_to": row.get("effective_to"),
            "risk_chain": row.get("risk_chain"), "taxonomy_status": row.get("status"),
            "taxonomy_confidence": row.get("confidence"), "evidence_source": row.get("evidence_source"),
            "evidence_available_date": row.get("evidence_available_date"), "price_date": row.get("price_date"),
            "strict_prior_price": row.get("price"), "quality_input_ready": bool(row.get("quality_factor_input_ready")),
            "quality_score_generated": bool(row.get("quality_score_generated")),
            "valuation_score_generated": bool(row.get("valuation_score_generated")),
            "liquidity_status": row.get("liquidity_status"), "broker_tradability_status": row.get("broker_tradability_status"),
            "component_improvement": "NOT_EVALUATED", "incumbent_gate": "NOT_EVALUATED",
            "live_eligible": False, "candidate_selected": False,
            "blockers": ";".join(dict.fromkeys(blockers)),
            "why_not_selected": ";".join(dict.fromkeys(blockers)),
        })
    return pd.DataFrame(rows)


def attach_current_competition(
    readiness: pd.DataFrame,
    competition: pd.DataFrame,
    shortlist: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the audited component ranking without opening admission gates."""
    required = {
        "ticker", "attack_score", "quality_score", "competition_eligible",
        "competition_blockers", "risk_chain_price_rank", "valuation_score",
        "valuation_guarded_price_score", "valuation_guard_ready",
        "valuation_guard_penalty_attack_equivalent",
    }
    missing = sorted(required - set(competition.columns))
    if missing:
        raise NdxMarginalStage1Error(f"competition columns missing: {missing}")
    if competition["ticker"].duplicated().any() or len(competition) != 101:
        raise NdxMarginalStage1Error("competition must contain 101 unique securities")
    ranks = shortlist[["ticker", "shortlist_rank"]].drop_duplicates("ticker")
    attached = readiness.merge(
        competition[list(required)], on="ticker", how="left", validate="one_to_one"
    ).merge(ranks, on="ticker", how="left", validate="one_to_one")
    attached["component_shortlisted"] = attached["shortlist_rank"].notna()
    attached["candidate_selected"] = False
    attached["component_improvement"] = "RANKED_NOT_PERFORMANCE_EVALUATED"
    attached["incumbent_gate"] = "NOT_EVALUATED_UNTIL_FRESH_OOS"
    guard_ready = bool(
        attached.loc[attached["component_shortlisted"], "valuation_guard_ready"]
        .fillna(False).astype(bool).all()
    )
    extra = (
        "FRESH_OOS_NOT_AVAILABLE;EXACT_NDX_EVENT_EXECUTION_BLOCKED;"
        "HSBC_TRADABILITY_UNVERIFIED"
    )
    if not guard_ready:
        extra = "VALUATION_OVERPAY_GUARD_NOT_READY;" + extra
    attached["why_not_selected"] = attached.apply(
        lambda row: extra if row["component_shortlisted"] else (
            str(row.get("competition_blockers") or "NOT_RISK_CHAIN_CHAMPION")
            + (";" if str(row.get("competition_blockers") or "") else "")
            + "NOT_RISK_CHAIN_CHAMPION"
        ),
        axis=1,
    )
    return attached


def _post_allocation_metrics(
    *,
    config: Mapping[str, Any],
    incumbent_risk_chains: Mapping[str, str],
    candidate: Mapping[str, Any] | None,
    new_money: float,
    target_share: float,
    actual_candidate_amount: float,
) -> dict[str, float]:
    symbols = config["symbols"]
    base_total = sum(float(row["cap_total"]) for row in symbols)
    incumbent_money = new_money * (1.0 - target_share)
    issuer_amounts: dict[str, float] = {}
    chain_amounts: dict[str, float] = {}
    readiness_by_ticker = {str(row["ticker"]): row for row in readiness_records(candidate)}
    for symbol in symbols:
        ticker = str(symbol["ticker"])
        amount = float(symbol["cap_total"]) * (1.0 + incumbent_money / base_total)
        evidence = readiness_by_ticker.get(ticker) or {}
        issuer = str(evidence.get("issuer_id") or f"incumbent:{ticker}")
        chain = str(incumbent_risk_chains.get(ticker) or evidence.get("risk_chain") or "unclassified")
        issuer_amounts[issuer] = issuer_amounts.get(issuer, 0.0) + amount
        chain_amounts[chain] = chain_amounts.get(chain, 0.0) + amount
    if candidate is not None and actual_candidate_amount > 0:
        issuer = str(candidate["issuer_id"])
        chain = str(candidate["risk_chain"])
        issuer_amounts[issuer] = issuer_amounts.get(issuer, 0.0) + actual_candidate_amount
        chain_amounts[chain] = chain_amounts.get(chain, 0.0) + actual_candidate_amount
    risk_invested = sum(issuer_amounts.values())
    issuer_weights = [amount / risk_invested for amount in issuer_amounts.values()] if risk_invested else []
    chain_weights = sorted((amount / risk_invested for amount in chain_amounts.values()), reverse=True) if risk_invested else []
    return {
        "post_risk_chain_top1": chain_weights[0] if chain_weights else math.nan,
        "post_risk_chain_top3": sum(chain_weights[:3]),
        "post_issuer_top1": max(issuer_weights) if issuer_weights else math.nan,
        "post_effective_n": 1.0 / sum(weight * weight for weight in issuer_weights) if issuer_weights else math.nan,
    }


def readiness_records(candidate: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """Small hook replaced by allocation_rows while keeping metric math isolated."""
    return [] if candidate is None else list(candidate.get("_incumbent_evidence", []))


def allocation_rows(
    readiness: pd.DataFrame,
    *,
    new_money: float | None,
    lot_size: float,
    fee_bps: float,
    minimum_fee: float,
    config: Mapping[str, Any] | None = None,
    incumbent_risk_chains: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    challengers = readiness.loc[readiness["role"].eq("challenger")].copy()
    if "component_shortlisted" in challengers.columns:
        challengers = challengers.loc[challengers["component_shortlisted"]].copy()
    incumbent_evidence = readiness.loc[readiness["role"].eq("incumbent_frozen")].to_dict("records")
    rows = [{
        "action_id": "control_00pct", "ticker": "", "security_id": "", "issuer_id": "",
        "risk_chain": "", "new_money": new_money, "target_candidate_share": 0.0,
        "target_candidate_amount": 0.0 if new_money is not None else None, "whole_lot_shares": 0,
        "actual_candidate_amount": 0.0 if new_money is not None else None, "transaction_cost": 0.0 if new_money is not None else None,
        "cash_or_sgov_residual": 0.0 if new_money is not None else None, "turnover": 0.0,
        "post_risk_chain_top1": None, "post_risk_chain_top3": None, "post_issuer_top1": None,
        "post_effective_n": None, "status": "CONTROL_INCUMBENTS_ONLY_FORWARD_WATCH",
        "why_not_selected": "control action; no challenger",
    }]
    for row in challengers.to_dict("records"):
        price = float(row["strict_prior_price"]) if pd.notna(row["strict_prior_price"]) else math.nan
        for share in ALLOWED_SHARES[1:]:
            target = float(new_money) * share if new_money is not None else None
            lots = None
            actual = None
            cost = None
            residual = None
            turnover = None
            if target is not None and math.isfinite(price) and price > 0:
                lots = math.floor(target / (price * lot_size))
                actual = lots * price * lot_size
                cost = max(minimum_fee, actual * fee_bps / 10_000.0) if actual > 0 else 0.0
                while lots > 0 and actual + cost > target + 1e-9:
                    lots -= 1
                    actual = lots * price * lot_size
                    cost = max(minimum_fee, actual * fee_bps / 10_000.0) if actual > 0 else 0.0
                residual = target - actual - cost
                turnover = actual / (37_000.0 + float(new_money))
            concentration = {
                "post_risk_chain_top1": None, "post_risk_chain_top3": None,
                "post_issuer_top1": None, "post_effective_n": None,
            }
            if new_money is not None and config is not None:
                metric_candidate = {**row, "_incumbent_evidence": incumbent_evidence}
                concentration = _post_allocation_metrics(
                    config=config,
                    incumbent_risk_chains=incumbent_risk_chains or {},
                    candidate=metric_candidate,
                    new_money=float(new_money),
                    target_share=share,
                    actual_candidate_amount=float(actual or 0.0),
                )
            rows.append({
                "action_id": f"{row['ticker']}_{int(share*100):02d}pct", "ticker": row["ticker"],
                "security_id": row["security_id"], "issuer_id": row["issuer_id"], "risk_chain": row["risk_chain"],
                "new_money": new_money, "target_candidate_share": share, "target_candidate_amount": target,
                "whole_lot_shares": lots, "actual_candidate_amount": actual, "transaction_cost": cost,
                "cash_or_sgov_residual": residual, "turnover": turnover,
                **concentration,
                "status": "FORWARD_WATCH_ONLY_NOT_SELECTED", "why_not_selected": row["why_not_selected"],
            })
    return pd.DataFrame(rows)
