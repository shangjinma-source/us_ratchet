"""Proposed distributional P4 gate for prospective dynamic selector lanes.

This module is deliberately not an activation or promotion mechanism.  It
rebuilds monthly 126-session cohort outcomes from the verified prospective
whole-lot path chain while preserving the separate 252-session dynamic-shadow
research gate and the already registered forward-v5 gate.
"""
from __future__ import annotations

import json
import hashlib
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_daily import (
    _jsonable,
    canonical_sha256,
    load_lane_path_ledger,
    load_target_012922_trace_ledger,
    replay_lane_path,
    replay_original8_control_path,
    validate_nominal_price_evidence,
    verify_realized_decision_chain,
)
from backtest.ndx_dynamic_shadow_daily_v2 import verify_daily_run_manifest
from backtest.ndx_dynamic_shadow_outcome import load_resolution_ledger
from backtest.ndx_dynamic_shadow_fresh_search import (
    load_frozen_original_8_definition,
    verify_final_candidate_snapshot,
    verify_final_role_seal_record,
)
from backtest.ndx_observed_session_calendar_v2 import (
    PROSPECTIVE_SESSION_EVENT,
    verify_canonical_reviewed_calendar_v2,
)
from data.versioning import file_sha256


TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
COMPETITIVE_ROLES = set(ROLES) - {"USER_PREFERENCE"}
VALID_REGIMES = {"BULL", "BEAR", "TRANSITION"}
CANONICAL_SOURCE_PATHS = {
    "reviewed_calendar_manifest": "data/cache/research/ndx_observed_us_session_calendar_v2/manifest.json",
    "daily_run_manifest": "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json",
    "realized_decision_root": "data/cache/research/ndx_dynamic_shadow_daily_v1/realized_decisions",
    "selector_lane_root": "data/cache/research/ndx_dynamic_shadow_daily_v1/lane_paths",
    "original_8_control_ledger": "data/cache/research/ndx_dynamic_shadow_daily_v1/benchmark_controls/original_8_incumbent_v0.jsonl",
    "target_012922_first_observed_trace": "data/cache/research/ndx_dynamic_shadow_daily_v1/benchmark_controls/target_012922_asof.jsonl",
    "target_012922_resolution_ledger": "data/cache/research/ndx_dynamic_shadow_outcome_v1/target_012922_resolved_outcomes.jsonl",
    "fresh_search_final_root": "data/cache/research/ndx_dynamic_shadow_fresh_search_v1/final",
    "fresh_search_role_seal_ledger": "data/cache/research/ndx_dynamic_shadow_fresh_search_v1/role_seals.jsonl",
}
COHORT_COLUMNS = {
    "selector_id", "universe_track", "policy_role", "decision_date",
    "execution_date", "exit_date", "holding_count",
    "active_tickers", "active_security_ids", "horizon_trading_sessions",
    "return_basis",
    "starting_portfolio_id", "evaluation_path_semantics",
    "fixed_starting_portfolio_hold_assumed",
    "observation_regime", "portfolio_return", "original_8_return",
    "target_012922_return", "portfolio_max_drawdown",
    "original_8_max_drawdown", "target_012922_max_drawdown",
}


class NdxDynamicShadowP4GateV2Error(RuntimeError):
    """Raised when proposed dynamic P4 evidence is incomplete or mutable."""


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise NdxDynamicShadowP4GateV2Error(f"{label} fields changed")


def load_proposed_dynamic_p4_contract(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NdxDynamicShadowP4GateV2Error("proposed dynamic P4 contract must be a mapping")
    _exact_keys(payload, {
        "schema_version", "gate_id", "status", "research_track",
        "migration_control_included", "source_contract",
        "dynamic_shadow_research_gate", "proposed_distributional_gate",
        "registered_formal_v5_boundary", "mutation_boundary",
    }, "proposed dynamic P4 contract")
    sources = payload["source_contract"]
    shadow = payload["dynamic_shadow_research_gate"]
    proposed = payload["proposed_distributional_gate"]
    formal = payload["registered_formal_v5_boundary"]
    mutation = payload["mutation_boundary"]
    if not all(isinstance(value, Mapping) for value in (sources, shadow, proposed, formal, mutation)):
        raise NdxDynamicShadowP4GateV2Error("proposed dynamic P4 sections must be mappings")
    _exact_keys(sources, {
        "reviewed_calendar_manifest", "daily_run_manifest", "realized_decision_root",
        "selector_lane_root", "original_8_control_ledger",
        "target_012922_first_observed_trace", "target_012922_resolution_ledger",
        "fresh_search_final_root", "fresh_search_role_seal_ledger",
        "exact_selector_lane_count", "universe_tracks", "policy_roles",
    }, "source contract")
    _exact_keys(shadow, {
        "minimum_same_calendar_trading_sessions", "minimum_monthly_decisions",
        "one_year_gate_may_be_reduced_to_formal_v5_horizon",
    }, "dynamic shadow research gate")
    _exact_keys(proposed, {
        "cohort_horizon_trading_sessions", "minimum_mature_cohorts_per_selector",
        "return_basis",
        "minimum_distinct_regimes_per_selector", "regimes",
        "paired_return_p50_minimum", "paired_return_p10_minimum",
        "paired_drawdown_cost_p50_maximum", "paired_drawdown_cost_p90_maximum",
        "target_012922_componentwise_not_worse_than_original_8",
        "target_012922_scalar_l1_used_for_admission",
        "require_at_least_one_strict_target_dimension_improvement",
        "require_at_least_one_strict_incumbent_dimension_improvement",
        "whole_lot_execution_path_required", "portfolio_path_baseline",
        "portfolio_close_observations", "target_path_baseline",
        "cohort_evaluation_unit", "subsequent_monthly_rebalances_included",
        "starting_portfolio_frozen_for_horizon", "fixed_holding_count",
        "dynamic_k_preserved", "user_preference_reference_only",
    }, "proposed distributional gate")
    _exact_keys(formal, {
        "contract", "primary_horizon_trading_days", "minimum_fresh_mature_cohorts",
        "minimum_distinct_regimes", "remains_independently_required",
        "dynamic_gate_substitution_allowed", "automatic_registration_allowed",
    }, "registered formal v5 boundary")
    _exact_keys(mutation, {
        "research_output_only", "proposed_gate_registered", "p5_unlock_allowed",
        "promotion_allowed", "live_config_mutation_allowed", "state_mutation_allowed",
        "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
        "order_creation_allowed",
    }, "mutation boundary")
    if (
        payload["schema_version"] != 1
        or payload["gate_id"] != "ndx_dynamic_shadow_p4_gate_v2"
        or payload["status"] != "PROPOSED_RESEARCH_GATE_NOT_REGISTERED"
        or payload["research_track"] != "portfolio_optimization"
        or payload["migration_control_included"] is not False
        or int(sources["exact_selector_lane_count"]) != 10
        or list(sources["universe_tracks"]) != list(TRACKS)
        or list(sources["policy_roles"]) != list(ROLES)
        or any(str(sources[key]) != value for key, value in CANONICAL_SOURCE_PATHS.items())
        or int(shadow["minimum_same_calendar_trading_sessions"]) != 252
        or int(shadow["minimum_monthly_decisions"]) != 12
        or shadow["one_year_gate_may_be_reduced_to_formal_v5_horizon"] is not False
        or int(proposed["cohort_horizon_trading_sessions"]) != 126
        or proposed["return_basis"] != "126_SESSION_CUMULATIVE_RETURN_NOT_ANNUALIZED"
        or int(proposed["minimum_mature_cohorts_per_selector"]) != 12
        or int(proposed["minimum_distinct_regimes_per_selector"]) != 2
        or set(proposed["regimes"]) != VALID_REGIMES
        or any(float(proposed[key]) != 0.0 for key in (
            "paired_return_p50_minimum", "paired_return_p10_minimum",
            "paired_drawdown_cost_p50_maximum", "paired_drawdown_cost_p90_maximum",
        ))
        or proposed["target_012922_componentwise_not_worse_than_original_8"] is not True
        or proposed["target_012922_scalar_l1_used_for_admission"] is not False
        or proposed["require_at_least_one_strict_target_dimension_improvement"] is not True
        or proposed["require_at_least_one_strict_incumbent_dimension_improvement"] is not True
        or proposed["whole_lot_execution_path_required"] is not True
        or proposed["portfolio_path_baseline"] != "VERIFIED_PRETRADE_EQUITY_AT_EXECUTION_OPEN"
        or int(proposed["portfolio_close_observations"]) != 126
        or proposed["target_path_baseline"] != "VERIFIED_NO_FUTURE_ASOF_NAV_AT_DECISION_CLOSE"
        or proposed["cohort_evaluation_unit"] != "SELECTOR_POLICY_CONTINUOUS_PATH"
        or proposed["subsequent_monthly_rebalances_included"] is not True
        or proposed["starting_portfolio_frozen_for_horizon"] is not False
        or proposed["fixed_holding_count"] is not None
        or proposed["dynamic_k_preserved"] is not True
        or proposed["user_preference_reference_only"] is not True
        or formal["contract"] != "config/ndx_challenger_forward_v5.yaml"
        or int(formal["primary_horizon_trading_days"]) != 126
        or int(formal["minimum_fresh_mature_cohorts"]) != 12
        or int(formal["minimum_distinct_regimes"]) != 2
        or formal["remains_independently_required"] is not True
        or formal["dynamic_gate_substitution_allowed"] is not False
        or formal["automatic_registration_allowed"] is not False
        or mutation["research_output_only"] is not True
        or any(mutation[key] is not False for key in (
            "proposed_gate_registered", "p5_unlock_allowed", "promotion_allowed",
            "live_config_mutation_allowed", "state_mutation_allowed",
            "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
            "order_creation_allowed",
        ))
    ):
        raise NdxDynamicShadowP4GateV2Error("proposed dynamic P4 safety contract changed")
    return payload


def _selector_id(track: str, role: str) -> str:
    return f"{track}__{role.lower()}__v1"


def _expected_selectors() -> set[str]:
    return {_selector_id(track, role) for track in TRACKS for role in ROLES}


def _selector_parts(selector_id: str) -> tuple[str, str]:
    for track in TRACKS:
        prefix = f"{track}__"
        if selector_id.startswith(prefix) and selector_id.endswith("__v1"):
            role = selector_id[len(prefix):-4].upper()
            if role in ROLES:
                return track, role
    raise NdxDynamicShadowP4GateV2Error("selector identity is outside the 2x5 matrix")


def _path_metrics(values: list[float], *, baseline_value: float) -> tuple[float, float]:
    series = pd.Series([baseline_value, *values], dtype=float)
    if len(series) != 127 or (~np.isfinite(series) | series.le(0)).any():
        raise NdxDynamicShadowP4GateV2Error("cohort path contains invalid values")
    return (
        float(series.iloc[-1] / series.iloc[0] - 1.0),
        float((1.0 - series / series.cummax()).max()),
    )


def _quantile(frame: pd.DataFrame, column: str, quantile: float) -> float:
    values = pd.to_numeric(frame[column], errors="coerce")
    if len(values) != len(frame) or values.isna().any() or (~np.isfinite(values)).any():
        raise NdxDynamicShadowP4GateV2Error(f"mature cohort metric is incomplete: {column}")
    return float(values.quantile(quantile))


def _target_componentwise_gate(
    candidate: Mapping[str, float], original: Mapping[str, float], target: Mapping[str, float],
) -> dict[str, Any]:
    checks = {}
    strict = 0
    for key in ("return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90"):
        candidate_distance = abs(float(candidate[key]) - float(target[key]))
        original_distance = abs(float(original[key]) - float(target[key]))
        passed = candidate_distance <= original_distance + 1e-12
        improved = candidate_distance < original_distance - 1e-12
        strict += int(improved)
        checks[key] = {
            "candidate_absolute_distance": candidate_distance,
            "original_8_absolute_distance": original_distance,
            "not_worse": passed,
            "strictly_improved": improved,
        }
    return {
        "checks": checks,
        "componentwise_not_worse": all(value["not_worse"] for value in checks.values()),
        "strict_improvement_count": strict,
        "passed": all(value["not_worse"] for value in checks.values()) and strict >= 1,
        "scalar_l1_reporting_only": {
            "candidate": sum(value["candidate_absolute_distance"] for value in checks.values()),
            "original_8": sum(value["original_8_absolute_distance"] for value in checks.values()),
            "used_for_admission": False,
        },
    }


def summarize_dynamic_p4_cohorts(
    cohorts: pd.DataFrame, *, resolved_session_count: int,
    monthly_decision_count: int, selector_decision_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Summarize already rebuilt raw cohorts; this function grants no authority."""

    expected = _expected_selectors()
    counts = {str(key): int(value) for key, value in selector_decision_counts.items()}
    if counts and set(counts) != expected:
        raise NdxDynamicShadowP4GateV2Error("decision chain is not the exact 2x5 selector matrix")
    if counts and len(set(counts.values())) != 1:
        raise NdxDynamicShadowP4GateV2Error("selector decision chains have unequal lengths")
    if not counts and monthly_decision_count:
        raise NdxDynamicShadowP4GateV2Error("monthly decision count lacks selector evidence")
    if counts and next(iter(counts.values())) != int(monthly_decision_count):
        raise NdxDynamicShadowP4GateV2Error("monthly decision count changed")
    if cohorts.empty:
        frame = pd.DataFrame(columns=sorted(COHORT_COLUMNS))
    else:
        if set(cohorts.columns) != COHORT_COLUMNS:
            raise NdxDynamicShadowP4GateV2Error("dynamic P4 cohort schema changed")
        frame = cohorts.copy()
        if frame[["selector_id", "decision_date"]].astype(str).duplicated().any():
            raise NdxDynamicShadowP4GateV2Error("dynamic P4 cohort coordinate is duplicated")
        if not set(frame["selector_id"].astype(str)).issubset(expected):
            raise NdxDynamicShadowP4GateV2Error("unknown selector entered dynamic P4 cohorts")
        numeric = [
            "holding_count", "horizon_trading_sessions", "portfolio_return",
            "original_8_return", "target_012922_return", "portfolio_max_drawdown",
            "original_8_max_drawdown", "target_012922_max_drawdown",
        ]
        converted = frame[numeric].apply(pd.to_numeric, errors="coerce")
        if converted.isna().any().any() or (~np.isfinite(converted)).any().any():
            raise NdxDynamicShadowP4GateV2Error("dynamic P4 cohort contains non-finite metrics")
        frame[numeric] = converted
        if (
            not frame["horizon_trading_sessions"].eq(126).all()
            or not frame["return_basis"].eq(
                "126_SESSION_CUMULATIVE_RETURN_NOT_ANNUALIZED"
            ).all()
            or frame["holding_count"].lt(1).any()
            or any(frame[key].lt(0).any() or frame[key].gt(1).any() for key in (
                "portfolio_max_drawdown", "original_8_max_drawdown",
                "target_012922_max_drawdown",
            ))
        ):
            raise NdxDynamicShadowP4GateV2Error("dynamic P4 cohort metric boundary changed")
        allowed_regimes = VALID_REGIMES | {"INSUFFICIENT_HISTORY"}
        if not set(frame["observation_regime"].astype(str)).issubset(allowed_regimes):
            raise NdxDynamicShadowP4GateV2Error("dynamic P4 regime changed")
        for row in frame.itertuples(index=False):
            track, role = _selector_parts(str(row.selector_id))
            if str(row.universe_track) != track or str(row.policy_role) != role:
                raise NdxDynamicShadowP4GateV2Error("selector track/role identity changed")
            if (
                str(row.evaluation_path_semantics)
                != "SELECTOR_POLICY_CONTINUOUS_PATH_WITH_SUBSEQUENT_MONTHLY_REBALANCES"
                or bool(row.fixed_starting_portfolio_hold_assumed) is not False
            ):
                raise NdxDynamicShadowP4GateV2Error("cohort policy-path semantics changed")
            if counts and str(row.selector_id) not in counts:
                raise NdxDynamicShadowP4GateV2Error("cohort lacks verified decision chain")

    one_year_ready = (
        int(resolved_session_count) >= 252 and int(monthly_decision_count) >= 12
    )
    summaries = []
    eligible: list[str] = []
    for selector in sorted(expected):
        track, role = _selector_parts(selector)
        group = frame.loc[frame["selector_id"].astype(str).eq(selector)].copy()
        regimes = set(group["observation_regime"].astype(str)) & VALID_REGIMES
        distribution_ready = len(group) >= 12 and len(regimes) >= 2
        metrics: dict[str, Any] = {}
        incumbent_gate = target_gate = False
        if distribution_ready:
            candidate = {
                "return_p50": _quantile(group, "portfolio_return", 0.50),
                "return_p10": _quantile(group, "portfolio_return", 0.10),
                "max_drawdown_p50": _quantile(group, "portfolio_max_drawdown", 0.50),
                "max_drawdown_p90": _quantile(group, "portfolio_max_drawdown", 0.90),
            }
            original = {
                "return_p50": _quantile(group, "original_8_return", 0.50),
                "return_p10": _quantile(group, "original_8_return", 0.10),
                "max_drawdown_p50": _quantile(group, "original_8_max_drawdown", 0.50),
                "max_drawdown_p90": _quantile(group, "original_8_max_drawdown", 0.90),
            }
            target = {
                "return_p50": _quantile(group, "target_012922_return", 0.50),
                "return_p10": _quantile(group, "target_012922_return", 0.10),
                "max_drawdown_p50": _quantile(group, "target_012922_max_drawdown", 0.50),
                "max_drawdown_p90": _quantile(group, "target_012922_max_drawdown", 0.90),
            }
            paired = {
                "return_p50": candidate["return_p50"] - original["return_p50"],
                "return_p10": candidate["return_p10"] - original["return_p10"],
                "drawdown_cost_p50": (
                    candidate["max_drawdown_p50"] - original["max_drawdown_p50"]
                ),
                "drawdown_cost_p90": (
                    candidate["max_drawdown_p90"] - original["max_drawdown_p90"]
                ),
            }
            incumbent_gate = bool(
                paired["return_p50"] >= -1e-12
                and paired["return_p10"] >= -1e-12
                and paired["drawdown_cost_p50"] <= 1e-12
                and paired["drawdown_cost_p90"] <= 1e-12
                and any(value > 1e-12 for value in (
                    paired["return_p50"], paired["return_p10"],
                    -paired["drawdown_cost_p50"], -paired["drawdown_cost_p90"],
                ))
            )
            target_result = _target_componentwise_gate(candidate, original, target)
            target_gate = bool(target_result["passed"])
            metrics = {
                "candidate": candidate, "original_8": original, "target_012922": target,
                "paired_vs_original_8": paired,
                "target_012922_componentwise": target_result,
            }
        user_reference = role == "USER_PREFERENCE"
        proposed_pass = bool(
            one_year_ready and distribution_ready and incumbent_gate and target_gate
            and not user_reference
        )
        if proposed_pass:
            eligible.append(selector)
        holding_counts = sorted(set(
            int(value) for value in pd.to_numeric(group["holding_count"], errors="coerce").dropna()
        ))
        summaries.append({
            "selector_id": selector,
            "universe_track": track,
            "policy_role": role,
            "user_preference_reference_only": user_reference,
            "verified_monthly_decisions": counts.get(selector, 0),
            "mature_126_session_cohorts": len(group),
            "distinct_mature_regimes": sorted(regimes),
            "distributional_evidence_ready": distribution_ready,
            "observed_holding_counts": holding_counts,
            "fixed_holding_count_assumed": False,
            "cohort_evaluation_unit": "SELECTOR_POLICY_CONTINUOUS_PATH",
            "subsequent_monthly_rebalances_included": True,
            "incumbent_componentwise_gate_passed": incumbent_gate,
            "target_012922_componentwise_gate_passed": target_gate,
            "proposed_gate_passed": proposed_pass,
            "metrics": metrics,
        })

    if not counts:
        status = "NOT_DUE_NO_PROSPECTIVE_DYNAMIC_DECISIONS"
    elif not one_year_ready:
        status = "ACCUMULATING_252_SESSION_DYNAMIC_SHADOW"
    elif not any(item["distributional_evidence_ready"] for item in summaries):
        status = "ACCUMULATING_126_SESSION_MONTHLY_COHORT_DISTRIBUTIONS"
    elif eligible:
        status = "SYNTHETIC_CAPABILITY_EVIDENCE_ONLY"
    else:
        status = "PROPOSED_DYNAMIC_P4_GATE_FAILED_RESEARCH_ONLY"
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_p4_gate_v2_readiness",
        "status": status,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "resolved_same_calendar_trading_sessions": int(resolved_session_count),
        "minimum_same_calendar_trading_sessions": 252,
        "monthly_dynamic_decisions": int(monthly_decision_count),
        "minimum_monthly_dynamic_decisions": 12,
        "dynamic_shadow_one_year_research_gate_ready": one_year_ready,
        "cohort_horizon_trading_sessions": 126,
        "return_basis": "126_SESSION_CUMULATIVE_RETURN_NOT_ANNUALIZED",
        "minimum_mature_cohorts_per_selector": 12,
        "minimum_distinct_regimes_per_selector": 2,
        "selector_lane_count": 10,
        "selector_summaries": summaries,
        "proposed_gate_passed_selector_ids": [],
        "synthetic_capability_passed_selector_ids": eligible,
        "user_preference_can_admit": False,
        "target_012922_scalar_used_for_admission": False,
        "registered_formal_v5_gate_remains_independently_required": True,
        "formal_v5_gate_substitution_allowed": False,
        "proposed_gate_registered": False,
        "p5_unlock_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


def _resolve(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise NdxDynamicShadowP4GateV2Error("dynamic P4 source escapes repository root") from exc
    return path


def _regime(qqq_closes: Mapping[str, float], decision_date: str) -> str:
    cutoff = pd.Timestamp(decision_date).normalize()
    values = [
        float(value) for date, value in sorted(qqq_closes.items())
        if pd.Timestamp(date).normalize() <= cutoff
    ][-200:]
    if len(values) < 200:
        return "INSUFFICIENT_HISTORY"
    close = values[-1]
    above50 = close >= float(np.mean(values[-50:]))
    above200 = close >= float(np.mean(values))
    return "BULL" if above50 and above200 else (
        "BEAR" if not above50 and not above200 else "TRANSITION"
    )


def _qqq_closes_for_decision(verified: Any, decision_date: str) -> dict[str, float]:
    """Load only the full QQQ history frozen with the decision-session event."""

    matches = [
        event for event in verified.events
        if event.get("event_type") == PROSPECTIVE_SESSION_EVENT
        and str(event.get("session_date")) == decision_date
    ]
    if len(matches) != 1 or matches[0].get("decision_eligible") is not True:
        raise NdxDynamicShadowP4GateV2Error("decision lacks one eligible sealed calendar event")
    snapshot_id = str(matches[0].get("source_snapshot_id") or "")
    snapshot = verified.source_snapshots.get(snapshot_id)
    if snapshot is None or "QQQ" not in snapshot.raw_bytes:
        raise NdxDynamicShadowP4GateV2Error("decision QQQ source snapshot is missing")
    try:
        frame = pd.read_csv(StringIO(snapshot.raw_bytes["QQQ"].decode("utf-8-sig")))
    except (UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise NdxDynamicShadowP4GateV2Error("decision QQQ source snapshot is unreadable") from exc
    if not {"Date", "Close"}.issubset(frame.columns):
        raise NdxDynamicShadowP4GateV2Error("decision QQQ source snapshot schema changed")
    frame = frame[["Date", "Close"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise").dt.normalize()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="raise")
    cutoff = pd.Timestamp(decision_date).normalize()
    frame = frame.loc[frame["Date"].le(cutoff)]
    if (
        frame["Date"].duplicated().any() or not frame["Date"].is_monotonic_increasing
        or (~np.isfinite(frame["Close"]) | frame["Close"].le(0)).any()
    ):
        raise NdxDynamicShadowP4GateV2Error("decision QQQ source snapshot values changed")
    return {
        date.date().isoformat(): float(close)
        for date, close in zip(frame["Date"], frame["Close"], strict=True)
    }


def _load_decision_payloads(root: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    batches = verify_realized_decision_chain(root)
    lanes: dict[str, list[dict[str, Any]]] = {}
    for batch in batches:
        directory = root / str(batch["decision_date"])
        for path in sorted(directory.glob("*.json")):
            if path.name == "batch_manifest.json":
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            lanes.setdefault(str(payload["selector_id"]), []).append(payload)
    if batches and set(lanes) != _expected_selectors():
        raise NdxDynamicShadowP4GateV2Error("realized decision chain lost the 2x5 matrix")
    return batches, lanes


def _values(records: list[dict[str, Any]], dates: list[str], label: str) -> list[float]:
    mapping = {
        str(value["date"]): float((value.get("path_state") or {})["total_value_usd"])
        for value in records
    }
    if any(date not in mapping for date in dates):
        raise NdxDynamicShadowP4GateV2Error(f"{label} does not cover resolved target calendar")
    return [mapping[date] for date in dates]


def _descriptor_matches(
    descriptor: Mapping[str, Any] | None, expected_path: Path, *, rows: int | None = None,
) -> None:
    if not isinstance(descriptor, Mapping):
        raise NdxDynamicShadowP4GateV2Error("daily canonical source descriptor is missing")
    if Path(str(descriptor.get("path") or "")).resolve() != expected_path.resolve():
        raise NdxDynamicShadowP4GateV2Error("daily canonical source path changed")
    if not expected_path.is_file() or descriptor.get("sha256") != file_sha256(expected_path):
        raise NdxDynamicShadowP4GateV2Error("daily canonical source hash changed")
    if rows is not None and int(descriptor.get("rows", -1)) != rows:
        raise NdxDynamicShadowP4GateV2Error("daily canonical source row count changed")


def _calendar_dates(calendar: Any) -> list[str]:
    dates = [
        str(row["session_date"]) for row in calendar.session_projection
        if row.get("source_price_replay_available") is True
    ]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise NdxDynamicShadowP4GateV2Error("sealed reviewed calendar order changed")
    return dates


def _cohort_dates_from_calendar(
    calendar_dates: list[str], execution_date: str, *, horizon: int = 126,
) -> list[str]:
    eligible = [date for date in calendar_dates if date >= execution_date]
    if len(eligible) < horizon:
        return []
    result = eligible[:horizon]
    if result[0] != execution_date:
        raise NdxDynamicShadowP4GateV2Error("execution is not a sealed calendar session")
    return result


def _pre_execution_portfolio_value(
    records: list[dict[str, Any]], *, execution_date: str, decision_date: str | None,
    previous_session_date: str | None, require_rebalance: bool,
) -> float:
    current = [value for value in records if str(value["date"]) == execution_date]
    if len(current) != 1:
        raise NdxDynamicShadowP4GateV2Error("execution path record is missing or duplicated")
    rebalances = [
        value for value in current[0].get("rebalance_events", [])
        if str(value.get("execution_date")) == execution_date
        and (decision_date is None or str(value.get("decision_date")) == decision_date)
    ]
    if rebalances:
        if len(rebalances) != 1:
            raise NdxDynamicShadowP4GateV2Error("execution rebalance baseline is ambiguous")
        baseline = float(rebalances[0].get("pretrade_equity_usd"))
    elif require_rebalance:
        raise NdxDynamicShadowP4GateV2Error("candidate execution lacks pretrade equity evidence")
    else:
        prior = [value for value in records if str(value["date"]) == previous_session_date]
        if len(prior) != 1:
            raise NdxDynamicShadowP4GateV2Error("control path lacks pre-execution close baseline")
        baseline = float((prior[0].get("path_state") or {}).get("total_value_usd"))
    if not np.isfinite(baseline) or baseline <= 0:
        raise NdxDynamicShadowP4GateV2Error("pre-execution portfolio baseline is invalid")
    return baseline


def _target_baseline_at_decision(
    resolved: list[dict[str, Any]], *, decision_date: str,
) -> float | None:
    matches = [
        value for value in resolved if str(value.get("session_date")) == decision_date
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise NdxDynamicShadowP4GateV2Error("target decision baseline is duplicated")
    baseline = float(matches[0]["normalized_value_usd"])
    if not np.isfinite(baseline) or baseline <= 0:
        raise NdxDynamicShadowP4GateV2Error("target decision baseline is invalid")
    return baseline


def _verify_execution_identity(
    records: list[dict[str, Any]], selected: Mapping[str, Any], *,
    decision_date: str, execution_date: str,
) -> None:
    execution = [value for value in records if str(value["date"]) == execution_date]
    if len(execution) != 1:
        raise NdxDynamicShadowP4GateV2Error("candidate execution record is ambiguous")
    rebalances = [
        value for value in execution[0].get("rebalance_events", [])
        if str(value.get("decision_date")) == decision_date
        and str(value.get("execution_date")) == execution_date
    ]
    if len(rebalances) != 1:
        raise NdxDynamicShadowP4GateV2Error("candidate execution rebalance is ambiguous")
    targets = selected.get("targets") or {}
    expected_ids = set(str(value) for value in targets)
    rebalance = rebalances[0]

    def decoded(value: Any, label: str) -> Mapping[str, Any]:
        try:
            result = json.loads(value) if isinstance(value, str) else value
        except json.JSONDecodeError as exc:
            raise NdxDynamicShadowP4GateV2Error(f"candidate {label} is malformed") from exc
        if not isinstance(result, Mapping):
            raise NdxDynamicShadowP4GateV2Error(f"candidate {label} is malformed")
        return result

    weights = decoded(rebalance.get("target_weights"), "rebalance weights")
    holdings = decoded(rebalance.get("holdings"), "execution holdings")
    path_state = execution[0].get("path_state", {})
    active = path_state.get("active_security_ids")
    try:
        active_ids = set(json.loads(active) if isinstance(active, str) else active)
        active_tickers_value = path_state.get("active_tickers")
        active_tickers = set(
            json.loads(active_tickers_value)
            if isinstance(active_tickers_value, str) else active_tickers_value
        )
    except (TypeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4GateV2Error("candidate active holdings are malformed") from exc
    path_holdings = decoded(path_state.get("holdings"), "path holdings")
    executable_holdings = True
    for security_id in expected_ids:
        holding = holdings.get(security_id)
        if not isinstance(holding, Mapping):
            executable_holdings = False
            break
        shares = holding.get("shares")
        target = targets[security_id]
        if (
            isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0
            or str(holding.get("ticker")) != str(target.get("ticker"))
            or str(holding.get("issuer_id")) != str(target.get("issuer_id"))
        ):
            executable_holdings = False
            break
    if (
        int(rebalance.get("target_k", -1)) != int(selected.get("holding_count", -1))
        or int(path_state.get("holding_count", -1)) != int(selected.get("holding_count", -1))
        or set(weights) != expected_ids
        or set(holdings) != expected_ids
        or active_ids != expected_ids
        or active_tickers != {
            str(value.get("ticker")) for value in targets.values()
        }
        or path_holdings != holdings
        or not executable_holdings
        or any(
            not np.isclose(
                float(weights[security_id]),
                float(targets[security_id]["target_weight"]), atol=1e-12,
            )
            for security_id in expected_ids
        )
    ):
        raise NdxDynamicShadowP4GateV2Error(
            "candidate role identity differs from execution rebalance"
        )


def _split_pipe(value: Any) -> list[str]:
    return [item for item in str(value).split("|") if item]


def _selected_candidate_from_final(
    final_path: Path, final: Mapping[str, Any], selector_id: str,
) -> dict[str, Any] | None:
    artifacts = final.get("artifacts") or {}

    def frozen_csv(name: str) -> pd.DataFrame:
        descriptor = artifacts.get(name) or {}
        filename = str(descriptor.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise NdxDynamicShadowP4GateV2Error(
                f"final {name} descriptor is invalid"
            )
        try:
            raw = (final_path.parent / filename).read_bytes()
            if hashlib.sha256(raw).hexdigest() != descriptor.get("sha256"):
                raise NdxDynamicShadowP4GateV2Error(
                    f"final {name} bytes changed after verification"
                )
            frame = pd.read_csv(StringIO(raw.decode("utf-8-sig")), low_memory=False)
        except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
            raise NdxDynamicShadowP4GateV2Error(
                f"final {name} artifact is unreadable"
            ) from exc
        if len(frame) != int(descriptor.get("rows", -1)):
            raise NdxDynamicShadowP4GateV2Error(f"final {name} rows changed")
        return frame

    try:
        roles = frozen_csv("role_lock")
        candidates = frozen_csv("candidates")
    except (KeyError, TypeError, ValueError) as exc:
        raise NdxDynamicShadowP4GateV2Error("final selection artifacts are unreadable") from exc
    selected_role = roles.loc[roles["selector_id"].astype(str).eq(selector_id)]
    if len(selected_role) != 1:
        raise NdxDynamicShadowP4GateV2Error("selector lacks one frozen role")
    role = selected_role.iloc[0]
    status = str(role["status"])
    if status == "REFERENCE_UNAVAILABLE_NOT_REPLACED":
        if str(role["policy_role"]) != "USER_PREFERENCE":
            raise NdxDynamicShadowP4GateV2Error("competitive role is unavailable")
        return None
    portfolio_id = str(role["portfolio_id"])
    matches = candidates.loc[
        candidates["universe_track"].astype(str).eq(str(role["universe_track"]))
        & candidates["portfolio_id"].astype(str).eq(portfolio_id)
    ]
    if len(matches) != 1:
        raise NdxDynamicShadowP4GateV2Error("frozen role does not resolve to one candidate")
    candidate = matches.iloc[0]
    tickers = _split_pipe(candidate["tickers"])
    security_ids = _split_pipe(candidate["security_ids"])
    issuer_ids = _split_pipe(candidate["issuer_ids"])
    weights: dict[str, float] = {}
    for item in _split_pipe(candidate["weights"]):
        ticker, separator, raw = item.rpartition(":")
        if not separator or ticker in weights:
            raise NdxDynamicShadowP4GateV2Error("frozen candidate weights are malformed")
        weights[ticker] = float(raw)
    holding_count = int(candidate["holding_count"])
    if (
        len(tickers) != holding_count
        or not (len(tickers) == len(security_ids) == len(issuer_ids))
        or len(set(tickers)) != holding_count
        or len(set(security_ids)) != holding_count
        or len(set(issuer_ids)) != holding_count
        or set(weights) != set(tickers)
        or not np.isclose(sum(weights.values()), 1.0, atol=1e-6)
    ):
        raise NdxDynamicShadowP4GateV2Error("frozen candidate identity changed")
    return {
        "portfolio_id": portfolio_id,
        "holding_count": holding_count,
        "targets": {
            security_id: {
                "ticker": ticker, "issuer_id": issuer_id,
                "target_weight": float(weights[ticker]),
            }
            for ticker, security_id, issuer_id in zip(
                tickers, security_ids, issuer_ids, strict=True,
            )
        },
    }


def _verify_realized_timing(
    calendar: Any, payload: Mapping[str, Any], final: Mapping[str, Any],
    role_record: Mapping[str, Any],
) -> None:
    timing = payload.get("timing") or {}
    decision_date = str(timing.get("decision_date") or "")
    execution_date = str(timing.get("execution_date") or "")
    projection = list(calendar.session_projection)
    decision_indices = [
        index for index, row in enumerate(projection)
        if str(row.get("session_date")) == decision_date
    ]
    if len(decision_indices) != 1 or decision_indices[0] + 1 >= len(projection):
        raise NdxDynamicShadowP4GateV2Error("decision lacks one next sealed session")
    decision = projection[decision_indices[0]]
    execution = projection[decision_indices[0] + 1]
    try:
        open_time = pd.Timestamp(execution["open_timestamp_utc"]).tz_convert("UTC")
        close_time = pd.Timestamp(execution["close_timestamp_utc"]).tz_convert("UTC")
        sealed = pd.Timestamp(role_record["roles_sealed_at_utc"]).tz_convert("UTC")
        realized = pd.Timestamp(timing["execution_realized_at_utc"]).tz_convert("UTC")
        supplied_open = pd.Timestamp(timing["execution_open_timestamp_utc"]).tz_convert("UTC")
        supplied_close = pd.Timestamp(timing["execution_close_timestamp_utc"]).tz_convert("UTC")
    except (KeyError, TypeError, ValueError) as exc:
        raise NdxDynamicShadowP4GateV2Error("realized timing evidence is invalid") from exc
    if (
        decision.get("decision_eligible") is not True
        or decision.get("is_first_observed_session_of_month") is not True
        or execution_date != str(execution["session_date"])
        or supplied_open != open_time
        or supplied_close != close_time
        or str(timing.get("candidate_sealed_at_utc")) != str(final.get("roles_sealed_at_utc"))
        or str(role_record.get("roles_sealed_at_utc")) != str(final.get("roles_sealed_at_utc"))
        or sealed >= open_time
        or realized < close_time
    ):
        raise NdxDynamicShadowP4GateV2Error("realized execution timing changed")


def _verified_session_frame(calendar: Any) -> pd.DataFrame:
    frame = pd.DataFrame(list(calendar.session_projection))
    frame["completed"] = True
    return frame


def _load_frozen_nominal_snapshot(
    manifest_path: Path, *, root: Path, sessions: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame, str]:
    expected_keys = {
        "schema_version", "manifest_type", "status", "valuation_end_date",
        "tickers", "price_basis", "execution_field", "valuation_field",
        "sources", "artifact", "module_sha256", "script_sha256",
        "promotion_allowed", "live_mutation", "manifest_sha256",
    }
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4GateV2Error("frozen nominal manifest is unreadable") from exc
    unsigned = dict(manifest)
    declared = unsigned.pop("manifest_sha256", None)
    valuation_end = str(manifest.get("valuation_end_date") or "")
    expected_path = (
        root / "data/cache/research/ndx_dynamic_shadow_daily_v1/nominal_price_evidence"
        / valuation_end / "manifest.json"
    ).resolve()
    tickers = list(manifest.get("tickers") or [])
    if (
        manifest_path.resolve() != expected_path
        or set(manifest) != expected_keys
        or canonical_sha256(unsigned) != declared
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "ndx_dynamic_shadow_nominal_open_close_evidence"
        or manifest.get("status") != "IMMUTABLE_EXACT_TICKER_SESSION_GRID"
        or manifest.get("price_basis") != "UNADJUSTED_NOMINAL_TRADE_PRICE"
        or manifest.get("execution_field") != "Open"
        or manifest.get("valuation_field") != "Close"
        or manifest.get("module_sha256") != file_sha256(
            root / "backtest/ndx_dynamic_shadow_daily.py"
        )
        or manifest.get("script_sha256") != file_sha256(
            root / "scripts/ndx_dynamic_shadow_daily.py"
        )
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
        or tickers != sorted(set(str(value) for value in tickers))
    ):
        raise NdxDynamicShadowP4GateV2Error("frozen nominal manifest boundary changed")
    sources = manifest.get("sources") or {}
    if set(sources) != set(tickers):
        raise NdxDynamicShadowP4GateV2Error("frozen nominal source inventory changed")
    source_frames = []
    for ticker in tickers:
        descriptor = sources[ticker]
        if set(descriptor) != {
            "filename", "rows", "sha256", "source_mode", "fallback_errors",
            "data_start", "data_end",
        } or descriptor["filename"] != f"sources/{ticker}.csv":
            raise NdxDynamicShadowP4GateV2Error("frozen nominal source descriptor changed")
        source_path = manifest_path.parent / descriptor["filename"]
        raw = source_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise NdxDynamicShadowP4GateV2Error("frozen nominal source bytes changed")
        frame = pd.read_csv(StringIO(raw.decode("utf-8-sig")))
        if len(frame) != int(descriptor["rows"]):
            raise NdxDynamicShadowP4GateV2Error("frozen nominal source rows changed")
        source_frames.append(frame)
    prefix = sessions.loc[
        pd.to_datetime(sessions["session_date"]).le(pd.Timestamp(valuation_end))
    ].copy()
    rebuilt = validate_nominal_price_evidence(
        pd.concat(source_frames, ignore_index=True), prefix,
        tickers=tickers, valuation_end_date=valuation_end,
    )
    artifact = manifest.get("artifact") or {}
    if set(artifact) != {"filename", "rows", "sha256"} or artifact["filename"] != "prices.csv":
        raise NdxDynamicShadowP4GateV2Error("frozen nominal artifact descriptor changed")
    data_path = manifest_path.parent / artifact["filename"]
    data_bytes = data_path.read_bytes()
    expected_bytes = rebuilt.assign(
        Date=rebuilt["Date"].dt.date.astype(str)
    ).to_csv(index=False, lineterminator="\n").encode("utf-8")
    if (
        data_bytes != expected_bytes
        or hashlib.sha256(data_bytes).hexdigest() != artifact["sha256"]
        or len(rebuilt) != int(artifact["rows"])
    ):
        raise NdxDynamicShadowP4GateV2Error("frozen nominal artifact differs from sources")
    return manifest, rebuilt, hashlib.sha256(manifest_bytes).hexdigest()


def _verify_replayed_lane_economics(
    *, root: Path, daily: Mapping[str, Any], calendar: Any,
    decisions: Mapping[str, list[dict[str, Any]]],
    lane_records: Mapping[str, list[dict[str, Any]]],
    original_records: list[dict[str, Any]],
) -> dict[str, Any]:
    valuation_end = str(daily.get("latest_observed_session") or "")
    latest_manifest = (
        root / "data/cache/research/ndx_dynamic_shadow_daily_v1/nominal_price_evidence"
        / valuation_end / "manifest.json"
    )
    descriptor = (daily.get("research_artifacts") or {}).get(
        "nominal_price_evidence_manifest"
    )
    if (
        not isinstance(descriptor, Mapping)
        or Path(str(descriptor.get("path") or "")).resolve() != latest_manifest.resolve()
    ):
        raise NdxDynamicShadowP4GateV2Error("daily nominal source path changed")
    sessions = _verified_session_frame(calendar)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for selector_records in lane_records.values():
        for record in selector_records:
            by_date.setdefault(str(record["date"]), []).append(record)
    for record in original_records:
        by_date.setdefault(str(record["date"]), []).append(record)
    frozen_by_date: dict[str, pd.DataFrame] = {}
    frozen_manifest_sha256_by_date: dict[str, str] = {}
    mixed: dict[tuple[str, str], dict[str, Any]] = {}

    def add_rows(rows: pd.DataFrame) -> None:
        for row in rows.to_dict("records"):
            coordinate = (pd.Timestamp(row["Date"]).date().isoformat(), str(row["ticker"]))
            normalized = {
                "Date": pd.Timestamp(row["Date"]).normalize(), "ticker": str(row["ticker"]),
                "Open": float(row["Open"]), "Close": float(row["Close"]),
            }
            previous = mixed.setdefault(coordinate, normalized)
            if previous != normalized:
                raise NdxDynamicShadowP4GateV2Error(
                    "frozen nominal snapshots revise an earlier path coordinate"
                )

    for date, records in sorted(by_date.items()):
        hashes = {str(value.get("price_evidence_sha256") or "") for value in records}
        if len(hashes) != 1:
            raise NdxDynamicShadowP4GateV2Error("lane price evidence differs by selector")
        dated_manifest = latest_manifest.parent.parent / date / "manifest.json"
        if not dated_manifest.is_file():
            raise NdxDynamicShadowP4GateV2Error("lane price evidence is not the dated snapshot")
        _, frozen, manifest_digest = _load_frozen_nominal_snapshot(
            dated_manifest, root=root, sessions=sessions,
        )
        if manifest_digest not in hashes:
            raise NdxDynamicShadowP4GateV2Error("lane price evidence is not the dated snapshot")
        if date == valuation_end and descriptor.get("sha256") != manifest_digest:
            raise NdxDynamicShadowP4GateV2Error("daily nominal source hash changed")
        frozen_by_date[date] = frozen
        frozen_manifest_sha256_by_date[date] = manifest_digest
        rows = frozen.loc[frozen["Date"].eq(pd.Timestamp(date))]
        if rows.empty:
            raise NdxDynamicShadowP4GateV2Error("dated nominal snapshot lacks its session")
        add_rows(rows)
    for payloads in decisions.values():
        for payload in payloads:
            timing = payload["timing"]
            decision_date = str(timing["decision_date"])
            execution_date = str(timing["execution_date"])
            frozen = frozen_by_date.get(execution_date)
            if frozen is None:
                raise NdxDynamicShadowP4GateV2Error(
                    "execution snapshot is unavailable for decision-price proof"
                )
            rows = frozen.loc[frozen["Date"].eq(pd.Timestamp(decision_date))]
            if rows.empty:
                raise NdxDynamicShadowP4GateV2Error(
                    "execution snapshot lacks the preceding decision coordinate"
                )
            add_rows(rows)
    long = pd.DataFrame(list(mixed.values()))
    opens = long.pivot(index="Date", columns="ticker", values="Open")
    closes = long.pivot(index="Date", columns="ticker", values="Close")

    def compare(
        stored: list[dict[str, Any]], path: pd.DataFrame,
        rebalances: pd.DataFrame, trades: pd.DataFrame, label: str,
    ) -> None:
        expected_dates = path["date"].astype(str).tolist()
        if [str(value["date"]) for value in stored] != expected_dates:
            raise NdxDynamicShadowP4GateV2Error(f"{label} replay calendar changed")
        for record, row in zip(stored, path.to_dict("records"), strict=True):
            date = str(row["date"])
            expected_state = {
                "cash_usd": float(row["cash_usd"]),
                "holdings_value_usd": float(row["holdings_value_usd"]),
                "total_value_usd": float(row["total_value_usd"]),
                "holding_count": int(row["holding_count"]),
                "active_security_ids": str(row["active_security_ids"]),
                "active_tickers": str(row["active_tickers"]),
                "holdings": str(row["holdings"]),
            }
            actual_state = record.get("path_state") or {}
            numeric = ("cash_usd", "holdings_value_usd", "total_value_usd")
            if (
                any(
                    not np.isclose(
                        float(actual_state.get(key)), expected_state[key],
                        rtol=0.0, atol=1e-8,
                    ) for key in numeric
                )
                or any(actual_state.get(key) != expected_state[key] for key in (
                    "holding_count", "active_security_ids", "active_tickers", "holdings",
                ))
                or record.get("rebalance_events") != (
                    _jsonable(rebalances.loc[
                        rebalances["execution_date"].astype(str).eq(date)
                    ].to_dict("records")) if not rebalances.empty else []
                )
                or record.get("trade_events") != (
                    _jsonable(trades.loc[
                        trades["execution_date"].astype(str).eq(date)
                    ].to_dict("records")) if not trades.empty else []
                )
            ):
                raise NdxDynamicShadowP4GateV2Error(
                    f"{label} ledger differs from sealed nominal whole-lot replay"
                )

    for selector, payloads in decisions.items():
        _, rebalances, trades, path = replay_lane_path(
            payloads, sessions=sessions, valuation_closes=closes,
            execution_opens=opens, valuation_end_date=valuation_end,
        )
        compare(lane_records[selector], path, rebalances, trades, selector)

    original_manifest = (
        root / "data/cache/research/ndx_original_8_control_v1/manifest.json"
    )
    try:
        original_bytes = original_manifest.read_bytes()
        original_sha256 = hashlib.sha256(original_bytes).hexdigest()
        _, _, verified_original_sha256 = load_frozen_original_8_definition(
            original_manifest
        )
        if (
            original_manifest.read_bytes() != original_bytes
            or verified_original_sha256 != original_sha256
        ):
            raise NdxDynamicShadowP4GateV2Error(
                "frozen original-8 bytes changed during verification"
            )
        payload = json.loads(original_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowP4GateV2Error(
            "frozen original-8 definition is unreadable"
        ) from exc
    securities = list((payload.get("definition") or {}).get("securities") or [])
    if len(securities) != 8:
        raise NdxDynamicShadowP4GateV2Error("frozen original-8 definition changed")
    _, rebalances, trades, path = replay_original8_control_path(
        decisions["strict_technology__return__v1"],
        frozen_securities=securities, sessions=sessions,
        valuation_closes=closes, execution_opens=opens,
        valuation_end_date=valuation_end,
    )
    compare(original_records, path, rebalances, trades, "original-8")
    return {
        "nominal_economic_replay_verified": True,
        "verified_selector_lane_count": len(decisions),
        "verified_original_8_control_count": 1,
        "frozen_original_8_manifest_sha256": original_sha256,
        "frozen_nominal_manifest_sha256_by_date": frozen_manifest_sha256_by_date,
    }


def rebuild_dynamic_p4_cohorts_from_canonical_chain(
    contract: Mapping[str, Any], *, repository_root: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Verify canonical raw chains and rebuild every mature monthly cohort."""

    root = Path(repository_root).resolve()
    sources = contract["source_contract"]
    calendar_path = _resolve(root, str(sources["reviewed_calendar_manifest"]))
    daily_path = _resolve(root, str(sources["daily_run_manifest"]))
    decision_root = _resolve(root, str(sources["realized_decision_root"]))
    calendar = verify_canonical_reviewed_calendar_v2(calendar_path, repository_root=root)
    daily = verify_daily_run_manifest(daily_path, repository_root=root)
    batches, decisions = _load_decision_payloads(decision_root)
    artifacts = daily["research_artifacts"]
    if Path(str(artifacts["observed_calendar_manifest"]["path"])).resolve() != calendar_path:
        raise NdxDynamicShadowP4GateV2Error("daily run is not bound to the reviewed calendar")
    daily_batches = artifacts["realized_batch_manifests"]
    if set(daily_batches) != {str(value["decision_date"]) for value in batches}:
        raise NdxDynamicShadowP4GateV2Error("daily run/decision batch registry changed")
    for batch in batches:
        decision = str(batch["decision_date"])
        _descriptor_matches(
            daily_batches[decision], decision_root / decision / "batch_manifest.json",
        )
    source_evidence = {
        "reviewed_calendar_manifest": {
            "path": calendar_path.as_posix(), "sha256": file_sha256(calendar_path),
        },
        "daily_run_manifest": {
            "path": daily_path.as_posix(), "sha256": file_sha256(daily_path),
        },
        "realized_decision_batch_count": len(batches),
        "canonical_chain_rebuilt": True,
        "caller_supplied_gate_booleans_trusted": False,
    }
    if not batches:
        if int(daily.get("realized_decision_batches", -1)) != 0:
            raise NdxDynamicShadowP4GateV2Error("daily run/decision chain count changed")
        return pd.DataFrame(columns=sorted(COHORT_COLUMNS)), {
            **source_evidence, "resolved_session_count": 0,
            "monthly_decision_count": 0, "selector_decision_counts": {},
            "nominal_economic_replay_verified": False,
            "verified_selector_lane_count": 0,
            "verified_original_8_control_count": 0,
            "frozen_original_8_manifest_sha256": None,
            "frozen_nominal_manifest_sha256_by_date": {},
        }
    if int(daily.get("realized_decision_batches", -1)) != len(batches):
        raise NdxDynamicShadowP4GateV2Error("daily run/decision batch count changed")

    lane_root = _resolve(root, str(sources["selector_lane_root"]))
    original_path = _resolve(root, str(sources["original_8_control_ledger"]))
    trace_path = _resolve(root, str(sources["target_012922_first_observed_trace"]))
    resolution_path = _resolve(root, str(sources["target_012922_resolution_ledger"]))
    final_root = _resolve(root, str(sources["fresh_search_final_root"]))
    role_seal_path = _resolve(root, str(sources["fresh_search_role_seal_ledger"]))
    lane_records = {
        selector: load_lane_path_ledger(lane_root / f"{selector}.jsonl", selector)
        for selector in sorted(_expected_selectors())
    }
    original = load_lane_path_ledger(original_path, "ndx_original_8_incumbent_v0")
    for selector, records in lane_records.items():
        _descriptor_matches(
            artifacts["selector_lane_ledgers"].get(selector),
            lane_root / f"{selector}.jsonl", rows=len(records),
        )
    _descriptor_matches(
        artifacts["original_8_control_ledger"], original_path, rows=len(original),
    )
    trace_records = load_target_012922_trace_ledger(trace_path)
    _descriptor_matches(
        artifacts["target_012922_trace_ledger"], trace_path, rows=len(trace_records),
    )
    resolved = load_resolution_ledger(
        resolution_path, first_observed_trace_path=trace_path,
    )
    resolved_dates = [str(value["session_date"]) for value in resolved]
    target_values = {
        str(value["session_date"]): float(value["normalized_value_usd"])
        for value in resolved
    }
    if len(resolved_dates) != len(set(resolved_dates)) or resolved_dates != sorted(resolved_dates):
        raise NdxDynamicShadowP4GateV2Error("resolved target calendar changed")
    calendar_dates = _calendar_dates(calendar)
    if resolved_dates:
        try:
            resolved_start = calendar_dates.index(resolved_dates[0])
        except ValueError as exc:
            raise NdxDynamicShadowP4GateV2Error(
                "resolved target starts outside the sealed calendar"
            ) from exc
        if resolved_dates != calendar_dates[
            resolved_start:resolved_start + len(resolved_dates)
        ]:
            raise NdxDynamicShadowP4GateV2Error(
                "resolved target is not a contiguous sealed calendar prefix"
            )
    original_by_date = {
        str(value["date"]): float(value["path_state"]["total_value_usd"])
        for value in original
    }
    lanes_by_date = {
        selector: {
            str(value["date"]): float(value["path_state"]["total_value_usd"])
            for value in records
        }
        for selector, records in lane_records.items()
    }
    target_values = {
        str(value["session_date"]): float(value["normalized_value_usd"])
        for value in resolved
    }

    verified_final_by_date: dict[str, dict[str, Any]] = {}
    for payloads in decisions.values():
        for payload in payloads:
            provenance = payload.get("provenance") or {}
            decision_date = str((payload.get("timing") or {}).get("decision_date") or "")
            expected_final = final_root / decision_date / "manifest.json"
            if Path(str(provenance.get("candidate_manifest_path") or "")).resolve() != expected_final:
                raise NdxDynamicShadowP4GateV2Error("decision candidate path is not canonical")
            if decision_date not in verified_final_by_date:
                try:
                    captured_final_bytes = expected_final.read_bytes()
                    captured_final = json.loads(captured_final_bytes.decode("utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise NdxDynamicShadowP4GateV2Error(
                        "final candidate manifest is unreadable"
                    ) from exc
                captured_final_sha256 = hashlib.sha256(
                    captured_final_bytes
                ).hexdigest()
                final = verify_final_candidate_snapshot(expected_final)
                role_record = verify_final_role_seal_record(
                    expected_final, role_seal_path, expected_final_root=final_root,
                )
                if (
                    expected_final.read_bytes() != captured_final_bytes
                    or captured_final != final
                    or role_record.get("final_manifest_sha256")
                    != captured_final_sha256
                ):
                    raise NdxDynamicShadowP4GateV2Error(
                        "final candidate manifest changed during verification"
                    )
                verified_final_by_date[decision_date] = {
                    "manifest": final, "role_record": role_record,
                    "role_record_sha256": role_record["record_sha256"],
                    "manifest_bytes": captured_final_bytes,
                    "manifest_sha256": captured_final_sha256,
                }
            verified_final = verified_final_by_date[decision_date]
            if expected_final.read_bytes() != verified_final["manifest_bytes"]:
                raise NdxDynamicShadowP4GateV2Error(
                    "final candidate manifest changed after verification"
                )
            final = verified_final["manifest"]
            if (
                provenance.get("candidate_manifest_sha256")
                != verified_final["manifest_sha256"]
                or provenance.get("snapshot_manifest_sha256") != final["snapshot_manifest_sha256"]
                or provenance.get("snapshot_fingerprint") != final["snapshot_fingerprint"]
            ):
                raise NdxDynamicShadowP4GateV2Error("decision candidate provenance changed")
            if payload.get("selected_candidate") != _selected_candidate_from_final(
                expected_final, final, str(payload.get("selector_id") or ""),
            ):
                raise NdxDynamicShadowP4GateV2Error(
                    "realized candidate differs from the append-only role seal"
                )
            _verify_realized_timing(
                calendar, payload, final,
                verified_final_by_date[decision_date]["role_record"],
            )

    batch_dates = [str(value["decision_date"]) for value in batches]
    batch_months = [pd.Timestamp(value).to_period("M") for value in batch_dates]
    if len(batch_months) != len(set(batch_months)):
        raise NdxDynamicShadowP4GateV2Error("monthly decision batches share a month")
    execution_dates = {
        str((payload.get("timing") or {}).get("execution_date") or "")
        for payloads in decisions.values() for payload in payloads
    }
    first_execution_by_batch = {
        decision_date: {
            str((payload.get("timing") or {}).get("execution_date") or "")
            for payloads in decisions.values() for payload in payloads
            if str((payload.get("timing") or {}).get("decision_date") or "") == decision_date
        }
        for decision_date in batch_dates
    }
    if any(len(values) != 1 for values in first_execution_by_batch.values()):
        raise NdxDynamicShadowP4GateV2Error("a decision batch spans execution sessions")
    first_execution = min(execution_dates)
    shadow_dates = [date for date in resolved_dates if date >= first_execution]
    if shadow_dates:
        _values(original, shadow_dates, "original-8 shadow")
        for selector, records in lane_records.items():
            _values(records, shadow_dates, f"{selector} shadow")
    economic_replay_evidence = _verify_replayed_lane_economics(
        root=root, daily=daily, calendar=calendar,
        decisions=decisions, lane_records=lane_records,
        original_records=original,
    )
    if any(
        value["manifest"].get("original_8_sha256")
        != economic_replay_evidence["frozen_original_8_manifest_sha256"]
        for value in verified_final_by_date.values()
    ):
        raise NdxDynamicShadowP4GateV2Error(
            "final candidate original-8 definition binding changed"
        )

    rows: list[dict[str, Any]] = []
    for selector, payloads in sorted(decisions.items()):
        track, role = _selector_parts(selector)
        for payload in payloads:
            selected = payload.get("selected_candidate")
            if selected is None:
                if role != "USER_PREFERENCE" or payload.get("status") != "REFERENCE_UNAVAILABLE_NOT_REPLACED":
                    raise NdxDynamicShadowP4GateV2Error("competitive selector lacks a candidate")
                continue
            timing = payload.get("timing") or {}
            decision_date = str(timing.get("decision_date") or "")
            execution_date = str(timing.get("execution_date") or "")
            cohort_dates = _cohort_dates_from_calendar(calendar_dates, execution_date)
            if not cohort_dates:
                continue
            if any(date not in target_values for date in cohort_dates):
                continue
            if any(date not in original_by_date for date in cohort_dates):
                raise NdxDynamicShadowP4GateV2Error("original-8 misses an exact cohort session")
            if any(date not in lanes_by_date[selector] for date in cohort_dates):
                raise NdxDynamicShadowP4GateV2Error("selector misses an exact cohort session")
            target_baseline = _target_baseline_at_decision(
                resolved, decision_date=decision_date,
            )
            if target_baseline is None:
                continue
            positions = selected.get("targets") or {}
            if not isinstance(positions, Mapping) or len(positions) != int(selected["holding_count"]):
                raise NdxDynamicShadowP4GateV2Error("dynamic k identity changed")
            tickers = sorted(str(value.get("ticker") or "") for value in positions.values())
            security_ids = sorted(str(value) for value in positions)
            if any(not value for value in tickers + security_ids):
                raise NdxDynamicShadowP4GateV2Error("dynamic candidate identity is incomplete")
            _verify_execution_identity(
                lane_records[selector], selected, decision_date=decision_date,
                execution_date=execution_date,
            )
            execution_index = calendar_dates.index(execution_date)
            previous_session_date = (
                calendar_dates[execution_index - 1] if execution_index > 0 else None
            )
            candidate_baseline = _pre_execution_portfolio_value(
                lane_records[selector], execution_date=execution_date,
                decision_date=decision_date, previous_session_date=previous_session_date,
                require_rebalance=True,
            )
            original_baseline = _pre_execution_portfolio_value(
                original, execution_date=execution_date, decision_date=None,
                previous_session_date=previous_session_date, require_rebalance=False,
            )
            candidate_return, candidate_dd = _path_metrics(
                [lanes_by_date[selector][date] for date in cohort_dates],
                baseline_value=candidate_baseline,
            )
            original_return, original_dd = _path_metrics(
                [original_by_date[date] for date in cohort_dates],
                baseline_value=original_baseline,
            )
            target_return, target_dd = _path_metrics(
                [target_values[date] for date in cohort_dates],
                baseline_value=target_baseline,
            )
            rows.append({
                "selector_id": selector,
                "universe_track": track,
                "policy_role": role,
                "decision_date": decision_date,
                "execution_date": execution_date,
                "exit_date": cohort_dates[-1],
                "starting_portfolio_id": str(selected.get("portfolio_id") or ""),
                "evaluation_path_semantics": (
                    "SELECTOR_POLICY_CONTINUOUS_PATH_WITH_SUBSEQUENT_MONTHLY_REBALANCES"
                ),
                "fixed_starting_portfolio_hold_assumed": False,
                "holding_count": int(selected["holding_count"]),
                "active_tickers": json.dumps(tickers, separators=(",", ":")),
                "active_security_ids": json.dumps(security_ids, separators=(",", ":")),
                "horizon_trading_sessions": 126,
                "return_basis": "126_SESSION_CUMULATIVE_RETURN_NOT_ANNUALIZED",
                "observation_regime": _regime(
                    _qqq_closes_for_decision(calendar, decision_date), decision_date,
                ),
                "portfolio_return": candidate_return,
                "original_8_return": original_return,
                "target_012922_return": target_return,
                "portfolio_max_drawdown": candidate_dd,
                "original_8_max_drawdown": original_dd,
                "target_012922_max_drawdown": target_dd,
            })
    counts = {selector: len(values) for selector, values in decisions.items()}
    return pd.DataFrame(rows, columns=sorted(COHORT_COLUMNS)), {
        **source_evidence,
        **economic_replay_evidence,
        "resolved_session_count": len(shadow_dates),
        "monthly_decision_count": len(set(batch_months)),
        "selector_decision_counts": counts,
        "selector_lane_prefix_sha256": {
            selector: file_sha256(lane_root / f"{selector}.jsonl")
            for selector in sorted(_expected_selectors())
        },
        "original_8_control_sha256": file_sha256(original_path),
        "target_012922_resolution_sha256": (
            file_sha256(resolution_path) if resolution_path.is_file() else None
        ),
        "fresh_candidate_role_seal_sha256": file_sha256(role_seal_path),
        "verified_final_candidate_manifests": {
            date: {
                "path": (final_root / date / "manifest.json").as_posix(),
                "sha256": value["manifest_sha256"],
                "role_seal_record_sha256": value["role_record_sha256"],
            }
            for date, value in sorted(verified_final_by_date.items())
        },
    }


def assess_proposed_dynamic_p4_gate(
    contract_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    contract = load_proposed_dynamic_p4_contract(contract_path)
    cohorts, evidence = rebuild_dynamic_p4_cohorts_from_canonical_chain(
        contract, repository_root=repository_root,
    )
    result = summarize_dynamic_p4_cohorts(
        cohorts,
        resolved_session_count=evidence["resolved_session_count"],
        monthly_decision_count=evidence["monthly_decision_count"],
        selector_decision_counts=evidence["selector_decision_counts"],
    )
    if result["status"] == "SYNTHETIC_CAPABILITY_EVIDENCE_ONLY":
        result["status"] = "READY_FOR_INDEPENDENT_DYNAMIC_P4_REGISTRATION_REVIEW_ONLY"
        result["proposed_gate_passed_selector_ids"] = result.pop(
            "synthetic_capability_passed_selector_ids"
        )
    else:
        result.pop("synthetic_capability_passed_selector_ids", None)
    result.update({
        "source_chain_evidence": evidence,
        "raw_cohort_rows_rebuilt": len(cohorts),
        "return_data_read": bool(len(cohorts)),
        "fresh_oos_consumed_for_research_evaluation": bool(len(cohorts)),
    })
    return result


__all__ = [
    "COHORT_COLUMNS", "NdxDynamicShadowP4GateV2Error",
    "assess_proposed_dynamic_p4_gate", "load_proposed_dynamic_p4_contract",
    "rebuild_dynamic_p4_cohorts_from_canonical_chain",
    "summarize_dynamic_p4_cohorts",
]
