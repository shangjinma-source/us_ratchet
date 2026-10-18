"""Hash-bound prospective full-k search executor and cross-k role freezer."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import yaml

from backtest.ndx_cardinality_discovery import (
    _frontier_tags,
    search_two_stage_cardinality,
)
from backtest.ndx_dynamic_candidate_policy import (
    NdxDynamicCandidatePolicyError,
    select_dynamic_candidate_policy,
    select_user_preference_reference_policy,
)
from backtest.ndx_original8_control import build_original8_control
from data.versioning import file_sha256


class NdxDynamicShadowFreshSearchError(ValueError):
    """Raised when fresh search provenance or coverage is incomplete."""


TRACKS = ("strict_technology", "technology_plus_adjacent")
ROLES = ("RETURN", "BAD_TAIL", "DRAWDOWN", "TARGET_ENVELOPE", "USER_PREFERENCE")
EXECUTION_COORDINATE_RULE = "FIRST_OBSERVED_COMMON_SESSION_STRICTLY_AFTER_DECISION"
FINAL_MANIFEST_TYPE = "ndx_dynamic_shadow_point_in_time_candidate_snapshot"
FINAL_STATUS = "FRESH_MONTHLY_CANDIDATES_COMPLETE_NOT_ADMISSION"


def _system_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text.lower())


def coordinate_hash(
    job: Mapping[str, Any], *, snapshot_manifest_sha256: str,
    executor_sha256: str, original_8_sha256: str,
) -> str:
    for label, value in (
        ("snapshot manifest", snapshot_manifest_sha256),
        ("executor", executor_sha256),
        ("original-8", original_8_sha256),
    ):
        if not _is_sha256(value):
            raise NdxDynamicShadowFreshSearchError(f"{label} hash is invalid")
    fields = {
        key: (value.item() if hasattr(value, "item") else value)
        for key, value in dict(job).items()
    }
    return canonical_sha256({
        "schema_version": 1,
        "job": fields,
        "snapshot_manifest_sha256": str(snapshot_manifest_sha256),
        "executor_sha256": str(executor_sha256),
        "original_8_sha256": str(original_8_sha256),
        "historical_candidate_replay_allowed": False,
    })


def load_executor_contract(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise NdxDynamicShadowFreshSearchError(f"cannot read executor contract: {source}") from exc
    if not isinstance(value, Mapping):
        raise NdxDynamicShadowFreshSearchError("executor contract must be a mapping")
    contract = dict(value)
    if (
        contract.get("schema_version") != 1
        or contract.get("executor_id") != "ndx_dynamic_shadow_fresh_search_v1"
        or contract.get("research_track") != "portfolio_optimization"
        or contract.get("migration_control_included") is not False
    ):
        raise NdxDynamicShadowFreshSearchError("unexpected executor identity or track")
    inputs = contract.get("input_contract") or {}
    for key in (
        "historical_runner_registry_read_allowed",
        "historical_candidate_snapshot_read_allowed",
        "frozen_forward_candidate_source_allowed",
    ):
        if inputs.get(key) is not False:
            raise NdxDynamicShadowFreshSearchError(f"{key} must remain false")
    search = contract.get("search_contract") or {}
    if search.get("bounded_global_optimality_claimed") is not False:
        raise NdxDynamicShadowFreshSearchError("bounded search cannot claim global optimality")
    completion = contract.get("completion_contract") or {}
    if tuple(completion.get("required_policy_roles") or ()) != ROLES:
        raise NdxDynamicShadowFreshSearchError("five-role completion registry changed")
    if completion.get("aggregate_requires_all_track_k_shards") is not True:
        raise NdxDynamicShadowFreshSearchError("all dynamic-k shards must be required")
    return contract


def load_frozen_original_8_definition(path: str | Path) -> tuple[list[str], dict[str, float], str]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowFreshSearchError(f"cannot read frozen original-8 definition: {source}") from exc
    if (
        payload.get("manifest_type") != "ndx_original_8_frozen_research_control"
        or payload.get("status") != "FROZEN_RESEARCH_CONTROL_NOT_CURRENT_BROKER_OVERLAY"
    ):
        raise NdxDynamicShadowFreshSearchError("unexpected original-8 definition identity")
    expected = ["NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG"]
    definition = payload.get("definition") or {}
    securities = definition.get("securities") or []
    tickers = [str(row.get("ticker") or "").upper() for row in securities]
    if tickers != expected:
        raise NdxDynamicShadowFreshSearchError("original-8 ticker order or identity changed")
    if any(not row.get("security_id") or not row.get("issuer_id") for row in securities):
        raise NdxDynamicShadowFreshSearchError("original-8 security/issuer identities are incomplete")
    if (
        len({str(row["security_id"]) for row in securities}) != 8
        or len({str(row["issuer_id"]) for row in securities}) != 8
    ):
        raise NdxDynamicShadowFreshSearchError("original-8 security/issuer identities are not unique")
    weights = {str(row["ticker"]).upper(): float(row["target_weight"]) for row in securities}
    if any(not np.isfinite(value) or value <= 0 for value in weights.values()):
        raise NdxDynamicShadowFreshSearchError("original-8 weights must be finite and positive")
    if not np.isclose(sum(weights.values()), 1.0, atol=1e-10):
        raise NdxDynamicShadowFreshSearchError("original-8 weights must sum to one")
    if payload.get("definition_sha256") != canonical_sha256(definition):
        raise NdxDynamicShadowFreshSearchError("original-8 definition hash mismatch")
    if payload.get("weight_source") != "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS":
        raise NdxDynamicShadowFreshSearchError("original-8 weights are not immutable child-manifest consensus")
    if payload.get("broker_current_overlay_included") is not False:
        raise NdxDynamicShadowFreshSearchError("original-8 control cannot include current broker overlay")
    if (
        float(definition.get("starting_capital_usd", 0)) != 25000.0
        or float(definition.get("minimum_cash_buffer_usd", -1)) != 100.0
        or float(definition.get("transaction_cost_bps", -1)) != 10.0
    ):
        raise NdxDynamicShadowFreshSearchError("original-8 capital/cost contract changed")
    mutation = payload.get("live_mutation") or {}
    if set(mutation) != {"config", "state", "broker", "today_advice", "orders"} or any(mutation.values()):
        raise NdxDynamicShadowFreshSearchError("original-8 control is not isolated from live mutation")
    inputs = payload.get("inputs") or {}
    dynamic_path = Path(str((inputs.get("dynamic_walkforward_manifest") or {}).get("path") or ""))
    identity_path = Path(str((inputs.get("identity_manifest") or {}).get("path") or ""))
    if not dynamic_path.is_file() or not identity_path.is_file():
        raise NdxDynamicShadowFreshSearchError("original-8 canonical input manifests are missing")
    if (
        file_sha256(dynamic_path) != (inputs.get("dynamic_walkforward_manifest") or {}).get("sha256")
        or file_sha256(identity_path) != (inputs.get("identity_manifest") or {}).get("sha256")
    ):
        raise NdxDynamicShadowFreshSearchError("original-8 canonical input manifest hash mismatch")
    roots = [parent for parent in source.resolve().parents if (parent / "config").is_dir() and (parent / "backtest").is_dir()]
    if len(roots) != 1:
        raise NdxDynamicShadowFreshSearchError("cannot resolve canonical repository root for original-8")
    rebuilt = build_original8_control(
        roots[0], dynamic_manifest_path=dynamic_path, identity_manifest_path=identity_path
    )
    if rebuilt.get("definition_sha256") != payload.get("definition_sha256"):
        raise NdxDynamicShadowFreshSearchError("original-8 manifest does not reproduce from canonical inputs")
    return tickers, weights, file_sha256(source)


def _boolean(series: pd.Series) -> pd.Series:
    return series.map(lambda value: value is True or str(value).strip().lower() == "true")


def validate_executor_inputs(
    job: Mapping[str, Any], eligible: pd.DataFrame, adjusted_close: pd.DataFrame,
    nominal_close: pd.DataFrame, target_aligned: pd.DataFrame,
    liquidity: pd.DataFrame, incumbent: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    required_job = {
        "snapshot_fingerprint", "universe_track", "decision_date", "execution_coordinate_rule",
        "decision_data_end", "holding_count", "eligible_issuer_count", "job_search_class",
        "checkpoint_key", "historical_candidate_replay_allowed",
    }
    if not required_job.issubset(job):
        raise NdxDynamicShadowFreshSearchError("job coordinate is incomplete")
    track = str(job["universe_track"])
    if track not in TRACKS:
        raise NdxDynamicShadowFreshSearchError("unknown universe track")
    if bool(job["historical_candidate_replay_allowed"]):
        raise NdxDynamicShadowFreshSearchError("historical candidate replay is forbidden")
    if str(job["execution_coordinate_rule"]) != EXECUTION_COORDINATE_RULE:
        raise NdxDynamicShadowFreshSearchError("job execution coordinate is not the sealed rule")
    if str(job["decision_data_end"]) != str(job["decision_date"]):
        raise NdxDynamicShadowFreshSearchError("job decision cutoff/date disagree")
    universe = eligible.loc[eligible["universe_track"].astype(str).eq(track)].copy()
    required_eligible = {"ticker", "security_id", "issuer_id", "risk_chain"}
    if universe.empty or not required_eligible.issubset(universe.columns):
        raise NdxDynamicShadowFreshSearchError("eligible universe is missing or incomplete")
    for key in ("ticker", "security_id", "issuer_id", "risk_chain"):
        if universe[key].isna().any() or universe[key].astype(str).str.strip().eq("").any():
            raise NdxDynamicShadowFreshSearchError(f"eligible universe has blank {key}")
    if universe["security_id"].duplicated().any():
        raise NdxDynamicShadowFreshSearchError("eligible universe duplicates security_id")
    issuer_count = int(universe["issuer_id"].nunique())
    k = int(job["holding_count"])
    if int(job["eligible_issuer_count"]) != issuer_count or not 1 <= k <= issuer_count:
        raise NdxDynamicShadowFreshSearchError("job dynamic-k coordinate disagrees with eligible issuer count")
    tickers = sorted(universe["ticker"].astype(str).unique())
    required_prices = set(tickers) | set(incumbent)

    def wide(frame: pd.DataFrame, name: str) -> pd.DataFrame:
        if "Date" not in frame:
            raise NdxDynamicShadowFreshSearchError(f"{name} lacks Date")
        result = frame.copy()
        result["Date"] = pd.to_datetime(result["Date"], errors="raise").dt.normalize()
        if result["Date"].duplicated().any() or not result["Date"].is_monotonic_increasing:
            raise NdxDynamicShadowFreshSearchError(f"{name} dates must be unique and sorted")
        result = result.set_index("Date")
        if not required_prices.issubset(result.columns):
            raise NdxDynamicShadowFreshSearchError(f"{name} lacks candidate/original-8 columns")
        result = result[sorted(required_prices)].apply(pd.to_numeric, errors="raise")
        if result.empty or result.isna().any().any() or (result <= 0).any().any():
            raise NdxDynamicShadowFreshSearchError(f"{name} contains invalid prices")
        return result

    adjusted = wide(adjusted_close, "adjusted training prices")
    nominal = wide(nominal_close, "nominal whole-lot prices")
    if not adjusted.index.equals(nominal.index):
        raise NdxDynamicShadowFreshSearchError("adjusted and nominal price calendars differ")
    if adjusted.index.max() != pd.Timestamp(job["decision_data_end"]).normalize():
        raise NdxDynamicShadowFreshSearchError("training prices do not end at decision close")
    if "Date" not in target_aligned or "Close" not in target_aligned:
        raise NdxDynamicShadowFreshSearchError("aligned 012922 target is incomplete")
    target = target_aligned.copy()
    target["Date"] = pd.to_datetime(target["Date"], errors="raise").dt.normalize()
    target = pd.to_numeric(target.set_index("Date")["Close"], errors="raise").reindex(adjusted.index)
    if target.isna().any() or (target <= 0).any():
        raise NdxDynamicShadowFreshSearchError("aligned 012922 target calendar differs")
    if not {"ticker", "median_dollar_volume_usd"}.issubset(liquidity.columns):
        raise NdxDynamicShadowFreshSearchError("liquidity inventory lacks median dollar volume")
    liquidity_map = liquidity.set_index(liquidity["ticker"].astype(str))["median_dollar_volume_usd"]
    universe["ticker"] = universe["ticker"].astype(str)
    universe["median_dollar_volume_usd"] = pd.to_numeric(universe["ticker"].map(liquidity_map), errors="coerce")
    universe["synthetic_price"] = universe["ticker"].map(nominal.iloc[-1])
    if universe[["median_dollar_volume_usd", "synthetic_price"]].isna().any().any():
        raise NdxDynamicShadowFreshSearchError("universe liquidity/nominal price mapping is incomplete")
    returns = adjusted.pct_change(fill_method=None).dropna()
    target_returns = target.pct_change(fill_method=None).reindex(returns.index)
    nominal = nominal.reindex(returns.index)
    if target_returns.isna().any() or nominal.isna().any().any():
        raise NdxDynamicShadowFreshSearchError("return or nominal training alignment failed")
    return universe, returns, target_returns, nominal, adjusted


def execute_fresh_shard(
    job: Mapping[str, Any], *, eligible: pd.DataFrame,
    adjusted_close: pd.DataFrame, nominal_close: pd.DataFrame,
    target_aligned: pd.DataFrame, liquidity: pd.DataFrame,
    incumbent: list[str], incumbent_weights: Mapping[str, float],
    contract: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    universe, returns, target_returns, nominal, _ = validate_executor_inputs(
        job, eligible, adjusted_close, nominal_close, target_aligned, liquidity, incumbent
    )
    search = contract["search_contract"]
    results, shortlist, audit = search_two_stage_cardinality(
        universe,
        returns,
        target_returns,
        incumbent,
        holding_count=int(job["holding_count"]),
        exact_limit=int(search["exact_enumeration_max_feasible_combinations"]),
        beam_width=int(search["beam_width"]),
        window_days=int(search["window_days"]),
        step_days=int(search["step_days"]),
        transaction_cost_bps=float(search["transaction_cost_bps"]),
        second_stage_per_frontier=int(search["second_stage_per_frontier"]),
        second_stage_weight_specs=tuple(search["second_stage_weight_specs"]),
        fit_days=int(search["fit_days"]),
        shrinkage_intensity=float(search["shrinkage_intensity"]),
        max_single_weight=float(search["max_single_weight"]),
        min_single_weight=float(search["min_single_weight"]),
        top_weight_cap=float(search["top_weight_cap"]),
        minimum_effective_n_ratio=float(search["minimum_effective_n_ratio"]),
        risk_chain_top1_cap=float(search["risk_chain_top1_cap"]),
        turnover_anchor_strength=float(search["turnover_anchor_strength"]),
        portfolio_cash_usd=float(search["portfolio_cash_usd"]),
        minimum_cash_buffer_usd=float(search["minimum_cash_buffer_usd"]),
        minimum_median_dollar_volume_usd=float(search["minimum_median_dollar_volume_usd"]),
        incumbent_weights=incumbent_weights,
        execution_prices=nominal,
    )
    identity = universe.set_index("ticker")[["security_id", "issuer_id"]].to_dict("index")
    results = results.copy()
    results.insert(0, "universe_track", str(job["universe_track"]))
    results.insert(1, "execution_coordinate_rule", str(job["execution_coordinate_rule"]))
    results.insert(2, "decision_data_end", str(job["decision_data_end"]))
    results["security_ids"] = results["tickers"].map(
        lambda value: ";".join(identity[ticker]["security_id"] for ticker in str(value).split(";"))
    )
    results["issuer_ids"] = results["tickers"].map(
        lambda value: ";".join(identity[ticker]["issuer_id"] for ticker in str(value).split(";"))
    )
    results["fresh_point_in_time_search"] = True
    results["fresh_oos"] = False
    results["future_outcomes_consumed"] = False
    results["historical_consumed"] = False
    results["promotion_allowed"] = False
    results["job_search_class"] = str(job["job_search_class"])
    results["bounded_global_optimality_claimed"] = False
    expected_exact = str(job["job_search_class"]) == "EXACT_ENUMERATION"
    security_set_exhaustive = bool(audit.get("theoretical_feasible_portfolios") == audit.get("fully_evaluated_portfolios"))
    actual_exact = audit.get("search_mode") == "EXACT_ENUMERATION"
    if expected_exact != actual_exact:
        raise NdxDynamicShadowFreshSearchError("planned exact/bounded class disagrees with actual issuer-feasible space")
    if expected_exact and not security_set_exhaustive:
        raise NdxDynamicShadowFreshSearchError("exact security-set shard was not exhaustively evaluated")
    if not expected_exact and bool(audit.get("optimality_claim_allowed")):
        raise NdxDynamicShadowFreshSearchError("bounded shard attempted an optimality claim")
    audit = {
        **audit,
        "snapshot_fingerprint": str(job["snapshot_fingerprint"]),
        "checkpoint_key": str(job["checkpoint_key"]),
        "job_search_class": str(job["job_search_class"]),
        "security_set_enumeration_exhaustive": security_set_exhaustive,
        "weight_space_global_optimality_claimed": False,
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
    }
    return results, {"search_audit": audit, "second_stage_shortlist_rows": len(shortlist)}


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_completed_shard(
    output_dir: str | Path, results: pd.DataFrame, audit: Mapping[str, Any],
    *, coordinate_hash: str,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "candidates.csv"
    audit_path = output / "search_audit.json"
    checkpoint_path = output / "checkpoint.json"
    if (
        results.empty or "coordinate_hash" not in results
        or not results["coordinate_hash"].astype(str).eq(str(coordinate_hash)).all()
    ):
        raise NdxDynamicShadowFreshSearchError("shard rows do not match their coordinate hash")
    result_content = results.to_csv(index=False, lineterminator="\n")
    audit_content = json.dumps(dict(audit), ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    for path, content in ((result_path, result_content), (audit_path, audit_content)):
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowFreshSearchError(f"completed shard collision: {path}")
        if not path.exists():
            _atomic_text(path, content)
    checkpoint = {
        "schema_version": 1,
        "status": "COMPLETED_HASH_VERIFIED",
        "coordinate_hash": coordinate_hash,
        "results": {"filename": result_path.name, "rows": len(results), "sha256": file_sha256(result_path)},
        "audit": {"filename": audit_path.name, "sha256": file_sha256(audit_path)},
        "historical_candidate_replay_used": False,
        "promotion_allowed": False,
    }
    unsigned = dict(checkpoint)
    checkpoint["checkpoint_sha256"] = canonical_sha256(unsigned)
    content = json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if checkpoint_path.exists() and checkpoint_path.read_text(encoding="utf-8") != content:
        raise NdxDynamicShadowFreshSearchError(f"completed shard collision: {checkpoint_path}")
    if not checkpoint_path.exists():
        _atomic_text(checkpoint_path, content)
    verify_completed_shard(checkpoint_path, coordinate_hash=coordinate_hash)
    return checkpoint


def verify_completed_shard(
    path: str | Path, *, coordinate_hash: str,
    expected_job: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    checkpoint_path = Path(path)
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowFreshSearchError(f"cannot read shard checkpoint: {checkpoint_path}") from exc
    declared = str(checkpoint.get("checkpoint_sha256") or "")
    unsigned = dict(checkpoint)
    unsigned.pop("checkpoint_sha256", None)
    if canonical_sha256(unsigned) != declared or checkpoint.get("coordinate_hash") != coordinate_hash:
        raise NdxDynamicShadowFreshSearchError("shard checkpoint identity/hash mismatch")
    frames = []
    audit_value = None
    for key in ("results", "audit"):
        artifact = checkpoint.get(key) or {}
        filename = str(artifact.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise NdxDynamicShadowFreshSearchError(f"invalid shard artifact filename: {key}")
        artifact_path = checkpoint_path.parent / filename
        if not artifact_path.is_file() or file_sha256(artifact_path) != artifact.get("sha256"):
            raise NdxDynamicShadowFreshSearchError(f"shard artifact hash mismatch: {key}")
        if key == "results":
            frame = pd.read_csv(artifact_path, low_memory=False)
            if len(frame) != int(artifact.get("rows", -1)):
                raise NdxDynamicShadowFreshSearchError("shard result row count mismatch")
            if (
                frame.empty or "coordinate_hash" not in frame
                or not frame["coordinate_hash"].astype(str).eq(str(coordinate_hash)).all()
            ):
                raise NdxDynamicShadowFreshSearchError("shard result contains a foreign coordinate")
            frames.append(frame)
        else:
            audit_value = json.loads(artifact_path.read_text(encoding="utf-8"))
    if checkpoint.get("historical_candidate_replay_used") is not False or checkpoint.get("promotion_allowed") is not False:
        raise NdxDynamicShadowFreshSearchError("shard evidence boundary changed")
    if expected_job is not None:
        search_audit = (audit_value or {}).get("search_audit") or {}
        expected = {
            "snapshot_fingerprint": str(expected_job["snapshot_fingerprint"]),
            "checkpoint_key": str(expected_job["checkpoint_key"]),
            "job_search_class": str(expected_job["job_search_class"]),
        }
        if any(str(search_audit.get(key)) != value for key, value in expected.items()):
            raise NdxDynamicShadowFreshSearchError("shard audit disagrees with planned job coordinate")
        if (
            search_audit.get("historical_candidate_replay_used") is not False
            or search_audit.get("promotion_allowed") is not False
        ):
            raise NdxDynamicShadowFreshSearchError("shard audit evidence boundary changed")
    return frames[0], dict(audit_value or {})


def freeze_cross_k_roles(candidates: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {
        "universe_track", "execution_coordinate_rule", "decision_data_end", "holding_count",
        "portfolio_id", "weight_spec", "tickers", "weights", "security_ids",
        "issuer_ids", "declared_constraints_passed", "return_p50", "return_p10",
        "max_drawdown_p50", "max_drawdown_p90", "target_012922_distance", "turnover",
    }
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise NdxDynamicShadowFreshSearchError(f"aggregate candidate columns missing: {missing}")
    frame = candidates.copy()
    if frame.empty or frame.duplicated(["universe_track", "portfolio_id", "weight_spec"]).any():
        raise NdxDynamicShadowFreshSearchError("aggregate candidates are empty or duplicated")
    frame["cross_k_frontier_tags"] = ""
    role_rows = []
    for track in TRACKS:
        scoped = frame.loc[frame["universe_track"].eq(track)].copy()
        if scoped.empty:
            raise NdxDynamicShadowFreshSearchError(f"aggregate lacks universe track: {track}")
        compliant = scoped.loc[_boolean(scoped["declared_constraints_passed"])].copy()
        if compliant.empty:
            raise NdxDynamicShadowFreshSearchError(f"no compliant candidates for competitive roles: {track}")
        # The policy is selected at decision close.  Actual execution is bound
        # later from the observed calendar, so the preregistered date validator
        # receives a local, non-persisted surrogate strictly after data_end.
        selection_labels = scoped["execution_coordinate_rule"].astype(str).unique().tolist()
        if selection_labels != [EXECUTION_COORDINATE_RULE]:
            raise NdxDynamicShadowFreshSearchError("candidate selection coordinate must remain rule-based until realization")
        policy_scoped = scoped.copy()
        policy_scoped["selection_date"] = (
            pd.to_datetime(policy_scoped["decision_data_end"], errors="raise").dt.normalize()
            + pd.Timedelta(days=1)
        )
        policy_compliant = policy_scoped.loc[_boolean(policy_scoped["declared_constraints_passed"])].copy()
        tags = _frontier_tags(policy_compliant)
        frame.loc[tags.index, "cross_k_frontier_tags"] = tags
        for role in ROLES:
            selector_id = f"{track}__{role.lower()}__v1"
            try:
                selected = (
                    select_user_preference_reference_policy(policy_scoped)
                    if role == "USER_PREFERENCE"
                    else select_dynamic_candidate_policy(policy_scoped, policy_role=role)
                )
            except NdxDynamicCandidatePolicyError as exc:
                if role != "USER_PREFERENCE":
                    raise NdxDynamicShadowFreshSearchError(f"competitive role unavailable: {selector_id}: {exc}") from exc
                role_rows.append({
                    "selector_id": selector_id,
                    "universe_track": track,
                    "policy_role": role,
                    "status": "REFERENCE_UNAVAILABLE_NOT_REPLACED",
                    "portfolio_id": "",
                    "holding_count": None,
                    "reason": str(exc),
                    "replacement_allowed": False,
                    "promotion_allowed": False,
                })
                continue
            if len(selected) != 1:
                raise NdxDynamicShadowFreshSearchError(f"role lock is not unique: {selector_id}")
            row = selected.iloc[0]
            role_rows.append({
                "selector_id": selector_id,
                "universe_track": track,
                "policy_role": role,
                "status": "SELECTED_REFERENCE_NOT_FIXED_ANSWER" if role == "USER_PREFERENCE" else "SELECTED_FRESH_SHADOW_CANDIDATE",
                "portfolio_id": str(row["portfolio_id"]),
                "holding_count": int(row["holding_count"]),
                "reason": "",
                "replacement_allowed": False,
                "promotion_allowed": False,
            })
    roles = pd.DataFrame(role_rows)
    if len(roles) != 10 or roles["selector_id"].nunique() != 10:
        raise NdxDynamicShadowFreshSearchError("role lock is not the complete 2 x 5 matrix")
    return frame.sort_values(["universe_track", "holding_count", "portfolio_id", "weight_spec"]).reset_index(drop=True), roles


def _validate_role_lock(roles: pd.DataFrame, candidates: pd.DataFrame) -> None:
    required = {
        "selector_id", "universe_track", "policy_role", "status", "portfolio_id",
        "holding_count", "replacement_allowed", "promotion_allowed",
    }
    if len(roles) != len(TRACKS) * len(ROLES) or not required.issubset(roles.columns):
        raise NdxDynamicShadowFreshSearchError("final role lock is incomplete")
    expected = {
        (track, role, f"{track}__{role.lower()}__v1")
        for track in TRACKS for role in ROLES
    }
    observed = set(
        roles[["universe_track", "policy_role", "selector_id"]]
        .astype(str).itertuples(index=False, name=None)
    )
    if observed != expected or roles["selector_id"].duplicated().any():
        raise NdxDynamicShadowFreshSearchError("final role lock matrix identity changed")
    if _boolean(roles["replacement_allowed"]).any() or _boolean(roles["promotion_allowed"]).any():
        raise NdxDynamicShadowFreshSearchError("final role lock cannot replace or promote a role")
    for row in roles.itertuples(index=False):
        portfolio_id = "" if pd.isna(row.portfolio_id) else str(row.portfolio_id).strip()
        if row.status == "REFERENCE_UNAVAILABLE_NOT_REPLACED":
            if row.policy_role != "USER_PREFERENCE" or portfolio_id or not pd.isna(row.holding_count):
                raise NdxDynamicShadowFreshSearchError("only USER_PREFERENCE may be explicitly unavailable")
            continue
        expected_status = (
            "SELECTED_REFERENCE_NOT_FIXED_ANSWER"
            if row.policy_role == "USER_PREFERENCE"
            else "SELECTED_FRESH_SHADOW_CANDIDATE"
        )
        if row.status != expected_status or not portfolio_id or pd.isna(row.holding_count):
            raise NdxDynamicShadowFreshSearchError("selected role status/identity is invalid")
        matches = candidates.loc[
            candidates["universe_track"].astype(str).eq(str(row.universe_track))
            & candidates["portfolio_id"].astype(str).eq(portfolio_id)
            & pd.to_numeric(candidates["holding_count"], errors="coerce").eq(int(row.holding_count))
        ]
        if matches.empty:
            raise NdxDynamicShadowFreshSearchError("selected role does not reference a frozen candidate")


def write_final_candidate_snapshot(
    output_dir: str | Path, candidates: pd.DataFrame, roles: pd.DataFrame,
    job_plan: pd.DataFrame, *, snapshot_manifest_sha256: str,
    snapshot_fingerprint: str, executor_sha256: str, original_8_sha256: str,
    snapshot_seal_record_sha256: str = "0" * 64,
    snapshot_conservative_deadline_utc: str = "2999-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    expected_coordinates = {
        coordinate_hash(
            row._asdict(), snapshot_manifest_sha256=snapshot_manifest_sha256,
            executor_sha256=executor_sha256, original_8_sha256=original_8_sha256,
        )
        for row in job_plan.itertuples(index=False)
    }
    observed_coordinates = set(candidates["coordinate_hash"].astype(str)) if "coordinate_hash" in candidates else set()
    if observed_coordinates != expected_coordinates:
        raise NdxDynamicShadowFreshSearchError("final aggregation does not cover every planned track-k coordinate")
    _validate_role_lock(roles, candidates)
    decision_dates = set(job_plan["decision_date"].astype(str)) if "decision_date" in job_plan else set()
    if len(decision_dates) != 1:
        raise NdxDynamicShadowFreshSearchError("final job plan must contain one decision date")
    decision_date = next(iter(decision_dates))
    if not all(_is_sha256(value) for value in (
        snapshot_manifest_sha256, snapshot_fingerprint, executor_sha256,
        original_8_sha256, snapshot_seal_record_sha256,
    )):
        raise NdxDynamicShadowFreshSearchError("snapshot seal record hash is invalid")
    deadline = pd.Timestamp(snapshot_conservative_deadline_utc)
    if deadline.tzinfo is None:
        raise NdxDynamicShadowFreshSearchError("snapshot conservative deadline must be timezone-aware")
    artifacts = {}
    for name, frame in (("candidates", candidates), ("role_lock", roles), ("job_plan", job_plan)):
        path = output / f"{name}.csv"
        content = frame.to_csv(index=False, lineterminator="\n")
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise NdxDynamicShadowFreshSearchError(f"immutable final candidate collision: {path}")
        if not path.exists():
            _atomic_text(path, content)
        artifacts[name] = {"filename": path.name, "rows": len(frame), "sha256": file_sha256(path)}
    path = output / "manifest.json"
    if path.exists():
        existing = verify_final_candidate_snapshot(path)
        expected_identity = {
            "decision_date": decision_date,
            "snapshot_manifest_sha256": snapshot_manifest_sha256,
            "snapshot_fingerprint": snapshot_fingerprint,
            "snapshot_seal_record_sha256": snapshot_seal_record_sha256,
            "snapshot_conservative_deadline_utc": deadline.tz_convert("UTC").isoformat(),
            "executor_sha256": executor_sha256,
            "original_8_sha256": original_8_sha256,
            "planned_track_k_shards": len(job_plan),
            "completed_track_k_shards": len(expected_coordinates),
            "artifacts": artifacts,
        }
        if any(existing.get(key) != value for key, value in expected_identity.items()):
            raise NdxDynamicShadowFreshSearchError(f"immutable final candidate collision: {path}")
        return existing
    roles_sealed_at = pd.Timestamp(_system_utc_now()).tz_convert("UTC")
    if roles_sealed_at >= deadline.tz_convert("UTC"):
        raise NdxDynamicShadowFreshSearchError("role freeze missed the conservative pre-open deadline")
    roles_sealed_at_utc = roles_sealed_at.isoformat()
    manifest = {
        "schema_version": 1,
        "manifest_type": FINAL_MANIFEST_TYPE,
        "status": FINAL_STATUS,
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "decision_date": decision_date,
        "snapshot_manifest_sha256": snapshot_manifest_sha256,
        "snapshot_fingerprint": snapshot_fingerprint,
        "snapshot_seal_record_sha256": snapshot_seal_record_sha256,
        "snapshot_conservative_deadline_utc": deadline.tz_convert("UTC").isoformat(),
        "executor_sha256": executor_sha256,
        "original_8_sha256": original_8_sha256,
        "planned_track_k_shards": len(job_plan),
        "completed_track_k_shards": len(expected_coordinates),
        "complete_track_k_coverage": True,
        "role_lock_count": len(roles),
        "candidate_sealed_at_utc": roles_sealed_at_utc,
        "roles_sealed_at_utc": roles_sealed_at_utc,
        "execution_coordinate_rule": EXECUTION_COORDINATE_RULE,
        "actual_execution_date": None,
        "actual_execution_date_must_be_bound_from_later_observed_calendar": True,
        "historical_runner_registry_read": False,
        "historical_candidate_snapshot_read": False,
        "frozen_forward_candidate_source_used": False,
        "bounded_global_optimality_claimed": False,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
        "live_mutation": False,
        "artifacts": artifacts,
    }
    content = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_text(path, content)
    verify_final_candidate_snapshot(path)
    return manifest


def verify_final_candidate_snapshot(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NdxDynamicShadowFreshSearchError(f"cannot read final candidate manifest: {manifest_path}") from exc
    if manifest.get("manifest_type") != FINAL_MANIFEST_TYPE or manifest.get("status") != FINAL_STATUS:
        raise NdxDynamicShadowFreshSearchError("unexpected final candidate manifest identity")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("research_track") != "portfolio_optimization"
        or manifest.get("migration_control_included") is not False
        or not all(
            _is_sha256(manifest.get(key))
            for key in (
                "snapshot_manifest_sha256", "snapshot_fingerprint",
                "executor_sha256", "original_8_sha256",
            )
        )
    ):
        raise NdxDynamicShadowFreshSearchError("final candidate provenance/track changed")
    if not _is_sha256(manifest.get("snapshot_seal_record_sha256")):
        raise NdxDynamicShadowFreshSearchError("final candidate snapshot seal binding changed")
    for key in (
        "historical_runner_registry_read", "historical_candidate_snapshot_read",
        "frozen_forward_candidate_source_used", "bounded_global_optimality_claimed",
        "fresh_oos_consumed", "promotion_allowed", "live_mutation",
    ):
        if manifest.get(key) is not False:
            raise NdxDynamicShadowFreshSearchError(f"final candidate boundary changed: {key}")
    if (
        manifest.get("execution_coordinate_rule") != EXECUTION_COORDINATE_RULE
        or manifest.get("actual_execution_date") is not None
        or manifest.get("actual_execution_date_must_be_bound_from_later_observed_calendar") is not True
    ):
        raise NdxDynamicShadowFreshSearchError("execution date was prematurely caller-bound")
    try:
        candidate_seal = pd.Timestamp(manifest["candidate_sealed_at_utc"])
        roles_seal = pd.Timestamp(manifest["roles_sealed_at_utc"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NdxDynamicShadowFreshSearchError("final candidate seal timestamps are invalid") from exc
    if (
        candidate_seal.tzinfo is None or roles_seal.tzinfo is None
        or candidate_seal.tz_convert("UTC") != roles_seal.tz_convert("UTC")
    ):
        raise NdxDynamicShadowFreshSearchError("candidate/role seal timestamps disagree")
    deadline = pd.Timestamp(manifest.get("snapshot_conservative_deadline_utc"))
    if deadline.tzinfo is None or roles_seal.tz_convert("UTC") >= deadline.tz_convert("UTC"):
        raise NdxDynamicShadowFreshSearchError("role seal is not before the conservative deadline")
    frames = {}
    for name in ("candidates", "role_lock", "job_plan"):
        artifact = (manifest.get("artifacts") or {}).get(name) or {}
        filename = str(artifact.get("filename") or "")
        if not filename or Path(filename).name != filename:
            raise NdxDynamicShadowFreshSearchError(f"invalid final artifact filename: {name}")
        artifact_path = manifest_path.parent / filename
        if not artifact_path.is_file() or file_sha256(artifact_path) != artifact.get("sha256"):
            raise NdxDynamicShadowFreshSearchError(f"final artifact hash mismatch: {name}")
        frame = pd.read_csv(artifact_path, low_memory=False)
        if len(frame) != int(artifact.get("rows", -1)):
            raise NdxDynamicShadowFreshSearchError(f"final artifact row count mismatch: {name}")
        frames[name] = frame
    _validate_role_lock(frames["role_lock"], frames["candidates"])
    if len(frames["job_plan"]) != int(manifest.get("planned_track_k_shards", -1)):
        raise NdxDynamicShadowFreshSearchError("final planned shard count changed")
    expected = {
        coordinate_hash(
            row._asdict(), snapshot_manifest_sha256=manifest["snapshot_manifest_sha256"],
            executor_sha256=manifest["executor_sha256"],
            original_8_sha256=manifest["original_8_sha256"],
        )
        for row in frames["job_plan"].itertuples(index=False)
    }
    if set(frames["candidates"]["coordinate_hash"].astype(str)) != expected:
        raise NdxDynamicShadowFreshSearchError("final candidate coordinate coverage changed")
    return manifest


def load_and_validate_role_seal_ledger(
    path: str | Path, *, expected_final_root: str | Path,
) -> list[dict[str, Any]]:
    ledger_path = Path(path)
    final_root = Path(expected_final_root).resolve()
    if not ledger_path.exists():
        return []
    records: list[dict[str, Any]] = []
    previous_hash = None
    previous_date: pd.Timestamp | None = None
    for sequence, line in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            raise NdxDynamicShadowFreshSearchError("blank role-seal ledger row")
        record = json.loads(line)
        required = {
            "schema_version", "sequence", "decision_date", "roles_sealed_at_utc",
            "final_manifest_path", "final_manifest_sha256", "snapshot_manifest_sha256",
            "snapshot_fingerprint", "snapshot_seal_record_sha256",
            "previous_record_sha256", "promotion_allowed", "live_mutation",
            "record_sha256",
        }
        if not isinstance(record, dict) or set(record) != required:
            raise NdxDynamicShadowFreshSearchError("role-seal ledger schema changed")
        unsigned = dict(record)
        declared = str(unsigned.pop("record_sha256") or "")
        if (
            record.get("schema_version") != 1
            or int(record.get("sequence", -1)) != sequence
            or record.get("previous_record_sha256") != previous_hash
            or canonical_sha256(unsigned) != declared
            or not _is_sha256(declared)
            or not _is_sha256(record.get("final_manifest_sha256"))
            or not _is_sha256(record.get("snapshot_manifest_sha256"))
            or not _is_sha256(record.get("snapshot_fingerprint"))
            or not _is_sha256(record.get("snapshot_seal_record_sha256"))
            or (
                record.get("previous_record_sha256") is not None
                and not _is_sha256(record.get("previous_record_sha256"))
            )
            or record.get("promotion_allowed") is not False
            or record.get("live_mutation") is not False
        ):
            raise NdxDynamicShadowFreshSearchError("role-seal ledger hash/boundary changed")
        decision = pd.Timestamp(record["decision_date"]).normalize()
        if previous_date is not None and decision <= previous_date:
            raise NdxDynamicShadowFreshSearchError("role-seal decision dates are not increasing")
        manifest_path = Path(str(record["final_manifest_path"])).resolve()
        expected_path = final_root / decision.date().isoformat() / "manifest.json"
        if (
            manifest_path != expected_path
            or not manifest_path.is_file()
            or file_sha256(manifest_path) != record["final_manifest_sha256"]
        ):
            raise NdxDynamicShadowFreshSearchError("role-seal final manifest binding changed")
        manifest = verify_final_candidate_snapshot(manifest_path)
        checks = {
            "decision_date": manifest["decision_date"],
            "roles_sealed_at_utc": manifest["roles_sealed_at_utc"],
            "snapshot_manifest_sha256": manifest["snapshot_manifest_sha256"],
            "snapshot_fingerprint": manifest["snapshot_fingerprint"],
            "snapshot_seal_record_sha256": manifest["snapshot_seal_record_sha256"],
        }
        if any(record.get(key) != value for key, value in checks.items()):
            raise NdxDynamicShadowFreshSearchError("role-seal record disagrees with final manifest")
        records.append(record)
        previous_hash = declared
        previous_date = decision
    return records


def append_role_seal_record(
    ledger_path: str | Path, final_manifest_path: str | Path, *,
    expected_final_root: str | Path,
) -> dict[str, Any]:
    path = Path(final_manifest_path).resolve()
    manifest = verify_final_candidate_snapshot(path)
    records = load_and_validate_role_seal_ledger(
        ledger_path, expected_final_root=expected_final_root,
    )
    same_date = [record for record in records if record["decision_date"] == manifest["decision_date"]]
    if same_date:
        if same_date[0]["final_manifest_sha256"] != file_sha256(path):
            raise NdxDynamicShadowFreshSearchError("role seal already exists with different evidence")
        return same_date[0]
    record = {
        "schema_version": 1,
        "sequence": len(records) + 1,
        "decision_date": manifest["decision_date"],
        "roles_sealed_at_utc": manifest["roles_sealed_at_utc"],
        "final_manifest_path": path.as_posix(),
        "final_manifest_sha256": file_sha256(path),
        "snapshot_manifest_sha256": manifest["snapshot_manifest_sha256"],
        "snapshot_fingerprint": manifest["snapshot_fingerprint"],
        "snapshot_seal_record_sha256": manifest["snapshot_seal_record_sha256"],
        "previous_record_sha256": records[-1]["record_sha256"] if records else None,
        "promotion_allowed": False,
        "live_mutation": False,
    }
    record["record_sha256"] = canonical_sha256(record)
    destination = Path(ledger_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    load_and_validate_role_seal_ledger(destination, expected_final_root=expected_final_root)
    return record


def verify_final_role_seal_record(
    final_manifest_path: str | Path, role_seal_ledger_path: str | Path, *,
    expected_final_root: str | Path,
) -> dict[str, Any]:
    manifest_path = Path(final_manifest_path).resolve()
    manifest = verify_final_candidate_snapshot(manifest_path)
    records = load_and_validate_role_seal_ledger(
        role_seal_ledger_path, expected_final_root=expected_final_root,
    )
    matches = [record for record in records if record["decision_date"] == manifest["decision_date"]]
    if len(matches) != 1 or matches[0]["final_manifest_sha256"] != file_sha256(manifest_path):
        raise NdxDynamicShadowFreshSearchError("final candidate has no unique append-only role seal")
    return matches[0]


__all__ = [
    "EXECUTION_COORDINATE_RULE", "FINAL_MANIFEST_TYPE", "FINAL_STATUS",
    "NdxDynamicShadowFreshSearchError",
    "append_role_seal_record", "canonical_sha256", "coordinate_hash",
    "execute_fresh_shard", "freeze_cross_k_roles", "load_and_validate_role_seal_ledger",
    "load_executor_contract", "load_frozen_original_8_definition",
    "validate_executor_inputs", "verify_completed_shard", "verify_final_candidate_snapshot",
    "verify_final_role_seal_record", "write_completed_shard",
    "write_final_candidate_snapshot",
]
