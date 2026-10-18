"""Batch A/B replay for locked 2024-06-03 equal-weight candidates.

The runner changes one execution mechanism only: the existing 21-session
equal-weight rebalance cadence is continued to the already-frozen path end.
Every source candidate must first reproduce its stored identities, weights,
trace, and 13 whole-lot summary fields.  This is historical research, not a
new search, ranking, admission decision, live configuration, or order path.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

import backtest.ndx_cardinality_discovery as discovery
from backtest import ndx_cardinality_capital_replay_summary as replay_v1
from backtest.ndx_cardinality_capital_replay_pareto_summary import (
    _source_v1_summary,
    _v1_start_index,
)
from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from scripts import ndx_cardinality_real_smoke as real_smoke


SOURCE_SUMMARY_RELATIVE = replay_v1.OUTPUT_RELATIVE / "manifest.json"
OUTPUT_RELATIVE = Path(
    "data/cache/research/ndx_equal_weight_schedule_extension_runner_v1"
)
SOURCE_BATCH = "ndx_cardinality_real_runner_p2_exact_v3"
JOB_SEARCH_CLASS = "EXACT_ENUMERATION"
EVALUATOR_SHA256 = "f08700fc438e0e1258623fc687d13ac1556d5c4a398afa66cbb7c8e12fb7558f"
SELECTION_DATE = "2024-06-03"
TRACK_EXPECTED_COUNTS = {
    "strict_technology": {
        "total": 105, "eligible": 82, "whole_lot_only": 23, "other_failure": 0,
    },
    "technology_plus_adjacent": {
        "total": 218, "eligible": 131, "whole_lot_only": 87, "other_failure": 0,
    },
}
EXPECTED_TOTALS = {
    "total": 323, "eligible": 213, "whole_lot_only": 110, "other_failure": 0,
}
LOCKED_RISK_THRESHOLDS = {
    "max_single_weight": 0.45,
    "min_single_weight": 0.05,
    "top_weight_cap": 0.80,
    "minimum_effective_n_ratio": 0.70,
    "risk_chain_top1_cap": 0.55,
}
ORIGINAL_SUMMARY_FIELDS = (
    "whole_lot_rebalance_count",
    "whole_lot_initial_shares",
    "whole_lot_terminal_shares",
    "whole_lot_share_change_count",
    "whole_lot_total_trade_notional_usd",
    "whole_lot_total_transaction_cost_usd",
    "whole_lot_min_cash_usd",
    "whole_lot_cash_buffer_preserved",
    "whole_lot_constraints_preserved_all_days",
    "whole_lot_terminal_value_usd",
    "whole_lot_path_return_net",
    "whole_lot_path_max_drawdown",
    "whole_lot_rebalance_trace_sha256",
)


class NdxEqualWeightScheduleExtensionRunnerError(ValueError):
    """Raised when locked-source or replay evidence fails closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise NdxEqualWeightScheduleExtensionRunnerError(f"{label} is not numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            f"{label} is not numeric"
        ) from exc
    if not math.isfinite(parsed):
        raise NdxEqualWeightScheduleExtensionRunnerError(f"{label} is not finite")
    return parsed


def _file_descriptor(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    raw = resolved.read_bytes()
    return {"path": resolved.as_posix(), "sha256": _sha256(raw)}


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _single_instance_lock(path: Path):
    """Hold an OS-released nonblocking lock for one plan fingerprint."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if path.stat().st_size == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise NdxEqualWeightScheduleExtensionRunnerError(
                    "another replay for this plan fingerprint is running"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise NdxEqualWeightScheduleExtensionRunnerError(
                    "another replay for this plan fingerprint is running"
                ) from exc
        acquired = True
        yield
    finally:
        try:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _candidate_failure_class(candidate: Mapping[str, Any]) -> str:
    if candidate.get("source_failure_class") in {
        "SOURCE_REPORTED_ELIGIBLE", "WHOLE_LOT_EXECUTABILITY_FAILED_ONLY",
        "OTHER_SOURCE_REPORTED_FAILURE",
    }:
        return str(candidate["source_failure_class"])
    if candidate["source_reported_replay_eligible"] is True:
        return "SOURCE_REPORTED_ELIGIBLE"
    if candidate["failure_reasons"] == ["WHOLE_LOT_EXECUTABILITY_FAILED"]:
        return "WHOLE_LOT_EXECUTABILITY_FAILED_ONLY"
    return "OTHER_SOURCE_REPORTED_FAILURE"


def _expected_original_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    path = candidate["continuous_whole_lot_path"]
    tickers = list(candidate["tickers"])
    return {
        "whole_lot_rebalance_count": int(path["whole_lot_rebalance_count"]),
        "whole_lot_initial_shares": ";".join(
            f"{ticker}:{path['initial_shares'][ticker]}" for ticker in tickers
        ),
        "whole_lot_terminal_shares": ";".join(
            f"{ticker}:{path['terminal_shares'][ticker]}" for ticker in tickers
        ),
        "whole_lot_share_change_count": int(path["whole_lot_share_change_count"]),
        "whole_lot_total_trade_notional_usd": path[
            "whole_lot_total_trade_notional_usd"
        ],
        "whole_lot_total_transaction_cost_usd": path[
            "whole_lot_total_transaction_cost_usd"
        ],
        "whole_lot_min_cash_usd": path["whole_lot_min_cash_usd"],
        "whole_lot_cash_buffer_preserved": path["cash_buffer_preserved"],
        "whole_lot_constraints_preserved_all_days": path[
            "constraints_preserved_all_days"
        ],
        "whole_lot_terminal_value_usd": path["whole_lot_terminal_value_usd"],
        "whole_lot_path_return_net": path["whole_lot_path_return_net"],
        "whole_lot_path_max_drawdown": path["whole_lot_path_max_drawdown"],
        "whole_lot_rebalance_trace_sha256": path["rebalance_trace_sha256"],
    }


def _candidate_identity(
    candidate: Mapping[str, Any], *, coordinate: Mapping[str, str]
) -> dict[str, Any]:
    tickers = list(candidate["tickers"])
    weights = {ticker: float(candidate["weights"][ticker]) for ticker in tickers}
    target = 1.0 / len(tickers)
    if candidate["weight_spec"] != "equal_weight" or any(
        not math.isclose(weights[ticker], target, rel_tol=0.0, abs_tol=1e-10)
        for ticker in tickers
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "locked candidate is not equal weight"
        )
    payload = {
        **dict(coordinate),
        "portfolio_id": candidate["portfolio_id"],
        "holding_count": candidate["holding_count"],
        "weight_spec": "equal_weight",
        "tickers": tickers,
        "weights": weights,
        "security_ids": list(candidate["security_ids"]),
        "issuer_ids": list(candidate["issuer_ids"]),
        "risk_chains": list(candidate["risk_chains"]),
        "old_trace_sha256": candidate["continuous_whole_lot_path"][
            "rebalance_trace_sha256"
        ],
        "source_failure_class": _candidate_failure_class(candidate),
        "source_failure_reasons": list(candidate["failure_reasons"]),
        "source_reported_replay_eligible": candidate[
            "source_reported_replay_eligible"
        ],
        "expected_original_summary": _expected_original_summary(candidate),
    }
    return {
        **payload,
        "candidate_identity_sha256": _canonical_sha256(payload),
        "candidate_key": _canonical_sha256(payload)[:24],
    }


def _validate_scope_counts(
    candidates: Sequence[Mapping[str, Any]], expected: Mapping[str, int]
) -> dict[str, int]:
    counts = Counter(_candidate_failure_class(candidate) for candidate in candidates)
    observed = {
        "total": len(candidates),
        "eligible": counts["SOURCE_REPORTED_ELIGIBLE"],
        "whole_lot_only": counts["WHOLE_LOT_EXECUTABILITY_FAILED_ONLY"],
        "other_failure": counts["OTHER_SOURCE_REPORTED_FAILURE"],
    }
    if observed != dict(expected):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            f"locked equal-weight scope count changed: {observed} != {dict(expected)}"
        )
    return observed


def build_locked_replay_plan(*, repository_root: str | Path) -> dict[str, Any]:
    """Verify and enumerate exactly the two frozen latest exact coordinates."""

    root = Path(repository_root).resolve()
    source_path = (root / SOURCE_SUMMARY_RELATIVE).resolve()
    try:
        source_summary, source_summary_descriptor = _source_v1_summary(source_path, root)
        v1_starts = _v1_start_index(source_summary)
        top, lineages, jobs, top_evidence = replay_v1._verify_top(
            root / replay_v1.TOP_MANIFEST_RELATIVE, root
        )
    except (replay_v1.NdxCardinalityCapitalReplaySummaryError, ValueError) as exc:
        raise NdxEqualWeightScheduleExtensionRunnerError(str(exc)) from exc
    lineage = lineages.get(SOURCE_BATCH)
    if (
        lineage is None
        or lineage.get("job_search_class") != JOB_SEARCH_CLASS
        or lineage.get("evaluation_semantics_sha256") != EVALUATOR_SHA256
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "frozen exact evaluator lineage changed"
        )
    source_run_path = Path(lineage["source_run_manifest"]["path"])
    source_run_raw = source_run_path.read_bytes()
    source_run = json.loads(source_run_raw.decode("utf-8"))
    if _sha256(source_run_raw) != lineage["source_run_manifest"]["historical_sha256"]:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "frozen source runner manifest bytes changed"
        )
    relevant_jobs = [
        job
        for job in jobs
        if job["source_batch"] == SOURCE_BATCH
        and job["selection_date"] == SELECTION_DATE
        and job["universe_track"] in TRACK_EXPECTED_COUNTS
    ]
    if len(relevant_jobs) != 2 or {job["universe_track"] for job in relevant_jobs} != set(
        TRACK_EXPECTED_COUNTS
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "latest exact two-track source scope changed"
        )
    replay_root = (root / replay_v1.TOP_MANIFEST_RELATIVE).parent.resolve()
    shortlist_path = (root / replay_v1.SHORTLIST_RELATIVE).resolve()
    groups: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    for job in sorted(relevant_jobs, key=lambda item: item["universe_track"]):
        track = job["universe_track"]
        child_path = replay_root / SOURCE_BATCH / track / SELECTION_DATE / "manifest.json"
        child_raw = child_path.read_bytes()
        child_manifest = json.loads(child_raw.decode("utf-8"))
        candidate_path = child_path.parent / "training_candidates.csv"
        candidate_raw = candidate_path.read_bytes()
        try:
            child = replay_v1._verify_child(
                job,
                root=root,
                replay_root=replay_root,
                shortlist_path=shortlist_path,
                shortlist_sha256=top_evidence["shortlist"]["historical_sha256"],
                lineage=lineage,
            )
        except replay_v1.NdxCardinalityCapitalReplaySummaryError as exc:
            raise NdxEqualWeightScheduleExtensionRunnerError(str(exc)) from exc
        child.pop("_recovered_source_bytes", None)
        if child_path.read_bytes() != child_raw or candidate_path.read_bytes() != candidate_raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked child source changed during verification"
            )
        start_key = (
            SOURCE_BATCH, JOB_SEARCH_CLASS, EVALUATOR_SHA256, track, SELECTION_DATE
        )
        published = v1_starts.get(start_key)
        if (
            published is None
            or published.get("source_manifest") != child.get("source_manifest")
            or child.get("source_manifest")
            != {"path": child_path.as_posix(), "sha256": _sha256(child_raw)}
            or published.get("artifacts", {}).get("candidates", {}).get(
                "historical_sha256"
            )
            != _sha256(candidate_raw)
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "published v1 per-start source binding changed"
            )
        fields, raw_rows = replay_v1._csv_rows(candidate_raw, "locked candidate source")
        if not replay_v1.REQUIRED_CANDIDATE_COLUMNS.issubset(fields):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked candidate source fields changed"
            )
        try:
            validated = [
                replay_v1._validate_candidate(
                    row,
                    selection_date=SELECTION_DATE,
                    training_end=str(child_manifest["training_end"]),
                )
                for row in raw_rows
            ]
        except replay_v1.NdxCardinalityCapitalReplaySummaryError as exc:
            raise NdxEqualWeightScheduleExtensionRunnerError(str(exc)) from exc
        equal_weight = [
            candidate for candidate in validated if candidate["weight_spec"] == "equal_weight"
        ]
        counts = _validate_scope_counts(equal_weight, TRACK_EXPECTED_COUNTS[track])
        coordinate = {
            "source_batch": SOURCE_BATCH,
            "job_search_class": JOB_SEARCH_CLASS,
            "evaluation_semantics_sha256": EVALUATOR_SHA256,
            "universe_track": track,
            "selection_date": SELECTION_DATE,
        }
        locked = [
            _candidate_identity(candidate, coordinate=coordinate)
            for candidate in equal_weight
        ]
        uniqueness = {
            (
                tuple(item["tickers"]), tuple(item["security_ids"]),
                tuple((ticker, item["weights"][ticker]) for ticker in item["tickers"]),
                item["old_trace_sha256"],
            )
            for item in locked
        }
        if len(uniqueness) != len(locked) or len({item["candidate_key"] for item in locked}) != len(
            locked
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked candidate workload is not unique within coordinate"
            )
        group = {
            **coordinate,
            "counts": counts,
            "source_child_manifest": {
                "path": child_path.as_posix(), "sha256": _sha256(child_raw)
            },
            "source_candidate_artifact": {
                "path": candidate_path.as_posix(),
                "sha256": _sha256(candidate_raw),
                "rows": len(raw_rows),
            },
            "candidates": locked,
        }
        groups.append(group)
        all_candidates.extend(locked)
    _validate_scope_counts(all_candidates, EXPECTED_TOTALS)
    source_inputs = source_run.get("inputs")
    run_contract = source_run.get("run_contract")
    if not isinstance(source_inputs, Mapping) or not isinstance(run_contract, Mapping):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "source runner execution contract is incomplete"
        )
    code_bindings = [
        _file_descriptor(root / relative)
        for relative in (
            "backtest/ndx_whole_lot_rebalance.py",
            "backtest/ndx_cardinality_discovery.py",
            "scripts/ndx_cardinality_real_smoke.py",
            "backtest/ndx_equal_weight_schedule_extension_runner.py",
            "scripts/ndx_equal_weight_schedule_extension_runner.py",
        )
    ]
    payload = {
        "schema_version": 1,
        "plan_type": "ndx_equal_weight_schedule_extension_locked_plan",
        "status": "LOCKED_HISTORICAL_REPLAY_PLAN",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "migration_control_included": False,
        "source_v1_summary_bundle": source_summary_descriptor,
        "source_top_manifest": top_evidence["top_manifest"],
        "source_runner_manifest": {
            "path": source_run_path.resolve().as_posix(), "sha256": _sha256(source_run_raw)
        },
        "source_runner_inputs": source_inputs,
        "source_run_contract": run_contract,
        "selection_date": SELECTION_DATE,
        "job_search_class": JOB_SEARCH_CLASS,
        "evaluation_semantics_sha256": EVALUATOR_SHA256,
        "track_load_count_clean_full_run": 2,
        "groups": groups,
        "counts": EXPECTED_TOTALS,
        "code_bindings": code_bindings,
        "mechanism": "CONTINUE_EXISTING_EQUAL_WEIGHT_21_SESSION_CADENCE_TO_FROZEN_PATH_END",
        "cadence_sessions": 21,
        "locked_risk_thresholds": LOCKED_RISK_THRESHOLDS,
        "checkpoint_write_boundary": "AFTER_COMPLETE_TRACK_CAPTURE",
        "candidate_set_or_weight_search_run": False,
        "threshold_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "cross_track_or_evaluator_ranking_allowed": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**payload, "plan_fingerprint": _canonical_sha256(payload)}


def _validate_prices(prices: pd.DataFrame, tickers: Sequence[str]) -> pd.DataFrame:
    frame = prices.copy()
    if (
        list(frame.columns) != list(tickers)
        or frame.empty
        or not isinstance(frame.index, pd.DatetimeIndex)
        or frame.index.tz is not None
        or not frame.index.equals(frame.index.normalize())
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "whole-lot price path coordinate changed"
        )
    frame.index = frame.index.normalize()
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "whole-lot price path coordinate changed"
        )
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "whole-lot price path contains invalid values"
        )
    return frame


def _validate_equal_weight_schedule(
    prices: pd.DataFrame,
    schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    tickers: Sequence[str],
    *,
    cadence_sessions: int,
) -> list[tuple[pd.Timestamp, dict[str, float]]]:
    if cadence_sessions != 21:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "only the frozen 21-session cadence is allowed"
        )
    target = 1.0 / len(tickers)
    positions = {day: index for index, day in enumerate(prices.index)}
    result = []
    for raw_day, raw_weights in schedule:
        day = pd.Timestamp(raw_day)
        if day.tz is not None or day != day.normalize():
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "stored schedule date is not a canonical daily coordinate"
            )
        day = day.normalize()
        weights = {str(ticker): _finite(value, "schedule weight") for ticker, value in raw_weights.items()}
        if (
            list(weights) != list(tickers)
            or day not in positions
            or any(
                not math.isclose(weights[ticker], target, rel_tol=0.0, abs_tol=1e-12)
                for ticker in tickers
            )
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "stored schedule is not the locked equal-weight schedule"
            )
        result.append((day, weights))
    if not result:
        raise NdxEqualWeightScheduleExtensionRunnerError("stored schedule is empty")
    indexes = [positions[day] for day, _ in result]
    if indexes != sorted(set(indexes)) or any(
        right - left != cadence_sessions for left, right in zip(indexes, indexes[1:])
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "stored schedule cadence changed"
        )
    return result


def extend_equal_weight_schedule_to_path_end(
    prices: pd.DataFrame,
    original_schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    tickers: Sequence[str],
    cadence_sessions: int = 21,
) -> list[tuple[pd.Timestamp, dict[str, float]]]:
    """Continue the same equal-weight cadence without a price/risk trigger."""

    frame = _validate_prices(prices, tickers)
    schedule = _validate_equal_weight_schedule(
        frame, original_schedule, tickers, cadence_sessions=cadence_sessions
    )
    positions = {day: index for index, day in enumerate(frame.index)}
    target = {ticker: 1.0 / len(tickers) for ticker in tickers}
    next_position = positions[schedule[-1][0]] + cadence_sessions
    while next_position < len(frame.index):
        schedule.append((frame.index[next_position], target.copy()))
        next_position += cadence_sessions
    return schedule


def _parse_ledger_shares(value: Any, tickers: Sequence[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in str(value or "").split(";"):
        ticker, separator, raw = item.partition(":")
        number = _finite(raw, "ledger shares") if separator else -1.0
        if (
            not separator
            or ticker in result
            or not number.is_integer()
            or number < 0
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "whole-lot ledger shares are invalid"
            )
        result[ticker] = int(number)
    if list(result) != list(tickers):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "whole-lot ledger ticker order changed"
        )
    return result


def _daily_risk_audit(
    prices: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    tickers: Sequence[str],
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    ledger_by_day = {
        pd.Timestamp(row["rebalance_date"]).normalize(): row
        for row in ledger.to_dict("records")
    }
    if len(ledger_by_day) != len(ledger):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "whole-lot ledger dates are duplicated"
        )
    shares = {ticker: 0 for ticker in tickers}
    cash = _finite(portfolio_cash_usd, "portfolio cash")
    values = []
    failures = []
    reason_counts: Counter[str] = Counter()
    zero_share_dates = []
    for raw_day, marks in prices.iterrows():
        day = pd.Timestamp(raw_day).normalize()
        if day in ledger_by_day:
            row = ledger_by_day[day]
            shares = _parse_ledger_shares(row["shares"], tickers)
            cash = _finite(row["posttrade_cash_usd"], "posttrade cash")
        notionals = {ticker: shares[ticker] * float(marks[ticker]) for ticker in tickers}
        invested = sum(notionals.values())
        if invested <= 0:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "whole-lot daily invested value is nonpositive"
            )
        weights = {ticker: notionals[ticker] / invested for ticker in tickers}
        ordered = sorted(weights.values(), reverse=True)
        effective_n = 1.0 / sum(value * value for value in ordered)
        chain_weights: dict[str, float] = {}
        for ticker, weight in weights.items():
            chain = str(risk_chain_by_ticker.get(ticker) or "")
            if not chain:
                raise NdxEqualWeightScheduleExtensionRunnerError(
                    "risk-chain evidence is missing"
                )
            chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
        checks = {
            "MAX_SINGLE_WEIGHT": ordered[0] <= max_single_weight + 1e-9,
            "MIN_SINGLE_WEIGHT": ordered[-1] >= min_single_weight - 1e-9,
            "SECURITY_TOP3_WEIGHT": sum(ordered[:3]) <= top_weight_cap + 1e-9,
            "MINIMUM_EFFECTIVE_N": effective_n
            >= minimum_effective_n_ratio * len(tickers) - 1e-9,
            "RISK_CHAIN_TOP1_WEIGHT": max(chain_weights.values())
            <= risk_chain_top1_cap + 1e-9,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if any(quantity == 0 for quantity in shares.values()):
            failed.append("ZERO_SHARE")
            zero_share_dates.append(day.date().isoformat())
        if cash < 0:
            failed.append("NEGATIVE_CASH")
        if failed:
            reason_counts.update(failed)
            failures.append(
                {
                    "session_date": day.date().isoformat(),
                    "failure_reasons": failed,
                    "top1_weight": ordered[0],
                    "minimum_single_weight": ordered[-1],
                    "top3_weight": sum(ordered[:3]),
                    "effective_n": effective_n,
                    "risk_chain_top1_weight": max(chain_weights.values()),
                    "cash_usd": cash,
                }
            )
        values.append(cash + invested)
    series = pd.Series(values, index=prices.index, dtype=float)
    legacy_drawdown = float((1.0 - series / series.cummax()).max())
    with_initial = pd.Series([portfolio_cash_usd, *values], dtype=float)
    corrected_drawdown = float((1.0 - with_initial / with_initial.cummax()).max())
    return {
        "session_count": len(series),
        "failure_session_count": len(failures),
        "failure_reason_counts": dict(sorted(reason_counts.items())),
        "failure_sessions": failures,
        "zero_share_session_count": len(zero_share_dates),
        "legacy_drawdown_without_initial_capital_peak": legacy_drawdown,
        "corrected_drawdown_with_initial_capital_peak": corrected_drawdown,
        "first_session_value_after_trade_and_fees_usd": float(series.iloc[0]),
        "terminal_value_usd": float(series.iloc[-1]),
    }


def _compare_original_summary(
    actual: Mapping[str, Any], expected: Mapping[str, Any]
) -> None:
    if set(expected) != set(ORIGINAL_SUMMARY_FIELDS):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "stored 13-field whole-lot summary is incomplete"
        )
    for field in ORIGINAL_SUMMARY_FIELDS:
        left = actual.get(field)
        right = expected[field]
        if isinstance(left, bool):
            matches = left is right
        elif isinstance(left, (float, int)) and not isinstance(left, bool):
            matches = math.isclose(
                float(left), _finite(right, field), rel_tol=1e-12, abs_tol=1e-10
            )
        else:
            matches = str(left) == str(right)
        if not matches:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                f"stored whole-lot summary was not reproduced: {field}"
            )


def diagnose_locked_equal_weight_candidate(
    prices: pd.DataFrame,
    original_schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    candidate: Mapping[str, Any],
    execution_contract: Mapping[str, Any],
    cadence_sessions: int = 21,
) -> dict[str, Any]:
    """Reproduce B first, then evaluate the sole allowed schedule extension A."""

    tickers = list(candidate["tickers"])
    if len(tickers) != int(candidate["holding_count"]):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "candidate dynamic-k identity is inconsistent"
        )
    frame = _validate_prices(prices, tickers)
    schedule = _validate_equal_weight_schedule(
        frame, original_schedule, tickers, cadence_sessions=cadence_sessions
    )
    contract_keys = {
        "risk_chain_by_ticker", "portfolio_cash_usd", "minimum_cash_buffer_usd",
        "transaction_cost_bps", "max_single_weight", "min_single_weight",
        "top_weight_cap", "minimum_effective_n_ratio", "risk_chain_top1_cap",
    }
    if set(execution_contract) != contract_keys:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "execution contract fields changed"
        )
    risk_chains = execution_contract["risk_chain_by_ticker"]
    if not isinstance(risk_chains, Mapping) or list(risk_chains) != tickers:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "candidate risk-chain mapping changed"
        )
    kwargs = {
        "risk_chain_by_ticker": dict(risk_chains),
        **{
            key: _finite(execution_contract[key], key)
            for key in contract_keys
            if key != "risk_chain_by_ticker"
        },
    }
    if (
        not math.isclose(kwargs["portfolio_cash_usd"], 25_000.0, abs_tol=1e-9)
        or not math.isclose(kwargs["minimum_cash_buffer_usd"], 100.0, abs_tol=1e-9)
        or not math.isclose(kwargs["transaction_cost_bps"], 10.0, abs_tol=1e-12)
        or any(
            not math.isclose(
                kwargs[field], expected, rel_tol=0.0, abs_tol=1e-12
            )
            for field, expected in LOCKED_RISK_THRESHOLDS.items()
        )
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "capital/cash-buffer/cost/risk-threshold contract changed"
        )
    original_summary, original_ledger = simulate_continuous_whole_lot_rebalance(
        frame, schedule, **kwargs
    )
    _compare_original_summary(
        original_summary, candidate["expected_original_summary"]
    )
    original_audit = _daily_risk_audit(
        frame,
        original_ledger,
        tickers=tickers,
        risk_chain_by_ticker=kwargs["risk_chain_by_ticker"],
        portfolio_cash_usd=kwargs["portfolio_cash_usd"],
        max_single_weight=kwargs["max_single_weight"],
        min_single_weight=kwargs["min_single_weight"],
        top_weight_cap=kwargs["top_weight_cap"],
        minimum_effective_n_ratio=kwargs["minimum_effective_n_ratio"],
        risk_chain_top1_cap=kwargs["risk_chain_top1_cap"],
    )
    extended = extend_equal_weight_schedule_to_path_end(
        frame,
        schedule,
        tickers=tickers,
        cadence_sessions=cadence_sessions,
    )
    continued_summary, continued_ledger = simulate_continuous_whole_lot_rebalance(
        frame, extended, **kwargs
    )
    continued_audit = _daily_risk_audit(
        frame,
        continued_ledger,
        tickers=tickers,
        risk_chain_by_ticker=kwargs["risk_chain_by_ticker"],
        portfolio_cash_usd=kwargs["portfolio_cash_usd"],
        max_single_weight=kwargs["max_single_weight"],
        min_single_weight=kwargs["min_single_weight"],
        top_weight_cap=kwargs["top_weight_cap"],
        minimum_effective_n_ratio=kwargs["minimum_effective_n_ratio"],
        risk_chain_top1_cap=kwargs["risk_chain_top1_cap"],
    )
    for summary in (original_summary, continued_summary):
        expected_fee = (
            summary["whole_lot_total_trade_notional_usd"]
            * kwargs["transaction_cost_bps"]
            / 10_000.0
        )
        if not math.isclose(
            summary["whole_lot_total_transaction_cost_usd"],
            expected_fee,
            rel_tol=1e-12,
            abs_tol=1e-8,
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "whole-lot fee relation changed"
            )
    original_return = float(original_summary["whole_lot_path_return_net"])
    continued_return = float(continued_summary["whole_lot_path_return_net"])
    original_dd = float(original_summary["whole_lot_path_max_drawdown"])
    continued_dd = float(continued_summary["whole_lot_path_max_drawdown"])
    return {
        "candidate_key": candidate["candidate_key"],
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "source_coordinate": {
            key: candidate[key]
            for key in (
                "source_batch", "job_search_class", "evaluation_semantics_sha256",
                "universe_track", "selection_date",
            )
        },
        "portfolio_id": candidate["portfolio_id"],
        "holding_count": candidate["holding_count"],
        "tickers": tickers,
        "weights": dict(candidate["weights"]),
        "security_ids": list(candidate["security_ids"]),
        "source_failure_class": candidate["source_failure_class"],
        "source_failure_reasons": list(candidate["source_failure_reasons"]),
        "stored_identity_weights_trace_and_13_summary_reproduced_before_a": True,
        "original_schedule_b": {
            "schedule_dates": [day.date().isoformat() for day, _ in schedule],
            "summary": original_summary,
            "daily_risk_audit": original_audit,
        },
        "continued_schedule_a": {
            "mechanism": "CONTINUE_EQUAL_WEIGHT_21_SESSION_CADENCE_TO_PATH_END",
            "schedule_dates": [day.date().isoformat() for day, _ in extended],
            "added_rebalance_dates": [
                day.date().isoformat() for day, _ in extended[len(schedule):]
            ],
            "summary": continued_summary,
            "daily_risk_audit": continued_audit,
        },
        "ab_comparison": {
            "cumulative_path_return_change": continued_return - original_return,
            "legacy_path_max_drawdown_change": continued_dd - original_dd,
            "corrected_path_max_drawdown_change": (
                continued_audit["corrected_drawdown_with_initial_capital_peak"]
                - original_audit["corrected_drawdown_with_initial_capital_peak"]
            ),
            "transaction_cost_usd_change": (
                continued_summary["whole_lot_total_transaction_cost_usd"]
                - original_summary["whole_lot_total_transaction_cost_usd"]
            ),
            "risk_failure_session_change": (
                continued_audit["failure_session_count"]
                - original_audit["failure_session_count"]
            ),
            "a_nonworse_return_and_legacy_drawdown": bool(
                continued_return >= original_return - 1e-12
                and continued_dd <= original_dd + 1e-12
            ),
            "a_nonworse_return_and_corrected_drawdown": bool(
                continued_return >= original_return - 1e-12
                and continued_audit["corrected_drawdown_with_initial_capital_peak"]
                <= original_audit["corrected_drawdown_with_initial_capital_peak"]
                + 1e-12
            ),
            "a_strictly_improves_return_or_drawdown": bool(
                continued_return > original_return + 1e-12
                or continued_dd < original_dd - 1e-12
            ),
            "a_removes_all_observed_daily_risk_failures": bool(
                original_audit["failure_session_count"] > 0
                and continued_audit["failure_session_count"] == 0
            ),
            "ranking_score_computed": False,
        },
        "candidate_set_or_weight_search_run": False,
        "threshold_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def serialize_replay_capture(
    prices: pd.DataFrame,
    schedule: Sequence[tuple[pd.Timestamp, Mapping[str, float]]],
    execution_contract: Mapping[str, Any],
) -> dict[str, Any]:
    tickers = list(prices.columns)
    frame = _validate_prices(prices, tickers)
    schedule_rows = _validate_equal_weight_schedule(
        frame, schedule, tickers, cadence_sessions=21
    )
    return {
        "schema_version": 1,
        "capture_type": "ndx_equal_weight_schedule_extension_replay_input",
        "tickers": tickers,
        "price_rows": [
            {
                "session_date": pd.Timestamp(day).date().isoformat(),
                "closes": {ticker: float(row[ticker]) for ticker in tickers},
            }
            for day, row in frame.iterrows()
        ],
        "original_schedule": [
            {
                "session_date": pd.Timestamp(day).date().isoformat(),
                "weights": {ticker: float(weights[ticker]) for ticker in tickers},
            }
            for day, weights in schedule_rows
        ],
        "execution_contract": {
            "risk_chain_by_ticker": dict(execution_contract["risk_chain_by_ticker"]),
            **{
                key: float(execution_contract[key])
                for key in (
                    "portfolio_cash_usd", "minimum_cash_buffer_usd",
                    "transaction_cost_bps", "max_single_weight", "min_single_weight",
                    "top_weight_cap", "minimum_effective_n_ratio", "risk_chain_top1_cap",
                )
            },
        },
        "price_source_role": "UNADJUSTED_NOMINAL_HISTORICAL_CLOSE_EXECUTION_ONLY",
    }


def rebuild_result_from_capture(
    capture: Mapping[str, Any], candidate: Mapping[str, Any]
) -> dict[str, Any]:
    expected_keys = {
        "schema_version", "capture_type", "tickers", "price_rows",
        "original_schedule", "execution_contract", "price_source_role",
    }
    tickers = list(candidate["tickers"])
    if (
        set(capture) != expected_keys
        or capture.get("schema_version") != 1
        or capture.get("capture_type")
        != "ndx_equal_weight_schedule_extension_replay_input"
        or capture.get("price_source_role")
        != "UNADJUSTED_NOMINAL_HISTORICAL_CLOSE_EXECUTION_ONLY"
        or capture.get("tickers") != tickers
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "sealed replay capture schema changed"
        )
    raw_prices = capture.get("price_rows")
    raw_schedule = capture.get("original_schedule")
    if not isinstance(raw_prices, list) or not raw_prices or not isinstance(
        raw_schedule, list
    ) or not raw_schedule:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "sealed replay capture is incomplete"
        )
    dates = []
    values = []
    for row in raw_prices:
        if not isinstance(row, Mapping) or set(row) != {"session_date", "closes"}:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed price row changed"
            )
        closes = row["closes"]
        if not isinstance(closes, Mapping) or list(closes) != tickers:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed price columns changed"
            )
        raw_session_date = str(row["session_date"])
        try:
            parsed_date = date.fromisoformat(raw_session_date)
        except ValueError as exc:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed price date is not canonical YYYY-MM-DD"
            ) from exc
        if parsed_date.isoformat() != raw_session_date:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed price date is not canonical YYYY-MM-DD"
            )
        dates.append(pd.Timestamp(parsed_date))
        values.append([_finite(closes[ticker], "sealed close") for ticker in tickers])
    prices = pd.DataFrame(values, index=dates, columns=tickers)
    schedule = []
    for row in raw_schedule:
        if not isinstance(row, Mapping) or set(row) != {"session_date", "weights"}:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed schedule row changed"
            )
        weights = row["weights"]
        if not isinstance(weights, Mapping) or list(weights) != tickers:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed schedule weights changed"
            )
        raw_session_date = str(row["session_date"])
        try:
            parsed_date = date.fromisoformat(raw_session_date)
        except ValueError as exc:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed schedule date is not canonical YYYY-MM-DD"
            ) from exc
        if parsed_date.isoformat() != raw_session_date:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "sealed schedule date is not canonical YYYY-MM-DD"
            )
        schedule.append(
            (
                pd.Timestamp(parsed_date),
                {ticker: _finite(weights[ticker], "sealed weight") for ticker in tickers},
            )
        )
    return diagnose_locked_equal_weight_candidate(
        prices,
        schedule,
        candidate=candidate,
        execution_contract=capture["execution_contract"],
        cadence_sessions=21,
    )


def _parse_result_candidate(
    row: Mapping[str, Any], source: Mapping[str, Any]
) -> None:
    tickers = list(source["tickers"])
    if str(row.get("portfolio_id") or "") != source["portfolio_id"]:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "replayed portfolio ID changed"
        )
    for column, expected in (
        ("tickers", ";".join(tickers)),
        ("security_ids", ";".join(source["security_ids"])),
        ("issuer_ids", ";".join(source["issuer_ids"])),
        ("risk_chains", ";".join(source["risk_chains"])),
        ("weight_spec", "equal_weight"),
    ):
        if str(row.get(column) or "") != expected:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                f"replayed {column} changed"
            )
    raw_weights: dict[str, float] = {}
    for item in str(row.get("weights") or "").split(";"):
        ticker, separator, value = item.partition(":")
        if not separator or ticker in raw_weights:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "replayed weights are malformed"
            )
        raw_weights[ticker] = _finite(value, "replayed weight")
    if list(raw_weights) != tickers or any(
        not math.isclose(
            raw_weights[ticker], source["weights"][ticker], rel_tol=0.0, abs_tol=1e-10
        )
        for ticker in tickers
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "replayed equal weights changed"
        )


def capture_track_batch(
    group: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], *, root: Path
) -> dict[str, dict[str, Any]]:
    """Load one track/date once and capture each locked candidate's old replay."""

    if not candidates:
        return {}
    expected_keys = {candidate["candidate_key"] for candidate in candidates}
    if len(expected_keys) != len(candidates):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "batch contains duplicate candidate keys"
        )
    source_run_path = Path(group["source_runner_manifest"]["path"])
    source_run_raw = source_run_path.read_bytes()
    if _sha256(source_run_raw) != group["source_runner_manifest"]["sha256"]:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "source runner manifest changed before batch load"
        )
    source_run = json.loads(source_run_raw.decode("utf-8"))
    source_inputs = source_run["inputs"]
    contract = source_run["run_contract"]
    captures: list[tuple[dict[str, Any], pd.DataFrame, list[Any], dict[str, Any]]] = []
    original_simulator = discovery.simulate_continuous_whole_lot_rebalance

    def capture(prices: pd.DataFrame, schedule: Iterable[Any], **kwargs: Any):
        schedule_rows = list(schedule)
        summary, ledger = original_simulator(prices, schedule_rows, **kwargs)
        captures.append((summary, prices.copy(), schedule_rows, dict(kwargs)))
        return summary, ledger

    protected = [
        root / "config/config.yaml", root / "data/state.json",
        root / "data/broker_positions.json",
    ]
    protected_before = {
        path.as_posix(): _sha256(path.read_bytes()) for path in protected if path.is_file()
    }
    caught: BaseException | None = None
    output_rows: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            batch_path = temporary / "locked_candidates.csv"
            with batch_path.open("x", encoding="utf-8", newline="") as handle:
                fields = [
                    "source_batch", "universe_track", "selection_date",
                    "holding_count", "tickers", "weight_spec",
                ]
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for candidate in candidates:
                    writer.writerow(
                        {
                            "source_batch": SOURCE_BATCH,
                            "universe_track": group["universe_track"],
                            "selection_date": SELECTION_DATE,
                            "holding_count": candidate["holding_count"],
                            "tickers": ";".join(candidate["tickers"]),
                            "weight_spec": "equal_weight",
                        }
                    )
            output = temporary / "smoke_output"
            args = argparse.Namespace(
                track=group["universe_track"], selection_date=SELECTION_DATE,
                holding_count=0, candidate_sets_file=str(batch_path),
                source_batch=SOURCE_BATCH, portfolio_cash_usd=25_000.0,
                spec=str((source_inputs.get("spec") or {}).get("path")),
                input_readiness_manifest=str(
                    (source_inputs.get("readiness_manifest") or {}).get("path")
                ),
                discovery_manifest=str(
                    (source_inputs.get("discovery_manifest") or {}).get("path")
                ),
                security_lifecycle=str(
                    (source_inputs.get("security_lifecycle") or {}).get("path")
                ),
                execution_price_manifest=str(
                    (source_inputs.get("execution_price_manifest") or {}).get("path")
                ),
                return_cache_dir="data/cache", target_nav="data/cache/funds/012922.csv",
                state="data/state.json", config="config/config.yaml",
                output_dir=str(output),
                minimum_price_rows_before_selection=int(
                    contract["minimum_price_rows_before_selection"]
                ),
                training_lookback_days=int(contract["training_lookback_days"]),
                fit_days=int(contract["fit_days"]), window_days=int(contract["window_days"]),
                step_days=int(contract["step_days"]), beam_width=int(contract["beam_width"]),
                transaction_cost_bps=float(contract["transaction_cost_bps"]),
                search_method=str(contract["search_method"]),
            )
            discovery.simulate_continuous_whole_lot_rebalance = capture
            real_smoke.run(args)
            with (output / "training_candidates.csv").open(
                "r", encoding="utf-8-sig", newline=""
            ) as handle:
                output_rows = list(csv.DictReader(handle))
    except BaseException as exc:
        caught = exc
    finally:
        discovery.simulate_continuous_whole_lot_rebalance = original_simulator
    protected_after = {
        path.as_posix(): _sha256(path.read_bytes()) for path in protected if path.is_file()
    }
    if protected_before != protected_after:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "batch replay changed a protected file"
        ) from caught
    if caught is not None:
        raise caught
    if len(captures) != len(candidates) or len(output_rows) != len(candidates):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "batch replay candidate count changed"
        )
    source_by_tickers = {tuple(item["tickers"]): item for item in candidates}
    if len(source_by_tickers) != len(candidates):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "batch replay ticker sets are duplicated"
        )
    output_by_tickers: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for row in output_rows:
        key = tuple(item for item in str(row.get("tickers") or "").split(";") if item)
        if key in output_by_tickers:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "batch replay output ticker set is duplicated"
            )
        output_by_tickers[key] = row
    captured_by_tickers = {
        tuple(prices.columns): (summary, prices, schedule, kwargs)
        for summary, prices, schedule, kwargs in captures
    }
    if set(source_by_tickers) != set(output_by_tickers) or set(source_by_tickers) != set(
        captured_by_tickers
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "batch replay output/capture identity changed"
        )
    result: dict[str, dict[str, Any]] = {}
    for tickers, candidate in source_by_tickers.items():
        _parse_result_candidate(output_by_tickers[tickers], candidate)
        old_summary, prices, schedule, kwargs = captured_by_tickers[tickers]
        _compare_original_summary(old_summary, candidate["expected_original_summary"])
        expected_chains = {
            ticker: chain for ticker, chain in zip(tickers, candidate["risk_chains"])
        }
        raw_chains = kwargs.get("risk_chain_by_ticker")
        if not isinstance(raw_chains, Mapping) or any(
            str(raw_chains.get(ticker) or "") != expected_chains[ticker]
            for ticker in tickers
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "replayed risk-chain mapping changed"
            )
        normalized_contract = {
            **kwargs,
            "risk_chain_by_ticker": expected_chains,
        }
        capture_payload = serialize_replay_capture(
            prices, schedule, normalized_contract
        )
        rebuilt = rebuild_result_from_capture(capture_payload, candidate)
        result[candidate["candidate_key"]] = {
            "capture": capture_payload,
            "result": rebuilt,
        }
    return result


def _checkpoint_payload(
    *, plan_fingerprint: str, candidate: Mapping[str, Any], captured: Mapping[str, Any]
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "checkpoint_type": "ndx_equal_weight_schedule_extension_candidate",
        "status": "COMPLETED",
        "plan_fingerprint": plan_fingerprint,
        "candidate_key": candidate["candidate_key"],
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "capture": captured["capture"],
        "result": captured["result"],
        "candidate_set_or_weight_search_run": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**payload, "checkpoint_sha256": _canonical_sha256(payload)}


def verify_candidate_checkpoint(
    checkpoint_path: str | Path,
    *,
    plan_fingerprint: str,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(checkpoint_path).resolve()
    try:
        raw = path.read_bytes()
        checkpoint = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "cannot read candidate checkpoint"
        ) from exc
    payload = dict(checkpoint)
    claimed = payload.pop("checkpoint_sha256", None)
    expected_keys = {
        "schema_version", "checkpoint_type", "status", "plan_fingerprint",
        "candidate_key", "candidate_identity_sha256", "capture", "result",
        "candidate_set_or_weight_search_run", "promotion_allowed",
        "live_mutation_allowed", "order_creation_allowed", "checkpoint_sha256",
    }
    if (
        set(checkpoint) != expected_keys
        or claimed != _canonical_sha256(payload)
        or checkpoint.get("schema_version") != 1
        or checkpoint.get("checkpoint_type")
        != "ndx_equal_weight_schedule_extension_candidate"
        or checkpoint.get("status") != "COMPLETED"
        or checkpoint.get("plan_fingerprint") != plan_fingerprint
        or checkpoint.get("candidate_key") != candidate["candidate_key"]
        or checkpoint.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or checkpoint.get("candidate_set_or_weight_search_run") is not False
        or checkpoint.get("promotion_allowed") is not False
        or checkpoint.get("live_mutation_allowed") is not False
        or checkpoint.get("order_creation_allowed") is not False
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "candidate checkpoint contract changed"
        )
    rebuilt = rebuild_result_from_capture(checkpoint["capture"], candidate)
    if rebuilt != checkpoint["result"]:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "candidate checkpoint result does not rebuild"
        )
    return checkpoint


def _verify_checkpoint_against_recapture(
    checkpoint_path: Path,
    *,
    plan_fingerprint: str,
    candidate: Mapping[str, Any],
    recaptured: Mapping[str, Any],
) -> dict[str, Any]:
    """Upgrade sealed-math verification with a fresh canonical source replay."""

    checkpoint = verify_candidate_checkpoint(
        checkpoint_path,
        plan_fingerprint=plan_fingerprint,
        candidate=candidate,
    )
    if (
        checkpoint["capture"] != recaptured.get("capture")
        or checkpoint["result"] != recaptured.get("result")
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "candidate checkpoint does not match a fresh canonical source replay"
        )
    return checkpoint


def _recapture_and_verify_checkpoints(
    plan: Mapping[str, Any],
    *,
    run_dir: Path,
    candidates: Sequence[Mapping[str, Any]],
    batch_loader: BatchLoader,
    source_revalidator: Callable[[], Mapping[str, Any]],
) -> int:
    """Recapture existing checkpoints once per track before canonical reuse."""

    requested = {candidate["candidate_key"]: candidate for candidate in candidates}
    track_loads = 0
    for group in plan["groups"]:
        batch = [
            candidate
            for candidate in group["candidates"]
            if candidate["candidate_key"] in requested
        ]
        if not batch:
            continue
        if source_revalidator() != plan:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked source changed before checkpoint recapture"
            )
        recaptured = batch_loader(
            {**group, "source_runner_manifest": plan["source_runner_manifest"]},
            batch,
        )
        track_loads += 1
        if source_revalidator() != plan:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked source changed during checkpoint recapture"
            )
        if set(recaptured) != {candidate["candidate_key"] for candidate in batch}:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "checkpoint recapture did not return every requested candidate"
            )
        for candidate in batch:
            _verify_checkpoint_against_recapture(
                _checkpoint_path(run_dir, candidate),
                plan_fingerprint=plan["plan_fingerprint"],
                candidate=candidate,
                recaptured=recaptured[candidate["candidate_key"]],
            )
    return track_loads


def write_candidate_checkpoint(
    checkpoint_path: str | Path,
    *,
    plan_fingerprint: str,
    candidate: Mapping[str, Any],
    captured: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(checkpoint_path).resolve()
    checkpoint = _checkpoint_payload(
        plan_fingerprint=plan_fingerprint, candidate=candidate, captured=captured
    )
    raw = _json_bytes(checkpoint)
    if path.exists():
        if path.read_bytes() != raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "immutable candidate checkpoint collision"
            )
    else:
        _atomic_write(path, raw)
    verify_candidate_checkpoint(
        path, plan_fingerprint=plan_fingerprint, candidate=candidate
    )
    return checkpoint


BatchLoader = Callable[
    [Mapping[str, Any], Sequence[Mapping[str, Any]]],
    dict[str, dict[str, Any]],
]


def _validate_plan_boundary(plan: Mapping[str, Any]) -> None:
    payload = dict(plan)
    fingerprint = payload.pop("plan_fingerprint", None)
    if (
        fingerprint != _canonical_sha256(payload)
        or plan.get("schema_version") != 1
        or plan.get("plan_type") != "ndx_equal_weight_schedule_extension_locked_plan"
        or plan.get("status") != "LOCKED_HISTORICAL_REPLAY_PLAN"
        or plan.get("research_track")
        != "portfolio_optimization_execution_diagnostic"
        or plan.get("migration_control_included") is not False
        or plan.get("selection_date") != SELECTION_DATE
        or plan.get("job_search_class") != JOB_SEARCH_CLASS
        or plan.get("evaluation_semantics_sha256") != EVALUATOR_SHA256
        or plan.get("track_load_count_clean_full_run") != 2
        or plan.get("counts") != EXPECTED_TOTALS
        or plan.get("cadence_sessions") != 21
        or plan.get("locked_risk_thresholds") != LOCKED_RISK_THRESHOLDS
        or plan.get("checkpoint_write_boundary") != "AFTER_COMPLETE_TRACK_CAPTURE"
        or plan.get("candidate_set_or_weight_search_run") is not False
        or plan.get("threshold_changed") is not False
        or plan.get("portfolio_cash_changed") is not False
        or plan.get("transaction_cost_changed") is not False
        or plan.get("cross_track_or_evaluator_ranking_allowed") is not False
        or any(
            plan.get(key) is not False
            for key in (
                "fresh_oos_consumed", "admission_claimed", "promotion_allowed",
                "live_mutation_allowed", "order_creation_allowed",
            )
        )
    ):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "locked replay plan boundary changed"
        )
    groups = plan.get("groups")
    if not isinstance(groups, list) or len(groups) != 2:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "locked replay plan track groups changed"
        )
    if {group.get("universe_track") for group in groups} != set(TRACK_EXPECTED_COUNTS):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "locked replay plan track identities changed"
        )
    all_candidates = []
    for group in groups:
        track = group["universe_track"]
        if (
            group.get("source_batch") != SOURCE_BATCH
            or group.get("job_search_class") != JOB_SEARCH_CLASS
            or group.get("evaluation_semantics_sha256") != EVALUATOR_SHA256
            or group.get("selection_date") != SELECTION_DATE
            or group.get("counts") != TRACK_EXPECTED_COUNTS[track]
            or not isinstance(group.get("candidates"), list)
        ):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked replay plan group changed"
            )
        _validate_scope_counts(group["candidates"], TRACK_EXPECTED_COUNTS[track])
        all_candidates.extend(group["candidates"])
    _validate_scope_counts(all_candidates, EXPECTED_TOTALS)
    keys = [candidate["candidate_key"] for candidate in all_candidates]
    if len(set(keys)) != len(keys):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "locked replay plan candidate keys are duplicated"
        )


def _checkpoint_path(run_dir: Path, candidate: Mapping[str, Any]) -> Path:
    track = str(candidate["universe_track"])
    if track not in TRACK_EXPECTED_COUNTS:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "checkpoint track is not canonical"
        )
    key = str(candidate["candidate_key"])
    if len(key) != 24 or any(character not in "0123456789abcdef" for character in key):
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "checkpoint candidate key is invalid"
        )
    return run_dir / "checkpoints" / track / f"{key}.json"


def _result_summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    transitions = Counter()
    for result in results:
        before = result["original_schedule_b"]["daily_risk_audit"][
            "failure_session_count"
        ]
        after = result["continued_schedule_a"]["daily_risk_audit"][
            "failure_session_count"
        ]
        if before > 0 and after == 0:
            transitions["FAIL_TO_PASS"] += 1
        elif before == 0 and after == 0:
            transitions["PASS_TO_PASS"] += 1
        elif before == 0 and after > 0:
            transitions["PASS_TO_FAIL"] += 1
        else:
            transitions["FAIL_TO_FAIL"] += 1
    return {
        "candidate_rows": len(results),
        "source_reported_eligible_rows": sum(
            result["source_failure_class"] == "SOURCE_REPORTED_ELIGIBLE"
            for result in results
        ),
        "source_whole_lot_only_failure_rows": sum(
            result["source_failure_class"]
            == "WHOLE_LOT_EXECUTABILITY_FAILED_ONLY"
            for result in results
        ),
        "a_nonworse_return_and_corrected_drawdown_rows": sum(
            result["ab_comparison"]["a_nonworse_return_and_corrected_drawdown"]
            for result in results
        ),
        "a_removes_all_observed_daily_risk_failures_rows": sum(
            result["ab_comparison"]["a_removes_all_observed_daily_risk_failures"]
            for result in results
        ),
        "risk_status_transitions": {
            key: transitions[key]
            for key in ("FAIL_TO_PASS", "PASS_TO_PASS", "PASS_TO_FAIL", "FAIL_TO_FAIL")
        },
        "ranking_or_winner_selected": False,
    }


def _write_run_state(
    run_dir: Path,
    *,
    plan: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    track_loads: int,
) -> dict[str, Any]:
    checkpoint_rows = []
    results = []
    for candidate in candidates:
        path = _checkpoint_path(run_dir, candidate)
        if path.is_file():
            checkpoint = verify_candidate_checkpoint(
                path,
                plan_fingerprint=plan["plan_fingerprint"],
                candidate=candidate,
            )
            results.append(checkpoint["result"])
            checkpoint_rows.append(
                {
                    "candidate_key": candidate["candidate_key"],
                    "universe_track": candidate["universe_track"],
                    "status": "COMPLETED",
                    "path": path.as_posix(),
                    "sha256": _sha256(path.read_bytes()),
                }
            )
        else:
            checkpoint_rows.append(
                {
                    "candidate_key": candidate["candidate_key"],
                    "universe_track": candidate["universe_track"],
                    "status": "NOT_COMPLETED",
                    "path": path.as_posix(),
                    "sha256": None,
                }
            )
    index_raw = _json_bytes(checkpoint_rows)
    _atomic_write(run_dir / "checkpoint_index.json", index_raw)
    complete = len(results) == len(candidates) and not failures
    results_descriptor = None
    if complete:
        ordered_results = sorted(
            results,
            key=lambda item: (item["source_coordinate"]["universe_track"], item["candidate_key"]),
        )
        result_payload = {
            "schema_version": 1,
            "result_type": "ndx_equal_weight_schedule_extension_full_ab_report",
            "status": "COMPLETE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "summary": _result_summary(ordered_results),
            "results": ordered_results,
            "cross_track_or_evaluator_ranking_performed": False,
            "candidate_set_or_weight_search_run": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        result_raw = _json_bytes(result_payload)
        result_path = run_dir / "results.json"
        if result_path.exists() and result_path.read_bytes() != result_raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "immutable full result collision"
            )
        if not result_path.exists():
            _atomic_write(result_path, result_raw)
        results_descriptor = {
            "path": result_path.as_posix(),
            "sha256": _sha256(result_raw),
            "rows": len(ordered_results),
        }
    manifest_payload = {
        "schema_version": 1,
        "manifest_type": "ndx_equal_weight_schedule_extension_runner",
        "status": "COMPLETE" if complete else "PARTIAL_OR_FAILED",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "migration_control_included": False,
        "plan_fingerprint": plan["plan_fingerprint"],
        "planned_candidate_rows": len(candidates),
        "completed_candidate_rows": len(results),
        "remaining_candidate_rows": len(candidates) - len(results),
        "failed_batch_count": len(failures),
        "failures": list(failures),
        "track_data_loads_this_invocation": track_loads,
        "checkpoint_index": {
            "path": (run_dir / "checkpoint_index.json").as_posix(),
            "sha256": _sha256(index_raw),
            "rows": len(checkpoint_rows),
        },
        "full_results": results_descriptor,
        "candidate_set_or_weight_search_run": False,
        "threshold_changed": False,
        "portfolio_cash_changed": False,
        "transaction_cost_changed": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    manifest = {
        **manifest_payload,
        "manifest_sha256": _canonical_sha256(manifest_payload),
    }
    _atomic_write(run_dir / "manifest.json", _json_bytes(manifest))
    return manifest


def _execute_plan_unlocked(
    plan: Mapping[str, Any],
    *,
    output_root: str | Path,
    resume: bool,
    fail_fast: bool,
    max_candidates: int | None,
    batch_loader: BatchLoader,
    source_revalidator: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    _validate_plan_boundary(plan)
    if max_candidates is not None and max_candidates <= 0:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "max_candidates must be positive"
        )
    output = Path(output_root).resolve()
    run_dir = output / "runs" / plan["plan_fingerprint"]
    plan_path = run_dir / "plan.json"
    plan_raw = _json_bytes(plan)
    if plan_path.exists():
        if not resume:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "run already exists; use resume"
            )
        if plan_path.read_bytes() != plan_raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked replay plan changed"
            )
    else:
        _atomic_write(plan_path, plan_raw)
    candidates = [
        candidate for group in plan["groups"] for candidate in group["candidates"]
    ]
    completed_candidates = [
        candidate
        for candidate in candidates
        if _checkpoint_path(run_dir, candidate).is_file()
    ]
    track_loads = 0
    if completed_candidates:
        track_loads += _recapture_and_verify_checkpoints(
            plan,
            run_dir=run_dir,
            candidates=completed_candidates,
            batch_loader=batch_loader,
            source_revalidator=source_revalidator,
        )
    completed_keys = {
        candidate["candidate_key"] for candidate in completed_candidates
    }
    pending = [
        candidate for candidate in candidates if candidate["candidate_key"] not in completed_keys
    ]
    if max_candidates is not None:
        pending = pending[:max_candidates]
    pending_keys = {candidate["candidate_key"] for candidate in pending}
    failures = []
    for group in plan["groups"]:
        batch = [
            candidate for candidate in group["candidates"]
            if candidate["candidate_key"] in pending_keys
        ]
        if not batch:
            continue
        before = source_revalidator()
        if before != plan:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "locked source changed before track batch"
            )
        try:
            captured = batch_loader(
                {**group, "source_runner_manifest": plan["source_runner_manifest"]},
                batch,
            )
            track_loads += 1
            after = source_revalidator()
            if after != plan:
                raise NdxEqualWeightScheduleExtensionRunnerError(
                    "locked source changed during track batch"
                )
            if set(captured) != {candidate["candidate_key"] for candidate in batch}:
                raise NdxEqualWeightScheduleExtensionRunnerError(
                    "track batch did not return every requested candidate"
                )
            for candidate in batch:
                write_candidate_checkpoint(
                    _checkpoint_path(run_dir, candidate),
                    plan_fingerprint=plan["plan_fingerprint"],
                    candidate=candidate,
                    captured=captured[candidate["candidate_key"]],
                )
        except Exception as exc:
            failures.append(
                {
                    "universe_track": group["universe_track"],
                    "candidate_rows": len(batch),
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
            if fail_fast:
                break
    return _write_run_state(
        run_dir,
        plan=plan,
        candidates=candidates,
        failures=failures,
        track_loads=track_loads,
    )


def _execute_plan(
    plan: Mapping[str, Any],
    *,
    output_root: str | Path,
    resume: bool,
    fail_fast: bool,
    max_candidates: int | None,
    batch_loader: BatchLoader,
    source_revalidator: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Serialize writers for one canonical output/fingerprint pair."""

    _validate_plan_boundary(plan)
    run_dir = Path(output_root).resolve() / "runs" / plan["plan_fingerprint"]
    with _single_instance_lock(run_dir / ".runner.lock"):
        return _execute_plan_unlocked(
            plan,
            output_root=output_root,
            resume=resume,
            fail_fast=fail_fast,
            max_candidates=max_candidates,
            batch_loader=batch_loader,
            source_revalidator=source_revalidator,
        )


def execute_locked_replay(
    *,
    repository_root: str | Path,
    output_root: str | Path,
    resume: bool = False,
    fail_fast: bool = False,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    """Canonical executor.  It never accepts a caller-supplied candidate plan."""

    root = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    try:
        output.relative_to(root / "data/cache/research")
    except ValueError as exc:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "output root is outside the research namespace"
        ) from exc
    plan = build_locked_replay_plan(repository_root=root)
    return _execute_plan(
        plan,
        output_root=output,
        resume=resume,
        fail_fast=fail_fast,
        max_candidates=max_candidates,
        batch_loader=lambda group, candidates: capture_track_batch(
            group, candidates, root=root
        ),
        source_revalidator=lambda: build_locked_replay_plan(repository_root=root),
    )


def verify_locked_replay_output(
    *,
    repository_root: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Rebuild the complete canonical output, including source recapture."""

    root = Path(repository_root).resolve()
    output = Path(output_root).resolve()
    try:
        output.relative_to(root / "data/cache/research")
    except ValueError as exc:
        raise NdxEqualWeightScheduleExtensionRunnerError(
            "output root is outside the research namespace"
        ) from exc
    plan = build_locked_replay_plan(repository_root=root)
    _validate_plan_boundary(plan)
    run_dir = output / "runs" / plan["plan_fingerprint"]
    with _single_instance_lock(run_dir / ".runner.lock"):
        plan_path = run_dir / "plan.json"
        if not plan_path.is_file() or plan_path.read_bytes() != _json_bytes(plan):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "canonical locked replay plan is missing or changed"
            )
        candidates = [
            candidate for group in plan["groups"] for candidate in group["candidates"]
        ]
        expected_checkpoint_paths = {
            _checkpoint_path(run_dir, candidate) for candidate in candidates
        }
        actual_checkpoint_paths = (
            set((run_dir / "checkpoints").rglob("*.json"))
            if (run_dir / "checkpoints").is_dir()
            else set()
        )
        if actual_checkpoint_paths != expected_checkpoint_paths:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "complete output does not contain exactly 323 canonical checkpoints"
            )
        batch_loader = lambda group, batch: capture_track_batch(
            group, batch, root=root
        )
        source_revalidator = lambda: build_locked_replay_plan(repository_root=root)
        recapture_loads = _recapture_and_verify_checkpoints(
            plan,
            run_dir=run_dir,
            candidates=candidates,
            batch_loader=batch_loader,
            source_revalidator=source_revalidator,
        )
        checkpoints = [
            verify_candidate_checkpoint(
                _checkpoint_path(run_dir, candidate),
                plan_fingerprint=plan["plan_fingerprint"],
                candidate=candidate,
            )
            for candidate in candidates
        ]
        checkpoint_rows = [
            {
                "candidate_key": candidate["candidate_key"],
                "universe_track": candidate["universe_track"],
                "status": "COMPLETED",
                "path": _checkpoint_path(run_dir, candidate).as_posix(),
                "sha256": _sha256(
                    _checkpoint_path(run_dir, candidate).read_bytes()
                ),
            }
            for candidate in candidates
        ]
        index_raw = _json_bytes(checkpoint_rows)
        index_path = run_dir / "checkpoint_index.json"
        if not index_path.is_file() or index_path.read_bytes() != index_raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "checkpoint index does not rebuild from canonical checkpoints"
            )
        ordered_results = sorted(
            (checkpoint["result"] for checkpoint in checkpoints),
            key=lambda item: (
                item["source_coordinate"]["universe_track"],
                item["candidate_key"],
            ),
        )
        result_payload = {
            "schema_version": 1,
            "result_type": "ndx_equal_weight_schedule_extension_full_ab_report",
            "status": "COMPLETE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "summary": _result_summary(ordered_results),
            "results": ordered_results,
            "cross_track_or_evaluator_ranking_performed": False,
            "candidate_set_or_weight_search_run": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        result_raw = _json_bytes(result_payload)
        result_path = run_dir / "results.json"
        if not result_path.is_file() or result_path.read_bytes() != result_raw:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "full result does not rebuild from canonical checkpoints"
            )
        manifest_path = run_dir / "manifest.json"
        try:
            manifest_raw = manifest_path.read_bytes()
            manifest = json.loads(manifest_raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "cannot read complete runner manifest"
            ) from exc
        track_loads = manifest.get("track_data_loads_this_invocation")
        if type(track_loads) is not int or track_loads < 0:
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "runner manifest track-load evidence is invalid"
            )
        manifest_payload = {
            "schema_version": 1,
            "manifest_type": "ndx_equal_weight_schedule_extension_runner",
            "status": "COMPLETE",
            "research_track": "portfolio_optimization_execution_diagnostic",
            "migration_control_included": False,
            "plan_fingerprint": plan["plan_fingerprint"],
            "planned_candidate_rows": len(candidates),
            "completed_candidate_rows": len(candidates),
            "remaining_candidate_rows": 0,
            "failed_batch_count": 0,
            "failures": [],
            "track_data_loads_this_invocation": track_loads,
            "checkpoint_index": {
                "path": index_path.as_posix(),
                "sha256": _sha256(index_raw),
                "rows": len(checkpoint_rows),
            },
            "full_results": {
                "path": result_path.as_posix(),
                "sha256": _sha256(result_raw),
                "rows": len(ordered_results),
            },
            "candidate_set_or_weight_search_run": False,
            "threshold_changed": False,
            "portfolio_cash_changed": False,
            "transaction_cost_changed": False,
            "fresh_oos_consumed": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }
        expected_manifest = {
            **manifest_payload,
            "manifest_sha256": _canonical_sha256(manifest_payload),
        }
        if manifest != expected_manifest or manifest_raw != _json_bytes(expected_manifest):
            raise NdxEqualWeightScheduleExtensionRunnerError(
                "complete runner manifest does not rebuild"
            )
        return {
            "status": "VERIFIED_COMPLETE",
            "plan_fingerprint": plan["plan_fingerprint"],
            "verified_candidate_rows": len(candidates),
            "verified_track_count": len(plan["groups"]),
            "canonical_source_recapture_track_loads": recapture_loads,
            "candidate_set_or_weight_search_run": False,
            "admission_claimed": False,
            "promotion_allowed": False,
            "live_mutation_allowed": False,
            "order_creation_allowed": False,
        }


__all__ = [
    "EXPECTED_TOTALS", "NdxEqualWeightScheduleExtensionRunnerError",
    "OUTPUT_RELATIVE", "ORIGINAL_SUMMARY_FIELDS", "TRACK_EXPECTED_COUNTS",
    "build_locked_replay_plan", "diagnose_locked_equal_weight_candidate",
    "execute_locked_replay", "extend_equal_weight_schedule_to_path_end",
    "rebuild_result_from_capture", "serialize_replay_capture",
    "verify_candidate_checkpoint", "verify_locked_replay_output",
    "write_candidate_checkpoint",
]
