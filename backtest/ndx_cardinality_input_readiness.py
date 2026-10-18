"""Price and target-data readiness for point-in-time cardinality jobs."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from backtest.ndx_cardinality_discovery import (
    NdxCardinalityDiscoveryError,
    issuer_dedup_feasible_count,
)
from data.versioning import file_sha256


class NdxCardinalityInputReadinessError(ValueError):
    pass


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_price_series(path: Path) -> pd.Series:
    if not path.exists():
        raise NdxCardinalityInputReadinessError(f"price file missing: {path}")
    frame = pd.read_csv(path, usecols=["Date", "Close"])
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    if frame[["Date", "Close"]].isna().any().any():
        raise NdxCardinalityInputReadinessError(f"price file has invalid rows: {path}")
    if frame["Date"].duplicated().any() or not frame["Date"].is_monotonic_increasing:
        raise NdxCardinalityInputReadinessError(f"price dates are not unique/sorted: {path}")
    if (~np.isfinite(frame["Close"]) | frame["Close"].le(0)).any():
        raise NdxCardinalityInputReadinessError(f"price close is not positive finite: {path}")
    return frame.set_index("Date")["Close"].astype(float)


def lifecycle_identity_audit(
    memberships: pd.DataFrame,
    *,
    return_cache_dir: Path,
    identity_evidence_dir: Path,
    relative_tolerance: float = 0.02,
) -> pd.DataFrame:
    """Cross-check lifecycle tickers against verified raw evidence for identity only."""
    if not 0 < relative_tolerance < 1:
        raise NdxCardinalityInputReadinessError("identity tolerance must be in (0,1)")
    lifecycle = memberships.loc[
        memberships["price_ticker_resolution"].eq("reviewed_ticker_lifecycle")
    ]
    rows = []
    for ticker in sorted(lifecycle["ticker"].dropna().astype(str).unique()):
        return_path = return_cache_dir / f"{ticker}.csv"
        evidence_path = identity_evidence_dir / f"{ticker}.csv"
        sidecar = Path(f"{evidence_path}.manifest.json")
        status = "IDENTITY_EVIDENCE_MISSING"
        common_date = None
        return_close = evidence_close = relative_difference = None
        evidence_hash_verified = False
        try:
            if not sidecar.exists():
                raise NdxCardinalityInputReadinessError(f"identity sidecar missing: {sidecar}")
            manifest = json.loads(sidecar.read_text(encoding="utf-8"))
            evidence_hash_verified = file_sha256(evidence_path) == manifest.get("content_sha256")
            if not evidence_hash_verified:
                raise NdxCardinalityInputReadinessError("identity evidence hash mismatch")
            if manifest.get("price_basis") != "unadjusted_nominal_trade_price":
                raise NdxCardinalityInputReadinessError("unexpected identity evidence basis")
            returns = load_price_series(return_path)
            evidence = load_price_series(evidence_path)
            common = returns.index.intersection(evidence.index)
            if common.empty:
                raise NdxCardinalityInputReadinessError("return/evidence prices do not overlap")
            common_date = common.max()
            return_close = float(returns.loc[common_date])
            evidence_close = float(evidence.loc[common_date])
            relative_difference = abs(return_close / evidence_close - 1.0)
            status = (
                "IDENTITY_MATCH" if relative_difference <= relative_tolerance
                else "RETURN_CACHE_IDENTITY_MISMATCH"
            )
        except Exception as exc:
            if status == "IDENTITY_EVIDENCE_MISSING":
                status = f"IDENTITY_AUDIT_ERROR:{type(exc).__name__}"
        issuer_ids = sorted(
            lifecycle.loc[lifecycle["ticker"].eq(ticker), "issuer_id"].astype(str).unique()
        )
        rows.append({
            "ticker": ticker,
            "issuer_ids": ";".join(issuer_ids),
            "return_path": return_path.as_posix(),
            "return_sha256": file_sha256(return_path) if return_path.exists() else None,
            "identity_evidence_path": evidence_path.as_posix(),
            "identity_evidence_sha256": file_sha256(evidence_path) if evidence_path.exists() else None,
            "identity_evidence_hash_verified": evidence_hash_verified,
            "common_date": common_date.date().isoformat() if common_date is not None else None,
            "return_close": return_close,
            "identity_evidence_close": evidence_close,
            "relative_difference": relative_difference,
            "relative_tolerance": relative_tolerance,
            "identity_status": status,
            "return_usage_of_identity_evidence": False,
        })
    return pd.DataFrame(rows)


def target_nav_readiness(
    target: pd.Series,
    selection: pd.Timestamp,
    maturity: pd.Timestamp,
    *,
    endpoint_tolerance_days: int,
) -> dict[str, Any]:
    start_candidates = target.index[(target.index >= selection) & (target.index <= selection + pd.Timedelta(days=endpoint_tolerance_days))]
    end_candidates = target.index[(target.index <= maturity) & (target.index >= maturity - pd.Timedelta(days=endpoint_tolerance_days))]
    start = start_candidates.min() if len(start_candidates) else None
    end = end_candidates.max() if len(end_candidates) else None
    ready = start is not None and end is not None and end > start
    return {
        "target_nav_ready": ready,
        "target_start_date": start.date().isoformat() if start is not None else None,
        "target_end_date": end.date().isoformat() if end is not None else None,
    }


def audit_membership_inputs(
    memberships: pd.DataFrame,
    *,
    return_cache_dir: Path,
    target_nav: pd.Series,
    identity_audit: pd.DataFrame,
    fit_days: int,
    horizon_days: int,
    target_endpoint_tolerance_days: int,
) -> pd.DataFrame:
    required = {
        "universe_track", "selection_date", "maturity_date", "ticker", "security_id",
        "issuer_id", "membership_window_eligible",
    }
    missing = sorted(required - set(memberships.columns))
    if missing:
        raise NdxCardinalityInputReadinessError(f"membership columns missing: {missing}")
    if fit_days <= 0 or horizon_days <= 0:
        raise NdxCardinalityInputReadinessError("fit/horizon days must be positive")
    identity_by_ticker = (
        identity_audit.set_index("ticker")["identity_status"].to_dict()
        if not identity_audit.empty else {}
    )
    failed_identity_issuers: set[str] = set()
    if not identity_audit.empty:
        failed = identity_audit.loc[~identity_audit["identity_status"].eq("IDENTITY_MATCH")]
        for value in failed["issuer_ids"].fillna("").astype(str):
            failed_identity_issuers.update(item for item in value.split(";") if item)
    series_cache: dict[str, pd.Series] = {}
    hash_cache: dict[str, str] = {}
    target_cache: dict[tuple[str, str], dict[str, Any]] = {}
    rows = []
    work = memberships.loc[memberships["membership_window_eligible"].astype(bool)].copy()
    for row in work.itertuples(index=False):
        ticker = str(row.ticker)
        selection = pd.Timestamp(row.selection_date).normalize()
        maturity = pd.Timestamp(row.maturity_date).normalize()
        price_path = return_cache_dir / f"{ticker}.csv"
        error = ""
        try:
            if ticker not in series_cache:
                series_cache[ticker] = load_price_series(price_path)
                hash_cache[ticker] = file_sha256(price_path)
            prices = series_cache[ticker]
            fit_rows = int((prices.index < selection).sum())
            evaluation_rows = int(((prices.index >= selection) & (prices.index <= maturity)).sum())
            minimum_training_price_rows = fit_days + horizon_days + 1
            training_price_ready = fit_rows >= minimum_training_price_rows
            coverage_ready = training_price_ready and evaluation_rows >= horizon_days
        except Exception as exc:
            fit_rows = evaluation_rows = 0
            minimum_training_price_rows = fit_days + horizon_days + 1
            training_price_ready = False
            coverage_ready = False
            error = f"{type(exc).__name__}:{exc}"
        identity_status = identity_by_ticker.get(ticker, "NO_LIFECYCLE_IDENTITY_CROSSCHECK_REQUIRED")
        if str(row.issuer_id) in failed_identity_issuers:
            identity_status = "ISSUER_LIFECYCLE_IDENTITY_CHAIN_INCOMPLETE"
        identity_ready = identity_status in {
            "IDENTITY_MATCH", "NO_LIFECYCLE_IDENTITY_CROSSCHECK_REQUIRED",
        }
        target_key = (selection.date().isoformat(), maturity.date().isoformat())
        if target_key not in target_cache:
            target_cache[target_key] = target_nav_readiness(
                target_nav, selection, maturity,
                endpoint_tolerance_days=target_endpoint_tolerance_days,
            )
        target_status = target_cache[target_key]
        target_training_rows = int((target_nav.index < selection).sum())
        minimum_target_training_rows = fit_days + horizon_days + 1
        target_training_ready = target_training_rows >= minimum_target_training_rows
        ready = (
            coverage_ready and identity_ready and bool(target_status["target_nav_ready"])
            and target_training_ready
        )
        reason = (
            "READY" if ready else
            identity_status if not identity_ready else
            "PRICE_COVERAGE_INSUFFICIENT" if not coverage_ready else
            "TARGET_NAV_TRAINING_HISTORY_INSUFFICIENT" if not target_training_ready else
            "TARGET_NAV_ENDPOINT_INSUFFICIENT"
        )
        rows.append({
            "universe_track": row.universe_track,
            "selection_date": target_key[0],
            "maturity_date": target_key[1],
            "ticker": ticker,
            "security_id": row.security_id,
            "issuer_id": row.issuer_id,
            "price_path": price_path.as_posix(),
            "price_sha256": hash_cache.get(ticker),
            "fit_rows_strictly_before_selection": fit_rows,
            "minimum_fit_rows": fit_days,
            "minimum_training_price_rows": minimum_training_price_rows,
            "training_price_ready": training_price_ready,
            "evaluation_rows": evaluation_rows,
            "minimum_evaluation_rows": horizon_days,
            "identity_status": identity_status,
            "target_training_rows_strictly_before_selection": target_training_rows,
            "minimum_target_training_rows": minimum_target_training_rows,
            "target_training_ready": target_training_ready,
            **target_status,
            "input_ready": ready,
            "readiness_reason": reason,
            "error": error,
        })
    return pd.DataFrame(rows)


def rebuild_job_readiness(
    jobs: pd.DataFrame,
    membership_audit: pd.DataFrame,
    *,
    exact_limit: int,
) -> pd.DataFrame:
    if exact_limit <= 0:
        raise NdxCardinalityInputReadinessError("exact limit must be positive")
    rows = []
    for job in jobs.itertuples(index=False):
        active = membership_audit.loc[
            membership_audit["universe_track"].eq(job.universe_track)
            & membership_audit["selection_date"].eq(job.selection_date)
        ].copy()
        complete_ready = bool(len(active) and active["input_ready"].all())
        degraded = active.loc[active["input_ready"]].copy()
        degraded_issuers = int(degraded["issuer_id"].nunique())
        k = int(job.holding_count)
        feasible = issuer_dedup_feasible_count(degraded, k) if degraded_issuers >= k else 0
        degraded_ready = feasible > 0 and bool(active["target_nav_ready"].all())
        excluded = active.loc[~active["input_ready"]]
        rows.append({
            **job._asdict(),
            "complete_universe_job_ready": complete_ready,
            "degraded_research_job_ready": degraded_ready,
            "degraded_available_security_count": len(degraded),
            "degraded_available_issuer_count": degraded_issuers,
            "degraded_issuer_dedup_feasible_combinations": feasible,
            "degraded_search_method": (
                "NOT_RUNNABLE" if not degraded_ready else
                "EXACT_ENUMERATION" if feasible <= exact_limit else
                "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND"
            ),
            "excluded_issuer_ids": ";".join(sorted(excluded["issuer_id"].astype(str).unique())),
            "excluded_reasons": ";".join(sorted(excluded["readiness_reason"].astype(str).unique())),
            "promotion_allowed": False,
            "result_scope": "TRAINING_INPUT_READINESS_ONLY",
        })
    return pd.DataFrame(rows)
