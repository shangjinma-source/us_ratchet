"""Append-only 012922 outcome resolution and non-admission shadow diagnostics."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_daily import (
    canonical_sha256,
    load_lane_path_ledger,
    load_target_012922_trace_ledger,
    verify_realized_decision_chain,
)
from data.versioning import file_sha256


class NdxDynamicShadowOutcomeError(ValueError):
    """Raised when resolved target or paired outcome evidence is not reproducible."""


TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
RESOLUTION_KEYS = {
    "schema_version", "artifact_type", "sequence", "session_date",
    "first_observed_record_sha256", "status", "source_date", "source_close",
    "normalized_value_usd", "lag_calendar_days", "carry_forward_used",
    "resolved_at_utc", "source_fetched_at_utc",
    "source_csv_snapshot_path", "source_manifest_snapshot_path",
    "source_csv_sha256", "source_manifest_sha256", "publication_time_known",
    "previous_resolution_sha256", "evidence_role", "selection_time_knowledge_claimed",
    "performance_admission_allowed", "performance_veto_allowed",
    "promotion_allowed", "live_mutation", "record_sha256",
}


def _system_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: Any, label: str) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if pd.isna(result) or result.tzinfo is None:
        raise NdxDynamicShadowOutcomeError(f"{label} must be timezone-aware")
    return result.tz_convert("UTC")


def load_outcome_contract(path: str | Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowOutcomeError("outcome contract is missing/invalid") from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowOutcomeError("outcome contract must be a mapping")
    contract = dict(value)
    resolution = contract.get("resolution_contract") or {}
    evaluation = contract.get("evaluation_contract") or {}
    formal = contract.get("formal_forward_v5_boundary") or {}
    mutation = contract.get("mutation_boundary") or {}
    if (
        contract.get("schema_version") != 1
        or contract.get("contract_id") != "ndx_dynamic_shadow_outcome_v1"
        or contract.get("status") != "IMPLEMENTED_RESEARCH_ONLY_NOT_AUTOMATION_REGISTERED"
        or contract.get("research_track") != "portfolio_optimization"
        or contract.get("migration_control_included") is not False
        or resolution.get("target_id") != "012922"
        or resolution.get("event_role") != "RESOLVED_OUTCOME_BENCHMARK"
        or resolution.get("exact_session_nav_required") is not False
        or resolution.get("no_future_asof_nav_required") is not True
        or resolution.get("cross_calendar_carry_forward_allowed") is not True
        or resolution.get("first_observed_trace_is_rewritten") is not False
        or resolution.get("immutable_source_snapshot_required") is not True
        or resolution.get("append_only_hash_chain_required") is not True
        or resolution.get("retrospective_value_as_if_known_at_selection_allowed") is not False
        or int(evaluation.get("independent_selector_lane_count", -1)) != 10
        or int(evaluation.get("minimum_shadow_trading_sessions", -1)) != 252
        or int(evaluation.get("minimum_monthly_decisions", -1)) != 12
        or evaluation.get("early_performance_veto_allowed") is not False
        or evaluation.get("early_performance_admission_allowed") is not False
        or evaluation.get("target_scalar_used_for_admission") is not False
        or formal.get("policy_id") != "ndx_challenger_forward_v5_componentwise_target_v1"
        or int(formal.get("primary_horizon_trading_days", -1)) != 126
        or int(formal.get("minimum_fresh_mature_cohorts", -1)) != 12
        or int(formal.get("minimum_distinct_regimes", -1)) != 2
        or formal.get("dynamic_shadow_substitutes_formal_v5_gate") is not False
        or formal.get("dynamic_shadow_directly_promotes_configuration") is not False
        or formal.get("dynamic_shadow_directly_promotes_live") is not False
        or mutation.get("research_output_only") is not True
        or mutation.get("automation_registered") is not False
        or any(mutation.get(key) is not False for key in (
            "live_config_mutation_allowed", "state_mutation_allowed",
            "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
            "order_creation_allowed", "promotion_allowed",
        ))
    ):
        raise NdxDynamicShadowOutcomeError("outcome evidence/admission boundary changed")
    return contract


def _validate_source_snapshot(
    csv_path: Path, manifest_path: Path, csv_sha256: str, manifest_sha256: str,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    if (
        not csv_path.is_file() or not manifest_path.is_file()
        or file_sha256(csv_path) != csv_sha256
        or file_sha256(manifest_path) != manifest_sha256
    ):
        raise NdxDynamicShadowOutcomeError("resolved target source snapshot hash changed")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = pd.read_csv(csv_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowOutcomeError("resolved target source snapshot is invalid") from exc
    if not {"Date", "Close"}.issubset(frame.columns):
        raise NdxDynamicShadowOutcomeError("resolved target source schema changed")
    frame = frame[["Date", "Close"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise").dt.normalize()
    frame["Close"] = pd.to_numeric(frame["Close"], errors="raise")
    if (
        manifest.get("dataset_key") != "012922"
        or manifest.get("content_sha256") != csv_sha256
        or int(manifest.get("row_count", -1)) != len(frame)
        or manifest.get("publication_time_known") is not False
        or frame["Date"].duplicated().any() or not frame["Date"].is_monotonic_increasing
        or (~np.isfinite(frame["Close"]) | frame["Close"].le(0)).any()
    ):
        raise NdxDynamicShadowOutcomeError("resolved target source content changed")
    return frame, _aware_utc(manifest.get("fetched_at"), "target source fetched-at")


def load_resolution_ledger(
    path: str | Path, *, first_observed_trace_path: str | Path,
) -> list[dict[str, Any]]:
    trace = load_target_012922_trace_ledger(first_observed_trace_path)
    trace_by_date = {str(value["session_date"]): value for value in trace}
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    previous_hash = None
    previous_date = None
    previous_resolved_at = None
    base_close = None
    for sequence, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise NdxDynamicShadowOutcomeError("blank resolved-outcome ledger row")
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != RESOLUTION_KEYS:
            raise NdxDynamicShadowOutcomeError("resolved-outcome ledger schema changed")
        unsigned = dict(value)
        declared = str(unsigned.pop("record_sha256", ""))
        session_date = pd.Timestamp(value.get("session_date")).normalize()
        trace_record = trace_by_date.get(session_date.date().isoformat())
        resolved_at = _aware_utc(value.get("resolved_at_utc"), "resolved-at")
        csv_path = Path(str(value.get("source_csv_snapshot_path") or "")).resolve()
        manifest_path = Path(str(value.get("source_manifest_snapshot_path") or "")).resolve()
        expected_source_root = (source.parent / "source_snapshots").resolve()
        frame, fetched_at = _validate_source_snapshot(
            csv_path, manifest_path, str(value.get("source_csv_sha256") or ""),
            str(value.get("source_manifest_sha256") or ""),
        )
        available = frame.loc[frame["Date"].le(session_date)]
        selected = available.iloc[-1] if not available.empty else None
        source_close = float(value.get("source_close"))
        source_date = pd.Timestamp(value.get("source_date")).normalize()
        if base_close is None:
            base_close = source_close
        if (
            canonical_sha256(unsigned) != declared
            or int(value.get("sequence", -1)) != sequence
            or value.get("artifact_type") != "ndx_dynamic_shadow_target_012922_resolution_event"
            or value.get("status") != "RESOLVED_NO_FUTURE_ASOF_NAV"
            or value.get("evidence_role") != "RESOLVED_OUTCOME_BENCHMARK"
            or value.get("previous_resolution_sha256") != previous_hash
            or previous_date is not None and session_date <= previous_date
            or sequence > len(trace)
            or session_date.date().isoformat() != str(trace[sequence - 1]["session_date"])
            or previous_resolved_at is not None and resolved_at < previous_resolved_at
            or trace_record is None
            or value.get("first_observed_record_sha256") != trace_record.get("record_sha256")
            or selected is None
            or source_date > session_date
            or pd.Timestamp(selected["Date"]).normalize() != source_date
            or not np.isclose(float(selected["Close"]), source_close, atol=1e-12)
            or int(value.get("lag_calendar_days", -1)) != (session_date - source_date).days
            or bool(value.get("carry_forward_used")) != (source_date < session_date)
            or not np.isclose(
                float(value.get("normalized_value_usd")), 25000.0 * source_close / base_close,
                atol=1e-8,
            )
            or csv_path.parent != expected_source_root or manifest_path.parent != expected_source_root
            or fetched_at > resolved_at
            or _aware_utc(value.get("source_fetched_at_utc"), "source fetched-at") != fetched_at
            or value.get("publication_time_known") is not False
            or value.get("selection_time_knowledge_claimed") is not False
            or value.get("performance_admission_allowed") is not False
            or value.get("performance_veto_allowed") is not False
            or value.get("promotion_allowed") is not False
            or value.get("live_mutation") is not False
        ):
            raise NdxDynamicShadowOutcomeError("resolved-outcome hash/source boundary changed")
        records.append(value)
        previous_hash = declared
        previous_date = session_date
        previous_resolved_at = resolved_at
    return records


def append_resolution_events(
    ledger_path: str | Path, *, first_observed_trace_path: str | Path,
    target_nav: pd.DataFrame, source_csv_snapshot_path: str | Path,
    source_manifest_snapshot_path: str | Path,
) -> list[dict[str, Any]]:
    destination = Path(ledger_path)
    trace = load_target_012922_trace_ledger(first_observed_trace_path)
    existing = load_resolution_ledger(
        destination, first_observed_trace_path=first_observed_trace_path,
    )
    csv_path = Path(source_csv_snapshot_path).resolve()
    manifest_path = Path(source_manifest_snapshot_path).resolve()
    expected_source_root = (destination.parent / "source_snapshots").resolve()
    if csv_path.parent != expected_source_root or manifest_path.parent != expected_source_root:
        raise NdxDynamicShadowOutcomeError("resolved target source path is not canonical")
    csv_hash, manifest_hash = file_sha256(csv_path), file_sha256(manifest_path)
    frame, fetched_at = _validate_source_snapshot(csv_path, manifest_path, csv_hash, manifest_hash)
    supplied = target_nav[["Date", "Close"]].copy()
    supplied["Date"] = pd.to_datetime(supplied["Date"], errors="raise").dt.normalize()
    supplied["Close"] = pd.to_numeric(supplied["Close"], errors="raise")
    if supplied.reset_index(drop=True).to_dict("records") != frame.to_dict("records"):
        raise NdxDynamicShadowOutcomeError("caller target NAV differs from immutable source")
    resolved_at = _aware_utc(_system_utc_now(), "resolved-at")
    if fetched_at > resolved_at:
        raise NdxDynamicShadowOutcomeError("target source was fetched after resolution time")
    previous_hash = existing[-1]["record_sha256"] if existing else None
    base_close = float(existing[0]["source_close"]) if existing else None
    additions: list[dict[str, Any]] = []
    for trace_record in trace[len(existing):]:
        session_date = pd.Timestamp(trace_record["session_date"]).normalize()
        available = frame.loc[frame["Date"].le(session_date)]
        if available.empty:
            break
        selected = available.iloc[-1]
        source_date = pd.Timestamp(selected["Date"]).normalize()
        close = float(selected["Close"])
        if base_close is None:
            base_close = close
        record = {
            "schema_version": 1,
            "artifact_type": "ndx_dynamic_shadow_target_012922_resolution_event",
            "sequence": len(existing) + len(additions) + 1,
            "session_date": session_date.date().isoformat(),
            "first_observed_record_sha256": trace_record["record_sha256"],
            "status": "RESOLVED_NO_FUTURE_ASOF_NAV",
            "source_date": source_date.date().isoformat(),
            "source_close": close,
            "normalized_value_usd": 25000.0 * close / base_close,
            "lag_calendar_days": int((session_date - source_date).days),
            "carry_forward_used": bool(source_date < session_date),
            "resolved_at_utc": resolved_at.isoformat(),
            "source_fetched_at_utc": fetched_at.isoformat(),
            "source_csv_snapshot_path": csv_path.as_posix(),
            "source_manifest_snapshot_path": manifest_path.as_posix(),
            "source_csv_sha256": csv_hash,
            "source_manifest_sha256": manifest_hash,
            "publication_time_known": False,
            "previous_resolution_sha256": previous_hash,
            "evidence_role": "RESOLVED_OUTCOME_BENCHMARK",
            "selection_time_knowledge_claimed": False,
            "performance_admission_allowed": False,
            "performance_veto_allowed": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        record["record_sha256"] = canonical_sha256(record)
        additions.append(record)
        previous_hash = record["record_sha256"]
    if additions:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8", newline="\n") as handle:
            for record in additions:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return load_resolution_ledger(
        destination, first_observed_trace_path=first_observed_trace_path,
    )


def _path_metrics(values: pd.Series) -> dict[str, float | None]:
    series = pd.to_numeric(values, errors="raise").astype(float)
    if series.empty or (~np.isfinite(series) | series.le(0)).any():
        raise NdxDynamicShadowOutcomeError("paired path contains invalid values")
    terminal_return = float(series.iloc[-1] / series.iloc[0] - 1.0)
    maximum_drawdown = float((1.0 - series / series.cummax()).max())
    annualized = None
    if len(series) > 1:
        annualized = float((series.iloc[-1] / series.iloc[0]) ** (252.0 / (len(series) - 1)) - 1.0)
    return {
        "terminal_return": terminal_return,
        "annualized_return": annualized,
        "maximum_drawdown": maximum_drawdown,
    }


def evaluate_dynamic_shadow_outcomes(
    *, selector_lane_ledgers: Mapping[str, str | Path], original_8_ledger: str | Path,
    resolution_ledger: str | Path, first_observed_trace_path: str | Path,
    realized_decision_root: str | Path,
) -> dict[str, Any]:
    expected = {f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES}
    if set(selector_lane_ledgers) != expected:
        raise NdxDynamicShadowOutcomeError("evaluation requires the exact 10 selector lanes")
    lanes = {
        selector: load_lane_path_ledger(path, selector)
        for selector, path in selector_lane_ledgers.items()
    }
    original = load_lane_path_ledger(original_8_ledger, "ndx_original_8_incumbent_v0")
    resolved = load_resolution_ledger(
        resolution_ledger, first_observed_trace_path=first_observed_trace_path,
    )
    decisions = verify_realized_decision_chain(realized_decision_root)
    dates = [str(value["session_date"]) for value in resolved]
    decision_months = {
        pd.Timestamp(value["decision_date"]).to_period("M")
        for value in decisions
        if dates and pd.Timestamp(value["decision_date"]).normalize() <= pd.Timestamp(dates[-1])
    }
    monthly_decision_count = len(decision_months)
    if not dates:
        status = "EARLY_PROGRESS_FALSIFICATION_DIAGNOSTIC_ONLY"
        metrics: dict[str, Any] = {}
    else:
        def values(records: Iterable[Mapping[str, Any]], label: str) -> pd.Series:
            mapping = {str(value["date"]): float(value["path_state"]["total_value_usd"]) for value in records}
            if any(date not in mapping for date in dates):
                raise NdxDynamicShadowOutcomeError(f"{label} does not cover resolved target calendar")
            return pd.Series([mapping[date] for date in dates], index=dates, dtype=float)

        target_values = pd.Series(
            [float(value["normalized_value_usd"]) for value in resolved], index=dates,
        )
        original_values = values(original, "original-8")
        target_metrics = _path_metrics(target_values)
        original_metrics = _path_metrics(original_values)
        metrics = {}
        for selector_id, records in sorted(lanes.items()):
            selector_values = values(records, selector_id)
            selector_metrics = _path_metrics(selector_values)
            metrics[selector_id] = {
                "selector": selector_metrics,
                "original_8": original_metrics,
                "target_012922": target_metrics,
                "terminal_return_minus_original_8": (
                    selector_metrics["terminal_return"] - original_metrics["terminal_return"]
                ),
                "terminal_return_minus_target_012922": (
                    selector_metrics["terminal_return"] - target_metrics["terminal_return"]
                ),
                "maximum_drawdown_cost_minus_original_8": (
                    selector_metrics["maximum_drawdown"] - original_metrics["maximum_drawdown"]
                ),
                "maximum_drawdown_cost_minus_target_012922": (
                    selector_metrics["maximum_drawdown"] - target_metrics["maximum_drawdown"]
                ),
            }
        status = (
            "ONE_YEAR_SHADOW_RESEARCH_REVIEW_READY_NON_ADMISSION"
            if len(dates) >= 252 and monthly_decision_count >= 12
            else "EARLY_PROGRESS_FALSIFICATION_DIAGNOSTIC_ONLY"
        )
    return {
        "schema_version": 1,
        "artifact_type": "ndx_dynamic_shadow_resolved_outcome_evaluation",
        "status": status,
        "resolved_trading_session_count": len(dates),
        "monthly_decision_count": monthly_decision_count,
        "minimum_shadow_trading_sessions": 252,
        "minimum_monthly_decisions": 12,
        "same_calendar_selector_original8_target": bool(dates),
        "selector_lane_count": 10,
        "metrics": metrics,
        "evidence_role": (
            "FALSIFICATION_AND_PROGRESS_DIAGNOSTIC"
            if status.startswith("EARLY_PROGRESS") else "ONE_YEAR_SHADOW_RESEARCH_REVIEW"
        ),
        "performance_admission_allowed": False,
        "performance_veto_allowed": False,
        "target_scalar_used_for_admission": False,
        "formal_v5_gate_substitution_allowed": False,
        "formal_v5_required_horizon_trading_days": 126,
        "formal_v5_required_mature_cohorts": 12,
        "formal_v5_required_distinct_regimes": 2,
        "promotion_allowed": False,
        "live_mutation": False,
    }


__all__ = [
    "NdxDynamicShadowOutcomeError", "append_resolution_events",
    "evaluate_dynamic_shadow_outcomes", "load_outcome_contract",
    "load_resolution_ledger",
]
