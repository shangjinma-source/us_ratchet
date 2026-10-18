"""Research-only daily state machine for prospective dynamic-cardinality shadow paths.

The module owns no live configuration or broker state.  It separates a monthly
decision into three irreversible evidence boundaries: point-in-time input seal,
pre-open candidate/role seal, and later execution-date realization from the
append-only observed-session calendar.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_dynamic_shadow_fresh_search import (
    EXECUTION_COORDINATE_RULE,
    load_frozen_original_8_definition,
    verify_final_candidate_snapshot,
)
from backtest.ndx_dynamic_whole_lot_path import (
    simulate_dynamic_security_id_whole_lot_path,
)
from data.versioning import file_sha256


class NdxDynamicShadowDailyError(ValueError):
    """Raised when a daily phase cannot be proven without backfill or leakage."""


TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
FIRST_DECISION_DATE = pd.Timestamp("2026-10-01")
BEIJING = ZoneInfo("Asia/Shanghai")


def _system_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise NdxDynamicShadowDailyError(f"invalid boolean value: {value!r}")


def _aware_utc(value: Any, label: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise NdxDynamicShadowDailyError(f"invalid {label}") from exc
    if pd.isna(result) or result.tzinfo is None:
        raise NdxDynamicShadowDailyError(f"{label} must be timezone-aware")
    return result.tz_convert("UTC")


def load_daily_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowDailyError(f"cannot read daily contract: {source}") from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowDailyError("daily contract must be a mapping")
    contract = dict(value)
    if (
        contract.get("schema_version") != 1
        or contract.get("orchestrator_id") != "ndx_dynamic_shadow_daily_v1"
        or contract.get("status") != "IMPLEMENTED_RESEARCH_ONLY_NOT_AUTOMATION_REGISTERED"
        or contract.get("research_track") != "portfolio_optimization"
        or contract.get("migration_control_included") is not False
    ):
        raise NdxDynamicShadowDailyError("unexpected daily orchestrator identity/track")
    schedule = contract.get("schedule_contract") or {}
    if (
        str(schedule.get("first_decision_not_before")) != "2026-10-01"
        or schedule.get("execution_coordinate_rule") != EXECUTION_COORDINATE_RULE
        or schedule.get("missed_decision_action") != "NO_DECISION_NO_BACKFILL"
        or schedule.get("retrospective_decision_backfill_allowed") is not False
        or schedule.get("candidate_seal_must_precede_realized_open") is not True
    ):
        raise NdxDynamicShadowDailyError("daily timing/no-backfill contract changed")
    stages = contract.get("stage_contract") or {}
    if (
        stages.get("all_track_k_shards_required") is not True
        or int(stages.get("expected_independent_lane_count", -1)) != 10
        or stages.get("historical_candidate_replay_allowed") is not False
        or stages.get("frozen_forward_candidate_source_allowed") is not False
        or stages.get("candidate_training_search_counts_as_fresh_oos") is not False
    ):
        raise NdxDynamicShadowDailyError("daily stage/evidence boundary changed")
    execution = contract.get("execution_contract") or {}
    if (
        float(execution.get("initial_cash_usd", 0)) != 25000.0
        or float(execution.get("minimum_cash_buffer_usd", -1)) != 100.0
        or float(execution.get("transaction_cost_bps", -1)) != 10.0
        or execution.get("fractional_shares_allowed") is not False
        or execution.get("execution_price") != "unadjusted_nominal_open"
        or execution.get("valuation_price") != "unadjusted_nominal_close"
        or execution.get("security_identity_key") != "security_id"
        or execution.get("cash_and_integer_shares_continuous") is not True
    ):
        raise NdxDynamicShadowDailyError("daily $25k whole-lot execution contract changed")
    benchmarks = contract.get("benchmark_contract") or {}
    if (
        int(benchmarks.get("selector_lane_count", -1)) != 10
        or benchmarks.get("benchmark_controls_are_selector_lanes") is not False
        or benchmarks.get("original_8_control_id") != "ndx_original_8_incumbent_v0"
        or benchmarks.get("original_8_execution_mode")
        != "monthly_whole_lot_rebalance_same_execution_session"
        or float(benchmarks.get("original_8_initial_cash_usd", 0)) != 25000.0
        or float(benchmarks.get("original_8_minimum_cash_buffer_usd", -1)) != 100.0
        or float(benchmarks.get("original_8_transaction_cost_bps", -1)) != 10.0
        or benchmarks.get("target_012922_control_id")
        != "target_012922_dynamic_external_target"
        or benchmarks.get("target_012922_execution_simulated") is not False
        or benchmarks.get("target_012922_alignment")
        != "first_observed_no_future_asof"
        or benchmarks.get("target_012922_trace_role")
        != "runtime_diagnostic_not_resolved_outcome_benchmark"
        or benchmarks.get("target_012922_resolved_outcome_chain_implemented") is not False
        or benchmarks.get("target_012922_publication_time_known") is not False
        or benchmarks.get("exact_three_way_calendar_alignment_required") is not True
        or benchmarks.get("benchmark_prefixes_append_only") is not True
    ):
        raise NdxDynamicShadowDailyError("daily dual-benchmark contract changed")
    mutation = contract.get("mutation_boundary") or {}
    if mutation.get("research_output_only") is not True or any(
        mutation.get(key) is not False for key in (
            "live_config_mutation_allowed", "state_mutation_allowed",
            "broker_snapshot_mutation_allowed", "today_advice_mutation_allowed",
            "order_creation_allowed", "promotion_allowed", "task_registration_allowed",
        )
    ):
        raise NdxDynamicShadowDailyError("daily mutation boundary changed")
    return contract


def normalize_observed_sessions(sessions: pd.DataFrame) -> pd.DataFrame:
    required = {
        "session_date", "open_timestamp_utc", "close_timestamp_utc", "completed",
        "is_first_observed_session_of_month", "origin", "decision_eligible",
    }
    if sessions.empty or not required.issubset(sessions.columns):
        raise NdxDynamicShadowDailyError("observed session projection is incomplete")
    result = sessions.copy()
    result["session_date"] = pd.to_datetime(result["session_date"], errors="raise").dt.normalize()
    if result["session_date"].duplicated().any() or not result["session_date"].is_monotonic_increasing:
        raise NdxDynamicShadowDailyError("observed sessions must be unique and sorted")
    for column in ("completed", "is_first_observed_session_of_month", "decision_eligible"):
        result[column] = result[column].map(_truth)
    if not result["completed"].all():
        raise NdxDynamicShadowDailyError("observed projection cannot contain incomplete sessions")
    for column in ("open_timestamp_utc", "close_timestamp_utc"):
        result[column] = result[column].map(lambda value: _aware_utc(value, column))
    if (result["open_timestamp_utc"] >= result["close_timestamp_utc"]).any():
        raise NdxDynamicShadowDailyError("observed session open/close ordering is invalid")
    return result


def validate_nominal_price_evidence(
    values: pd.DataFrame, sessions: pd.DataFrame, *, tickers: Iterable[str],
    valuation_end_date: Any,
) -> pd.DataFrame:
    """Require one separately sourced nominal Open/Close per ticker-session."""
    required = {"Date", "ticker", "Open", "Close"}
    if values.empty or not required.issubset(values.columns):
        raise NdxDynamicShadowDailyError("nominal price evidence schema is incomplete")
    names = sorted({str(value).strip().upper() for value in tickers if str(value).strip()})
    if not names:
        raise NdxDynamicShadowDailyError("nominal price evidence ticker set is empty")
    calendar = normalize_observed_sessions(sessions)
    end = pd.Timestamp(valuation_end_date).normalize()
    expected_dates = calendar.loc[calendar["session_date"].le(end), "session_date"]
    if expected_dates.empty or expected_dates.iloc[-1] != end:
        raise NdxDynamicShadowDailyError("nominal evidence end is not an observed completed session")
    frame = values[["Date", "ticker", "Open", "Close"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="raise").dt.normalize()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    if frame[["Date", "ticker"]].duplicated().any():
        raise NdxDynamicShadowDailyError("nominal price evidence duplicates ticker-session")
    for column in ("Open", "Close"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if (~np.isfinite(frame[column]) | frame[column].le(0)).any():
            raise NdxDynamicShadowDailyError(f"nominal {column} contains nonpositive/nonfinite values")
    expected = {
        (date, ticker)
        for date in expected_dates.tolist()
        for ticker in names
    }
    observed = set(frame[["Date", "ticker"]].itertuples(index=False, name=None))
    if observed != expected:
        raise NdxDynamicShadowDailyError(
            "nominal price evidence lacks exact ticker-session Cartesian coverage"
        )
    return frame.sort_values(["Date", "ticker"], kind="stable").reset_index(drop=True)


def decision_coordinates(sessions: pd.DataFrame) -> list[str]:
    frame = normalize_observed_sessions(sessions)
    eligible = frame.loc[
        frame["decision_eligible"]
        & frame["is_first_observed_session_of_month"]
        & frame["origin"].astype(str).eq("PROSPECTIVE_OBSERVED_APPEND")
        & frame["session_date"].ge(FIRST_DECISION_DATE)
    ]
    return eligible["session_date"].dt.date.astype(str).tolist()


def within_conservative_seal_window(
    now_utc: Any, *, decision_close_timestamp_utc: Any,
) -> bool:
    now = _aware_utc(now_utc, "system now")
    close = _aware_utc(decision_close_timestamp_utc, "decision close")
    local_now = now.tz_convert(BEIJING)
    local_close = close.tz_convert(BEIJING)
    return bool(
        now >= close
        and local_now.date() == local_close.date()
        and time(6, 0) <= local_now.time().replace(tzinfo=None) < time(21, 30)
    )


def resolve_first_observed_execution_session(
    sessions: pd.DataFrame, decision_date: Any,
) -> dict[str, str] | None:
    frame = normalize_observed_sessions(sessions)
    decision = pd.Timestamp(decision_date).normalize()
    later = frame.loc[frame["session_date"].gt(decision)]
    if later.empty:
        return None
    row = later.iloc[0]
    return {
        "decision_date": decision.date().isoformat(),
        "execution_date": row["session_date"].date().isoformat(),
        "execution_open_timestamp_utc": row["open_timestamp_utc"].isoformat(),
        "execution_close_timestamp_utc": row["close_timestamp_utc"].isoformat(),
    }


def classify_daily_phase(
    sessions: pd.DataFrame, *, decision_date: str, now_utc: Any,
    input_snapshot_exists: bool, final_candidate_exists: bool,
    no_decision_disposition_exists: bool, decisions_realized: bool,
    final_roles_sealed_at_utc: Any | None = None,
) -> str:
    frame = normalize_observed_sessions(sessions)
    decision = pd.Timestamp(decision_date).normalize()
    row = frame.loc[frame["session_date"].eq(decision)]
    if len(row) != 1 or decision.date().isoformat() not in decision_coordinates(frame):
        raise NdxDynamicShadowDailyError("decision coordinate is not prospectively eligible")
    if no_decision_disposition_exists:
        return "NO_DECISION_NO_BACKFILL"
    execution = resolve_first_observed_execution_session(frame, decision)
    if decisions_realized:
        return "APPEND_CLOSE_VALUATION"
    if execution is not None:
        if not final_candidate_exists:
            return "NO_DECISION_NO_BACKFILL"
        if final_roles_sealed_at_utc is None:
            raise NdxDynamicShadowDailyError("final role seal timestamp is required")
        if _aware_utc(final_roles_sealed_at_utc, "role seal") >= _aware_utc(
            execution["execution_open_timestamp_utc"], "execution open"
        ):
            return "NO_DECISION_NO_BACKFILL"
        return "REALIZE_NEXT_SESSION_AND_APPEND_PATHS"
    in_window = within_conservative_seal_window(
        now_utc, decision_close_timestamp_utc=row.iloc[0]["close_timestamp_utc"]
    )
    if not input_snapshot_exists:
        return "SEAL_FRESH_PIT_INPUT" if in_window else "NO_DECISION_NO_BACKFILL"
    if not final_candidate_exists:
        return "RESUME_ALL_K_FRESH_SEARCH" if in_window else "NO_DECISION_NO_BACKFILL"
    if final_roles_sealed_at_utc is None:
        raise NdxDynamicShadowDailyError("final role seal timestamp is required")
    if not within_conservative_seal_window(
        final_roles_sealed_at_utc,
        decision_close_timestamp_utc=row.iloc[0]["close_timestamp_utc"],
    ):
        return "NO_DECISION_NO_BACKFILL"
    return "WAIT_FOR_NEXT_OBSERVED_SESSION"


def _split(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    return value


def _target_payload(row: pd.Series) -> dict[str, dict[str, Any]]:
    tickers = _split(row["tickers"])
    security_ids = _split(row["security_ids"])
    issuer_ids = _split(row["issuer_ids"])
    raw_weights = _split(row["weights"])
    weights: dict[str, float] = {}
    for item in raw_weights:
        ticker, separator, raw = item.rpartition(":")
        if not separator or ticker in weights:
            raise NdxDynamicShadowDailyError("selected candidate weights are malformed")
        weights[ticker] = float(raw)
    if (
        len(tickers) != int(row["holding_count"])
        or len(tickers) != len(set(tickers))
        or len(security_ids) != len(set(security_ids))
        or len(issuer_ids) != len(set(issuer_ids))
        or not (len(tickers) == len(security_ids) == len(issuer_ids))
        or set(weights) != set(tickers)
        or not np.isclose(sum(weights.values()), 1.0, atol=1e-6)
    ):
        raise NdxDynamicShadowDailyError("selected candidate identity/weight cardinality mismatch")
    return {
        security_id: {
            "ticker": ticker,
            "issuer_id": issuer_id,
            "target_weight": float(weights[ticker]),
        }
        for ticker, security_id, issuer_id in zip(tickers, security_ids, issuer_ids)
    }


def build_realized_lane_decisions(
    final_manifest_path: str | Path, sessions: pd.DataFrame, *,
    previous_lane_heads: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    manifest_path = Path(final_manifest_path)
    manifest = verify_final_candidate_snapshot(manifest_path)
    artifacts = manifest["artifacts"]

    def frame(name: str) -> pd.DataFrame:
        item = artifacts[name]
        path = manifest_path.parent / item["filename"]
        if file_sha256(path) != item["sha256"]:
            raise NdxDynamicShadowDailyError(f"final candidate artifact hash mismatch: {name}")
        return pd.read_csv(path, low_memory=False)

    candidates = frame("candidates")
    roles = frame("role_lock")
    jobs = frame("job_plan")
    decision_values = set(jobs["decision_date"].astype(str))
    if len(decision_values) != 1:
        raise NdxDynamicShadowDailyError("candidate job plan spans decision dates")
    decision = next(iter(decision_values))
    timing = resolve_first_observed_execution_session(sessions, decision)
    if timing is None:
        raise NdxDynamicShadowDailyError("next execution session is not observed complete")
    sealed = _aware_utc(manifest["roles_sealed_at_utc"], "role seal")
    execution_open = _aware_utc(timing["execution_open_timestamp_utc"], "execution open")
    if sealed >= execution_open:
        raise NdxDynamicShadowDailyError("candidate roles were not frozen before realized execution open")
    realized_at = _aware_utc(_system_utc_now(), "realized at")
    execution_close = _aware_utc(timing["execution_close_timestamp_utc"], "execution close")
    if realized_at < execution_close:
        raise NdxDynamicShadowDailyError("execution cannot be realized before its observed close")
    previous = dict(previous_lane_heads or {})
    expected_ids = {f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES}
    if previous and set(previous) != expected_ids:
        raise NdxDynamicShadowDailyError("previous lane heads are not a complete 10-lane matrix")
    output: list[dict[str, Any]] = []
    for role in roles.sort_values("selector_id", kind="stable").itertuples(index=False):
        selector_id = str(role.selector_id)
        prior = previous.get(selector_id)
        prior_hash = None
        sequence = 1
        if prior is not None:
            prior_hash = str(prior.get("payload_sha256") or "")
            unsigned = dict(prior)
            unsigned.pop("payload_sha256", None)
            if canonical_sha256(unsigned) != prior_hash:
                raise NdxDynamicShadowDailyError("previous lane head hash mismatch")
            sequence = int(prior["decision_sequence"]) + 1
        selected: dict[str, Any] | None = None
        portfolio_id = "" if pd.isna(role.portfolio_id) else str(role.portfolio_id)
        if role.status != "REFERENCE_UNAVAILABLE_NOT_REPLACED":
            matches = candidates.loc[
                candidates["universe_track"].astype(str).eq(str(role.universe_track))
                & candidates["portfolio_id"].astype(str).eq(portfolio_id)
            ]
            if len(matches) != 1:
                raise NdxDynamicShadowDailyError("role does not resolve to exactly one frozen candidate")
            chosen = matches.iloc[0]
            selected = {
                "portfolio_id": portfolio_id,
                "holding_count": int(chosen["holding_count"]),
                "targets": _target_payload(chosen),
            }
        elif role.policy_role != "USER_PREFERENCE":
            raise NdxDynamicShadowDailyError("competitive role cannot be unavailable")
        payload = {
            "schema_version": 1,
            "artifact_type": "ndx_dynamic_shadow_realized_monthly_lane_decision",
            "selector_id": selector_id,
            "universe_track": str(role.universe_track),
            "policy_role": str(role.policy_role),
            "decision_sequence": sequence,
            "previous_decision_sha256": prior_hash,
            "timing": {
                **timing,
                "candidate_sealed_at_utc": sealed.isoformat(),
                "execution_realized_at_utc": realized_at.isoformat(),
            },
            "status": str(role.status),
            "selected_candidate": selected,
            "provenance": {
                "candidate_manifest_path": manifest_path.resolve().as_posix(),
                "candidate_manifest_sha256": file_sha256(manifest_path),
                "snapshot_manifest_sha256": manifest["snapshot_manifest_sha256"],
                "snapshot_fingerprint": manifest["snapshot_fingerprint"],
            },
            "selection_training_only": True,
            "fresh_oos_outcome_consumed_at_selection": False,
            "historical_candidate_replay_used": False,
            "independent_lane_only": True,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        payload["payload_sha256"] = canonical_sha256(payload)
        output.append(payload)
    if len(output) != 10 or {item["selector_id"] for item in output} != expected_ids:
        raise NdxDynamicShadowDailyError("realized decisions are not a complete 10-lane matrix")
    return output


def write_immutable_realized_decisions(
    output_root: str | Path, decisions: Iterable[Mapping[str, Any]],
) -> list[Path]:
    items = [dict(value) for value in decisions]
    if len(items) != 10:
        raise NdxDynamicShadowDailyError("realized decision write requires 10 lanes")
    dates = {str(item["timing"]["decision_date"]) for item in items}
    if len(dates) != 1:
        raise NdxDynamicShadowDailyError("realized decision batch spans coordinates")
    output = Path(output_root)
    decision_date = next(iter(dates))
    directory = output / decision_date
    staging = output / f".{decision_date}.pending"
    rendered: list[tuple[Path, str]] = []
    for item in items:
        declared = str(item.get("payload_sha256") or "")
        unsigned = dict(item)
        unsigned.pop("payload_sha256", None)
        if canonical_sha256(unsigned) != declared:
            raise NdxDynamicShadowDailyError("realized decision hash mismatch")
        path = staging / f"{item['selector_id']}.json"
        rendered.append((path, json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n"))
    if directory.exists():
        verify_realized_decision_chain(output)
        existing = sorted(path for path in directory.glob("*.json") if path.name != "batch_manifest.json")
        expected_content = {path.name: content for path, content in rendered}
        if len(existing) != 10 or any(
            path.read_text(encoding="utf-8") != expected_content.get(path.name)
            for path in existing
        ):
            raise NdxDynamicShadowDailyError("immutable realized decision batch collision")
        return existing
    output.mkdir(parents=True, exist_ok=True)
    prior_batches = verify_realized_decision_chain(output)
    if prior_batches and str(prior_batches[-1]["decision_date"]) >= decision_date:
        raise NdxDynamicShadowDailyError("realized decision batches cannot be backfilled")
    staging.mkdir(parents=True, exist_ok=True)
    for path, content in rendered:
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowDailyError(f"immutable realized decision collision: {path}")
    for path, content in rendered:
        if not path.exists():
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temporary, path)
    artifacts = {
        path.name: {"sha256": file_sha256(path), "bytes": path.stat().st_size}
        for path, _ in rendered
    }
    batch = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_realized_decision_batch",
        "status": "COMMITTED_COMPLETE_TEN_LANES",
        "decision_date": decision_date,
        "lane_count": 10,
        "previous_batch_manifest_sha256": (
            prior_batches[-1]["manifest_sha256"] if prior_batches else None
        ),
        "artifacts": artifacts,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    batch["manifest_sha256"] = canonical_sha256(batch)
    batch_path = staging / "batch_manifest.json"
    batch_content = json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if batch_path.exists() and batch_path.read_text(encoding="utf-8") != batch_content:
        raise NdxDynamicShadowDailyError("pending realized decision batch manifest changed")
    if not batch_path.exists():
        temporary = batch_path.with_suffix(".json.tmp")
        temporary.write_text(batch_content, encoding="utf-8", newline="\n")
        os.replace(temporary, batch_path)
    verify_realized_decision_batch(staging)
    os.replace(staging, directory)
    verify_realized_decision_chain(output)
    return sorted(path for path in directory.glob("*.json") if path.name != "batch_manifest.json")


def verify_realized_decision_batch(path: str | Path) -> dict[str, Any]:
    directory = Path(path)
    manifest_path = directory / "batch_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowDailyError("realized decision batch commit manifest is missing/invalid") from exc
    declared = str(manifest.get("manifest_sha256") or "")
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    expected_manifest_keys = {
        "schema_version", "manifest_type", "status", "decision_date", "lane_count",
        "previous_batch_manifest_sha256", "artifacts", "promotion_allowed",
        "live_mutation", "manifest_sha256",
    }
    if (
        set(manifest) != expected_manifest_keys
        or canonical_sha256(unsigned) != declared
        or manifest.get("manifest_type") != "ndx_dynamic_shadow_realized_decision_batch"
        or manifest.get("status") != "COMMITTED_COMPLETE_TEN_LANES"
        or int(manifest.get("lane_count", -1)) != 10
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowDailyError("realized decision batch commit boundary changed")
    artifacts = manifest.get("artifacts") or {}
    files = sorted(path for path in directory.glob("*.json") if path.name != "batch_manifest.json")
    if len(files) != 10 or set(artifacts) != {path.name for path in files}:
        raise NdxDynamicShadowDailyError("realized decision batch is partially visible")
    selector_ids = set()
    for item_path in files:
        item = artifacts[item_path.name]
        if (
            file_sha256(item_path) != item.get("sha256")
            or item_path.stat().st_size != int(item.get("bytes", -1))
        ):
            raise NdxDynamicShadowDailyError("realized decision artifact hash changed")
        payload = json.loads(item_path.read_text(encoding="utf-8"))
        declared_payload = str(payload.get("payload_sha256") or "")
        unsigned_payload = dict(payload)
        unsigned_payload.pop("payload_sha256", None)
        if canonical_sha256(unsigned_payload) != declared_payload:
            raise NdxDynamicShadowDailyError("realized decision payload hash changed")
        selector_ids.add(str(payload.get("selector_id")))
    expected = {f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES}
    if selector_ids != expected:
        raise NdxDynamicShadowDailyError("realized decision batch lane matrix changed")
    return manifest


def verify_realized_decision_chain(path: str | Path) -> list[dict[str, Any]]:
    root = Path(path)
    if not root.exists():
        return []
    directories = sorted(
        value for value in root.iterdir()
        if value.is_dir() and not value.name.startswith(".")
    )
    manifests = []
    previous_batch_hash = None
    lane_heads: dict[str, str] = {}
    lane_sequences: dict[str, int] = {}
    for directory in directories:
        manifest = verify_realized_decision_batch(directory)
        if (
            str(manifest["decision_date"]) != directory.name
            or manifest.get("previous_batch_manifest_sha256") != previous_batch_hash
        ):
            raise NdxDynamicShadowDailyError("realized decision batch chain changed")
        files = sorted(
            value for value in directory.glob("*.json")
            if value.name != "batch_manifest.json"
        )
        for item_path in files:
            payload = json.loads(item_path.read_text(encoding="utf-8"))
            selector_id = str(payload["selector_id"])
            expected_sequence = lane_sequences.get(selector_id, 0) + 1
            if (
                int(payload.get("decision_sequence", -1)) != expected_sequence
                or payload.get("previous_decision_sha256") != lane_heads.get(selector_id)
                or str((payload.get("timing") or {}).get("decision_date")) != directory.name
            ):
                raise NdxDynamicShadowDailyError("realized per-lane decision chain changed")
            lane_sequences[selector_id] = expected_sequence
            lane_heads[selector_id] = str(payload["payload_sha256"])
        manifests.append(manifest)
        previous_batch_hash = str(manifest["manifest_sha256"])
    return manifests


def replay_lane_path(
    decisions: Iterable[Mapping[str, Any]], *, sessions: pd.DataFrame,
    valuation_closes: pd.DataFrame, execution_opens: pd.DataFrame,
    valuation_end_date: Any,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    items = [dict(value) for value in decisions]
    if not items or len({item["selector_id"] for item in items}) != 1:
        raise NdxDynamicShadowDailyError("lane replay requires one nonempty selector chain")
    prior_hash = None
    for sequence, item in enumerate(items, start=1):
        declared = str(item.get("payload_sha256") or "")
        unsigned = dict(item)
        unsigned.pop("payload_sha256", None)
        if canonical_sha256(unsigned) != declared or item.get("previous_decision_sha256") != prior_hash:
            raise NdxDynamicShadowDailyError("lane decision hash chain changed")
        if int(item["decision_sequence"]) != sequence:
            raise NdxDynamicShadowDailyError("lane decision sequence changed")
        prior_hash = declared
    frame = normalize_observed_sessions(sessions)
    end = pd.Timestamp(valuation_end_date).normalize()
    completed_dates = frame.loc[frame["session_date"].le(end), "session_date"]
    if completed_dates.empty or completed_dates.iloc[-1] != end:
        raise NdxDynamicShadowDailyError("valuation end is not an observed completed session")
    first_execution = pd.Timestamp(items[0]["timing"]["execution_date"]).normalize()
    dates = completed_dates.loc[completed_dates.ge(first_execution)]
    schedules = [
        {
            "decision_date": item["timing"]["decision_date"],
            "execution_date": item["timing"]["execution_date"],
            "targets": item["selected_candidate"]["targets"],
        }
        for item in items if item.get("selected_candidate") is not None
    ]
    if not schedules:
        path = pd.DataFrame({
            "date": dates.dt.date.astype(str),
            "cash_usd": 25000.0,
            "holdings_value_usd": 0.0,
            "total_value_usd": 25000.0,
            "holding_count": 0,
            "active_security_ids": "[]",
            "active_tickers": "[]",
            "holdings": "{}",
        })
        return ({
            "selector_id": items[0]["selector_id"],
            "status": "REFERENCE_UNAVAILABLE_CASH_ONLY_NOT_REPLACED",
            "rebalance_count": 0,
            "path_trading_session_count": len(path),
            "terminal_value_usd": 25000.0,
            "promotion_allowed": False,
            "live_mutation": False,
        }, pd.DataFrame(), pd.DataFrame(), path)
    closes = valuation_closes.copy()
    opens = execution_opens.copy()
    closes.index = pd.to_datetime(closes.index).normalize()
    opens.index = pd.to_datetime(opens.index).normalize()
    summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
        closes,
        schedules,
        execution_prices=opens,
        require_separate_execution_prices=True,
        require_next_session_execution=True,
        require_issuer_trace=True,
        initial_cash_usd=25000.0,
        minimum_cash_buffer_usd=100.0,
        transaction_cost_bps=10.0,
        valuation_end_date=end,
    )
    first_selected = pd.Timestamp(schedules[0]["execution_date"]).normalize()
    leading = dates.loc[dates.lt(first_selected)]
    if len(leading):
        cash = pd.DataFrame({
            "date": leading.dt.date.astype(str), "cash_usd": 25000.0,
            "holdings_value_usd": 0.0, "total_value_usd": 25000.0,
            "holding_count": 0, "active_security_ids": "[]",
            "active_tickers": "[]", "holdings": "{}",
        })
        path = pd.concat([cash, path], ignore_index=True)
    summary.update({
        "selector_id": items[0]["selector_id"],
        "evidence_role": "FRESH_DYNAMIC_SHADOW_RESEARCH_ONLY",
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    })
    return summary, rebalances, trades, path


def replay_original8_control_path(
    decision_chain: Iterable[Mapping[str, Any]], *,
    frozen_securities: Iterable[Mapping[str, Any]], sessions: pd.DataFrame,
    valuation_closes: pd.DataFrame, execution_opens: pd.DataFrame,
    valuation_end_date: Any,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Replay the frozen incumbent as a separate same-session whole-lot control."""
    decisions = [dict(value) for value in decision_chain]
    securities = [dict(value) for value in frozen_securities]
    if not decisions:
        raise NdxDynamicShadowDailyError("original-8 control requires a decision chain")
    if len(securities) != 8:
        raise NdxDynamicShadowDailyError("original-8 control must contain exactly eight securities")
    tickers = [str(value.get("ticker") or "").strip().upper() for value in securities]
    security_ids = [str(value.get("security_id") or "").strip() for value in securities]
    issuer_ids = [str(value.get("issuer_id") or "").strip() for value in securities]
    weights = [float(value.get("target_weight")) for value in securities]
    if (
        any(not value for value in tickers + security_ids + issuer_ids)
        or len(set(tickers)) != 8 or len(set(security_ids)) != 8 or len(set(issuer_ids)) != 8
        or any(not np.isfinite(value) or value <= 0 for value in weights)
        or not np.isclose(sum(weights), 1.0, atol=1e-10)
    ):
        raise NdxDynamicShadowDailyError("original-8 identity/weight definition is invalid")
    targets = {
        security_id: {
            "ticker": ticker,
            "issuer_id": issuer_id,
            "target_weight": weight,
        }
        for ticker, security_id, issuer_id, weight in zip(
            tickers, security_ids, issuer_ids, weights
        )
    }
    schedules = []
    previous_execution = None
    for item in decisions:
        timing = item.get("timing") or {}
        decision_date = pd.Timestamp(timing.get("decision_date")).normalize()
        execution_date = pd.Timestamp(timing.get("execution_date")).normalize()
        if previous_execution is not None and execution_date <= previous_execution:
            raise NdxDynamicShadowDailyError("original-8 control decision chain is not increasing")
        schedules.append({
            "decision_date": decision_date,
            "execution_date": execution_date,
            "targets": targets,
        })
        previous_execution = execution_date
    closes = valuation_closes.copy()
    opens = execution_opens.copy()
    closes.index = pd.to_datetime(closes.index).normalize()
    opens.index = pd.to_datetime(opens.index).normalize()
    summary, rebalances, trades, path = simulate_dynamic_security_id_whole_lot_path(
        closes,
        schedules,
        execution_prices=opens,
        require_separate_execution_prices=True,
        require_next_session_execution=True,
        require_issuer_trace=True,
        initial_cash_usd=25000.0,
        minimum_cash_buffer_usd=100.0,
        transaction_cost_bps=10.0,
        valuation_end_date=pd.Timestamp(valuation_end_date).normalize(),
    )
    summary.update({
        "control_id": "ndx_original_8_incumbent_v0",
        "benchmark_control_not_selector_lane": True,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
        "live_mutation": False,
    })
    return summary, rebalances, trades, path


TARGET_TRACE_RECORD_KEYS = {
    "schema_version", "artifact_type", "sequence", "session_date",
    "evidence_role",
    "status", "source_date", "source_close", "normalized_value_usd",
    "lag_calendar_days", "lag_observed_session_count", "observed_at_utc",
    "source_csv_snapshot_path", "source_manifest_snapshot_path",
    "source_csv_sha256", "source_manifest_sha256", "source_fetched_at_utc",
    "publication_time_known", "previous_record_sha256", "promotion_allowed",
    "live_mutation", "record_sha256",
}


def load_target_012922_trace_ledger(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    previous_hash = None
    previous_date = None
    previous_observed_at = None
    previous_available_source_date = None
    base_nav = None
    for sequence, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise NdxDynamicShadowDailyError("blank 012922 trace ledger row")
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != TARGET_TRACE_RECORD_KEYS:
            raise NdxDynamicShadowDailyError("012922 trace ledger schema changed")
        unsigned = dict(value)
        declared = str(unsigned.pop("record_sha256") or "")
        session_date = pd.Timestamp(value["session_date"]).normalize()
        status = str(value.get("status") or "")
        observed_at = _aware_utc(value.get("observed_at_utc"), "012922 observed at")
        fetched_at = _aware_utc(value.get("source_fetched_at_utc"), "012922 fetched at")
        common_invalid = (
            int(value.get("schema_version", -1)) != 1
            or value.get("artifact_type") != "ndx_dynamic_shadow_target_012922_asof_record"
            or value.get("evidence_role")
            != "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME"
            or int(value.get("sequence", -1)) != sequence
            or value.get("previous_record_sha256") != previous_hash
            or canonical_sha256(unsigned) != declared
            or previous_date is not None and session_date <= previous_date
            or previous_observed_at is not None and observed_at < previous_observed_at
            or fetched_at > observed_at
            or value.get("publication_time_known") is not False
            or value.get("promotion_allowed") is not False
            or value.get("live_mutation") is not False
        )
        if common_invalid:
            raise NdxDynamicShadowDailyError("012922 trace ledger hash/as-of boundary changed")
        if status == "AVAILABLE_STALE_ASOF":
            csv_path = Path(str(value.get("source_csv_snapshot_path") or "")).resolve()
            manifest_path = Path(str(value.get("source_manifest_snapshot_path") or "")).resolve()
            expected_source_root = (source.parent / "target_012922_sources").resolve()
            try:
                source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                source_frame = pd.read_csv(csv_path)
            except (OSError, json.JSONDecodeError) as exc:
                raise NdxDynamicShadowDailyError("012922 immutable source snapshot is missing") from exc
            source_date = pd.Timestamp(value["source_date"]).normalize()
            source_close = float(value["source_close"])
            normalized = float(value["normalized_value_usd"])
            if not {"Date", "Close"}.issubset(source_frame.columns):
                raise NdxDynamicShadowDailyError("012922 immutable source schema changed")
            source_frame = source_frame[["Date", "Close"]].copy()
            source_frame["Date"] = pd.to_datetime(source_frame["Date"], errors="raise").dt.normalize()
            source_frame["Close"] = pd.to_numeric(source_frame["Close"], errors="raise")
            asof_rows = source_frame.loc[source_frame["Date"].le(session_date)]
            selected_source = asof_rows.iloc[-1] if not asof_rows.empty else None
            if base_nav is None:
                base_nav = source_close
            if (
                source_date > session_date
                or selected_source is None
                or pd.Timestamp(selected_source["Date"]).normalize() != source_date
                or not np.isclose(float(selected_source["Close"]), source_close, atol=1e-12)
                or csv_path.parent != expected_source_root
                or manifest_path.parent != expected_source_root
                or previous_available_source_date is not None
                and source_date < previous_available_source_date
                or len(str(value.get("source_csv_sha256") or "")) != 64
                or len(str(value.get("source_manifest_sha256") or "")) != 64
                or not csv_path.is_file()
                or file_sha256(csv_path) != value.get("source_csv_sha256")
                or file_sha256(manifest_path) != value.get("source_manifest_sha256")
                or source_manifest.get("content_sha256") != value.get("source_csv_sha256")
                or source_manifest.get("dataset_key") != "012922"
                or int(source_manifest.get("row_count", -1)) != len(source_frame)
                or _aware_utc(source_manifest.get("fetched_at"), "012922 snapshot fetched at") != fetched_at
                or not np.isfinite(source_close) or source_close <= 0
                or not np.isclose(normalized, 25000.0 * source_close / base_nav, atol=1e-8)
                or int(value.get("lag_calendar_days", -1)) != (session_date - source_date).days
                or int(value.get("lag_observed_session_count", -1)) < 0
            ):
                raise NdxDynamicShadowDailyError("012922 available trace value is invalid")
        elif status == "TARGET_ASOF_UNAVAILABLE_PENDING":
            if any(value.get(key) is not None for key in (
                "source_date", "source_close", "normalized_value_usd",
                "lag_calendar_days", "lag_observed_session_count",
                "source_csv_snapshot_path", "source_manifest_snapshot_path",
                "source_csv_sha256", "source_manifest_sha256",
            )):
                raise NdxDynamicShadowDailyError("012922 pending trace must have null value fields")
        else:
            raise NdxDynamicShadowDailyError("012922 trace status changed")
        records.append(value)
        previous_hash = declared
        previous_date = session_date
        previous_observed_at = observed_at
        if status == "AVAILABLE_STALE_ASOF":
            previous_available_source_date = source_date
    return records


def append_target_012922_trace(
    ledger_path: str | Path, *, path_dates: Iterable[Any], target_nav: pd.DataFrame,
    observed_at_utc: Any, source_csv_snapshot_path: str | Path | None,
    source_manifest_snapshot_path: str | Path | None,
    source_csv_sha256: str | None, source_manifest_sha256: str | None,
    source_fetched_at_utc: Any,
) -> list[dict[str, Any]]:
    """Append first-observed no-future target values; never revise old sessions."""
    destination = Path(ledger_path)
    existing = load_target_012922_trace_ledger(destination)
    if not target_nav.empty and not {"Date", "Close"}.issubset(target_nav.columns):
        raise NdxDynamicShadowDailyError("012922 target source schema is incomplete")
    nav = (
        target_nav[["Date", "Close"]].copy()
        if not target_nav.empty else pd.DataFrame(columns=["Date", "Close"])
    )
    nav["Date"] = pd.to_datetime(nav["Date"], errors="raise").dt.normalize()
    nav["Close"] = pd.to_numeric(nav["Close"], errors="raise")
    if (
        nav["Date"].duplicated().any() or not nav["Date"].is_monotonic_increasing
        or (~np.isfinite(nav["Close"]) | nav["Close"].le(0)).any()
    ):
        raise NdxDynamicShadowDailyError("012922 target source is invalid")
    dates = pd.DatetimeIndex(pd.to_datetime(list(path_dates), errors="raise")).normalize()
    if dates.empty or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise NdxDynamicShadowDailyError("012922 trace path dates must be unique and increasing")
    existing_dates = [pd.Timestamp(value["session_date"]).normalize() for value in existing]
    if existing_dates and existing_dates != dates[:len(existing_dates)].tolist():
        raise NdxDynamicShadowDailyError("012922 trace prefix calendar changed")
    observed = _aware_utc(observed_at_utc, "012922 observation time")
    fetched = _aware_utc(source_fetched_at_utc, "012922 source fetch time")
    if fetched > observed:
        raise NdxDynamicShadowDailyError("012922 source fetch time is after observation time")
    csv_snapshot = Path(source_csv_snapshot_path).resolve() if source_csv_snapshot_path else None
    manifest_snapshot = (
        Path(source_manifest_snapshot_path).resolve() if source_manifest_snapshot_path else None
    )
    source_ready = bool(
        csv_snapshot is not None and manifest_snapshot is not None
        and csv_snapshot.is_file() and manifest_snapshot.is_file()
        and len(str(source_csv_sha256 or "")) == 64
        and len(str(source_manifest_sha256 or "")) == 64
        and file_sha256(csv_snapshot) == source_csv_sha256
        and file_sha256(manifest_snapshot) == source_manifest_sha256
    )
    if not nav.empty and not source_ready:
        raise NdxDynamicShadowDailyError("012922 immutable source snapshot is not hash-bound")
    if source_ready:
        try:
            source_manifest = json.loads(manifest_snapshot.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NdxDynamicShadowDailyError("012922 immutable source manifest is invalid") from exc
        if (
            source_manifest.get("content_sha256") != source_csv_sha256
            or _aware_utc(source_manifest.get("fetched_at"), "012922 snapshot fetched at") != fetched
        ):
            raise NdxDynamicShadowDailyError("012922 immutable source manifest provenance changed")
    additions = []
    previous_hash = existing[-1]["record_sha256"] if existing else None
    base_nav = next(
        (float(value["source_close"]) for value in existing if value["status"] == "AVAILABLE_STALE_ASOF"),
        None,
    )
    missing_dates = dates[len(existing):]
    for offset, session_date in enumerate(missing_dates, start=1):
        sequence = len(existing) + offset
        available = nav.loc[nav["Date"].le(session_date)]
        force_pending_gap = len(missing_dates) > 1 and offset < len(missing_dates)
        if available.empty or force_pending_gap or not source_ready:
            status = "TARGET_ASOF_UNAVAILABLE_PENDING"
            source_date = source_close = normalized = lag_days = lag_sessions = None
        else:
            status = "AVAILABLE_STALE_ASOF"
            source_row = available.iloc[-1]
            source_date_value = pd.Timestamp(source_row["Date"]).normalize()
            source_close_value = float(source_row["Close"])
            if base_nav is None:
                base_nav = source_close_value
            source_date = source_date_value.date().isoformat()
            source_close = source_close_value
            normalized = 25000.0 * source_close_value / base_nav
            lag_days = int((session_date - source_date_value).days)
            lag_sessions = int(((dates > source_date_value) & (dates <= session_date)).sum())
        record = {
            "schema_version": 1,
            "artifact_type": "ndx_dynamic_shadow_target_012922_asof_record",
            "evidence_role": "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME",
            "sequence": sequence,
            "session_date": session_date.date().isoformat(),
            "status": status,
            "source_date": source_date,
            "source_close": source_close,
            "normalized_value_usd": normalized,
            "lag_calendar_days": lag_days,
            "lag_observed_session_count": lag_sessions,
            "observed_at_utc": observed.isoformat(),
            "source_csv_snapshot_path": csv_snapshot.as_posix() if status == "AVAILABLE_STALE_ASOF" else None,
            "source_manifest_snapshot_path": manifest_snapshot.as_posix() if status == "AVAILABLE_STALE_ASOF" else None,
            "source_csv_sha256": str(source_csv_sha256) if status == "AVAILABLE_STALE_ASOF" else None,
            "source_manifest_sha256": str(source_manifest_sha256) if status == "AVAILABLE_STALE_ASOF" else None,
            "source_fetched_at_utc": fetched.isoformat(),
            "publication_time_known": False,
            "previous_record_sha256": previous_hash,
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
    result = load_target_012922_trace_ledger(destination)
    if [value["session_date"] for value in result] != dates.date.astype(str).tolist():
        raise NdxDynamicShadowDailyError("012922 trace calendar is incomplete")
    return result


LANE_PATH_RECORD_KEYS = {
    "schema_version", "artifact_type", "selector_id", "date",
    "previous_record_sha256", "path_state", "rebalance_events", "trade_events",
    "price_evidence_sha256", "independent_lane_only",
    "historical_candidate_replay_used", "promotion_allowed", "live_mutation",
    "record_sha256",
}


def _load_lane_ledger(path: Path, selector_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    prior = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or set(value) != LANE_PATH_RECORD_KEYS:
            raise NdxDynamicShadowDailyError("lane path ledger schema changed")
        declared = str(value.get("record_sha256") or "")
        unsigned = dict(value)
        unsigned.pop("record_sha256", None)
        if (
            canonical_sha256(unsigned) != declared
            or value.get("previous_record_sha256") != prior
            or value.get("selector_id") != selector_id
            or value.get("artifact_type") != "ndx_dynamic_shadow_daily_lane_path_record"
            or value.get("independent_lane_only") is not True
            or value.get("historical_candidate_replay_used") is not False
            or value.get("promotion_allowed") is not False
            or value.get("live_mutation") is not False
            or len(str(value.get("price_evidence_sha256") or "")) != 64
        ):
            raise NdxDynamicShadowDailyError("lane path ledger hash chain changed")
        records.append(value)
        prior = declared
    dates = [str(record["date"]) for record in records]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise NdxDynamicShadowDailyError("lane path ledger dates changed")
    return records


def load_lane_path_ledger(path: str | Path, selector_id: str) -> list[dict[str, Any]]:
    return _load_lane_ledger(Path(path), selector_id)


def append_lane_path(
    ledger_path: str | Path, *, selector_id: str, path: pd.DataFrame,
    rebalances: pd.DataFrame, trades: pd.DataFrame,
    price_evidence_sha256_by_date: Mapping[str, str],
) -> list[dict[str, Any]]:
    destination = Path(ledger_path)
    existing = _load_lane_ledger(destination, selector_id)
    economic: dict[str, dict[str, Any]] = {}
    for row in path.itertuples(index=False):
        date = str(row.date)
        economic[date] = {
            "path_state": {
                "cash_usd": float(row.cash_usd),
                "holdings_value_usd": float(row.holdings_value_usd),
                "total_value_usd": float(row.total_value_usd),
                "holding_count": int(row.holding_count),
                "active_security_ids": str(row.active_security_ids),
                "active_tickers": str(row.active_tickers),
                "holdings": str(row.holdings),
            },
            "rebalance_events": (
                _jsonable(rebalances.loc[
                    rebalances["execution_date"].astype(str).eq(date)
                ].to_dict("records"))
                if not rebalances.empty else []
            ),
            "trade_events": (
                _jsonable(trades.loc[
                    trades["execution_date"].astype(str).eq(date)
                ].to_dict("records"))
                if not trades.empty else []
            ),
        }
    for record in existing:
        date = str(record["date"])
        if date not in economic or any(record.get(key) != economic[date][key] for key in economic[date]):
            raise NdxDynamicShadowDailyError("recomputed lane prefix differs from append-only ledger")
    additions: list[dict[str, Any]] = []
    prior = existing[-1]["record_sha256"] if existing else None
    existing_dates = {str(record["date"]) for record in existing}
    for date in sorted(economic):
        if date in existing_dates:
            continue
        evidence_hash = str(price_evidence_sha256_by_date.get(date) or "")
        if len(evidence_hash) != 64:
            raise NdxDynamicShadowDailyError(f"price evidence hash missing for {date}")
        record = {
            "schema_version": 1,
            "artifact_type": "ndx_dynamic_shadow_daily_lane_path_record",
            "selector_id": selector_id,
            "date": date,
            "previous_record_sha256": prior,
            **economic[date],
            "price_evidence_sha256": evidence_hash,
            "independent_lane_only": True,
            "historical_candidate_replay_used": False,
            "promotion_allowed": False,
            "live_mutation": False,
        }
        record["record_sha256"] = canonical_sha256(record)
        additions.append(record)
        prior = record["record_sha256"]
    if additions:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8", newline="\n") as handle:
            for record in additions:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return existing + additions


ALIGNMENT_MANIFEST_KEYS = {
    "schema_version", "manifest_type", "status", "valuation_end_date",
    "calendar_start_date", "calendar_end_date", "calendar_session_count",
    "calendar_dates_sha256", "selector_lane_count", "benchmark_control_count",
    "target_available_rows", "target_pending_rows",
    "target_first_observed_trace_complete",
    "target_resolved_outcome_benchmark_ready", "target_trace_evidence_role",
    "selector_lane_prefixes", "original_8_control_prefix", "target_012922_prefix",
    "observed_calendar_source", "calendar_artifact", "three_way_calendar_exact",
    "promotion_allowed", "live_mutation", "manifest_sha256",
}


def _prefix_descriptor(path: Path, records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise NdxDynamicShadowDailyError("calendar alignment cannot bind an empty ledger")
    return {
        "path": path.resolve().as_posix(),
        "prefix_rows": len(records),
        "terminal_record_sha256": records[-1]["record_sha256"],
    }


def write_three_way_calendar_manifest(
    output_dir: str | Path, *, selector_lane_ledgers: Mapping[str, str | Path],
    original_8_ledger: str | Path, target_012922_ledger: str | Path,
    observed_sessions: pd.DataFrame, observed_calendar_manifest_path: str | Path,
) -> dict[str, Any]:
    expected_selectors = {
        f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES
    }
    if set(selector_lane_ledgers) != expected_selectors:
        raise NdxDynamicShadowDailyError("calendar alignment requires the exact 10 selector lanes")
    lane_records = {
        selector_id: load_lane_path_ledger(path, selector_id)
        for selector_id, path in selector_lane_ledgers.items()
    }
    original_path = Path(original_8_ledger)
    original_records = load_lane_path_ledger(original_path, "ndx_original_8_incumbent_v0")
    target_path = Path(target_012922_ledger)
    target_records = load_target_012922_trace_ledger(target_path)
    calendars = [
        [str(value["date"]) for value in records]
        for records in lane_records.values()
    ]
    calendars.append([str(value["date"]) for value in original_records])
    calendars.append([str(value["session_date"]) for value in target_records])
    if not calendars or any(values != calendars[0] for values in calendars[1:]):
        raise NdxDynamicShadowDailyError("selector/original8/012922 calendars are not identical")
    dates = calendars[0]
    if not dates:
        raise NdxDynamicShadowDailyError("three-way aligned calendar is empty")
    sessions = normalize_observed_sessions(observed_sessions)
    calendar = sessions.loc[
        sessions["session_date"].dt.date.astype(str).isin(dates),
        ["session_date", "open_timestamp_utc", "close_timestamp_utc"],
    ].copy()
    calendar["session_date"] = calendar["session_date"].dt.date.astype(str)
    calendar["open_timestamp_utc"] = calendar["open_timestamp_utc"].map(pd.Timestamp.isoformat)
    calendar["close_timestamp_utc"] = calendar["close_timestamp_utc"].map(pd.Timestamp.isoformat)
    if calendar["session_date"].tolist() != dates:
        raise NdxDynamicShadowDailyError("aligned paths are not the canonical observed sessions")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    calendar_path = output / "calendar_sessions.csv"
    calendar_content = calendar.to_csv(index=False, lineterminator="\n")
    if calendar_path.exists() and calendar_path.read_text(encoding="utf-8") != calendar_content:
        raise NdxDynamicShadowDailyError("immutable alignment calendar collision")
    if not calendar_path.exists():
        temporary = calendar_path.with_suffix(".csv.tmp")
        temporary.write_text(calendar_content, encoding="utf-8", newline="\n")
        os.replace(temporary, calendar_path)
    calendar_source = Path(observed_calendar_manifest_path)
    if not calendar_source.is_file():
        raise NdxDynamicShadowDailyError("observed calendar source manifest is missing")
    calendar_source_snapshot = output / "observed_calendar_manifest_snapshot.json"
    source_bytes = calendar_source.read_bytes()
    if calendar_source_snapshot.exists() and calendar_source_snapshot.read_bytes() != source_bytes:
        raise NdxDynamicShadowDailyError("immutable observed calendar source snapshot collision")
    if not calendar_source_snapshot.exists():
        temporary = calendar_source_snapshot.with_suffix(".json.tmp")
        temporary.write_bytes(source_bytes)
        os.replace(temporary, calendar_source_snapshot)
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_three_way_calendar_alignment",
        "status": "EXACT_SELECTOR_ORIGINAL8_TARGET_ALIGNMENT_RESEARCH_ONLY",
        "valuation_end_date": dates[-1],
        "calendar_start_date": dates[0],
        "calendar_end_date": dates[-1],
        "calendar_session_count": len(dates),
        "calendar_dates_sha256": canonical_sha256(dates),
        "selector_lane_count": 10,
        "benchmark_control_count": 2,
        "target_available_rows": sum(
            value["status"] == "AVAILABLE_STALE_ASOF" for value in target_records
        ),
        "target_pending_rows": sum(
            value["status"] == "TARGET_ASOF_UNAVAILABLE_PENDING" for value in target_records
        ),
        "target_first_observed_trace_complete": len(target_records) == len(dates),
        "target_resolved_outcome_benchmark_ready": False,
        "target_trace_evidence_role": (
            "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME"
        ),
        "selector_lane_prefixes": {
            selector_id: _prefix_descriptor(Path(selector_lane_ledgers[selector_id]), lane_records[selector_id])
            for selector_id in sorted(expected_selectors)
        },
        "original_8_control_prefix": _prefix_descriptor(original_path, original_records),
        "target_012922_prefix": _prefix_descriptor(target_path, target_records),
        "observed_calendar_source": {
            "canonical_path": calendar_source.resolve().as_posix(),
            "sha256_at_alignment": file_sha256(calendar_source),
            "snapshot_filename": calendar_source_snapshot.name,
            "snapshot_sha256": file_sha256(calendar_source_snapshot),
        },
        "calendar_artifact": {
            "filename": calendar_path.name,
            "rows": len(calendar),
            "sha256": file_sha256(calendar_path),
        },
        "three_way_calendar_exact": True,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_path = output / "manifest.json"
    content = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists() and manifest_path.read_text(encoding="utf-8") != content:
        raise NdxDynamicShadowDailyError("immutable three-way alignment manifest collision")
    if not manifest_path.exists():
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, manifest_path)
    verify_three_way_calendar_manifest(manifest_path)
    return manifest


def verify_three_way_calendar_manifest(
    path: str | Path, *, require_current_calendar_manifest_hash: bool = False,
) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowDailyError("three-way alignment manifest is missing/invalid") from exc
    unsigned = dict(manifest)
    declared = str(unsigned.pop("manifest_sha256", ""))
    if (
        set(manifest) != ALIGNMENT_MANIFEST_KEYS
        or canonical_sha256(unsigned) != declared
        or manifest.get("manifest_type") != "ndx_dynamic_shadow_three_way_calendar_alignment"
        or manifest.get("status") != "EXACT_SELECTOR_ORIGINAL8_TARGET_ALIGNMENT_RESEARCH_ONLY"
        or int(manifest.get("selector_lane_count", -1)) != 10
        or int(manifest.get("benchmark_control_count", -1)) != 2
        or int(manifest.get("target_available_rows", -1))
        + int(manifest.get("target_pending_rows", -1))
        != int(manifest.get("calendar_session_count", -1))
        or manifest.get("target_first_observed_trace_complete") is not True
        or manifest.get("target_resolved_outcome_benchmark_ready") is not False
        or manifest.get("target_trace_evidence_role")
        != "FIRST_OBSERVED_ASOF_RUNTIME_DIAGNOSTIC_NOT_RESOLVED_OUTCOME"
        or manifest.get("three_way_calendar_exact") is not True
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowDailyError("three-way alignment manifest boundary changed")
    artifact = manifest.get("calendar_artifact") or {}
    calendar_path = manifest_path.parent / str(artifact.get("filename") or "")
    if (
        calendar_path.parent != manifest_path.parent
        or not calendar_path.is_file()
        or file_sha256(calendar_path) != artifact.get("sha256")
    ):
        raise NdxDynamicShadowDailyError("three-way alignment calendar artifact changed")
    calendar = pd.read_csv(calendar_path)
    dates = calendar["session_date"].astype(str).tolist()
    if (
        len(calendar) != int(artifact.get("rows", -1))
        or len(dates) != int(manifest.get("calendar_session_count", -1))
        or dates != sorted(dates) or len(dates) != len(set(dates))
        or canonical_sha256(dates) != manifest.get("calendar_dates_sha256")
        or dates[0] != manifest.get("calendar_start_date")
        or dates[-1] != manifest.get("calendar_end_date")
        or dates[-1] != manifest.get("valuation_end_date")
    ):
        raise NdxDynamicShadowDailyError("three-way alignment calendar metadata changed")
    expected_selectors = {
        f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES
    }
    descriptors = manifest.get("selector_lane_prefixes") or {}
    if set(descriptors) != expected_selectors:
        raise NdxDynamicShadowDailyError("three-way selector prefix registry changed")

    alignment_root = manifest_path.parent.parent
    daily_root = alignment_root.parent
    if (
        alignment_root.name != "three_way_calendar_alignment"
        or manifest_path.parent.name != str(manifest.get("valuation_end_date"))
    ):
        raise NdxDynamicShadowDailyError("three-way alignment path is not canonical")
    expected_lane_root = (daily_root / "lane_paths").resolve()
    expected_control_root = (daily_root / "benchmark_controls").resolve()

    def verify_prefix(descriptor: Mapping[str, Any], selector_id: str, *, target: bool = False) -> list[str]:
        ledger_path = Path(str(descriptor.get("path") or "")).resolve()
        expected_path = (
            expected_control_root / (
                "target_012922_asof.jsonl" if target else "original_8_incumbent_v0.jsonl"
            )
            if target or selector_id == "ndx_original_8_incumbent_v0"
            else expected_lane_root / f"{selector_id}.jsonl"
        )
        if ledger_path != expected_path:
            raise NdxDynamicShadowDailyError("three-way ledger prefix path is not canonical")
        records = (
            load_target_012922_trace_ledger(ledger_path)
            if target else load_lane_path_ledger(ledger_path, selector_id)
        )
        count = int(descriptor.get("prefix_rows", -1))
        if count <= 0 or len(records) < count:
            raise NdxDynamicShadowDailyError("three-way ledger prefix is incomplete")
        prefix = records[:count]
        if prefix[-1]["record_sha256"] != descriptor.get("terminal_record_sha256"):
            raise NdxDynamicShadowDailyError("three-way ledger prefix terminal changed")
        return [str(value["session_date"] if target else value["date"]) for value in prefix]

    for selector_id, descriptor in descriptors.items():
        if verify_prefix(descriptor, selector_id) != dates:
            raise NdxDynamicShadowDailyError("selector lane calendar differs from alignment")
    if verify_prefix(
        manifest.get("original_8_control_prefix") or {}, "ndx_original_8_incumbent_v0"
    ) != dates:
        raise NdxDynamicShadowDailyError("original-8 calendar differs from alignment")
    if verify_prefix(
        manifest.get("target_012922_prefix") or {}, "target_012922_dynamic_external_target",
        target=True,
    ) != dates:
        raise NdxDynamicShadowDailyError("012922 calendar differs from alignment")
    source = manifest.get("observed_calendar_source") or {}
    if set(source) != {
        "canonical_path", "sha256_at_alignment", "snapshot_filename", "snapshot_sha256"
    }:
        raise NdxDynamicShadowDailyError("observed calendar alignment source schema changed")
    repository_root = daily_root.parents[3]
    canonical_source = (
        repository_root
        / "data/cache/research/ndx_observed_us_session_calendar_v1/manifest.json"
    ).resolve()
    source_snapshot = manifest_path.parent / str(source.get("snapshot_filename") or "")
    if (
        Path(str(source.get("canonical_path") or "")).resolve() != canonical_source
        or source_snapshot.parent != manifest_path.parent
        or not source_snapshot.is_file()
        or file_sha256(source_snapshot) != source.get("snapshot_sha256")
        or source.get("snapshot_sha256") != source.get("sha256_at_alignment")
        or require_current_calendar_manifest_hash
        and file_sha256(canonical_source) != source.get("sha256_at_alignment")
    ):
        raise NdxDynamicShadowDailyError("observed calendar alignment source binding changed")
    current_source = json.loads(canonical_source.read_text(encoding="utf-8"))
    projection = (current_source.get("artifacts") or {}).get("session_projection") or {}
    projection_path = Path(str(projection.get("path") or "")).resolve()
    if (
        projection_path != canonical_source.parent / "sessions.csv"
        or not projection_path.is_file()
        or file_sha256(projection_path) != projection.get("sha256")
    ):
        raise NdxDynamicShadowDailyError("current observed calendar projection binding changed")
    current = normalize_observed_sessions(pd.read_csv(projection_path, low_memory=False))
    current = current.loc[
        current["session_date"].dt.date.astype(str).isin(dates),
        ["session_date", "open_timestamp_utc", "close_timestamp_utc"],
    ].copy()
    current["session_date"] = current["session_date"].dt.date.astype(str)
    current["open_timestamp_utc"] = current["open_timestamp_utc"].map(pd.Timestamp.isoformat)
    current["close_timestamp_utc"] = current["close_timestamp_utc"].map(pd.Timestamp.isoformat)
    if current.reset_index(drop=True).to_dict("records") != calendar.to_dict("records"):
        raise NdxDynamicShadowDailyError("frozen alignment calendar differs from canonical observed prefix")
    return manifest


def build_daily_readiness(
    contract_path: str | Path, *, calendar_manifest_path: str | Path,
    repository_root: str | Path, as_of_utc: Any,
) -> dict[str, Any]:
    path = Path(contract_path).resolve()
    contract = load_daily_contract(path)
    root = Path(repository_root).resolve()
    if path != (root / "config/ndx_dynamic_shadow_daily_v1.yaml").resolve():
        raise NdxDynamicShadowDailyError("daily readiness contract path is not canonical")
    sources = contract["source_contract"]
    required_files = {
        name: (root / value).resolve()
        for name, value in sources.items()
        if name.endswith("_script") or name.endswith("_contract")
        or name.endswith("_manifest")
    }
    checks = {
        name: {"path": source.as_posix(), "present": source.is_file(), "sha256": file_sha256(source) if source.is_file() else None}
        for name, source in required_files.items()
    }
    blockers = []
    if not all(value["present"] for value in checks.values()):
        blockers.append("REQUIRED_RESEARCH_SOURCE_MISSING")
    expected_calendar = (root / str(sources["observed_calendar_manifest"])).resolve()
    supplied_calendar = Path(calendar_manifest_path).resolve()
    if supplied_calendar != expected_calendar:
        raise NdxDynamicShadowDailyError("daily readiness calendar path is not canonical")
    from backtest.ndx_dynamic_shadow_activation_readiness import (
        verify_observed_session_calendar_manifest,
    )
    calendar_audit = verify_observed_session_calendar_manifest(supplied_calendar, root)
    if not calendar_audit.get("verified"):
        blockers.append("OBSERVED_SESSION_CALENDAR_NOT_VERIFIED")
    original8_path = (root / str(sources["frozen_original_8_manifest"])).resolve()
    try:
        load_frozen_original_8_definition(original8_path)
    except Exception:
        blockers.append("FROZEN_ORIGINAL_8_CONTROL_NOT_VERIFIED")
    target_csv = (root / str(sources["target_012922_csv"])).resolve()
    target_manifest = (root / str(sources["target_012922_manifest"])).resolve()
    try:
        target_meta = json.loads(target_manifest.read_text(encoding="utf-8"))
        target_verified = bool(
            target_meta.get("dataset_key") == "012922"
            and target_meta.get("content_sha256") == file_sha256(target_csv)
            and int(target_meta.get("row_count", -1)) == len(pd.read_csv(target_csv))
            and target_meta.get("publication_time_known") is False
        )
    except (OSError, json.JSONDecodeError, ValueError):
        target_verified = False
    if not target_verified:
        blockers.append("TARGET_012922_SOURCE_NOT_VERIFIED_FOR_TRACE")
    if _aware_utc(as_of_utc, "as-of").tz_convert(None).normalize() < FIRST_DECISION_DATE:
        blockers.append("FIRST_PROSPECTIVE_DECISION_NOT_REACHED")
    return {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_shadow_daily_readiness",
        "generated_at": _aware_utc(as_of_utc, "as-of").isoformat(),
        "status": "BLOCKED" if blockers else "READY_FOR_MANUAL_RESEARCH_ORCHESTRATION",
        "blockers": blockers,
        "source_checks": checks,
        "observed_calendar_verification": calendar_audit,
        "stages_implemented": [1, 2, 3],
        "automation_registered": False,
        "historical_candidate_replay_allowed": False,
        "retrospective_decision_backfill_allowed": False,
        "promotion_allowed": False,
        "live_mutation": False,
    }


DAILY_RUN_MANIFEST_KEYS = {
    "schema_version", "manifest_type", "generated_at", "status",
    "calendar_manifest_sha256", "latest_observed_session", "decision_phases",
    "realized_decision_batches", "independent_lane_count", "benchmark_control_count",
    "appended_lane_path_records", "original_8_control_rows",
    "target_012922_trace_rows", "target_012922_pending_rows",
    "target_012922_source_error", "three_way_alignment_manifest",
    "research_artifacts", "single_instance_lock_used",
    "historical_candidate_replay_used", "retrospective_decision_backfill_used",
    "automation_registered", "promotion_allowed", "live_mutation",
    "run_manifest_sha256",
}


def verify_daily_run_manifest(
    path: str | Path, *, repository_root: str | Path | None = None,
) -> dict[str, Any]:
    manifest_path = Path(path).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowDailyError("daily run manifest is missing/invalid") from exc
    unsigned = dict(manifest)
    declared = str(unsigned.pop("run_manifest_sha256", ""))
    if (
        set(manifest) != DAILY_RUN_MANIFEST_KEYS
        or canonical_sha256(unsigned) != declared
        or manifest.get("manifest_type") != "ndx_dynamic_shadow_daily_run"
        or manifest.get("status") not in {
            "RESEARCH_DAILY_COMPLETE", "RESEARCH_DAILY_COMPLETE_TARGET_TRACE_PENDING",
        }
        or int(manifest.get("independent_lane_count", -1)) not in {0, 10}
        or int(manifest.get("benchmark_control_count", -1))
        != (2 if int(manifest.get("independent_lane_count", -1)) == 10 else 0)
        or manifest.get("single_instance_lock_used") is not True
        or manifest.get("historical_candidate_replay_used") is not False
        or manifest.get("retrospective_decision_backfill_used") is not False
        or manifest.get("automation_registered") is not False
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_mutation") is not False
    ):
        raise NdxDynamicShadowDailyError("daily run manifest boundary changed")
    if repository_root is not None:
        expected = (
            Path(repository_root).resolve()
            / "data/cache/research/ndx_dynamic_shadow_daily_v1/latest_run.json"
        ).resolve()
        if manifest_path != expected:
            raise NdxDynamicShadowDailyError("daily run manifest path is not canonical")
    artifacts = manifest.get("research_artifacts") or {}
    expected_artifact_keys = {
        "daily_contract", "daily_engine", "daily_script", "observed_calendar_manifest",
        "realized_batch_manifests", "selector_lane_ledgers",
        "original_8_control_ledger", "target_012922_trace_ledger",
        "three_way_alignment_manifest", "nominal_price_evidence_manifest",
    }
    if set(artifacts) != expected_artifact_keys:
        raise NdxDynamicShadowDailyError("daily research artifact registry changed")

    def verify_item(value: Mapping[str, Any] | None) -> Path | None:
        if value is None:
            return None
        if set(value) not in ({"path", "sha256"}, {"path", "sha256", "rows"}):
            raise NdxDynamicShadowDailyError("daily artifact descriptor schema changed")
        source = Path(str(value.get("path") or ""))
        if not source.is_file() or file_sha256(source) != value.get("sha256"):
            raise NdxDynamicShadowDailyError("daily artifact path/hash changed")
        return source

    for key in ("daily_contract", "daily_engine", "daily_script", "observed_calendar_manifest"):
        verify_item(artifacts.get(key))
    for value in (artifacts.get("realized_batch_manifests") or {}).values():
        verify_item(value)
    selector_items = artifacts.get("selector_lane_ledgers") or {}
    if int(manifest["independent_lane_count"]) == 10:
        expected_selectors = {
            f"{track}__{role.lower()}__v1" for track in TRACKS for role in ROLES
        }
        if set(selector_items) != expected_selectors:
            raise NdxDynamicShadowDailyError("daily selector ledger registry is incomplete")
        for selector_id, descriptor in selector_items.items():
            source = verify_item(descriptor)
            records = load_lane_path_ledger(source, selector_id)
            if len(records) != int(descriptor.get("rows", -1)):
                raise NdxDynamicShadowDailyError("daily selector ledger rows changed")
        original_path = verify_item(artifacts.get("original_8_control_ledger"))
        original_records = load_lane_path_ledger(
            original_path, "ndx_original_8_incumbent_v0"
        )
        if len(original_records) != int(
            artifacts["original_8_control_ledger"].get("rows", -1)
        ):
            raise NdxDynamicShadowDailyError("daily original-8 ledger rows changed")
        target_path = verify_item(artifacts.get("target_012922_trace_ledger"))
        target_records = load_target_012922_trace_ledger(target_path)
        if len(target_records) != int(
            artifacts["target_012922_trace_ledger"].get("rows", -1)
        ):
            raise NdxDynamicShadowDailyError("daily target ledger rows changed")
        alignment_path = verify_item(artifacts.get("three_way_alignment_manifest"))
        alignment = verify_three_way_calendar_manifest(
            alignment_path,
            require_current_calendar_manifest_hash=repository_root is not None,
        )
        if int(alignment["target_pending_rows"]) != int(manifest["target_012922_pending_rows"]):
            raise NdxDynamicShadowDailyError("daily target pending count changed")
        verify_item(artifacts.get("nominal_price_evidence_manifest"))
    elif selector_items or any(
        artifacts.get(key) is not None for key in (
            "original_8_control_ledger", "target_012922_trace_ledger",
            "three_way_alignment_manifest", "nominal_price_evidence_manifest",
        )
    ):
        raise NdxDynamicShadowDailyError("daily empty run cannot expose partial path artifacts")
    return manifest


__all__ = [
    "NdxDynamicShadowDailyError", "append_lane_path", "append_target_012922_trace",
    "build_daily_readiness", "build_realized_lane_decisions", "canonical_sha256",
    "classify_daily_phase", "decision_coordinates", "load_daily_contract",
    "load_lane_path_ledger", "load_target_012922_trace_ledger",
    "normalize_observed_sessions", "replay_lane_path",
    "replay_original8_control_path", "resolve_first_observed_execution_session",
    "validate_nominal_price_evidence", "verify_daily_run_manifest",
    "verify_realized_decision_batch", "verify_realized_decision_chain",
    "verify_three_way_calendar_manifest", "within_conservative_seal_window",
    "write_immutable_realized_decisions", "write_three_way_calendar_manifest",
]
