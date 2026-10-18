"""Pure validation and construction for the challenger forward registry."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date

import pandas as pd

from scripts.ndx_cardinality_frontier_attribution import parse_weight_string


class NdxChallengerForwardRegistryError(ValueError):
    pass


def _boolean_series(series: pd.Series, field: str) -> pd.Series:
    mapped = series.map(lambda value: value if isinstance(value, bool) else {
        "true": True, "false": False,
    }.get(str(value).strip().lower()))
    if mapped.isna().any():
        raise NdxChallengerForwardRegistryError(f"invalid boolean field: {field}")
    return mapped.astype(bool)


def validate_forward_spec(spec: Mapping[str, object]) -> None:
    if int(spec.get("schema_version") or 0) != 1:
        raise NdxChallengerForwardRegistryError("forward registry schema_version must be 1")
    if spec.get("status") != "PRE_REGISTERED_FORWARD_ONLY_NOT_ADMISSION":
        raise NdxChallengerForwardRegistryError("forward registry status changed")
    for field in ("safe_leg_included", "external_index_included", "personal_off_strategy_positions_included"):
        if spec.get(field) is not False:
            raise NdxChallengerForwardRegistryError(f"forward scope violation: {field}")
    candidate = spec.get("candidate_contract") or {}
    forward = spec.get("forward_contract") or {}
    promotion = spec.get("promotion_contract") or {}
    if not isinstance(candidate, Mapping) or not isinstance(forward, Mapping) or not isinstance(promotion, Mapping):
        raise NdxChallengerForwardRegistryError("forward registry contract sections are invalid")
    required_true = (
        "failed_controls_preserved", "source_roles_are_independent",
        "target_weights_frozen_at_registration", "historical_whole_lot_shares_are_audit_only",
        "future_whole_lot_shares_must_be_resized_from_cohort_cash_and_prior_close",
    )
    if any(candidate.get(key) is not True for key in required_true) or candidate.get("composite_score_used") is not False:
        raise NdxChallengerForwardRegistryError("candidate freeze contract changed")
    frozen_entries = candidate.get("frozen_entries")
    if not isinstance(frozen_entries, list) or not frozen_entries:
        raise NdxChallengerForwardRegistryError("candidate freeze list must be explicit and non-empty")
    frozen_identities = []
    for entry in frozen_entries:
        if not isinstance(entry, Mapping):
            raise NdxChallengerForwardRegistryError("candidate freeze entry is invalid")
        identity = (str(entry.get("candidate_id") or ""), str(entry.get("selection_role") or ""))
        if not all(identity) or not str(entry.get("rationale") or ""):
            raise NdxChallengerForwardRegistryError("candidate freeze entry is incomplete")
        frozen_identities.append(identity)
    if len(set(frozen_identities)) != len(frozen_identities):
        raise NdxChallengerForwardRegistryError("candidate freeze identity is duplicated")
    if int(forward.get("primary_horizon_trading_days") or 0) != 126:
        raise NdxChallengerForwardRegistryError("primary forward horizon must remain 126 trading days")
    if int(forward.get("minimum_fresh_mature_cohorts") or 0) < 12:
        raise NdxChallengerForwardRegistryError("fresh cohort minimum cannot be below 12")
    if int(forward.get("minimum_distinct_regimes") or 0) < 2:
        raise NdxChallengerForwardRegistryError("forward watch needs at least two regimes")
    if forward.get("cohort_frequency") != "monthly_first_completed_us_trading_session":
        raise NdxChallengerForwardRegistryError("monthly cohort convention changed")
    if forward.get("observation_price") != "completed_session_close":
        raise NdxChallengerForwardRegistryError("observation price convention changed")
    if forward.get("entry") != "first_common_session_open_strictly_after_observation_date":
        raise NdxChallengerForwardRegistryError("forward entry convention changed")
    if float(forward.get("standardized_execution_cash_usd") or 0) <= 0:
        raise NdxChallengerForwardRegistryError("standardized execution cash must be positive")
    registry_id = str(spec.get("registry_id") or "")
    if registry_id.endswith(("_v4", "_v5")):
        if forward.get("standardized_execution_cash_role") != "full_sleeve_comparison_capital_not_incremental_funding":
            raise NdxChallengerForwardRegistryError("versioned execution capital role is invalid")
        if forward.get("capital_feasibility_uses_return_data") is not False:
            raise NdxChallengerForwardRegistryError("capital feasibility cannot use returns")
        dates = forward.get("capital_feasibility_observation_dates")
        if not isinstance(dates, list) or not dates:
            raise NdxChallengerForwardRegistryError("capital feasibility observations are missing")
        if forward.get("cohort_version_reset_required") is not True:
            raise NdxChallengerForwardRegistryError("versioned registry must reset its fresh cohort chain")
    first_fresh = str(forward.get("first_fresh_observation_on_or_after") or "")
    if first_fresh:
        try:
            first_fresh_date = date.fromisoformat(first_fresh)
            registration_date = date.fromisoformat(str(spec.get("registration_date") or ""))
        except ValueError as exc:
            raise NdxChallengerForwardRegistryError("forward registry dates are invalid") from exc
        if first_fresh_date < registration_date:
            raise NdxChallengerForwardRegistryError(
                "first fresh cohort cannot precede registry registration"
            )
    if registry_id.endswith("_v5"):
        if not first_fresh or first_fresh_date < date(2026, 10, 1):
            raise NdxChallengerForwardRegistryError(
                "v5 first fresh observation must remain on or after 2026-10-01"
            )
    if float(forward.get("minimum_cash_buffer_usd") or 0) < 0:
        raise NdxChallengerForwardRegistryError("minimum cash buffer cannot be negative")
    liquidity_lookback = int(forward.get("liquidity_lookback_trading_days") or 0)
    liquidity_observations = int(forward.get("minimum_liquidity_observations") or 0)
    if liquidity_lookback <= 0 or liquidity_observations <= 0 or liquidity_observations > liquidity_lookback:
        raise NdxChallengerForwardRegistryError("forward liquidity observation contract is invalid")
    if float(forward.get("minimum_median_dollar_volume_usd") or 0) != 50_000_000.0:
        raise NdxChallengerForwardRegistryError("forward liquidity threshold must remain 50 million USD")
    if forward.get("selection_date_or_later_data_for_registration_allowed") is not False:
        raise NdxChallengerForwardRegistryError("registration cannot consume forward data")
    if any(promotion.get(key) is not True for key in (
        "fresh_oos_required", "incumbent_p50_p10_and_drawdown_p50_p90_required",
        "target_012922_envelope_required", "execution_cost_liquidity_and_risk_chain_required",
        "today_diff_and_rollback_required", "user_confirmation_required",
    )):
        raise NdxChallengerForwardRegistryError("promotion gates are incomplete")
    if promotion.get("promotion_allowed_at_registration") is not False or promotion.get("live_mutation_allowed") is not False:
        raise NdxChallengerForwardRegistryError("registration unexpectedly permits live mutation")
    policy = promotion.get("policy_gate") or {}
    if not isinstance(policy, Mapping):
        raise NdxChallengerForwardRegistryError("forward policy gate is invalid")
    expected_zero = (
        "paired_return_p50_minimum", "paired_return_p10_minimum",
        "paired_drawdown_cost_p50_maximum", "paired_drawdown_cost_p90_maximum",
    )
    if any(float(policy.get(key, float("nan"))) != 0.0 for key in expected_zero):
        raise NdxChallengerForwardRegistryError("forward non-inferiority thresholds must remain zero")
    if any(policy.get(key) is not True for key in (
        "require_continuous_and_execution_tracks",
        "require_at_least_one_strict_incumbent_improvement",
    )):
        raise NdxChallengerForwardRegistryError("forward policy gate requirements are incomplete")
    if registry_id.endswith("_v5"):
        if (
            policy.get("target_012922_componentwise_not_worse_than_original_8") is not True
            or policy.get("target_012922_scalar_l1_used_for_admission") is not False
            or policy.get("require_at_least_one_strict_target_dimension_improvement") is not True
            or policy.get("target_012922_distance_not_worse_than_original_8") is True
        ):
            raise NdxChallengerForwardRegistryError(
                "v5 target gate must be componentwise with one strict improvement"
            )
    elif (
        policy.get("target_012922_distance_not_worse_than_original_8") is not True
        and policy.get("target_012922_componentwise_not_worse_than_original_8") is not True
    ):
        raise NdxChallengerForwardRegistryError("forward target policy gate is incomplete")


def validate_registry_spec_binding(
    registry_manifest: Mapping[str, object],
    spec: Mapping[str, object],
    *,
    spec_sha256: str,
) -> None:
    """Require a registry and its policy spec to be one immutable snapshot."""
    if registry_manifest.get("manifest_type") != "ndx_pure_equity_challenger_forward_registry":
        raise NdxChallengerForwardRegistryError("unexpected forward registry manifest")
    if registry_manifest.get("registry_id") != spec.get("registry_id"):
        raise NdxChallengerForwardRegistryError("forward registry/spec id mismatch")
    inputs = registry_manifest.get("inputs") or {}
    if not isinstance(inputs, Mapping):
        raise NdxChallengerForwardRegistryError("forward registry inputs are invalid")
    frozen_spec = inputs.get("spec") or {}
    if not isinstance(frozen_spec, Mapping) or frozen_spec.get("sha256") != str(spec_sha256):
        raise NdxChallengerForwardRegistryError("forward registry/spec hash mismatch")
    if registry_manifest.get("promotion_allowed") is not False:
        raise NdxChallengerForwardRegistryError("forward registry unexpectedly permits promotion")


def build_forward_registry(master: pd.DataFrame, spec: Mapping[str, object]) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_forward_spec(spec)
    required = {
        "candidate_id", "action_scope", "selection_role", "candidate_tickers",
        "candidate_weights", "whole_lot_shares", "execution_status", "evidence_status",
        "portfolio_scope", "safe_leg_included", "external_index_included", "promotion_allowed",
    }
    if not required.issubset(master.columns):
        raise NdxChallengerForwardRegistryError(f"master columns missing: {sorted(required-set(master.columns))}")
    if len(master) == 0:
        raise NdxChallengerForwardRegistryError("challenger master is empty")
    if master[["candidate_id", "selection_role"]].duplicated().any():
        raise NdxChallengerForwardRegistryError("candidate-role identity is duplicated")
    if _boolean_series(master["safe_leg_included"], "safe_leg_included").any() or _boolean_series(
        master["external_index_included"], "external_index_included"
    ).any():
        raise NdxChallengerForwardRegistryError("master scope includes an external or safe leg")
    if _boolean_series(master["promotion_allowed"], "promotion_allowed").any():
        raise NdxChallengerForwardRegistryError("master unexpectedly permits promotion")
    if not master["portfolio_scope"].astype(str).eq("HSBC_US_EQUITY_SLEEVE_ONLY").all():
        raise NdxChallengerForwardRegistryError("master portfolio scope changed")
    allowed_scopes = {"ADD_ONLY", "SINGLE_REPLACEMENT", "DOUBLE_REPLACEMENT", "VARIABLE_CARDINALITY"}
    if not set(master["action_scope"].astype(str)).issubset(allowed_scopes):
        raise NdxChallengerForwardRegistryError("master action scope is not allowed")
    active_status = str((spec["candidate_contract"] or {})["active_execution_status"])
    frozen_entries = spec["candidate_contract"]["frozen_entries"]
    frozen = {
        (str(entry["candidate_id"]), str(entry["selection_role"])): str(entry["rationale"])
        for entry in frozen_entries
    }
    master_identities = set(zip(master["candidate_id"].astype(str), master["selection_role"].astype(str)))
    missing_frozen = sorted(set(frozen) - master_identities)
    if missing_frozen:
        raise NdxChallengerForwardRegistryError(f"frozen candidates missing from master: {missing_frozen}")
    rows = []
    for row in master.to_dict("records"):
        weights = parse_weight_string(row["candidate_weights"])
        tickers = sorted(item for item in str(row["candidate_tickers"]).split(";") if item)
        if sorted(weights) != tickers:
            raise NdxChallengerForwardRegistryError(f"ticker/weight mismatch: {row['candidate_id']}")
        candidate_identity = (str(row["candidate_id"]), str(row["selection_role"]))
        selected = candidate_identity in frozen
        identity = f"{row['candidate_id']}|{row['selection_role']}|{row['candidate_weights']}"
        if row["execution_status"] != active_status:
            registry_status = "FAILED_EXECUTION_CONTROL"
        elif selected:
            registry_status = "ACTIVE_FORWARD_WATCH"
        else:
            registry_status = "FROZEN_NOT_SELECTED_CONTROL"
        rows.append({
            "registry_entry_id": "FWD_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            "candidate_id": row["candidate_id"], "action_scope": row["action_scope"],
            "research_track": (
                "portfolio_optimization"
                if str(row["action_scope"]) == "VARIABLE_CARDINALITY"
                else "migration_control"
            ),
            "holding_count_interpretation": (
                "dynamic_k_portfolio_structure"
                if str(row["action_scope"]) == "VARIABLE_CARDINALITY"
                else "frozen_incumbent_migration_action_not_target_cardinality"
            ),
            "selection_role": row["selection_role"], "candidate_tickers": ";".join(tickers),
            "frozen_target_weights": row["candidate_weights"],
            "historical_execution_audit_shares": row["whole_lot_shares"],
            "future_cohort_shares": "",
            "registry_status": registry_status,
            "selection_rationale": frozen.get(candidate_identity, "not_selected_by_preregistered_shortlist"),
            "source_execution_status": row["execution_status"],
            "source_evidence_status": row["evidence_status"],
            "registration_date": str(spec["registration_date"]),
            "fresh_oos_cohorts": 0,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
        })
    registry = pd.DataFrame(rows)
    if registry["registry_entry_id"].duplicated().any():
        raise NdxChallengerForwardRegistryError("registry entry hash collision")
    return (
        registry.loc[registry["registry_status"].eq("ACTIVE_FORWARD_WATCH")].reset_index(drop=True),
        registry.loc[registry["registry_status"].ne("ACTIVE_FORWARD_WATCH")].reset_index(drop=True),
    )
