"""Prospective, point-in-time input snapshot and full dynamic-k shard planner."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import yaml

from data.versioning import file_sha256


class NdxDynamicShadowCandidateSnapshotError(ValueError):
    """Raised when a prospective monthly input cannot be proven point-in-time."""


TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
READY_STATUS = "FRESH_MONTHLY_INPUT_SNAPSHOT_AND_SHARD_PLAN_READY_NOT_ADMISSION"
MANIFEST_TYPE = "ndx_dynamic_shadow_candidate_input_snapshot"
SEARCH_CLASSES = ("EXACT_ENUMERATION", "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND")

CONTRACT_KEYS = {
    "schema_version", "generator_id", "status", "research_track",
    "migration_control_included", "schedule_contract", "universe_contract",
    "search_contract", "input_contract", "checkpoint_contract", "mutation_boundary",
}
SCHEDULE_KEYS = {
    "first_decision_not_before", "decision_time", "execution_time", "information_cutoff",
    "registration_clock_source", "caller_asof_max_skew_seconds",
    "missed_registration_window_action", "retrospective_backfill_allowed",
    "execution_date_known_at_decision_seal",
    "authoritative_next_session_date_claimed_at_decision_seal", "conservative_seal_deadline",
}
UNIVERSE_KEYS = {
    "primary_membership_source", "historical_identity_crosscheck_source",
    "source_effective_date_known", "exact_ndx_membership_claimed",
    "official_runtime_snapshot_must_be_observed_between_decision_close_and_execution_open",
    "nport_may_replace_official_runtime_snapshot", "source_conflict_may_be_silent",
    "degraded_reviewed_taxonomy_subset_requires_explicit_flag", "universe_tracks", "k_range",
    "fixed_holding_count", "one_security_per_issuer_required", "identity_keys_required",
    "identity_issue_exclusion_artifact_required", "degraded_research_may_exclude_affected_identity",
    "unresolved_identity_allowed", "unclassified_security_allowed", "complete_universe_claimed",
}
SEARCH_KEYS = {
    "exact_enumeration_max_feasible_combinations", "exact_search_label", "bounded_search_label",
    "bounded_global_optimality_claimed", "planned_shard_global_optimality_claimed",
    "planned_shard_completion_status", "required_policy_roles", "role_lane_generation_stage",
    "input_snapshot_claims_completed_lanes", "user_preference_tickers", "user_preference_role",
}
INPUT_KEYS = {
    "minimum_common_adjusted_price_rows", "training_lookback_rows",
    "nominal_price_basis", "nominal_price_liquidity_lookback_rows",
    "minimum_median_dollar_volume_usd",
    "adjusted_return_and_nominal_execution_panels_separate",
    "liquidity_exclusions_artifact_required",
    "adjusted_training_prices_must_end_on_decision_date", "target_012922_future_fill_allowed",
    "target_012922_source_date_trace_required", "source_hashes_must_be_sha256",
    "source_path_registry_required", "historical_runner_registry_read_allowed",
    "historical_candidate_snapshot_read_allowed", "frozen_forward_candidate_source_allowed",
    "frozen_original8_control_manifest_path",
}
CHECKPOINT_KEYS = {
    "key_fields", "resume_requires_exact_fingerprint", "completed_shard_overwrite_allowed",
    "partial_shard_atomic_replace_allowed", "decision_seal_requires_all_track_k_shards",
}
MUTATION_KEYS = {
    "research_output_only", "live_config_mutation_allowed", "state_mutation_allowed",
    "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
    "order_creation_allowed", "promotion_allowed",
}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowCandidateSnapshotError(f"{label} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    observed = set(value)
    if observed != expected:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{label} schema changed: missing={sorted(expected - observed)} extra={sorted(observed - expected)}"
        )


def _strict_false(value: Mapping[str, Any], key: str, label: str) -> None:
    if value.get(key) is not False:
        raise NdxDynamicShadowCandidateSnapshotError(f"{label}.{key} must remain false")


def _strict_true(value: Mapping[str, Any], key: str, label: str) -> None:
    if value.get(key) is not True:
        raise NdxDynamicShadowCandidateSnapshotError(f"{label}.{key} must remain true")


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_generator_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowCandidateSnapshotError(f"cannot read generator contract: {source}") from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowCandidateSnapshotError("generator contract must be a mapping")
    contract = dict(value)
    _exact_keys(contract, CONTRACT_KEYS, "generator contract")
    if (
        contract.get("schema_version") != 1
        or contract.get("generator_id") != "ndx_dynamic_shadow_candidate_generator_v1"
        or contract.get("research_track") != "portfolio_optimization"
        or contract.get("migration_control_included") is not False
    ):
        raise NdxDynamicShadowCandidateSnapshotError("unexpected generator identity or track")
    schedule = _mapping(contract.get("schedule_contract"), "schedule_contract")
    _exact_keys(schedule, SCHEDULE_KEYS, "schedule_contract")
    if (
        str(schedule.get("first_decision_not_before")) != "2026-10-01"
        or schedule.get("decision_time") != "completed_session_close"
        or schedule.get("execution_time")
        != "resolved_later_as_first_observed_common_session_strictly_after_decision"
        or schedule.get("information_cutoff") != "decision_close"
        or schedule.get("registration_clock_source") != "SYSTEM_UTC_NOT_CALLER_SUPPLIED"
        or int(schedule.get("caller_asof_max_skew_seconds", -1)) != 300
        or schedule.get("missed_registration_window_action") != "NO_DECISION_NO_BACKFILL"
        or schedule.get("conservative_seal_deadline")
        != "before_next_calendar_weekday_09_30_new_york"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("prospective schedule contract changed")
    _strict_false(schedule, "retrospective_backfill_allowed", "schedule_contract")
    _strict_false(schedule, "execution_date_known_at_decision_seal", "schedule_contract")
    _strict_false(
        schedule, "authoritative_next_session_date_claimed_at_decision_seal", "schedule_contract"
    )
    universe = _mapping(contract.get("universe_contract"), "universe_contract")
    _exact_keys(universe, UNIVERSE_KEYS, "universe_contract")
    if (
        universe.get("primary_membership_source") != "NASDAQ_OFFICIAL_CURRENT_RUNTIME_SNAPSHOT"
        or universe.get("historical_identity_crosscheck_source") != "QQQ_SEC_NPORT_POINT_IN_TIME_PROXY"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("prospective universe sources changed")
    for key in (
        "source_effective_date_known", "exact_ndx_membership_claimed",
        "nport_may_replace_official_runtime_snapshot", "source_conflict_may_be_silent",
        "unresolved_identity_allowed", "unclassified_security_allowed", "complete_universe_claimed",
    ):
        _strict_false(universe, key, "universe_contract")
    for key in (
        "official_runtime_snapshot_must_be_observed_between_decision_close_and_execution_open",
        "degraded_reviewed_taxonomy_subset_requires_explicit_flag", "one_security_per_issuer_required",
        "identity_issue_exclusion_artifact_required", "degraded_research_may_exclude_affected_identity",
    ):
        _strict_true(universe, key, "universe_contract")
    if tuple(universe.get("universe_tracks") or ()) != TRACKS:
        raise NdxDynamicShadowCandidateSnapshotError("universe tracks changed")
    if universe.get("k_range") != "1..point_in_time_eligible_pool_distinct_issuer_count":
        raise NdxDynamicShadowCandidateSnapshotError("dynamic k contract changed")
    if universe.get("fixed_holding_count") is not None:
        raise NdxDynamicShadowCandidateSnapshotError("fixed holding count is forbidden")
    search = _mapping(contract.get("search_contract"), "search_contract")
    _exact_keys(search, SEARCH_KEYS, "search_contract")
    if tuple(search.get("required_policy_roles") or ()) != ROLES:
        raise NdxDynamicShadowCandidateSnapshotError("five-role registry changed")
    if (
        search.get("exact_search_label") != SEARCH_CLASSES[0]
        or search.get("bounded_search_label") != SEARCH_CLASSES[1]
        or search.get("planned_shard_completion_status") != "PLANNED_NOT_EXECUTED"
        or search.get("role_lane_generation_stage") != "DOWNSTREAM_FRESH_SEARCH_AND_SELECTOR"
        or search.get("user_preference_role") != "REFERENCE_NOT_FIXED_ANSWER"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("search disclosure contract changed")
    for key in (
        "bounded_global_optimality_claimed", "planned_shard_global_optimality_claimed",
        "input_snapshot_claims_completed_lanes",
    ):
        _strict_false(search, key, "search_contract")
    inputs = _mapping(contract.get("input_contract"), "input_contract")
    _exact_keys(inputs, INPUT_KEYS, "input_contract")
    for key in (
        "historical_runner_registry_read_allowed",
        "historical_candidate_snapshot_read_allowed",
        "frozen_forward_candidate_source_allowed",
    ):
        if inputs.get(key) is not False:
            raise NdxDynamicShadowCandidateSnapshotError(f"{key} must remain false")
    _strict_false(inputs, "target_012922_future_fill_allowed", "input_contract")
    for key in (
        "adjusted_training_prices_must_end_on_decision_date",
        "target_012922_source_date_trace_required", "source_hashes_must_be_sha256",
        "source_path_registry_required", "adjusted_return_and_nominal_execution_panels_separate",
        "liquidity_exclusions_artifact_required",
    ):
        _strict_true(inputs, key, "input_contract")
    if (
        inputs.get("nominal_price_basis") != "UNADJUSTED_NOMINAL_TRADE_PRICE"
        or int(inputs.get("nominal_price_liquidity_lookback_rows", -1)) != 63
        or float(inputs.get("minimum_median_dollar_volume_usd", -1)) != 50_000_000.0
        or inputs.get("frozen_original8_control_manifest_path")
        != "data/cache/research/ndx_original_8_control_v1/manifest.json"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("nominal-price/liquidity contract changed")
    checkpoint = _mapping(contract.get("checkpoint_contract"), "checkpoint_contract")
    _exact_keys(checkpoint, CHECKPOINT_KEYS, "checkpoint_contract")
    if checkpoint.get("key_fields") != [
        "snapshot_fingerprint", "universe_track", "decision_date", "holding_count"
    ]:
        raise NdxDynamicShadowCandidateSnapshotError("checkpoint key contract changed")
    for key in (
        "resume_requires_exact_fingerprint", "partial_shard_atomic_replace_allowed",
        "decision_seal_requires_all_track_k_shards",
    ):
        _strict_true(checkpoint, key, "checkpoint_contract")
    _strict_false(checkpoint, "completed_shard_overwrite_allowed", "checkpoint_contract")
    mutation = _mapping(contract.get("mutation_boundary"), "mutation_boundary")
    _exact_keys(mutation, MUTATION_KEYS, "mutation_boundary")
    _strict_true(mutation, "research_output_only", "mutation_boundary")
    for key in MUTATION_KEYS - {"research_output_only"}:
        _strict_false(mutation, key, "mutation_boundary")
    return contract


def _utc_timestamp(value: Any, label: str) -> pd.Timestamp:
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowCandidateSnapshotError(f"invalid {label}") from exc
    if parsed.tzinfo is None:
        raise NdxDynamicShadowCandidateSnapshotError(f"{label} must be timezone-aware")
    return parsed.tz_convert("UTC")


def _normalize_eligible(
    frame: pd.DataFrame,
    decision_date: pd.Timestamp,
    decision_close_timestamp_utc: pd.Timestamp,
) -> pd.DataFrame:
    required = {
        "universe_track", "selection_date", "membership_snapshot_date", "ticker",
        "security_id", "issuer_id", "risk_chain", "evidence_available_date",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise NdxDynamicShadowCandidateSnapshotError(f"eligible membership columns missing: {missing}")
    result = frame.copy()
    for key in ("ticker", "security_id", "issuer_id", "risk_chain", "universe_track"):
        if result[key].isna().any() or result[key].astype(str).str.strip().eq("").any():
            raise NdxDynamicShadowCandidateSnapshotError(f"eligible membership has blank {key}")
        result[key] = result[key].astype(str).str.strip()
    if set(result["universe_track"]) != set(TRACKS):
        raise NdxDynamicShadowCandidateSnapshotError("eligible membership must cover both universe tracks")
    selection = pd.to_datetime(result["selection_date"], errors="raise").dt.normalize()
    snapshots = pd.to_datetime(result["membership_snapshot_date"], errors="raise").dt.normalize()
    evidence_dates = pd.to_datetime(
        result["evidence_available_date"], errors="raise", utc=True
    ).dt.tz_convert(None).dt.normalize()
    if "evidence_available_timestamp_utc" in result.columns:
        evidence_timestamps = pd.to_datetime(
            result["evidence_available_timestamp_utc"], errors="raise", utc=True
        )
        evidence_resolution = "SOURCE_TIMESTAMP"
    else:
        # A date-only disclosure does not prove an intraday publication time.
        # Treat it as available only at the conservative UTC end of that date.
        evidence_timestamps = pd.to_datetime(
            evidence_dates + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1), utc=True
        )
        evidence_resolution = "DATE_ONLY_CONSERVATIVE_UTC_END_OF_DAY"
    if not selection.eq(decision_date).all():
        raise NdxDynamicShadowCandidateSnapshotError("eligible membership selection_date must equal decision date")
    if snapshots.gt(decision_date).any() or (evidence_timestamps > decision_close_timestamp_utc).any():
        raise NdxDynamicShadowCandidateSnapshotError("future membership or taxonomy evidence entered snapshot")
    if result.duplicated(["universe_track", "security_id"]).any():
        raise NdxDynamicShadowCandidateSnapshotError("eligible membership duplicates security_id within track")
    identity = result[["security_id", "issuer_id"]].drop_duplicates()
    if identity.duplicated("security_id", keep=False).any():
        raise NdxDynamicShadowCandidateSnapshotError("security_id maps to multiple issuer_id values")
    result["selection_date"] = decision_date.date().isoformat()
    result["membership_snapshot_date"] = snapshots.dt.date.astype(str)
    result["evidence_available_date"] = evidence_dates.dt.date.astype(str)
    result["evidence_available_timestamp_utc"] = evidence_timestamps.map(lambda value: value.isoformat())
    result["evidence_availability_resolution"] = evidence_resolution
    return result.sort_values(["universe_track", "issuer_id", "security_id"]).reset_index(drop=True)


def build_runtime_official_eligible_membership(
    official_snapshot: pd.DataFrame,
    nport_crosscheck_snapshot: pd.DataFrame,
    taxonomy_records: pd.DataFrame,
    search_plan: Mapping[str, Any],
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
    """Build the prospective pool from an official runtime observation.

    Nasdaq's current page has a known fetch time but no constituent effective
    timestamp.  The QQQ N-PORT filing is therefore only an identity/lag
    cross-check and can never replace the official runtime observation.
    """
    decision = pd.Timestamp(decision_date).normalize()
    observed = pd.Timestamp(observed_at_utc)
    if observed.tzinfo is None:
        raise NdxDynamicShadowCandidateSnapshotError("official runtime observed_at must be timezone-aware")
    observed = observed.tz_convert("UTC")
    decision_close = _utc_timestamp(decision_close_timestamp_utc, "decision close timestamp")
    seal_timestamp = _utc_timestamp(seal_timestamp_utc, "decision seal timestamp")
    seal_deadline = _utc_timestamp(conservative_seal_deadline_utc, "conservative seal deadline")
    if not decision_close <= observed <= seal_timestamp:
        raise NdxDynamicShadowCandidateSnapshotError(
            "official runtime snapshot was not observed inside the decision registration window"
        )
    if seal_timestamp >= seal_deadline:
        raise NdxDynamicShadowCandidateSnapshotError(
            "official runtime snapshot missed the conservative pre-open deadline"
        )
    required_official = {"ticker", "as_of_date", "source_id", "source_type", "source_locator"}
    if not required_official.issubset(official_snapshot.columns):
        raise NdxDynamicShadowCandidateSnapshotError("official runtime snapshot columns are incomplete")
    official = official_snapshot.copy()
    official["ticker"] = official["ticker"].astype(str).str.strip().str.upper()
    if official["ticker"].eq("").any() or official["ticker"].duplicated().any():
        raise NdxDynamicShadowCandidateSnapshotError("official runtime tickers must be nonblank and unique")
    if (
        set(official["source_id"].astype(str)) != {"nasdaq_100"}
        or set(official["source_type"].astype(str)) != {"index_constituent"}
        or official["source_locator"].astype(str).str.strip().eq("").any()
    ):
        raise NdxDynamicShadowCandidateSnapshotError("official runtime snapshot source identity is invalid")
    if not 100 <= len(official) <= 110:
        raise NdxDynamicShadowCandidateSnapshotError("official runtime snapshot security count is implausible")
    nport_required = {"ticker"}
    if not nport_required.issubset(nport_crosscheck_snapshot.columns):
        raise NdxDynamicShadowCandidateSnapshotError("NPORT cross-check snapshot lacks ticker")
    nport_tickers = set(nport_crosscheck_snapshot["ticker"].astype(str).str.strip().str.upper())
    official_tickers = set(official["ticker"])

    required_taxonomy = {
        "ticker", "security_id", "issuer_id", "risk_chain", "status",
        "evidence_available_date", "selection_date_end",
    }
    missing = sorted(required_taxonomy - set(taxonomy_records.columns))
    if missing:
        raise NdxDynamicShadowCandidateSnapshotError(f"taxonomy records missing: {missing}")
    taxonomy = taxonomy_records.copy()
    taxonomy["ticker"] = taxonomy["ticker"].astype(str).str.strip().str.upper()
    excluded_security_ids = set(excluded_identity_security_ids or ())
    excluded_issuer_ids = set(excluded_identity_issuer_ids or ())
    excluded_tickers = {str(value).upper() for value in (excluded_identity_tickers or ())}
    identity_issue_mask = (
        taxonomy["security_id"].astype(str).isin(excluded_security_ids)
        | taxonomy["issuer_id"].astype(str).isin(excluded_issuer_ids)
        | taxonomy["ticker"].isin(excluded_tickers)
    )
    taxonomy = taxonomy.loc[~identity_issue_mask].copy()
    taxonomy["evidence_available_date_parsed"] = pd.to_datetime(
        taxonomy["evidence_available_date"], errors="coerce", utc=True
    ).dt.tz_convert(None).dt.normalize()
    taxonomy["selection_date_end_parsed"] = pd.to_datetime(
        taxonomy["selection_date_end"], errors="coerce"
    ).dt.normalize()
    eligible_evidence = taxonomy.loc[
        taxonomy["ticker"].isin(official_tickers)
        & taxonomy["evidence_available_date_parsed"].notna()
        & taxonomy["evidence_available_date_parsed"].le(decision)
    ].copy()
    eligible_evidence = eligible_evidence.sort_values(
        ["ticker", "selection_date_end_parsed", "evidence_available_date_parsed", "security_id"],
        kind="stable",
    ).drop_duplicates("ticker", keep="last")
    if eligible_evidence["security_id"].duplicated().any():
        raise NdxDynamicShadowCandidateSnapshotError("official tickers resolve to duplicate security_id")
    if eligible_evidence["security_id"].isna().any() or eligible_evidence["issuer_id"].isna().any():
        raise NdxDynamicShadowCandidateSnapshotError("official runtime identity resolution is incomplete")

    resolved = set(eligible_evidence["ticker"])
    missing_taxonomy = sorted(official_tickers - resolved)
    unclassified = sorted(
        eligible_evidence.loc[~eligible_evidence["status"].astype(str).str.lower().eq("accepted"), "ticker"].tolist()
    )
    official_only = sorted(official_tickers - nport_tickers)
    nport_only = sorted(nport_tickers - official_tickers)
    degraded_reasons = []
    if excluded_security_ids or excluded_issuer_ids or excluded_tickers:
        degraded_reasons.append("IDENTITY_ISSUE_SECURITIES_EXPLICITLY_EXCLUDED")
    if missing_taxonomy:
        degraded_reasons.append("OFFICIAL_TICKERS_MISSING_TAXONOMY_IDENTITY")
    if unclassified:
        degraded_reasons.append("OFFICIAL_TICKERS_UNCLASSIFIED")
    if official_only or nport_only:
        degraded_reasons.append("OFFICIAL_RUNTIME_AND_NPORT_CROSSCHECK_DIFFER")
    degraded_reasons.append("OFFICIAL_SOURCE_EFFECTIVE_DATE_UNKNOWN")
    if not allow_degraded_reviewed_taxonomy_subset:
        raise NdxDynamicShadowCandidateSnapshotError(
            "official runtime source requires explicit degraded reviewed-taxonomy-subset acknowledgement"
        )

    tracks = search_plan.get("universe_tracks") or {}
    strict = set((tracks.get("strict_technology") or {}).get("accepted_risk_chains") or [])
    adjacent_cfg = tracks.get("technology_plus_adjacent") or {}
    if not strict or adjacent_cfg.get("inherits") != "strict_technology":
        raise NdxDynamicShadowCandidateSnapshotError("search-plan universe tracks are invalid")
    adjacent = strict | set(adjacent_cfg.get("additional_risk_chains") or [])
    accepted = eligible_evidence.loc[
        eligible_evidence["status"].astype(str).str.lower().eq("accepted")
    ].copy()
    rows = []
    for track, chains in ((TRACKS[0], strict), (TRACKS[1], adjacent)):
        scoped = accepted.loc[accepted["risk_chain"].isin(chains)].copy()
        if scoped.empty:
            raise NdxDynamicShadowCandidateSnapshotError(f"official reviewed eligible track is empty: {track}")
        scoped["universe_track"] = track
        scoped["selection_date"] = decision.date().isoformat()
        scoped["membership_snapshot_date"] = decision.date().isoformat()
        scoped["official_runtime_observed_at_utc"] = observed.tz_convert("UTC").isoformat()
        scoped["membership_source"] = "NASDAQ_OFFICIAL_CURRENT_RUNTIME_SNAPSHOT"
        scoped["membership_source_effective_date_known"] = False
        rows.append(scoped)
    eligible = pd.concat(rows, ignore_index=True)
    audit = {
        "membership_source": "NASDAQ_OFFICIAL_CURRENT_RUNTIME_SNAPSHOT",
        "membership_source_effective_date_known": False,
        "exact_ndx_membership_claimed": False,
        "nport_role": "IDENTITY_AND_LAG_CROSSCHECK_NOT_PRIMARY",
        "official_security_count": len(official_tickers),
        "nport_crosscheck_security_count": len(nport_tickers),
        "official_nport_overlap_count": len(official_tickers & nport_tickers),
        "official_only_tickers": official_only,
        "nport_only_tickers": nport_only,
        "missing_taxonomy_identity_tickers": missing_taxonomy,
        "unclassified_official_tickers": unclassified,
        "excluded_identity_security_ids": sorted(excluded_security_ids),
        "excluded_identity_issuer_ids": sorted(excluded_issuer_ids),
        "excluded_identity_tickers": sorted(excluded_tickers),
        "degraded": True,
        "degraded_reasons": degraded_reasons,
        "degraded_acknowledged": True,
        "complete_universe_claimed": False,
        "source_conflict_silently_ignored": False,
    }
    return eligible, audit


def _close_series(frame: pd.DataFrame, ticker: str, decision_date: pd.Timestamp) -> tuple[pd.Series, dict[str, Any]]:
    work = frame.copy()
    if "Date" in work.columns:
        work["Date"] = pd.to_datetime(work["Date"], errors="raise")
        work = work.set_index("Date")
    else:
        work.index = pd.to_datetime(work.index, errors="raise")
    if "Close" not in work.columns:
        raise NdxDynamicShadowCandidateSnapshotError(f"{ticker} adjusted price cache lacks Close")
    work.index = pd.DatetimeIndex(work.index).tz_localize(None).normalize()
    if work.index.has_duplicates or not work.index.is_monotonic_increasing:
        raise NdxDynamicShadowCandidateSnapshotError(f"{ticker} adjusted price dates must be sorted and unique")
    values = pd.to_numeric(work["Close"], errors="raise")
    if values.isna().any() or values.le(0).any():
        raise NdxDynamicShadowCandidateSnapshotError(f"{ticker} adjusted Close contains invalid values")
    source_max = work.index.max()
    consumed = values.loc[values.index <= decision_date]
    if consumed.empty or consumed.index.max() != decision_date:
        observed = consumed.index.max().date().isoformat() if not consumed.empty else None
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} adjusted prices do not end at decision close; observed={observed}"
        )
    return consumed.rename(ticker), {
        "ticker": ticker,
        "source_max_date": source_max.date().isoformat(),
        "consumed_max_date": consumed.index.max().date().isoformat(),
        "future_rows_consumed": False,
        "rows_through_decision": len(consumed),
    }


def _nominal_close_and_liquidity(
    frame: pd.DataFrame,
    ticker: str,
    decision_date: pd.Timestamp,
    *,
    liquidity_lookback_rows: int,
) -> tuple[pd.Series, dict[str, Any]]:
    work = frame.copy()
    if "Date" in work.columns:
        work["Date"] = pd.to_datetime(work["Date"], errors="raise")
        work = work.set_index("Date")
    else:
        work.index = pd.to_datetime(work.index, errors="raise")
    required = {"Close", "Volume"}
    if not required.issubset(work.columns):
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} nominal price input lacks Close/Volume"
        )
    work.index = pd.DatetimeIndex(work.index).tz_localize(None).normalize()
    if work.index.has_duplicates or not work.index.is_monotonic_increasing:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} nominal price dates must be sorted and unique"
        )
    close = pd.to_numeric(work["Close"], errors="raise")
    volume = pd.to_numeric(work["Volume"], errors="raise")
    if close.isna().any() or close.le(0).any() or volume.isna().any() or volume.lt(0).any():
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} nominal Close/Volume contains invalid values"
        )
    source_max = work.index.max()
    consumed = pd.DataFrame({"Close": close, "Volume": volume}).loc[
        lambda value: value.index <= decision_date
    ]
    if consumed.empty or consumed.index.max() != decision_date:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} nominal prices do not end at decision close"
        )
    if len(consumed) < int(liquidity_lookback_rows):
        raise NdxDynamicShadowCandidateSnapshotError(
            f"{ticker} nominal liquidity history is insufficient"
        )
    dollar_volume = consumed["Close"] * consumed["Volume"]
    median_dollar_volume = float(dollar_volume.tail(int(liquidity_lookback_rows)).median())
    return consumed["Close"].rename(ticker), {
        "ticker": ticker,
        "nominal_source_max_date": source_max.date().isoformat(),
        "nominal_consumed_max_date": consumed.index.max().date().isoformat(),
        "nominal_future_rows_consumed": False,
        "nominal_rows_through_decision": len(consumed),
        "liquidity_lookback_rows": int(liquidity_lookback_rows),
        "median_dollar_volume_usd": median_dollar_volume,
        "nominal_price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
    }


def _target_series(
    frame: pd.DataFrame, decision_date: pd.Timestamp
) -> tuple[pd.Series, pd.Series, str]:
    work = frame.copy()
    if "Date" in work.columns:
        work["Date"] = pd.to_datetime(work["Date"], errors="raise")
        work = work.set_index("Date")
    else:
        work.index = pd.to_datetime(work.index, errors="raise")
    if "Close" not in work.columns:
        raise NdxDynamicShadowCandidateSnapshotError("012922 target NAV lacks Close")
    work.index = pd.DatetimeIndex(work.index).tz_localize(None).normalize()
    values = pd.to_numeric(work["Close"], errors="raise").sort_index()
    values = values.loc[values.index <= decision_date]
    if values.empty or values.isna().any() or values.le(0).any():
        raise NdxDynamicShadowCandidateSnapshotError("012922 target NAV is unavailable by decision cutoff")
    source_dates = pd.Series(values.index, index=values.index, name="target_012922_source_date")
    return (
        values.rename("target_012922_close"),
        source_dates,
        values.index.max().date().isoformat(),
    )


def build_fresh_candidate_input_snapshot(
    eligible_membership: pd.DataFrame,
    adjusted_price_frames: Mapping[str, pd.DataFrame],
    nominal_price_frames: Mapping[str, pd.DataFrame],
    target_nav: pd.DataFrame,
    *,
    decision_date: str,
    decision_close_timestamp_utc: str,
    seal_timestamp_utc: str,
    conservative_seal_deadline_utc: str,
    source_versions: Mapping[str, str],
    source_paths: Mapping[str, str],
    frozen_original8_tickers: list[str],
    exact_enumeration_limit: int = 50_000,
    minimum_common_price_rows: int = 252,
    training_lookback_rows: int = 505,
    nominal_liquidity_lookback_rows: int = 63,
    minimum_median_dollar_volume_usd: float = 50_000_000.0,
) -> dict[str, Any]:
    decision = pd.Timestamp(decision_date).normalize()
    decision_close = _utc_timestamp(decision_close_timestamp_utc, "decision close timestamp")
    seal_timestamp = _utc_timestamp(seal_timestamp_utc, "decision seal timestamp")
    seal_deadline = _utc_timestamp(conservative_seal_deadline_utc, "conservative seal deadline")
    if decision < pd.Timestamp("2026-10-01"):
        raise NdxDynamicShadowCandidateSnapshotError("retrospective pre-activation snapshot is forbidden")
    if seal_timestamp < decision_close:
        raise NdxDynamicShadowCandidateSnapshotError("decision snapshot was sealed before decision close")
    if seal_timestamp >= seal_deadline:
        raise NdxDynamicShadowCandidateSnapshotError(
            "decision snapshot missed the conservative pre-open seal deadline"
        )
    if decision_close.tz_convert(None).normalize() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("decision close timestamp/date mismatch")
    normalized_versions = dict(sorted((str(k), str(v)) for k, v in source_versions.items()))
    normalized_paths = dict(sorted((str(k), str(v)) for k, v in source_paths.items()))
    if not normalized_versions or set(normalized_versions) != set(normalized_paths):
        raise NdxDynamicShadowCandidateSnapshotError("source path/hash registry is incomplete")
    if any(not _is_sha256(value) for value in normalized_versions.values()):
        raise NdxDynamicShadowCandidateSnapshotError("source versions must be lowercase SHA256 values")
    if any(not value or not Path(value).is_absolute() for value in normalized_paths.values()):
        raise NdxDynamicShadowCandidateSnapshotError("source paths must be nonblank absolute paths")
    eligible_before_liquidity = _normalize_eligible(
        eligible_membership, decision, decision_close
    )
    original8_tickers = sorted({str(value).upper().strip() for value in frozen_original8_tickers})
    if len(original8_tickers) != 8 or any(not value for value in original8_tickers):
        raise NdxDynamicShadowCandidateSnapshotError("frozen original-8 ticker set is invalid")
    candidate_tickers = sorted(eligible_before_liquidity["ticker"].unique())
    all_source_tickers = sorted(set(candidate_tickers) | set(original8_tickers))
    missing_nominal = sorted(set(all_source_tickers) - set(nominal_price_frames))
    if missing_nominal:
        raise NdxDynamicShadowCandidateSnapshotError(
            f"nominal price frames missing: {missing_nominal}"
        )
    nominal_series_by_ticker: dict[str, pd.Series] = {}
    nominal_inventories: list[dict[str, Any]] = []
    for ticker in all_source_tickers:
        series, inventory = _nominal_close_and_liquidity(
            nominal_price_frames[ticker],
            ticker,
            decision,
            liquidity_lookback_rows=int(nominal_liquidity_lookback_rows),
        )
        nominal_series_by_ticker[ticker] = series
        nominal_inventories.append(inventory)
    nominal_inventory = pd.DataFrame(nominal_inventories).sort_values("ticker").reset_index(drop=True)
    passing_tickers = set(
        nominal_inventory.loc[
            nominal_inventory["ticker"].isin(candidate_tickers)
            & nominal_inventory["median_dollar_volume_usd"].ge(
                float(minimum_median_dollar_volume_usd)
            ),
            "ticker",
        ]
    )
    excluded_inventory = nominal_inventory.loc[
        nominal_inventory["ticker"].isin(candidate_tickers)
        & ~nominal_inventory["ticker"].isin(passing_tickers),
        ["ticker", "median_dollar_volume_usd", "liquidity_lookback_rows", "nominal_consumed_max_date"],
    ].copy()
    excluded_inventory["exclusion_reason"] = "MEDIAN_DOLLAR_VOLUME_BELOW_PREREGISTERED_MINIMUM"
    excluded_inventory["minimum_median_dollar_volume_usd"] = float(
        minimum_median_dollar_volume_usd
    )
    liquidity_exclusions = excluded_inventory.reset_index(drop=True)
    eligible = eligible_before_liquidity.loc[
        eligible_before_liquidity["ticker"].isin(passing_tickers)
    ].reset_index(drop=True)
    for track in TRACKS:
        if eligible.loc[eligible["universe_track"].eq(track)].empty:
            raise NdxDynamicShadowCandidateSnapshotError(
                f"liquidity-eligible issuer pool is empty: {track}"
            )
    tickers = sorted(eligible["ticker"].unique())
    panel_tickers = sorted(set(tickers) | set(original8_tickers))
    missing_prices = sorted(set(panel_tickers) - set(adjusted_price_frames))
    if missing_prices:
        raise NdxDynamicShadowCandidateSnapshotError(f"adjusted price frames missing: {missing_prices}")
    price_series: list[pd.Series] = []
    inventories: list[dict[str, Any]] = []
    for ticker in panel_tickers:
        series, inventory = _close_series(adjusted_price_frames[ticker], ticker, decision)
        price_series.append(series)
        inventories.append(inventory)
    prices = pd.concat(price_series, axis=1, join="inner").dropna()
    if len(prices) < int(minimum_common_price_rows):
        raise NdxDynamicShadowCandidateSnapshotError(
            f"common adjusted price history is insufficient: {len(prices)} < {minimum_common_price_rows}"
        )
    prices = prices.tail(int(training_lookback_rows))
    if prices.index.max() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("common adjusted price panel does not end on decision date")
    target, target_source_dates, target_asof = _target_series(target_nav, decision)
    aligned_target = target.reindex(prices.index).ffill()
    aligned_target_source_dates = target_source_dates.reindex(prices.index).ffill()
    if aligned_target.isna().any():
        raise NdxDynamicShadowCandidateSnapshotError("012922 target NAV cannot align to training price calendar")
    training = prices.copy()
    training.insert(0, "Date", training.index.date.astype(str))
    target_cutoff = pd.DataFrame({
        "Date": aligned_target.index.date.astype(str),
        "Close": aligned_target.values,
        "source_date": pd.DatetimeIndex(aligned_target_source_dates).date.astype(str),
    })
    nominal_panel = pd.concat(
        [nominal_series_by_ticker[ticker] for ticker in panel_tickers], axis=1, join="inner"
    ).dropna().tail(int(training_lookback_rows))
    if nominal_panel.empty or nominal_panel.index.max() != decision:
        raise NdxDynamicShadowCandidateSnapshotError(
            "common nominal Close panel does not end on decision date"
        )
    nominal_training = nominal_panel.copy()
    nominal_training.insert(0, "Date", nominal_training.index.date.astype(str))
    inventory = pd.DataFrame(inventories).sort_values("ticker").reset_index(drop=True).merge(
        nominal_inventory, on="ticker", how="inner", validate="one_to_one"
    )
    inventory["included_in_dynamic_eligible_pool"] = inventory["ticker"].isin(tickers)
    inventory["included_in_frozen_original8_control"] = inventory["ticker"].isin(original8_tickers)

    fingerprint_payload = {
        "decision_date": decision.date().isoformat(),
        "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        "decision_close_timestamp_utc": decision_close.isoformat(),
        "seal_timestamp_utc": seal_timestamp.isoformat(),
        "conservative_seal_deadline_utc": seal_deadline.isoformat(),
        "source_versions": normalized_versions,
        "source_paths": normalized_paths,
        "frozen_original8_tickers": original8_tickers,
        "eligible_rows_sha256": hashlib.sha256(eligible.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "price_panel_sha256": hashlib.sha256(training.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "target_panel_sha256": hashlib.sha256(target_cutoff.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "nominal_panel_sha256": hashlib.sha256(nominal_training.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "price_inventory_sha256": hashlib.sha256(inventory.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest(),
        "liquidity_exclusions_sha256": hashlib.sha256(
            liquidity_exclusions.to_csv(index=False, lineterminator="\n").encode("utf-8")
        ).hexdigest(),
    }
    fingerprint = canonical_sha256(fingerprint_payload)
    jobs: list[dict[str, Any]] = []
    for track in TRACKS:
        scoped = eligible.loc[eligible["universe_track"].eq(track)]
        issuer_count = int(scoped["issuer_id"].nunique())
        if issuer_count < 1:
            raise NdxDynamicShadowCandidateSnapshotError(f"eligible issuer pool is empty: {track}")
        for k in range(1, issuer_count + 1):
            combinations = math.comb(issuer_count, k)
            exact = combinations <= int(exact_enumeration_limit)
            jobs.append({
                "snapshot_fingerprint": fingerprint,
                "universe_track": track,
                "decision_date": decision.date().isoformat(),
                "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
                "decision_data_end": decision.date().isoformat(),
                "holding_count": k,
                "eligible_security_count": int(scoped["security_id"].nunique()),
                "eligible_issuer_count": issuer_count,
                "one_security_per_issuer_required": True,
                "theoretical_issuer_combinations": combinations,
                "job_search_class": "EXACT_ENUMERATION" if exact else "MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND",
                "search_completion_status": "PLANNED_NOT_EXECUTED",
                "global_optimality_claimed": False,
                "bounded_search_disclosure": (
                    "EXHAUSTIVE_ENUMERATION_REQUIRED_NOT_YET_EXECUTED"
                    if exact else "HEURISTIC_NO_GLOBAL_OPTIMALITY_CLAIM"
                ),
                "checkpoint_key": f"{fingerprint}/{track}/{decision.date().isoformat()}/holding_count_{k:04d}",
                "historical_candidate_replay_allowed": False,
                "promotion_allowed": False,
            })
    job_plan = pd.DataFrame(jobs)
    verify_full_dynamic_k_plan(job_plan, eligible)
    return {
        "snapshot_fingerprint": fingerprint,
        "decision_date": decision.date().isoformat(),
        "execution_date": None,
        "execution_coordinate_rule": "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION",
        "decision_close_timestamp_utc": decision_close.isoformat(),
        "seal_timestamp_utc": seal_timestamp.isoformat(),
        "conservative_seal_deadline_utc": seal_deadline.isoformat(),
        "target_012922_asof_date": target_asof,
        "eligible_securities": eligible,
        "training_adjusted_close": training.reset_index(drop=True),
        "training_nominal_close": nominal_training.reset_index(drop=True),
        "target_012922_aligned": target_cutoff.reset_index(drop=True),
        "price_input_inventory": inventory,
        "liquidity_exclusions": liquidity_exclusions,
        "minimum_median_dollar_volume_usd": float(minimum_median_dollar_volume_usd),
        "nominal_liquidity_lookback_rows": int(nominal_liquidity_lookback_rows),
        "job_plan": job_plan,
        "source_versions": normalized_versions,
        "source_paths": normalized_paths,
        "frozen_original8_tickers": original8_tickers,
    }


def verify_full_dynamic_k_plan(job_plan: pd.DataFrame, eligible: pd.DataFrame) -> None:
    required = {
        "snapshot_fingerprint", "universe_track", "decision_date", "execution_coordinate_rule",
        "decision_data_end", "holding_count", "eligible_security_count",
        "eligible_issuer_count", "one_security_per_issuer_required",
        "theoretical_issuer_combinations", "job_search_class", "search_completion_status",
        "global_optimality_claimed", "bounded_search_disclosure", "checkpoint_key",
        "historical_candidate_replay_allowed", "promotion_allowed",
    }
    _exact_keys({column: None for column in job_plan.columns}, required, "job plan columns")
    if set(job_plan["universe_track"].astype(str)) != set(TRACKS):
        raise NdxDynamicShadowCandidateSnapshotError("job plan universe track set changed")
    if not set(job_plan["job_search_class"].astype(str)).issubset(SEARCH_CLASSES):
        raise NdxDynamicShadowCandidateSnapshotError("job plan contains an unknown search class")
    if not job_plan["search_completion_status"].eq("PLANNED_NOT_EXECUTED").all():
        raise NdxDynamicShadowCandidateSnapshotError("planned shards cannot claim search completion")
    dates = {
        key: set(job_plan[key].astype(str))
        for key in ("decision_date", "execution_coordinate_rule", "decision_data_end")
    }
    if (
        any(len(values) != 1 for values in dates.values())
        or dates["decision_date"] != dates["decision_data_end"]
        or dates["execution_coordinate_rule"]
        != {"FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"}
    ):
        raise NdxDynamicShadowCandidateSnapshotError("job plan dates are internally inconsistent")
    for track in TRACKS:
        scoped_jobs = job_plan.loc[job_plan["universe_track"].eq(track)].copy()
        issuer_count = int(eligible.loc[eligible["universe_track"].eq(track), "issuer_id"].nunique())
        observed = sorted(scoped_jobs["holding_count"].astype(int).tolist())
        if observed != list(range(1, issuer_count + 1)):
            raise NdxDynamicShadowCandidateSnapshotError(f"dynamic k coordinate set is incomplete: {track}")
        if not scoped_jobs["eligible_issuer_count"].astype(int).eq(issuer_count).all():
            raise NdxDynamicShadowCandidateSnapshotError(f"eligible issuer count drifted: {track}")
        security_count = int(
            eligible.loc[eligible["universe_track"].eq(track), "security_id"].nunique()
        )
        if not scoped_jobs["eligible_security_count"].astype(int).eq(security_count).all():
            raise NdxDynamicShadowCandidateSnapshotError(f"eligible security count drifted: {track}")
        expected_combinations = scoped_jobs["holding_count"].astype(int).map(
            lambda k: math.comb(issuer_count, k)
        )
        if not scoped_jobs["theoretical_issuer_combinations"].astype(int).eq(expected_combinations).all():
            raise NdxDynamicShadowCandidateSnapshotError(f"theoretical combinations drifted: {track}")
    if job_plan["checkpoint_key"].duplicated().any():
        raise NdxDynamicShadowCandidateSnapshotError("checkpoint keys must be unique")
    replay = job_plan["historical_candidate_replay_allowed"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    if replay.any():
        raise NdxDynamicShadowCandidateSnapshotError("historical candidate replay is forbidden")
    for key in ("one_security_per_issuer_required",):
        if not job_plan[key].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        ).all():
            raise NdxDynamicShadowCandidateSnapshotError(f"job plan boundary changed: {key}")
    if job_plan["promotion_allowed"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    ).any():
        raise NdxDynamicShadowCandidateSnapshotError("planned shards cannot allow promotion")
    expected_checkpoints = job_plan.apply(
        lambda row: (
            f"{row['snapshot_fingerprint']}/{row['universe_track']}/{row['decision_date']}/"
            f"holding_count_{int(row['holding_count']):04d}"
        ),
        axis=1,
    )
    if not job_plan["checkpoint_key"].astype(str).eq(expected_checkpoints).all():
        raise NdxDynamicShadowCandidateSnapshotError("checkpoint key is not canonical")
    bounded = job_plan["job_search_class"].eq(SEARCH_CLASSES[1])
    exact = job_plan["job_search_class"].eq(SEARCH_CLASSES[0])
    claimed = job_plan["global_optimality_claimed"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    if claimed.any():
        raise NdxDynamicShadowCandidateSnapshotError(
            "a shard plan cannot claim global optimality before verified execution"
        )
    if not job_plan.loc[bounded, "bounded_search_disclosure"].eq(
        "HEURISTIC_NO_GLOBAL_OPTIMALITY_CLAIM"
    ).all() or not job_plan.loc[exact, "bounded_search_disclosure"].eq(
        "EXHAUSTIVE_ENUMERATION_REQUIRED_NOT_YET_EXECUTED"
    ).all():
        raise NdxDynamicShadowCandidateSnapshotError("bounded search cannot claim global optimality")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_snapshot_bundle(output_dir: str | Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames = {
        "eligible_securities": snapshot["eligible_securities"],
        "training_adjusted_close": snapshot["training_adjusted_close"],
        "training_nominal_close": snapshot["training_nominal_close"],
        "target_012922_aligned": snapshot["target_012922_aligned"],
        "price_input_inventory": snapshot["price_input_inventory"],
        "liquidity_exclusions": snapshot["liquidity_exclusions"],
        "job_plan": snapshot["job_plan"],
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for name, frame in frames.items():
        path = output / f"{name}.csv"
        content = frame.to_csv(index=False, lineterminator="\n")
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowCandidateSnapshotError(f"immutable snapshot collision: {path}")
        if not path.exists():
            _atomic_text(path, content)
        artifacts[name] = {"filename": path.name, "rows": len(frame), "sha256": file_sha256(path)}
    checkpoint_contract = {
        "schema_version": 1,
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "key_fields": ["snapshot_fingerprint", "universe_track", "decision_date", "holding_count"],
        "resume_requires_exact_fingerprint": True,
        "completed_shard_overwrite_allowed": False,
        "decision_seal_requires_all_track_k_shards": True,
        "missed_window_action": "NO_DECISION_NO_BACKFILL",
    }
    checkpoint_path = output / "checkpoint_contract.json"
    checkpoint_content = json.dumps(checkpoint_contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if checkpoint_path.exists() and checkpoint_path.read_text(encoding="utf-8") != checkpoint_content:
        raise NdxDynamicShadowCandidateSnapshotError(f"immutable snapshot collision: {checkpoint_path}")
    if not checkpoint_path.exists():
        _atomic_text(checkpoint_path, checkpoint_content)
    artifacts["checkpoint_contract"] = {
        "filename": checkpoint_path.name,
        "rows": 1,
        "sha256": file_sha256(checkpoint_path),
    }
    jobs = snapshot["job_plan"]
    manifest = {
        "schema_version": 1,
        "manifest_type": MANIFEST_TYPE,
        "status": READY_STATUS,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "decision_date": snapshot["decision_date"],
        "execution_date": snapshot["execution_date"],
        "execution_coordinate_rule": snapshot["execution_coordinate_rule"],
        "information_cutoff": snapshot["decision_date"],
        "decision_close_timestamp_utc": snapshot["decision_close_timestamp_utc"],
        "seal_timestamp_utc": snapshot["seal_timestamp_utc"],
        "conservative_seal_deadline_utc": snapshot["conservative_seal_deadline_utc"],
        "snapshot_fingerprint": snapshot["snapshot_fingerprint"],
        "target_012922_asof_date": snapshot["target_012922_asof_date"],
        "nominal_price_basis": "UNADJUSTED_NOMINAL_TRADE_PRICE",
        "nominal_liquidity_lookback_rows": snapshot["nominal_liquidity_lookback_rows"],
        "minimum_median_dollar_volume_usd": snapshot["minimum_median_dollar_volume_usd"],
        "liquidity_excluded_ticker_count": len(snapshot["liquidity_exclusions"]),
        "frozen_original8_tickers": list(snapshot["frozen_original8_tickers"]),
        "universe_tracks": list(TRACKS),
        "dynamic_k": "1..point_in_time_eligible_pool_distinct_issuer_count",
        "track_k_shard_count": len(jobs),
        "exact_shard_count": int(jobs["job_search_class"].eq("EXACT_ENUMERATION").sum()),
        "bounded_shard_count": int(jobs["job_search_class"].eq("MULTIOBJECTIVE_BEAM_BRANCH_AND_BOUND").sum()),
        "bounded_global_optimality_claimed": False,
        "planned_shard_global_optimality_claimed": False,
        "required_policy_roles": list(ROLES),
        "expected_independent_lane_count": len(TRACKS) * len(ROLES),
        "completed_policy_lane_count": 0,
        "input_snapshot_claims_completed_lanes": False,
        "candidate_results_complete": False,
        "historical_runner_registry_read": False,
        "historical_candidate_snapshot_read": False,
        "frozen_forward_candidate_source_used": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_mutation": False,
        "source_versions": dict(snapshot["source_versions"]),
        "source_paths": dict(snapshot["source_paths"]),
        "membership_evidence_role": "DIAGNOSTIC_SOURCE_DISCLOSURE_NOT_READINESS_FACT",
        "membership_evidence": dict(snapshot.get("membership_evidence") or {}),
        "artifacts": artifacts,
    }
    manifest_path = output / "manifest.json"
    content = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != content:
        raise NdxDynamicShadowCandidateSnapshotError(f"immutable snapshot collision: {manifest_path}")
    if not manifest_path.exists():
        _atomic_text(manifest_path, content)
    verify_snapshot_bundle(manifest_path)
    return manifest


def verify_snapshot_bundle(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateSnapshotError(f"cannot read snapshot manifest: {path}") from exc
    if manifest.get("manifest_type") != MANIFEST_TYPE or manifest.get("status") != READY_STATUS:
        raise NdxDynamicShadowCandidateSnapshotError("unexpected snapshot manifest identity")
    expected_manifest_keys = {
        "schema_version", "manifest_type", "status", "research_track",
        "migration_control_included", "decision_date", "execution_date", "execution_coordinate_rule",
        "information_cutoff", "decision_close_timestamp_utc", "seal_timestamp_utc",
        "conservative_seal_deadline_utc",
        "snapshot_fingerprint", "target_012922_asof_date", "nominal_price_basis",
        "nominal_liquidity_lookback_rows", "minimum_median_dollar_volume_usd",
        "liquidity_excluded_ticker_count",
        "frozen_original8_tickers",
        "universe_tracks", "dynamic_k", "track_k_shard_count", "exact_shard_count",
        "bounded_shard_count", "bounded_global_optimality_claimed",
        "planned_shard_global_optimality_claimed", "required_policy_roles",
        "expected_independent_lane_count", "completed_policy_lane_count",
        "input_snapshot_claims_completed_lanes", "candidate_results_complete",
        "historical_runner_registry_read", "historical_candidate_snapshot_read",
        "frozen_forward_candidate_source_used", "fresh_oos_consumed", "promotion_allowed",
        "live_mutation", "source_versions", "source_paths", "membership_evidence_role",
        "membership_evidence", "artifacts",
    }
    _exact_keys(manifest, expected_manifest_keys, "snapshot manifest")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("research_track") != "portfolio_optimization"
        or manifest.get("migration_control_included") is not False
        or manifest.get("information_cutoff") != manifest.get("decision_date")
        or manifest.get("execution_date") is not None
        or manifest.get("execution_coordinate_rule")
        != "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
        or manifest.get("universe_tracks") != list(TRACKS)
        or manifest.get("dynamic_k") != "1..point_in_time_eligible_pool_distinct_issuer_count"
        or manifest.get("required_policy_roles") != list(ROLES)
        or manifest.get("nominal_price_basis") != "UNADJUSTED_NOMINAL_TRADE_PRICE"
        or int(manifest.get("nominal_liquidity_lookback_rows", -1)) != 63
        or float(manifest.get("minimum_median_dollar_volume_usd", -1)) != 50_000_000.0
        or not isinstance(manifest.get("frozen_original8_tickers"), list)
        or len(set(manifest.get("frozen_original8_tickers") or ())) != 8
        or int(manifest.get("expected_independent_lane_count", -1)) != 10
        or int(manifest.get("completed_policy_lane_count", -1)) != 0
        or manifest.get("membership_evidence_role")
        != "DIAGNOSTIC_SOURCE_DISCLOSURE_NOT_READINESS_FACT"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("snapshot semantic contract changed")
    for key in (
        "historical_runner_registry_read", "historical_candidate_snapshot_read",
        "frozen_forward_candidate_source_used", "fresh_oos_consumed", "promotion_allowed",
        "live_mutation", "bounded_global_optimality_claimed",
        "planned_shard_global_optimality_claimed", "input_snapshot_claims_completed_lanes",
        "candidate_results_complete",
    ):
        if manifest.get(key) is not False:
            raise NdxDynamicShadowCandidateSnapshotError(f"snapshot boundary changed: {key}")
    artifact_registry = _mapping(manifest.get("artifacts"), "snapshot artifacts")
    required_artifacts = {
        "eligible_securities", "training_adjusted_close", "training_nominal_close",
        "target_012922_aligned", "price_input_inventory", "liquidity_exclusions",
        "job_plan", "checkpoint_contract",
    }
    _exact_keys(artifact_registry, required_artifacts, "snapshot artifacts")
    frames: dict[str, pd.DataFrame] = {}
    for name, artifact in artifact_registry.items():
        artifact = _mapping(artifact, f"snapshot artifact {name}")
        _exact_keys(artifact, {"filename", "rows", "sha256"}, f"snapshot artifact {name}")
        filename = str(artifact.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise NdxDynamicShadowCandidateSnapshotError(f"invalid artifact filename: {name}")
        artifact_path = path.parent / filename
        if not artifact_path.is_file() or file_sha256(artifact_path) != artifact.get("sha256"):
            raise NdxDynamicShadowCandidateSnapshotError(f"artifact hash mismatch: {name}")
        if artifact_path.suffix == ".csv":
            frame = pd.read_csv(artifact_path, low_memory=False)
            if len(frame) != int(artifact.get("rows", -1)):
                raise NdxDynamicShadowCandidateSnapshotError(f"artifact row count mismatch: {name}")
            frames[name] = frame
    required = required_artifacts - {"checkpoint_contract"}
    if not required.issubset(frames):
        raise NdxDynamicShadowCandidateSnapshotError("snapshot artifacts are incomplete")
    verify_full_dynamic_k_plan(frames["job_plan"], frames["eligible_securities"])
    decision = pd.Timestamp(manifest["decision_date"]).normalize()
    decision_close = _utc_timestamp(manifest["decision_close_timestamp_utc"], "decision close timestamp")
    seal_timestamp = _utc_timestamp(manifest["seal_timestamp_utc"], "decision seal timestamp")
    seal_deadline = _utc_timestamp(
        manifest["conservative_seal_deadline_utc"], "conservative seal deadline"
    )
    if (
        decision < pd.Timestamp("2026-10-01")
        or seal_timestamp < decision_close
        or seal_timestamp >= seal_deadline
    ):
        raise NdxDynamicShadowCandidateSnapshotError("snapshot decision/seal timing is invalid")
    if decision_close.tz_convert(None).normalize() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("snapshot decision close timestamp/date mismatch")
    if pd.to_datetime(frames["training_adjusted_close"]["Date"], errors="raise").max().normalize() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("sealed training price cutoff changed")
    if pd.to_datetime(frames["training_nominal_close"]["Date"], errors="raise").max().normalize() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("sealed nominal price cutoff changed")
    if pd.to_datetime(frames["target_012922_aligned"]["Date"], errors="raise").max().normalize() != decision:
        raise NdxDynamicShadowCandidateSnapshotError("aligned target calendar cutoff changed")
    if set(frames["target_012922_aligned"].columns) != {"Date", "Close", "source_date"}:
        raise NdxDynamicShadowCandidateSnapshotError("aligned target source-date trace is missing")
    target_dates = pd.to_datetime(frames["target_012922_aligned"]["Date"], errors="raise").dt.normalize()
    target_source_dates = pd.to_datetime(
        frames["target_012922_aligned"]["source_date"], errors="raise"
    ).dt.normalize()
    if target_source_dates.gt(target_dates).any() or target_source_dates.max().date().isoformat() != manifest.get(
        "target_012922_asof_date"
    ):
        raise NdxDynamicShadowCandidateSnapshotError("012922 source-date trace violates no-future cutoff")
    if not frames["job_plan"]["snapshot_fingerprint"].eq(manifest["snapshot_fingerprint"]).all():
        raise NdxDynamicShadowCandidateSnapshotError("job plan fingerprint mismatch")
    if not frames["job_plan"]["decision_date"].astype(str).eq(manifest["decision_date"]).all():
        raise NdxDynamicShadowCandidateSnapshotError("job plan decision date mismatch")
    if not frames["job_plan"]["decision_data_end"].astype(str).eq(manifest["decision_date"]).all():
        raise NdxDynamicShadowCandidateSnapshotError("job plan information cutoff mismatch")
    if not frames["job_plan"]["execution_coordinate_rule"].astype(str).eq(
        manifest["execution_coordinate_rule"]
    ).all():
        raise NdxDynamicShadowCandidateSnapshotError("job plan execution-coordinate rule mismatch")
    if not frames["eligible_securities"]["selection_date"].astype(str).eq(manifest["decision_date"]).all():
        raise NdxDynamicShadowCandidateSnapshotError("eligible membership decision coordinate mismatch")
    eligible_tickers = set(frames["eligible_securities"]["ticker"].astype(str))
    original8_tickers = set(manifest["frozen_original8_tickers"])
    required_panel_tickers = eligible_tickers | original8_tickers
    adjusted_tickers = set(frames["training_adjusted_close"].columns) - {"Date"}
    nominal_tickers = set(frames["training_nominal_close"].columns) - {"Date"}
    if required_panel_tickers != adjusted_tickers or required_panel_tickers != nominal_tickers:
        raise NdxDynamicShadowCandidateSnapshotError(
            "eligible/adjusted/nominal ticker sets are inconsistent"
        )
    inventory = frames["price_input_inventory"]
    required_inventory = {
        "ticker", "median_dollar_volume_usd", "liquidity_lookback_rows",
        "nominal_consumed_max_date", "nominal_price_basis",
        "included_in_dynamic_eligible_pool", "included_in_frozen_original8_control",
    }
    if not required_inventory.issubset(inventory.columns) or set(inventory["ticker"].astype(str)) != required_panel_tickers:
        raise NdxDynamicShadowCandidateSnapshotError("nominal price inventory is incomplete")
    inventory_dynamic = inventory.set_index(inventory["ticker"].astype(str))[
        "included_in_dynamic_eligible_pool"
    ].map(lambda value: value is True or str(value).strip().lower() == "true")
    inventory_original8 = inventory.set_index(inventory["ticker"].astype(str))[
        "included_in_frozen_original8_control"
    ].map(lambda value: value is True or str(value).strip().lower() == "true")
    if set(inventory_dynamic.index[inventory_dynamic]) != eligible_tickers or set(
        inventory_original8.index[inventory_original8]
    ) != original8_tickers:
        raise NdxDynamicShadowCandidateSnapshotError("price inventory role mapping changed")
    if (
        not pd.to_numeric(
            inventory.loc[inventory["ticker"].astype(str).isin(eligible_tickers), "median_dollar_volume_usd"],
            errors="raise",
        ).ge(float(manifest["minimum_median_dollar_volume_usd"])).all()
        or not pd.to_numeric(inventory["liquidity_lookback_rows"], errors="raise").eq(
            int(manifest["nominal_liquidity_lookback_rows"])
        ).all()
        or not inventory["nominal_price_basis"].eq("UNADJUSTED_NOMINAL_TRADE_PRICE").all()
        or not pd.to_datetime(inventory["nominal_consumed_max_date"], errors="raise").dt.normalize().eq(
            decision
        ).all()
    ):
        raise NdxDynamicShadowCandidateSnapshotError("preregistered nominal liquidity gate changed")
    exclusions = frames["liquidity_exclusions"]
    if len(exclusions) != int(manifest["liquidity_excluded_ticker_count"]):
        raise NdxDynamicShadowCandidateSnapshotError("liquidity exclusion count mismatch")
    if not exclusions.empty:
        if set(exclusions["ticker"].astype(str)) & eligible_tickers:
            raise NdxDynamicShadowCandidateSnapshotError("liquidity-excluded ticker entered eligible pool")
        if not pd.to_numeric(exclusions["median_dollar_volume_usd"], errors="raise").lt(
            float(manifest["minimum_median_dollar_volume_usd"])
        ).all():
            raise NdxDynamicShadowCandidateSnapshotError("liquidity exclusion is not reproducible")
    versions = _mapping(manifest.get("source_versions"), "source_versions")
    source_paths = _mapping(manifest.get("source_paths"), "source_paths")
    if not versions or set(versions) != set(source_paths) or any(not _is_sha256(value) for value in versions.values()):
        raise NdxDynamicShadowCandidateSnapshotError("source path/hash registry is invalid")
    if any(not value or not Path(str(value)).is_absolute() for value in source_paths.values()):
        raise NdxDynamicShadowCandidateSnapshotError("source path registry contains a non-absolute path")
    fingerprint_payload = {
        "decision_date": manifest["decision_date"],
        "execution_coordinate_rule": manifest["execution_coordinate_rule"],
        "decision_close_timestamp_utc": decision_close.isoformat(),
        "seal_timestamp_utc": seal_timestamp.isoformat(),
        "conservative_seal_deadline_utc": seal_deadline.isoformat(),
        "source_versions": dict(sorted((str(k), str(v)) for k, v in versions.items())),
        "source_paths": dict(sorted((str(k), str(v)) for k, v in source_paths.items())),
        "frozen_original8_tickers": sorted(str(value) for value in manifest["frozen_original8_tickers"]),
        "eligible_rows_sha256": artifact_registry["eligible_securities"]["sha256"],
        "price_panel_sha256": artifact_registry["training_adjusted_close"]["sha256"],
        "target_panel_sha256": artifact_registry["target_012922_aligned"]["sha256"],
        "nominal_panel_sha256": artifact_registry["training_nominal_close"]["sha256"],
        "price_inventory_sha256": artifact_registry["price_input_inventory"]["sha256"],
        "liquidity_exclusions_sha256": artifact_registry["liquidity_exclusions"]["sha256"],
    }
    if canonical_sha256(fingerprint_payload) != manifest["snapshot_fingerprint"]:
        raise NdxDynamicShadowCandidateSnapshotError("snapshot fingerprint cannot be reproduced")
    if int(manifest["track_k_shard_count"]) != len(frames["job_plan"]):
        raise NdxDynamicShadowCandidateSnapshotError("track-k shard count mismatch")
    observed_exact = int(frames["job_plan"]["job_search_class"].eq(SEARCH_CLASSES[0]).sum())
    observed_bounded = int(frames["job_plan"]["job_search_class"].eq(SEARCH_CLASSES[1]).sum())
    if int(manifest["exact_shard_count"]) != observed_exact or int(manifest["bounded_shard_count"]) != observed_bounded:
        raise NdxDynamicShadowCandidateSnapshotError("search-class shard counts mismatch")
    checkpoint_path = path.parent / artifact_registry["checkpoint_contract"]["filename"]
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowCandidateSnapshotError("checkpoint contract is invalid") from exc
    expected_checkpoint = {
        "schema_version": 1,
        "snapshot_fingerprint": manifest["snapshot_fingerprint"],
        "key_fields": ["snapshot_fingerprint", "universe_track", "decision_date", "holding_count"],
        "resume_requires_exact_fingerprint": True,
        "completed_shard_overwrite_allowed": False,
        "decision_seal_requires_all_track_k_shards": True,
        "missed_window_action": "NO_DECISION_NO_BACKFILL",
    }
    if checkpoint != expected_checkpoint:
        raise NdxDynamicShadowCandidateSnapshotError("checkpoint contract semantics changed")
    return manifest


__all__ = [
    "MANIFEST_TYPE", "NdxDynamicShadowCandidateSnapshotError", "READY_STATUS",
    "build_fresh_candidate_input_snapshot", "build_runtime_official_eligible_membership",
    "canonical_sha256", "load_generator_contract",
    "verify_full_dynamic_k_plan", "verify_snapshot_bundle", "write_snapshot_bundle",
]
