"""Prospective candidate-v3 membership adapter with reviewed ticker lifecycles.

This module is a research-only, pure-data bridge.  It resolves taxonomy ticker
aliases on the decision date, then delegates the existing runtime source,
timing, track, and degraded-universe checks to the frozen candidate-v1
membership builder.  It is deliberately not registered with a generator or a
scheduler.

The adapter does not turn a current Nasdaq observation into historically or
execution-effective membership evidence.  It only prevents identities such as
``FB;META`` from being silently lost by exact ticker matching, while preserving
the issuer-level dynamic-cardinality contract.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
import re
from typing import Any

import pandas as pd

from backtest.ndx_dynamic_shadow_candidate_identity_v3 import (
    NdxDynamicShadowCandidateIdentityV3Error,
    resolve_decision_date_taxonomy_identities,
)
from backtest.ndx_dynamic_shadow_candidate_snapshot import (
    NdxDynamicShadowCandidateSnapshotError,
    TRACKS,
    build_runtime_official_eligible_membership,
)
from data.ndx_security_identity import SecurityLifecycle


class NdxDynamicShadowCandidateMembershipV3Error(ValueError):
    """Raised when the identity-v3 membership bridge cannot prove its output."""


ADAPTER_ID = "ndx_dynamic_shadow_candidate_membership_v3"
IDENTITY_RESOLVER_ID = "ndx_dynamic_shadow_candidate_identity_v3"
_TICKER_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9.\-]*")


def _ticker(value: Any, label: str) -> str:
    if pd.isna(value):
        raise NdxDynamicShadowCandidateMembershipV3Error(f"{label} is blank")
    text = str(value).strip().upper()
    if not _TICKER_PATTERN.fullmatch(text):
        raise NdxDynamicShadowCandidateMembershipV3Error(
            f"invalid {label}: {value!r}"
        )
    return text


def _aliases(value: Any) -> tuple[str, ...]:
    if pd.isna(value):
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "taxonomy ticker aliases are blank"
        )
    pieces = [part.strip() for part in str(value).split(";") if part.strip()]
    aliases = tuple(_ticker(part, "taxonomy ticker alias") for part in pieces)
    if not aliases or len(aliases) != len(set(aliases)):
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "taxonomy ticker aliases are empty or duplicated"
        )
    return aliases


def _identifier_set(values: set[str] | None, label: str) -> set[str]:
    result: set[str] = set()
    for value in values or set():
        if pd.isna(value) or not str(value).strip():
            raise NdxDynamicShadowCandidateMembershipV3Error(
                f"{label} contains a blank value"
            )
        result.add(str(value).strip())
    return result


def _ticker_set(values: set[str] | None) -> set[str]:
    return {_ticker(value, "excluded identity ticker") for value in values or set()}


def _canonical_date(value: Any, label: str) -> date:
    text = "" if pd.isna(value) else str(value).strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxDynamicShadowCandidateMembershipV3Error(f"invalid {label}") from exc
    if text != parsed.isoformat():
        raise NdxDynamicShadowCandidateMembershipV3Error(f"non-canonical {label}")
    return parsed


def _official_observation_date(
    official_membership: pd.DataFrame, decision_date: str,
) -> str:
    if "as_of_date" not in official_membership.columns:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "official membership lacks as_of_date"
        )
    decision = _canonical_date(decision_date, "decision_date")
    observed_dates = {
        _canonical_date(value, "official as_of_date")
        for value in official_membership["as_of_date"]
    }
    if len(observed_dates) != 1:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "official membership must contain one observation date"
        )
    observed = next(iter(observed_dates))
    if observed > decision:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "future official observation metadata entered decision membership"
        )
    return observed.isoformat()


def _official_source_locator(official_membership: pd.DataFrame) -> str:
    if "source_locator" not in official_membership.columns:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "official membership lacks source_locator"
        )
    locators = {
        "" if pd.isna(value) else str(value).strip()
        for value in official_membership["source_locator"]
    }
    if len(locators) != 1 or not next(iter(locators), ""):
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "official membership must contain one nonblank source locator"
        )
    return next(iter(locators))


def _lifecycle_review(lifecycle: SecurityLifecycle, decision_date: str) -> tuple[str, str]:
    mapping_id = str(lifecycle.mapping_id or "").strip()
    if not mapping_id:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "security lifecycle mapping_id is blank"
        )
    reviewed = _canonical_date(lifecycle.last_reviewed, "security lifecycle last_reviewed")
    decision = _canonical_date(decision_date, "decision_date")
    if reviewed > decision:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "security lifecycle was reviewed after the decision date"
        )
    return mapping_id, reviewed.isoformat()


def _filter_identity_issues_alias_aware(
    taxonomy_records: pd.DataFrame,
    *,
    excluded_security_ids: set[str],
    excluded_issuer_ids: set[str],
    excluded_tickers: set[str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"ticker", "security_id", "issuer_id"}
    missing = sorted(required - set(taxonomy_records.columns))
    if missing:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            f"taxonomy records missing identity issue fields: {missing}"
        )
    work = taxonomy_records.copy()
    alias_values = work["ticker"].map(_aliases)
    security_values = work["security_id"].map(
        lambda value: "" if pd.isna(value) else str(value).strip()
    )
    issuer_values = work["issuer_id"].map(
        lambda value: "" if pd.isna(value) else str(value).strip()
    )
    security_match = security_values.isin(excluded_security_ids)
    issuer_match = issuer_values.isin(excluded_issuer_ids)
    ticker_match = alias_values.map(
        lambda aliases: bool(set(aliases) & excluded_tickers)
    )
    direct_issue_mask = security_match | issuer_match | ticker_match
    # Do not let removing one bad row resurrect the same identity through a
    # later alias row, or make the resolver silently fall back to an older row
    # for the same ticker.  Propagate only through the connected security/alias
    # identity graph; an issuer is widened only when the caller explicitly
    # excluded that issuer above.
    issue_mask = direct_issue_mask.copy()
    while True:
        affected_security_ids = {
            value for value in security_values.loc[issue_mask] if value
        }
        affected_aliases = {
            alias for aliases in alias_values.loc[issue_mask] for alias in aliases
        }
        connected = (
            security_values.isin(affected_security_ids)
            | alias_values.map(lambda aliases: bool(set(aliases) & affected_aliases))
        )
        expanded = issue_mask | connected
        if expanded.equals(issue_mask):
            break
        issue_mask = expanded
    excluded_aliases = sorted({
        alias
        for aliases in alias_values.loc[issue_mask]
        for alias in aliases
    })
    evidence = {
        "directly_excluded_raw_taxonomy_row_count": int(direct_issue_mask.sum()),
        "excluded_raw_taxonomy_row_count": int(issue_mask.sum()),
        "excluded_raw_taxonomy_ticker_cells": sorted(
            work.loc[issue_mask, "ticker"].astype(str).unique()
        ),
        "excluded_raw_taxonomy_aliases": excluded_aliases,
        "excluded_by_security_id_row_count": int(security_match.sum()),
        "excluded_by_issuer_id_row_count": int(issuer_match.sum()),
        "excluded_by_ticker_alias_row_count": int(ticker_match.sum()),
        "alias_aware_pre_resolution_exclusion": True,
        "same_security_and_alias_connected_exclusion": True,
        "older_identity_fallback_allowed": False,
    }
    return work.loc[~issue_mask].reset_index(drop=True), evidence


def _post_resolution_exclusion_mask(
    resolved: pd.DataFrame,
    *,
    excluded_security_ids: set[str],
    excluded_issuer_ids: set[str],
    excluded_tickers: set[str],
) -> pd.Series:
    if resolved.empty:
        return pd.Series(False, index=resolved.index, dtype=bool)
    aliases = resolved["taxonomy_ticker_aliases"].map(_aliases)
    return (
        resolved["security_id"].astype(str).str.strip().isin(excluded_security_ids)
        | resolved["issuer_id"].astype(str).str.strip().isin(excluded_issuer_ids)
        | resolved["ticker"].map(lambda value: _ticker(value, "resolved ticker")).isin(excluded_tickers)
        | aliases.map(lambda values: bool(set(values) & excluded_tickers))
    )


def _expected_track_identity(
    resolved: pd.DataFrame,
    search_plan: Mapping[str, Any],
) -> set[tuple[str, str, str, str, str]]:
    tracks = search_plan.get("universe_tracks") or {}
    strict = set((tracks.get(TRACKS[0]) or {}).get("accepted_risk_chains") or [])
    adjacent_cfg = tracks.get(TRACKS[1]) or {}
    if not strict or adjacent_cfg.get("inherits") != TRACKS[0]:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "search-plan universe tracks are invalid"
        )
    adjacent = strict | set(adjacent_cfg.get("additional_risk_chains") or [])
    accepted = resolved.loc[
        resolved["status"].astype(str).str.lower().eq("accepted")
    ]
    expected: set[tuple[str, str, str, str, str]] = set()
    for track, chains in ((TRACKS[0], strict), (TRACKS[1], adjacent)):
        for row in accepted.loc[accepted["risk_chain"].isin(chains)].itertuples(index=False):
            expected.add((
                track,
                str(row.ticker),
                str(row.security_id),
                str(row.issuer_id),
                str(row.risk_chain),
            ))
    return expected


def _audit_final_tracks(eligible: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for track in TRACKS:
        scoped = eligible.loc[eligible["universe_track"].eq(track)]
        security_count = int(scoped["security_id"].nunique())
        issuer_count = int(scoped["issuer_id"].nunique())
        result[track] = {
            "eligible_security_count": security_count,
            "eligible_unique_issuer_count": issuer_count,
            "dynamic_k_minimum": 1,
            "dynamic_k_maximum": issuer_count,
            "dynamic_k_upper_bound_basis": "ELIGIBLE_UNIQUE_ISSUER_COUNT",
            "multiple_share_classes_do_not_increase_k_upper_bound": True,
        }
    return result


def build_runtime_official_eligible_membership_v3(
    official_membership: pd.DataFrame,
    nport_crosscheck_snapshot: pd.DataFrame,
    taxonomy_records: pd.DataFrame,
    search_plan: Mapping[str, Any],
    lifecycle: SecurityLifecycle,
    *,
    decision_date: str,
    observed_at_utc: str,
    decision_close_timestamp_utc: str,
    seal_timestamp_utc: str,
    conservative_seal_deadline_utc: str,
    allow_degraded_reviewed_taxonomy_subset: bool,
    excluded_identity_security_ids: set[str] | None = None,
    excluded_identity_issuer_ids: set[str] | None = None,
    excluded_identity_tickers: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resolve decision-date identities, then reuse the frozen membership gate.

    Identity issue exclusions are applied to every raw ticker alias before
    lifecycle resolution and repeated on normalized rows afterward.  The
    returned audit describes a dynamic issuer-count upper bound only; it does
    not grant execution, admission, promotion, or live authority.
    """

    excluded_security_ids = _identifier_set(
        excluded_identity_security_ids, "excluded identity security IDs"
    )
    excluded_issuer_ids = _identifier_set(
        excluded_identity_issuer_ids, "excluded identity issuer IDs"
    )
    excluded_tickers = _ticker_set(excluded_identity_tickers)
    official_observation_date = _official_observation_date(
        official_membership, decision_date
    )
    official_source_locator = _official_source_locator(official_membership)
    lifecycle_mapping_id, lifecycle_last_reviewed = _lifecycle_review(
        lifecycle, decision_date
    )
    filtered_taxonomy, exclusion_audit = _filter_identity_issues_alias_aware(
        taxonomy_records,
        excluded_security_ids=excluded_security_ids,
        excluded_issuer_ids=excluded_issuer_ids,
        excluded_tickers=excluded_tickers,
    )
    try:
        resolved, identity_audit = resolve_decision_date_taxonomy_identities(
            official_membership,
            filtered_taxonomy,
            lifecycle,
            decision_date=decision_date,
        )
    except NdxDynamicShadowCandidateIdentityV3Error as exc:
        raise NdxDynamicShadowCandidateMembershipV3Error(str(exc)) from exc

    post_mask = _post_resolution_exclusion_mask(
        resolved,
        excluded_security_ids=excluded_security_ids,
        excluded_issuer_ids=excluded_issuer_ids,
        excluded_tickers=excluded_tickers,
    )
    post_excluded_tickers = sorted(resolved.loc[post_mask, "ticker"].astype(str))
    resolved = resolved.loc[~post_mask].reset_index(drop=True)
    try:
        eligible, membership_audit = build_runtime_official_eligible_membership(
            official_membership,
            nport_crosscheck_snapshot,
            resolved,
            search_plan,
            decision_date=decision_date,
            observed_at_utc=observed_at_utc,
            decision_close_timestamp_utc=decision_close_timestamp_utc,
            seal_timestamp_utc=seal_timestamp_utc,
            conservative_seal_deadline_utc=conservative_seal_deadline_utc,
            allow_degraded_reviewed_taxonomy_subset=allow_degraded_reviewed_taxonomy_subset,
            excluded_identity_security_ids=excluded_security_ids,
            excluded_identity_issuer_ids=excluded_issuer_ids,
            excluded_identity_tickers=excluded_tickers,
        )
    except NdxDynamicShadowCandidateSnapshotError as exc:
        raise NdxDynamicShadowCandidateMembershipV3Error(str(exc)) from exc

    # The frozen v1 builder labels the prospective selection coordinate as the
    # membership snapshot date.  Preserve the source's actual observation date
    # in v3 so a stale current observation cannot masquerade as decision-date
    # membership.  ``selection_date`` remains the actual decision coordinate.
    eligible = eligible.copy()
    eligible["membership_snapshot_date"] = official_observation_date

    identity_columns = [
        "universe_track", "ticker", "security_id", "issuer_id", "risk_chain",
    ]
    if eligible.duplicated(["universe_track", "security_id"]).any():
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "eligible membership duplicates a security within a universe track"
        )
    actual_identity = {
        tuple(str(value) for value in row)
        for row in eligible[identity_columns].itertuples(index=False, name=None)
    }
    expected_identity = _expected_track_identity(resolved, search_plan)
    if actual_identity != expected_identity:
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "frozen membership builder changed the decision-date identity or track set"
        )

    track_audit = _audit_final_tracks(eligible)
    if any(item["dynamic_k_maximum"] < 1 for item in track_audit.values()):
        raise NdxDynamicShadowCandidateMembershipV3Error(
            "identity-v3 membership produced an empty issuer track"
        )
    audit = dict(membership_audit)
    degraded_reasons = list(audit.get("degraded_reasons") or [])
    observation_lag_days = (
        _canonical_date(decision_date, "decision_date")
        - _canonical_date(official_observation_date, "official observation date")
    ).days
    if observation_lag_days > 0:
        degraded_reasons.append("OFFICIAL_OBSERVATION_DATE_PRECEDES_DECISION")
    audit.update({
        "schema_version": 3,
        "adapter_id": ADAPTER_ID,
        "identity_resolver_id": IDENTITY_RESOLVER_ID,
        "security_lifecycle_mapping_id": lifecycle_mapping_id,
        "security_lifecycle_last_reviewed": lifecycle_last_reviewed,
        "security_lifecycle_review_not_after_decision": True,
        "identity_resolution": identity_audit,
        "identity_issue_exclusion": {
            **exclusion_audit,
            "post_resolution_excluded_tickers": post_excluded_tickers,
            "post_resolution_exclusion_rechecked": True,
        },
        "track_dynamic_cardinality": track_audit,
        "one_security_per_issuer_required": True,
        "portfolio_optimization_holding_count_policy": (
            "DYNAMIC_K_1_TO_ELIGIBLE_UNIQUE_ISSUER_COUNT"
        ),
        "migration_control_holding_count_policy": None,
        "official_membership_effective_date_proved": False,
        "official_observation_date": official_observation_date,
        "official_observation_date_not_after_decision": True,
        "official_observation_lag_calendar_days": observation_lag_days,
        "official_source_locator": official_source_locator,
        "official_source_locator_unique": True,
        "membership_snapshot_date_semantics": (
            "OFFICIAL_RUNTIME_OBSERVATION_DATE_NOT_DECISION_DATE"
        ),
        "degraded_reasons": degraded_reasons,
        "execution_valid_on_date_identity_proved": False,
        "admission_authority": False,
        "promotion_allowed": False,
        "live_mutation": False,
    })
    return eligible, audit


__all__ = [
    "ADAPTER_ID",
    "IDENTITY_RESOLVER_ID",
    "NdxDynamicShadowCandidateMembershipV3Error",
    "build_runtime_official_eligible_membership_v3",
]
