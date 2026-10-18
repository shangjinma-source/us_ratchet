r"""Build historical dynamic-k continuous paths from completed $25k replays.

This is consumed historical evidence for engine validation and policy
falsification.  It never substitutes for the v4 fresh-cohort gate and never
changes live configuration, state, broker truth, advice, or orders.

PowerShell:
    python -B scripts\ndx_dynamic_walkforward.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.ndx_dynamic_candidate_policy import (
    POLICY_ROLES,
    build_dynamic_policy_schedule,
    select_dynamic_candidate_policy,
    select_user_preference_reference_policy,
)
from backtest.ndx_dynamic_whole_lot_path import (
    simulate_dynamic_security_id_fractional_path,
    simulate_dynamic_security_id_whole_lot_path,
)
from core.helpers import atomic_write_text, resolve
from data.versioning import file_sha256


class NdxDynamicWalkforwardError(ValueError):
    pass


ORIGINAL_8 = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")
USER_PREFERENCE = ("AMAT", "AVGO", "CDNS", "GOOG")


def _canonical_runner_script_input() -> dict[str, str]:
    path = Path(__file__).resolve()
    canonical_path = (ROOT / "scripts" / "ndx_dynamic_walkforward.py").resolve()
    if path != canonical_path:
        raise NdxDynamicWalkforwardError("walkforward runner script is not canonical")
    return {"path": path.as_posix(), "sha256": file_sha256(path)}


def _with_canonical_runner_provenance(inputs: dict) -> dict:
    if "runner_script" in inputs:
        raise NdxDynamicWalkforwardError("runner_script provenance is reserved")
    return {"runner_script": _canonical_runner_script_input(), **inputs}


def _verified_artifact(manifest: dict, name: str) -> Path:
    artifact = (manifest.get("artifacts") or {}).get(name) or {}
    path = Path(str(artifact.get("path") or ""))
    if (
        not path.is_absolute() or not path.exists()
        or file_sha256(path) != artifact.get("sha256")
    ):
        raise NdxDynamicWalkforwardError(f"artifact mismatch: {name}")
    if artifact.get("rows") is not None:
        with path.open("r", encoding="utf-8-sig") as handle:
            rows = sum(1 for _ in handle) - 1
        if rows != int(artifact["rows"]):
            raise NdxDynamicWalkforwardError(f"artifact row count changed: {name}")
    return path


def _verified_input(manifest: dict, name: str) -> Path:
    item = (manifest.get("inputs") or {}).get(name) or {}
    path = Path(str(item.get("path") or ""))
    if (
        not path.is_absolute() or not path.exists()
        or file_sha256(path) != item.get("sha256")
    ):
        raise NdxDynamicWalkforwardError(f"input mismatch: {name}")
    return path


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_walkforward_contract(config: dict) -> None:
    capital = config.get("capital_contract") or {}
    preference = config.get("user_preference_reference") or {}
    benchmarks = config.get("comparison_benchmarks") or {}
    live_mutation = config.get("live_mutation") or {}
    if (
        config.get("schema_version") != 1
        or config.get("contract_id") != "ndx_dynamic_walkforward_v1"
        or config.get("status")
        != "HISTORICAL_RESEARCH_AND_FUTURE_SHADOW_NOT_LIVE_POLICY"
        or config.get("portfolio_scope") != "hsbc_us_equity_sleeve_only"
        or config.get("research_track") != "portfolio_optimization"
        or config.get("migration_control_included") is not False
        or float(capital.get("initial_comparison_capital_usd") or 0.0) != 25000.0
        or float(capital.get("minimum_cash_buffer_usd") or 0.0) != 100.0
        or float(capital.get("transaction_cost_bps") or 0.0) != 10.0
        or capital.get("fractional_and_whole_lot_tracks_required") is not True
        or tuple(config.get("dynamic_policy_lanes") or ()) != POLICY_ROLES
        or tuple(preference.get("tickers") or ()) != USER_PREFERENCE
        or preference.get("weight_spec") != "equal_weight"
        or preference.get("role") != "REFERENCE_NOT_FIXED_ANSWER"
        or tuple(benchmarks.get("original_8") or ()) != ORIGINAL_8
        or str(benchmarks.get("target")) != "012922"
        or benchmarks.get("single_path_scalar_target_distance_can_admit") is not False
        or set(live_mutation) != {
            "config", "state", "broker_snapshot", "today_advice", "orders",
        }
        or any(value is not False for value in live_mutation.values())
        or config.get("promotion_allowed") is not False
    ):
        raise NdxDynamicWalkforwardError("dynamic walk-forward contract is unsafe")


def _load_completed_replay_candidates(
    runner_manifest: dict,
) -> tuple[pd.DataFrame, dict[str, object]]:
    if (
        runner_manifest.get("manifest_type") != "ndx_cardinality_capital_replay_runner"
        or runner_manifest.get("status") != "CAPITAL_REPLAY_COMPLETE"
        or int(runner_manifest.get("completed") or 0)
        != int(runner_manifest.get("planned_job_count") or -1)
        or runner_manifest.get("promotion_allowed") is not False
    ):
        raise NdxDynamicWalkforwardError("$25k capital replay is not complete")
    scope = runner_manifest.get("execution_scope") or {}
    if (
        any(
            str(scope.get(key) or "").strip()
            for key in ("only_source_batch", "only_track", "only_selection_date")
        )
        or scope.get("max_jobs") is not None
    ):
        raise NdxDynamicWalkforwardError(
            "filtered or max_jobs capital replay cannot prove complete source coverage"
        )
    capital_manifest_path = _verified_input(runner_manifest, "capital_manifest")
    runner_shortlist_path = _verified_input(runner_manifest, "shortlist")
    capital_manifest = json.loads(capital_manifest_path.read_text(encoding="utf-8"))
    if (
        capital_manifest.get("manifest_type") != "ndx_cardinality_capital_sensitivity"
        or capital_manifest.get("status")
        != "CAPITAL_REPLAY_SHORTLIST_READY_RUNNERS_SEPARATE"
        or capital_manifest.get("whole_lot_25000_replay_completed") is not False
        or capital_manifest.get("cross_runner_semantics_compatible") is not False
        or capital_manifest.get("cross_runner_merge_allowed") is not False
        or capital_manifest.get("promotion_allowed") is not False
        or float(capital_manifest.get("target_replay_cash_usd") or 0.0) != 25000.0
        or float(capital_manifest.get("minimum_cash_buffer_usd") or 0.0) != 100.0
        or float(capital_manifest.get("transaction_cost_bps") or 0.0) != 10.0
    ):
        raise NdxDynamicWalkforwardError("capital sensitivity source contract mismatch")
    capital_shortlist_path = _verified_artifact(capital_manifest, "shortlist")
    if runner_shortlist_path.resolve() != capital_shortlist_path.resolve():
        raise NdxDynamicWalkforwardError("runner shortlist is not the capital source shortlist")
    shortlist = pd.read_csv(capital_shortlist_path, low_memory=False)
    coordinate_columns = ["source_batch", "universe_track", "selection_date"]
    if shortlist.empty or not set(coordinate_columns).issubset(shortlist.columns):
        raise NdxDynamicWalkforwardError("capital source shortlist is empty or incomplete")
    shortlist["selection_date"] = pd.to_datetime(
        shortlist["selection_date"], errors="raise"
    ).dt.date.astype(str)
    expected_counts = shortlist.groupby(
        coordinate_columns, sort=True, dropna=False
    ).size()
    expected_keys = {
        tuple(str(value) for value in key)
        for key in expected_counts.index.to_list()
    }
    index_path = _verified_artifact(runner_manifest, "job_index")
    jobs = pd.read_csv(index_path, low_memory=False)
    required_job_columns = set(coordinate_columns) | {
        "status", "shortlist_rows", "output_dir",
    }
    if jobs.empty or not required_job_columns.issubset(jobs.columns):
        raise NdxDynamicWalkforwardError("capital replay job index is incomplete")
    jobs["selection_date"] = pd.to_datetime(
        jobs["selection_date"], errors="raise"
    ).dt.date.astype(str)
    if (
        jobs.duplicated(coordinate_columns).any()
        or not jobs["status"].isin(["COMPLETED", "RESUMED_COMPLETED"]).all()
    ):
        raise NdxDynamicWalkforwardError("capital replay job index contains incomplete work")
    actual_keys = {
        tuple(str(value) for value in row)
        for row in jobs[coordinate_columns].itertuples(index=False, name=None)
    }
    if (
        actual_keys != expected_keys
        or len(jobs) != len(expected_keys)
        or int(runner_manifest.get("planned_job_count") or -1) != len(expected_keys)
    ):
        raise NdxDynamicWalkforwardError(
            "capital replay job index does not exactly cover the source shortlist"
        )
    frames: list[pd.DataFrame] = []
    incumbent_weight_versions: dict[str, dict[str, float]] = {}
    incumbent_state_hashes: set[str] = set()
    for job in jobs.to_dict("records"):
        job_key = (
            str(job["source_batch"]),
            str(job["universe_track"]),
            str(job["selection_date"]),
        )
        if int(job["shortlist_rows"]) != int(expected_counts.loc[job_key]):
            raise NdxDynamicWalkforwardError("capital replay shortlist row count mismatch")
        manifest_path = Path(str(job["output_dir"])) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        replay_source = manifest.get("candidate_replay_source") or {}
        if (
            manifest.get("manifest_type") != "ndx_cardinality_real_training_smoke"
            or manifest.get("status") != "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION"
            or manifest.get("candidate_replay_mode") is not True
            or str(manifest.get("universe_track")) != job_key[1]
            or str(manifest.get("selection_date")) != job_key[2]
            or float(manifest.get("portfolio_cash_usd") or 0.0) != 25000.0
            or manifest.get("promotion_allowed") is not False
            or replay_source.get("sha256") != file_sha256(capital_shortlist_path)
            or replay_source.get("source_batches") != [job_key[0]]
            or int(replay_source.get("coordinate_source_rows") or -1)
            != int(expected_counts.loc[job_key])
        ):
            raise NdxDynamicWalkforwardError("candidate replay manifest contract mismatch")
        raw_incumbent_weights = manifest.get("incumbent_weights") or {}
        if set(raw_incumbent_weights) != set(ORIGINAL_8):
            raise NdxDynamicWalkforwardError("original-8 source weights are incomplete")
        incumbent_weights = {
            ticker: float(raw_incumbent_weights[ticker]) for ticker in ORIGINAL_8
        }
        if (
            any(not math.isfinite(value) or value <= 0 for value in incumbent_weights.values())
            or not math.isclose(sum(incumbent_weights.values()), 1.0, abs_tol=1e-10)
        ):
            raise NdxDynamicWalkforwardError("original-8 source weights are invalid")
        weight_version = json.dumps(
            incumbent_weights, sort_keys=True, separators=(",", ":")
        )
        incumbent_weight_versions[weight_version] = incumbent_weights
        source_state_hash = str(
            ((manifest.get("inputs") or {}).get("state") or {}).get("sha256") or ""
        )
        if not source_state_hash:
            raise NdxDynamicWalkforwardError("original-8 source state hash is absent")
        incumbent_state_hashes.add(source_state_hash)
        candidates_path = _verified_artifact(manifest, "candidates")
        frame = pd.read_csv(candidates_path, low_memory=False)
        frame["source_batch"] = str(job["source_batch"])
        if (
            len(frame) != int(expected_counts.loc[job_key])
            or not frame["universe_track"].astype(str).eq(job_key[1]).all()
            or not frame["selection_date"].astype(str).eq(job_key[2]).all()
            or not pd.to_numeric(frame["portfolio_cash_usd"], errors="raise").eq(25000.0).all()
            or not pd.to_numeric(
                frame["minimum_cash_buffer_usd"], errors="raise"
            ).eq(100.0).all()
        ):
            raise NdxDynamicWalkforwardError("candidate replay coordinate contents mismatch")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    required = {
        "source_batch", "universe_track", "selection_date", "decision_data_end",
        "security_ids", "issuer_ids", "risk_chains",
    }
    if not required.issubset(combined.columns):
        raise NdxDynamicWalkforwardError("replay candidates lack point-in-time identities")
    if len(incumbent_weight_versions) != 1 or len(incumbent_state_hashes) != 1:
        raise NdxDynamicWalkforwardError(
            "capital replay jobs do not share one frozen original-8 definition"
        )
    frozen_incumbent_weights = next(iter(incumbent_weight_versions.values()))
    coverage = {
        "source_shortlist_rows": int(len(shortlist)),
        "expected_job_group_count": int(len(expected_keys)),
        "completed_job_group_count": int(len(actual_keys)),
        "job_group_key_set_exact_match": True,
        "unfiltered_execution_scope": True,
        "source_batches_kept_separate": True,
        "cross_runner_semantics_compatible": False,
        "cross_runner_merge_allowed": False,
        "original_8_weight_source": "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS",
        "original_8_incumbent_weights": frozen_incumbent_weights,
        "original_8_source_state_sha256": next(iter(incumbent_state_hashes)),
        "capital_manifest_path": capital_manifest_path.as_posix(),
        "capital_manifest_sha256": file_sha256(capital_manifest_path),
        "shortlist_path": capital_shortlist_path.as_posix(),
        "shortlist_sha256": file_sha256(capital_shortlist_path),
    }
    return combined, coverage


def _load_execution_and_valuation_prices(
    manifest_path: Path,
    tickers: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_type") != "ndx_cardinality_whole_lot_execution_price_bundle"
        or manifest.get("status") != "READY"
    ):
        raise NdxDynamicWalkforwardError("execution price bundle is not ready")
    inventory_path = _verified_artifact(manifest, "inventory")
    inventory = pd.read_csv(inventory_path, low_memory=False).set_index("ticker")
    missing = sorted(tickers - set(inventory.index.astype(str)))
    if missing:
        raise NdxDynamicWalkforwardError(f"execution inventory lacks tickers: {missing}")
    open_series = []
    close_series = []
    for ticker in sorted(tickers):
        row = inventory.loc[ticker]
        path = Path(str(row["path"]))
        sidecar_path = Path(str(row["sidecar_path"]))
        if (
            str(row["status"]) != "FETCHED" or not path.is_absolute()
            or file_sha256(path) != str(row["sha256"])
            or not sidecar_path.is_absolute()
            or file_sha256(sidecar_path) != str(row["sidecar_sha256"])
        ):
            raise NdxDynamicWalkforwardError(f"execution price artifact mismatch: {ticker}")
        frame = pd.read_csv(path, usecols=["Date", "Open", "Close"])
        frame["Date"] = pd.to_datetime(frame["Date"], errors="raise").dt.normalize()
        frame["Open"] = pd.to_numeric(frame["Open"], errors="raise")
        frame["Close"] = pd.to_numeric(frame["Close"], errors="raise")
        if (
            len(frame) != int(row["rows"])
            or frame["Date"].duplicated().any()
            or not frame["Date"].is_monotonic_increasing
            or not frame[["Open", "Close"]].apply(
                lambda column: column.map(math.isfinite)
            ).all().all()
            or bool((frame["Open"] <= 0).any())
            or bool((frame["Close"] <= 0).any())
        ):
            raise NdxDynamicWalkforwardError(f"execution prices are invalid: {ticker}")
        indexed = frame.set_index("Date")
        open_series.append(indexed["Open"].rename(ticker))
        close_series.append(indexed["Close"].rename(ticker))
    execution = pd.concat(open_series, axis=1, join="inner").sort_index()
    valuation = pd.concat(close_series, axis=1, join="inner").sort_index()
    if (
        execution.empty or valuation.empty
        or not execution.index.equals(valuation.index)
        or execution.isna().any().any() or valuation.isna().any().any()
    ):
        raise NdxDynamicWalkforwardError(
            "common nominal Open execution / Close valuation calendar is incomplete"
        )
    return execution, valuation


def _simulate_consumed_path(
    simulator,
    valuation_prices: pd.DataFrame,
    execution_prices: pd.DataFrame,
    schedule: list[dict],
    *,
    initial_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float,
    valuation_end_date: pd.Timestamp,
):
    """Run historical evidence with the mandatory nominal execution guards."""
    return simulator(
        valuation_prices,
        schedule,
        execution_prices=execution_prices,
        require_separate_execution_prices=True,
        require_next_session_execution=True,
        require_issuer_trace=True,
        initial_cash_usd=initial_cash_usd,
        minimum_cash_buffer_usd=minimum_cash_buffer_usd,
        transaction_cost_bps=transaction_cost_bps,
        valuation_end_date=valuation_end_date,
    )


def _user_preference_reference_diagnostics(
    candidates: pd.DataFrame,
    *,
    source_batch: str,
    track: str,
) -> list[dict[str, object]]:
    preference = set(USER_PREFERENCE)
    dates = sorted(pd.to_datetime(candidates["selection_date"]).dt.normalize().unique())
    scoped = candidates.loc[
        candidates["tickers"].astype(str).map(
            lambda value: {item for item in value.split(";") if item} == preference
        )
        & candidates["weight_spec"].astype(str).eq("equal_weight")
    ].copy()
    per_date: list[dict[str, object]] = []
    for raw_date in dates:
        selection_date = pd.Timestamp(raw_date).normalize()
        rows = scoped.loc[
            pd.to_datetime(scoped["selection_date"]).dt.normalize().eq(selection_date)
        ]
        present_count = int(len(rows))
        passed = False
        reason = "USER_PREFERENCE_REFERENCE_ABSENT"
        portfolio_id = tickers = weights = ""
        if present_count == 1:
            row = rows.iloc[0]
            passed = str(row["declared_constraints_passed"]).strip().lower() in {
                "true", "1",
            }
            reason = (
                "REFERENCE_CONSTRAINTS_PASSED"
                if passed else str(row.get("constraint_failure_reasons") or "")
                or "REFERENCE_CONSTRAINTS_FAILED"
            )
            portfolio_id = str(row.get("portfolio_id") or "")
            tickers = str(row.get("tickers") or "")
            weights = str(row.get("weights") or "")
        elif present_count > 1:
            reason = "USER_PREFERENCE_REFERENCE_AMBIGUOUS"
        per_date.append({
            "source_batch": source_batch,
            "universe_track": track,
            "selection_date": selection_date.date().isoformat(),
            "policy_role": "USER_PREFERENCE",
            "reference_role": "REFERENCE_NOT_FIXED_ANSWER",
            "present_row_count": present_count,
            "portfolio_id": portfolio_id,
            "tickers": tickers,
            "weights": weights,
            "declared_constraints_passed": passed,
            "reference_path_date_eligible": passed,
            "reason": reason,
            "admission_allowed": False,
            "promotion_allowed": False,
        })
    full_path_available = bool(per_date) and all(
        bool(item["reference_path_date_eligible"]) for item in per_date
    )
    for item in per_date:
        item["complete_reference_path_available"] = full_path_available
    return per_date


def _target_metrics_and_trace(
    path: pd.DataFrame,
    target_path: Path,
) -> tuple[dict[str, object], pd.DataFrame]:
    manifest_path = target_path.with_name(target_path.name + ".manifest.json")
    if not manifest_path.exists():
        raise NdxDynamicWalkforwardError("012922 manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("dataset_key") != "012922"
        or manifest.get("dataset_type") != "fund_nav"
        or manifest.get("completeness") != "verified_against_source_record_count"
        or manifest.get("content_sha256") != file_sha256(target_path)
        or int(manifest.get("row_count") or -1)
        != int(manifest.get("source_record_count") or -2)
    ):
        raise NdxDynamicWalkforwardError("012922 manifest contract mismatch")
    target = pd.read_csv(target_path, usecols=["Date", "Close"])
    target["Date"] = pd.to_datetime(target["Date"], errors="raise").dt.normalize()
    target["Close"] = pd.to_numeric(target["Close"], errors="raise")
    if (
        target["Date"].duplicated().any()
        or not target["Date"].is_monotonic_increasing
        or not target["Close"].map(math.isfinite).all()
        or bool((target["Close"] <= 0).any())
    ):
        raise NdxDynamicWalkforwardError("012922 target series is invalid")
    series = target.set_index("Date")["Close"].sort_index()
    dates = pd.to_datetime(path["date"], errors="raise").dt.normalize()
    union = series.index.union(pd.DatetimeIndex(dates)).sort_values()
    aligned = series.reindex(union).ffill().reindex(dates)
    source_dates = pd.Series(series.index, index=series.index).reindex(union).ffill().reindex(dates)
    if aligned.isna().any() or not math.isfinite(float(aligned.iloc[-1])):
        raise NdxDynamicWalkforwardError("012922 is incomplete for the path interval")
    nav = aligned / float(aligned.iloc[0])
    total_return = float(nav.iloc[-1] - 1.0)
    sessions = max(1, len(nav))
    no_future = bool(
        source_dates.notna().all() and (source_dates.to_numpy() <= dates.to_numpy()).all()
    )
    exact_date = source_dates.to_numpy() == dates.to_numpy()
    exact_count = int(exact_date.sum())
    lagged_count = int(len(dates) - exact_count)
    lag_days = (
        pd.Series(dates.to_numpy()) - pd.Series(source_dates.to_numpy())
    ).dt.days
    metrics = {
        "path_return_net": total_return,
        "path_annualized_return_net": float((1.0 + total_return) ** (252.0 / sessions) - 1.0),
        "path_max_drawdown": float((1.0 - nav / nav.cummax()).max()),
        "target_asof_no_future_passed": no_future,
        "target_path_session_count": int(len(dates)),
        "target_exact_source_date_count": exact_count,
        "target_lagged_session_count": lagged_count,
        "target_exact_source_date_coverage_ratio": float(exact_count / len(dates)),
        "maximum_target_nav_lag_calendar_days": int(lag_days.max()),
        "target_nav_freshness_threshold_registered": False,
        "target_nav_freshness_passed": None,
        "target_publication_time_known": manifest.get("publication_time_known") is True,
        "benchmark_alignment_role": "ASOF_DIAGNOSTIC_NOT_FRESHNESS_OR_ADMISSION",
    }
    trace = pd.DataFrame({
        "date": pd.DatetimeIndex(dates).date.astype(str),
        "target_source_date": pd.DatetimeIndex(source_dates).date.astype(str),
        "target_close_asof": aligned.to_numpy(dtype=float),
        "target_nav_asof": nav.to_numpy(dtype=float),
        "target_lag_calendar_days": lag_days.to_numpy(dtype=int),
        "target_exact_source_date": exact_date,
        "target_asof_no_future_passed": no_future,
        "freshness_threshold_registered": False,
        "freshness_passed": None,
        "diagnostic_only_not_admission": True,
    })
    return metrics, trace


def _target_metrics(path: pd.DataFrame, target_path: Path) -> dict[str, object]:
    metrics, _ = _target_metrics_and_trace(path, target_path)
    return metrics


def _load_incumbent_identities(manifest_path: Path) -> dict[str, dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("manifest_type") != "ndx_incumbent_pit_execution_attribution"
        or manifest.get("status")
        != "EXECUTION_ATTRIBUTION_ONLY_NOT_SELECTION_OR_ADMISSION"
        or manifest.get("historical_backfill_created") is not False
        or manifest.get("candidate_selection_allowed") is not False
        or manifest.get("promotion_allowed") is not False
    ):
        raise NdxDynamicWalkforwardError("original-8 identity manifest contract mismatch")
    projection_path = _verified_artifact(manifest, "projection")
    projection = pd.read_csv(projection_path, low_memory=False)
    required = {"ticker", "security_id", "issuer_id"}
    if projection.empty or not required.issubset(projection.columns):
        raise NdxDynamicWalkforwardError("original-8 identity projection is incomplete")
    identities: dict[str, dict[str, str]] = {}
    for ticker in ORIGINAL_8:
        rows = projection.loc[projection["ticker"].astype(str).eq(ticker)]
        security_ids = sorted(set(rows["security_id"].astype(str)))
        issuer_ids = sorted(set(rows["issuer_id"].astype(str)))
        if len(security_ids) != 1 or len(issuer_ids) != 1:
            raise NdxDynamicWalkforwardError(
                f"original-8 identity is absent or ambiguous: {ticker}"
            )
        identities[ticker] = {
            "security_id": security_ids[0],
            "issuer_id": issuer_ids[0],
        }
    if len({item["security_id"] for item in identities.values()}) != len(ORIGINAL_8):
        raise NdxDynamicWalkforwardError("original-8 security identities are not unique")
    if len({item["issuer_id"] for item in identities.values()}) != len(ORIGINAL_8):
        raise NdxDynamicWalkforwardError("original-8 issuer identities are not unique")
    return identities


def _incumbent_schedule(
    selection_rows: pd.DataFrame,
    incumbent_weights: dict[str, float],
    identities: dict[str, dict[str, str]],
) -> list[dict]:
    targets = {
        identities[ticker]["security_id"]: {
            "ticker": ticker,
            "issuer_id": identities[ticker]["issuer_id"],
            "target_weight": incumbent_weights[ticker],
        }
        for ticker in ORIGINAL_8
    }
    return [
        {
            "decision_date": row.decision_data_end,
            "execution_date": row.selection_date,
            "targets": targets,
        }
        for row in selection_rows.sort_values("selection_date").itertuples(index=False)
    ]


def _summary_row(
    *, source_batch: str, track: str, role: str, execution_track: str,
    summary: dict, incumbent: dict, target: dict,
) -> dict:
    return {
        "source_batch": source_batch,
        "universe_track": track,
        "policy_role": role,
        "execution_track": execution_track,
        "path_start": summary["valuation_start_date"],
        "valuation_end_date": summary["valuation_end_date"],
        "trading_session_count": summary["path_trading_session_count"],
        "rebalance_count": summary["rebalance_count"],
        "minimum_target_k": summary["minimum_target_k"],
        "maximum_target_k": summary["maximum_target_k"],
        "k_path": json.dumps(summary["k_path"], separators=(",", ":")),
        "path_return_net": summary["path_return_net"],
        "path_annualized_return_net": summary["path_annualized_return_net"],
        "path_max_drawdown": summary["path_max_drawdown"],
        "total_transaction_cost_usd": summary["total_transaction_cost_usd"],
        "annualized_return_vs_original_8": (
            summary["path_annualized_return_net"] - incumbent["path_annualized_return_net"]
        ),
        "max_drawdown_cost_vs_original_8": (
            summary["path_max_drawdown"] - incumbent["path_max_drawdown"]
        ),
        "annualized_return_vs_012922": (
            summary["path_annualized_return_net"] - target["path_annualized_return_net"]
        ),
        "max_drawdown_cost_vs_012922": summary["path_max_drawdown"] - target["path_max_drawdown"],
        "target_asof_no_future_passed": target["target_asof_no_future_passed"],
        "target_path_session_count": target["target_path_session_count"],
        "target_exact_source_date_count": target["target_exact_source_date_count"],
        "target_lagged_session_count": target["target_lagged_session_count"],
        "target_exact_source_date_coverage_ratio": target[
            "target_exact_source_date_coverage_ratio"
        ],
        "maximum_target_nav_lag_calendar_days": target["maximum_target_nav_lag_calendar_days"],
        "target_nav_freshness_threshold_registered": target[
            "target_nav_freshness_threshold_registered"
        ],
        "target_nav_freshness_passed": target["target_nav_freshness_passed"],
        "target_publication_time_known": target["target_publication_time_known"],
        "benchmark_alignment_role": target["benchmark_alignment_role"],
        "single_path_scalar_target_distance_used_for_admission": False,
        "historical_consumed_evidence": True,
        "fresh_oos_consumed": False,
        "promotion_allowed": False,
    }


def run(args: argparse.Namespace) -> dict:
    config_path = resolve(args.config)
    runner_manifest_path = resolve(args.capital_replay_manifest)
    execution_manifest_path = resolve(args.execution_price_manifest)
    target_path = resolve(args.target_nav)
    state_path = resolve(args.state)
    broker_path = resolve(args.broker)
    incumbent_identity_manifest_path = resolve(args.incumbent_identity_manifest)
    output = resolve(args.output_dir)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _validate_walkforward_contract(config)
    protected_paths = [resolve("config/config.yaml"), state_path, broker_path]
    protected_before = {path.as_posix(): file_sha256(path) for path in protected_paths}
    runner_manifest = json.loads(runner_manifest_path.read_text(encoding="utf-8"))
    candidates, replay_coverage = _load_completed_replay_candidates(runner_manifest)
    if (
        protected_before[state_path.as_posix()]
        != replay_coverage["original_8_source_state_sha256"]
    ):
        raise NdxDynamicWalkforwardError(
            "current state no longer matches the frozen original-8 source definition"
        )
    incumbent_identities = _load_incumbent_identities(incumbent_identity_manifest_path)
    valuation_end = pd.Timestamp(
        args.valuation_end or config["historical_consumed_evidence"]["valuation_end"]
    ).normalize()
    candidates["selection_date"] = pd.to_datetime(candidates["selection_date"]).dt.normalize()
    source_candidates = candidates.copy()
    candidates = candidates.loc[candidates["selection_date"] <= valuation_end].copy()
    if candidates.empty:
        raise NdxDynamicWalkforwardError("no replay decisions precede valuation cutoff")
    incumbent_tickers = set(ORIGINAL_8)
    all_tickers = incumbent_tickers | {
        ticker
        for value in candidates["tickers"].astype(str)
        for ticker in value.split(";") if ticker
    }
    execution_prices, valuation_prices = _load_execution_and_valuation_prices(
        execution_manifest_path, all_tickers
    )
    if valuation_end not in valuation_prices.index:
        raise NdxDynamicWalkforwardError("valuation cutoff is absent from valuation prices")
    capital = config["capital_contract"]
    initial_cash = float(capital["initial_comparison_capital_usd"])
    buffer = float(capital["minimum_cash_buffer_usd"])
    bps = float(capital["transaction_cost_bps"])
    output.mkdir(parents=True, exist_ok=True)
    summary_rows: list[dict] = []
    lane_artifacts: list[dict] = []
    unavailable_lanes: list[dict] = []
    preference_diagnostics: list[dict[str, object]] = []
    preference_path_coverage: dict[tuple[str, str], dict[str, object]] = {}
    for (source_batch, track), group in candidates.groupby(
        ["source_batch", "universe_track"], sort=True
    ):
        source_group = source_candidates.loc[
            source_candidates["source_batch"].astype(str).eq(str(source_batch))
            & source_candidates["universe_track"].astype(str).eq(str(track))
        ].copy()
        base_dates = group[["selection_date", "decision_data_end"]].drop_duplicates()
        if base_dates["selection_date"].duplicated().any():
            raise NdxDynamicWalkforwardError("decision cutoff differs within one selection date")
        incumbent_schedule = _incumbent_schedule(
            base_dates,
            replay_coverage["original_8_incumbent_weights"],
            incumbent_identities,
        )
        diagnostics = _user_preference_reference_diagnostics(
            source_group,
            source_batch=str(source_batch),
            track=str(track),
        )
        preference_diagnostics.extend(diagnostics)
        present_reference_dates = [
            item["selection_date"]
            for item in diagnostics
            if int(item["present_row_count"]) == 1
        ]
        cutoff_excluded = sorted(
            date for date in present_reference_dates
            if pd.Timestamp(date) > valuation_end
        )
        coverage_key = (str(source_batch), str(track))
        preference_path_coverage[coverage_key] = {
            "source_batch": str(source_batch),
            "universe_track": str(track),
            "reference_role": "REFERENCE_NOT_FIXED_ANSWER",
            "source_coordinate_dates": int(
                source_group["selection_date"].nunique()
            ),
            "source_reference_dates": len(present_reference_dates),
            "source_declared_constraints_passed_dates": sum(
                bool(item["declared_constraints_passed"])
                for item in diagnostics
                if int(item["present_row_count"]) == 1
            ),
            "executed_reference_dates": 0,
            "cutoff_excluded_dates": ";".join(cutoff_excluded),
            "old_declared_constraint_failures_do_not_create_admission": True,
            "admission_allowed": False,
            "promotion_allowed": False,
        }
        incumbent_summaries: dict[str, dict] = {}
        incumbent_paths: dict[str, pd.DataFrame] = {}
        target_summary: dict[str, object] | None = None
        target_trace: pd.DataFrame | None = None
        for role in config["dynamic_policy_lanes"]:
            try:
                if str(role) == "USER_PREFERENCE":
                    selected = select_user_preference_reference_policy(
                        group,
                        user_preference_tickers=USER_PREFERENCE,
                    )
                else:
                    selected = select_dynamic_candidate_policy(
                        group,
                        policy_role=str(role),
                        user_preference_tickers=USER_PREFERENCE,
                    )
            except ValueError as exc:
                unavailable_lanes.append({
                    "source_batch": source_batch,
                    "universe_track": track,
                    "policy_role": role,
                    "reason": str(exc),
                })
                continue
            selected = selected.loc[selected["selection_date"] <= valuation_end].copy()
            if str(role) == "USER_PREFERENCE":
                preference_path_coverage[coverage_key][
                    "executed_reference_dates"
                ] = int(len(selected))
            schedule = build_dynamic_policy_schedule(selected)
            lane_dir = output / str(source_batch) / str(track) / str(role).lower()
            lane_dir.mkdir(parents=True, exist_ok=True)
            selected_path = lane_dir / "selected_candidates.csv"
            _atomic_csv(selected, selected_path)
            for execution_track, simulator in (
                ("fractional", simulate_dynamic_security_id_fractional_path),
                ("whole_lot", simulate_dynamic_security_id_whole_lot_path),
            ):
                summary, rebalances, trades, path = _simulate_consumed_path(
                    simulator,
                    valuation_prices,
                    execution_prices,
                    schedule,
                    initial_cash_usd=initial_cash,
                    minimum_cash_buffer_usd=buffer,
                    transaction_cost_bps=bps,
                    valuation_end_date=valuation_end,
                )
                if execution_track not in incumbent_summaries:
                    (
                        incumbent_summary,
                        incumbent_rebalances,
                        incumbent_trades,
                        incumbent_path,
                    ) = _simulate_consumed_path(
                        simulator,
                        valuation_prices,
                        execution_prices,
                        incumbent_schedule,
                        initial_cash_usd=initial_cash,
                        minimum_cash_buffer_usd=buffer,
                        transaction_cost_bps=bps,
                        valuation_end_date=valuation_end,
                    )
                    incumbent_summaries[execution_track] = incumbent_summary
                    incumbent_paths[execution_track] = incumbent_path
                    control_dir = output / str(source_batch) / str(track) / "controls"
                    control_dir.mkdir(parents=True, exist_ok=True)
                    for control_name, control_frame in (
                        (f"original_8_{execution_track}_rebalances", incumbent_rebalances),
                        (f"original_8_{execution_track}_trades", incumbent_trades),
                        (f"original_8_{execution_track}_path", incumbent_path),
                    ):
                        control_path = control_dir / f"{control_name}.csv"
                        _atomic_csv(control_frame, control_path)
                        lane_artifacts.append({
                            "source_batch": source_batch,
                            "universe_track": track,
                            "policy_role": "ORIGINAL_8_CONTROL",
                            "name": control_name,
                            "path": control_path.as_posix(),
                            "rows": len(control_frame),
                            "sha256": file_sha256(control_path),
                        })
                    if target_summary is None:
                        target_summary, target_trace = _target_metrics_and_trace(
                            incumbent_path, target_path
                        )
                        target_trace_path = control_dir / "target_012922_asof_trace.csv"
                        _atomic_csv(target_trace, target_trace_path)
                        lane_artifacts.append({
                            "source_batch": source_batch,
                            "universe_track": track,
                            "policy_role": "TARGET_012922_CONTROL",
                            "name": "target_012922_asof_trace",
                            "path": target_trace_path.as_posix(),
                            "rows": len(target_trace),
                            "sha256": file_sha256(target_trace_path),
                        })
                assert target_summary is not None and target_trace is not None
                comparison_dates = path["date"].astype(str).tolist()
                if (
                    comparison_dates
                    != incumbent_paths[execution_track]["date"].astype(str).tolist()
                    or comparison_dates != target_trace["date"].astype(str).tolist()
                ):
                    raise NdxDynamicWalkforwardError(
                        "candidate and both benchmark controls do not share one path calendar"
                    )
                summary_row = _summary_row(
                    source_batch=str(source_batch), track=str(track), role=str(role),
                    execution_track=execution_track, summary=summary,
                    incumbent=incumbent_summaries[execution_track], target=target_summary,
                )
                summary_row["policy_role_contract"] = (
                    "REFERENCE_NOT_FIXED_ANSWER"
                    if str(role) == "USER_PREFERENCE"
                    else "COMPETITIVE_TRAINING_DIAGNOSTIC"
                )
                summary_row["admission_allowed"] = False
                summary_row["candidate_original_8_target_same_path_calendar"] = True
                if str(role) == "USER_PREFERENCE":
                    passed = selected[
                        "reference_declared_constraints_passed"
                    ].astype(bool)
                    summary_row["reference_declared_constraints_passed_dates"] = int(
                        passed.sum()
                    )
                    summary_row["reference_declared_constraints_failed_dates"] = int(
                        len(passed) - passed.sum()
                    )
                summary_rows.append(summary_row)
                for name, frame in (
                    (f"{execution_track}_rebalances", rebalances),
                    (f"{execution_track}_trades", trades),
                    (f"{execution_track}_path", path),
                ):
                    path_out = lane_dir / f"{name}.csv"
                    _atomic_csv(frame, path_out)
                    lane_artifacts.append({
                        "source_batch": source_batch, "universe_track": track,
                        "policy_role": role, "name": name,
                        "path": path_out.as_posix(), "rows": len(frame),
                        "sha256": file_sha256(path_out),
                    })
            lane_artifacts.append({
                "source_batch": source_batch, "universe_track": track,
                "policy_role": role, "name": "selected_candidates",
                "path": selected_path.as_posix(), "rows": len(selected),
                "sha256": file_sha256(selected_path),
            })
    if not summary_rows:
        raise NdxDynamicWalkforwardError("no dynamic policy lane could be evaluated")
    summary_frame = pd.DataFrame(summary_rows)
    summary_path = output / "dynamic_policy_path_summary.csv"
    artifact_index_path = output / "artifact_index.csv"
    unavailable_path = output / "unavailable_lanes.csv"
    preference_diagnostics_path = output / "user_preference_reference_diagnostics.csv"
    preference_coverage_path = output / "user_preference_reference_path_coverage.csv"
    _atomic_csv(summary_frame, summary_path)
    _atomic_csv(pd.DataFrame(lane_artifacts), artifact_index_path)
    _atomic_csv(pd.DataFrame(
        unavailable_lanes,
        columns=["source_batch", "universe_track", "policy_role", "reason"],
    ), unavailable_path)
    _atomic_csv(pd.DataFrame(preference_diagnostics), preference_diagnostics_path)
    preference_coverage_frame = pd.DataFrame(preference_path_coverage.values())
    _atomic_csv(preference_coverage_frame, preference_coverage_path)
    protected_after = {path.as_posix(): file_sha256(path) for path in protected_paths}
    if protected_before != protected_after:
        raise NdxDynamicWalkforwardError("protected live files changed")
    manifest = {
        "schema_version": 1,
        "manifest_type": "ndx_dynamic_cardinality_historical_walkforward",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": "CONSUMED_HISTORICAL_POLICY_PATHS_COMPLETE_NOT_ADMISSION",
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "dynamic_k_composition_and_weights_enabled": True,
        "fractional_and_whole_lot_tracks_completed": True,
        "execution_price_basis": "NOMINAL_UNADJUSTED_SESSION_OPEN",
        "valuation_price_basis": "NOMINAL_UNADJUSTED_SESSION_CLOSE",
        "separate_execution_and_valuation_price_channels_required": True,
        "first_common_session_after_decision_required": True,
        "security_id_and_issuer_id_continuity_required": True,
        "candidate_original_8_target_same_path_calendar_required": True,
        "original_8_rebalance_trade_and_path_traces_persisted": True,
        "target_012922_asof_trace_persisted": True,
        "target_012922_alignment_role": "ASOF_DIAGNOSTIC_NOT_FRESHNESS_OR_ADMISSION",
        "capital_replay_source_coverage": replay_coverage,
        "cross_runner_results_merged": False,
        "target_012922_single_path_scalar_used_for_admission": False,
        "historical_returns_read": True,
        "historical_consumed_evidence": True,
        "fresh_oos_consumed": False,
        "can_replace_v4_formal_gate": False,
        "promotion_allowed": False,
        "protected_hashes_unchanged": True,
        "live_mutation": {"config": False, "state": False, "broker": False, "today_advice": False, "orders": False},
        "valuation_end": valuation_end.date().isoformat(),
        "evaluated_lane_track_rows": len(summary_frame),
        "unavailable_lane_count": len(unavailable_lanes),
        "user_preference_reference_date_count": len(preference_diagnostics),
        "user_preference_reference_executed_path_count": sum(
            int(item["executed_reference_dates"]) > 0
            for item in preference_path_coverage.values()
        ),
        "user_preference_reference_all_source_constraints_passed_path_count": sum(
            int(item["source_reference_dates"]) > 0
            and int(item["source_declared_constraints_passed_dates"])
            == int(item["source_reference_dates"])
            for item in preference_path_coverage.values()
        ),
        "inputs": _with_canonical_runner_provenance({
            "config": {"path": config_path.as_posix(), "sha256": file_sha256(config_path)},
            "capital_replay_manifest": {"path": runner_manifest_path.as_posix(), "sha256": file_sha256(runner_manifest_path)},
            "execution_price_manifest": {"path": execution_manifest_path.as_posix(), "sha256": file_sha256(execution_manifest_path)},
            "target_nav": {"path": target_path.as_posix(), "sha256": file_sha256(target_path)},
            "target_nav_manifest": {
                "path": target_path.with_name(target_path.name + ".manifest.json").as_posix(),
                "sha256": file_sha256(target_path.with_name(target_path.name + ".manifest.json")),
            },
            "incumbent_identity_manifest": {
                "path": incumbent_identity_manifest_path.as_posix(),
                "sha256": file_sha256(incumbent_identity_manifest_path),
            },
            "state": {"path": state_path.as_posix(), "sha256": protected_before[state_path.as_posix()]},
        }),
        "artifacts": {
            "summary": {"path": summary_path.as_posix(), "rows": len(summary_frame), "sha256": file_sha256(summary_path)},
            "artifact_index": {"path": artifact_index_path.as_posix(), "rows": len(lane_artifacts), "sha256": file_sha256(artifact_index_path)},
            "unavailable_lanes": {"path": unavailable_path.as_posix(), "rows": len(unavailable_lanes), "sha256": file_sha256(unavailable_path)},
            "user_preference_reference_diagnostics": {
                "path": preference_diagnostics_path.as_posix(),
                "rows": len(preference_diagnostics),
                "sha256": file_sha256(preference_diagnostics_path),
            },
            "user_preference_reference_path_coverage": {
                "path": preference_coverage_path.as_posix(),
                "rows": len(preference_coverage_frame),
                "sha256": file_sha256(preference_coverage_path),
            },
        },
    }
    atomic_write_text(output / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="动态k跨月连续持仓历史walk-forward")
    parser.add_argument("--config", default="config/ndx_dynamic_walkforward_v1.yaml")
    parser.add_argument("--capital-replay-manifest", default="data/cache/research/ndx_cardinality_capital_replay_v1/manifest.json")
    parser.add_argument("--execution-price-manifest", default="data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json")
    parser.add_argument("--target-nav", default="data/cache/funds/012922.csv")
    parser.add_argument("--state", default="data/state.json")
    parser.add_argument("--broker", default="data/broker_positions.json")
    parser.add_argument(
        "--incumbent-identity-manifest",
        default="data/cache/research/ndx_incumbent_pit_attribution_v1/manifest.json",
    )
    parser.add_argument("--valuation-end", default="")
    parser.add_argument("--output-dir", default="data/cache/research/ndx_dynamic_walkforward_v1")
    return parser.parse_args()


def main() -> int:
    try:
        manifest = run(parse_args())
    except Exception as exc:
        print(f"动态k连续walk-forward失败闭环: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "动态k连续walk-forward完成 | "
        f"lane_tracks={manifest['evaluated_lane_track_rows']} | "
        f"unavailable={manifest['unavailable_lane_count']} | "
        "fresh_oos=False | promotion_allowed=False"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
