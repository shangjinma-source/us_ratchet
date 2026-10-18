"""Versioned A/B diagnosis for the historical four-name user preference row.

The module replays exactly one already-recorded historical candidate.  It does
not search, change a risk threshold, grant admission, or generate an order.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

import backtest.ndx_cardinality_discovery as discovery
from backtest.ndx_cardinality_capital_replay_summary import verify_summary_bundle
from backtest.ndx_whole_lot_rebalance import simulate_continuous_whole_lot_rebalance
from scripts import ndx_cardinality_real_smoke as real_smoke


SUMMARY_BUNDLE_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_replay_summary_v1/manifest.json"
)
OUTPUT_RELATIVE = Path(
    "data/cache/research/ndx_user_preference_whole_lot_diagnostic_v1"
)
USER_PREFERENCE_TICKERS = ("AMAT", "AVGO", "CDNS", "GOOG")
CANONICAL_RISK_CHAINS = {
    "AMAT": "semiconductor_equipment",
    "AVGO": "diversified_technology",
    "CDNS": "eda_ip",
    "GOOG": "platform_advertising",
}
CANONICAL_EXECUTION_CONTRACT = {
    "portfolio_cash_usd": 25_000.0,
    "minimum_cash_buffer_usd": 100.0,
    "transaction_cost_bps": 10.0,
    "max_single_weight": 0.45,
    "min_single_weight": 0.05,
    "top_weight_cap": 0.80,
    "minimum_effective_n_ratio": 0.70,
    "risk_chain_top1_cap": 0.55,
}
SELECTION_DATE = "2024-06-03"
SOURCE_BATCH = "ndx_cardinality_real_runner_p2_exact_v3"
UNIVERSE_TRACK = "strict_technology"
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


class NdxUserPreferenceWholeLotDiagnosticError(ValueError):
    pass


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _finite(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise NdxUserPreferenceWholeLotDiagnosticError(f"{label} is not finite")
    return result


def _strict_date(value: object, label: str) -> date:
    text = str(value or "")
    try:
        result = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            f"{label} is not a strict ISO date"
        ) from exc
    if result.isoformat() != text:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            f"{label} is not a strict ISO date"
        )
    return result


def _read_bound_json(
    path: Path, *, label: str, expected_sha256: str | None = None,
) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        actual_sha256 = _sha256_bytes(raw)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            f"cannot read {label}"
        ) from exc
    if not isinstance(value, dict):
        raise NdxUserPreferenceWholeLotDiagnosticError(f"{label} is not an object")
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise NdxUserPreferenceWholeLotDiagnosticError(f"{label} hash changed")
    return value, actual_sha256


def _read_bound_csv(
    path: Path, *, label: str, expected_sha256: str | None = None,
) -> tuple[pd.DataFrame, str]:
    try:
        raw = path.read_bytes()
        actual_sha256 = _sha256_bytes(raw)
        frame = pd.read_csv(io.BytesIO(raw), low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            f"cannot read {label}"
        ) from exc
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise NdxUserPreferenceWholeLotDiagnosticError(f"{label} hash changed")
    return frame, actual_sha256


def _parse_shares(value: object, tickers: Sequence[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in str(value or "").split(";"):
        ticker, separator, raw = item.partition(":")
        if not separator or ticker in result:
            raise NdxUserPreferenceWholeLotDiagnosticError("share trace is malformed")
        number = _finite(raw, "share quantity")
        if not number.is_integer() or number < 0:
            raise NdxUserPreferenceWholeLotDiagnosticError("share quantity is invalid")
        result[ticker] = int(number)
    if list(result) != list(tickers):
        raise NdxUserPreferenceWholeLotDiagnosticError("share trace ticker order changed")
    return result


def _weights_are_equal(
    schedule: Sequence[tuple[pd.Timestamp, Mapping[str, float]]],
    tickers: Sequence[str],
) -> bool:
    target = 1.0 / len(tickers)
    return all(
        list(weights) == list(tickers)
        and all(math.isclose(float(weights[ticker]), target, abs_tol=1e-12) for ticker in tickers)
        for _, weights in schedule
    )


def extend_equal_weight_schedule(
    prices: pd.DataFrame,
    original_schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    cadence_sessions: int = 21,
) -> list[tuple[pd.Timestamp, dict[str, float]]]:
    """Continue only the existing equal-weight cadence through the path end."""

    schedule = [
        (pd.Timestamp(session).normalize(), dict(weights))
        for session, weights in original_schedule
    ]
    if not schedule or cadence_sessions <= 0:
        raise NdxUserPreferenceWholeLotDiagnosticError("schedule/cadence is invalid")
    tickers = list(schedule[0][1])
    if tuple(tickers) != USER_PREFERENCE_TICKERS or not _weights_are_equal(schedule, tickers):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "A path is limited to the four-name equal-weight reference"
        )
    if list(prices.columns) != tickers or prices.empty or not prices.index.is_monotonic_increasing:
        raise NdxUserPreferenceWholeLotDiagnosticError("execution price path is invalid")
    positions = {pd.Timestamp(day).normalize(): index for index, day in enumerate(prices.index)}
    if any(day not in positions for day, _ in schedule):
        raise NdxUserPreferenceWholeLotDiagnosticError("schedule session is missing")
    original_positions = [positions[day] for day, _ in schedule]
    if original_positions != sorted(set(original_positions)):
        raise NdxUserPreferenceWholeLotDiagnosticError("original schedule is not ordered")
    if any(
        right - left != cadence_sessions
        for left, right in zip(original_positions, original_positions[1:])
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "original schedule does not follow the declared session cadence"
        )
    target_weights = {ticker: 1.0 / len(tickers) for ticker in tickers}
    next_position = original_positions[-1] + cadence_sessions
    while next_position < len(prices.index):
        schedule.append((pd.Timestamp(prices.index[next_position]).normalize(), target_weights.copy()))
        next_position += cadence_sessions
    return schedule


def _daily_path_audit(
    prices: pd.DataFrame,
    schedule: Sequence[tuple[pd.Timestamp, Mapping[str, float]]],
    ledger: pd.DataFrame,
    *,
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
) -> dict[str, Any]:
    tickers = list(prices.columns)
    ledger_rows = {
        pd.Timestamp(row["rebalance_date"]).normalize(): row
        for row in ledger.to_dict("records")
    }
    if len(ledger_rows) != len(schedule):
        raise NdxUserPreferenceWholeLotDiagnosticError("rebalance ledger is incomplete")
    shares = {ticker: 0 for ticker in tickers}
    cash = _finite(portfolio_cash_usd, "portfolio cash")
    values: list[float] = []
    failures: list[dict[str, Any]] = []
    daily_records: list[dict[str, Any]] = []
    for session, marks in prices.iterrows():
        day = pd.Timestamp(session).normalize()
        if day in ledger_rows:
            row = ledger_rows[day]
            shares = _parse_shares(row["shares"], tickers)
            cash = _finite(row["posttrade_cash_usd"], "posttrade cash")
        notionals = {ticker: shares[ticker] * float(marks[ticker]) for ticker in tickers}
        invested = sum(notionals.values())
        if invested <= 0:
            raise NdxUserPreferenceWholeLotDiagnosticError("daily invested value is invalid")
        weights = {ticker: notionals[ticker] / invested for ticker in tickers}
        ordered = sorted(weights.values(), reverse=True)
        effective_n = 1.0 / sum(value * value for value in weights.values())
        chain_weights: dict[str, float] = {}
        for ticker, weight in weights.items():
            chain = str(risk_chain_by_ticker.get(ticker) or "")
            if not chain:
                raise NdxUserPreferenceWholeLotDiagnosticError("risk chain is missing")
            chain_weights[chain] = chain_weights.get(chain, 0.0) + weight
        top1 = max(ordered)
        minimum = min(ordered)
        top3 = sum(ordered[:3])
        chain_top1 = max(chain_weights.values())
        checks = {
            "MAX_SINGLE_WEIGHT": top1 <= max_single_weight + 1e-9,
            "MIN_SINGLE_WEIGHT": minimum >= min_single_weight - 1e-9,
            "SECURITY_TOP3_WEIGHT": top3 <= top_weight_cap + 1e-9,
            "MINIMUM_EFFECTIVE_N": effective_n
            >= minimum_effective_n_ratio * len(weights) - 1e-9,
            "RISK_CHAIN_TOP1_WEIGHT": chain_top1 <= risk_chain_top1_cap + 1e-9,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            failures.append({
                "session_date": day.date().isoformat(),
                "failed_constraints": failed,
                "weights": weights,
                "top1_weight": top1,
                "minimum_single_weight": minimum,
                "top3_weight": top3,
                "top3_excess_bps": max(0.0, top3 - top_weight_cap) * 10_000.0,
                "effective_n": effective_n,
                "risk_chain_top1_weight": chain_top1,
            })
        portfolio_value = cash + invested
        values.append(portfolio_value)
        daily_records.append({
            "session_date": day.date().isoformat(),
            "portfolio_value_usd": portfolio_value,
            "posttrade_or_carried_cash_usd": cash,
            "shares": shares.copy(),
            "weights": weights,
            "failed_constraints": failed,
        })
    series = pd.Series(values, index=prices.index, dtype=float)
    old_drawdown = float((1.0 - series / series.cummax()).max())
    with_initial = pd.Series(
        [portfolio_cash_usd, *series.tolist()], dtype=float
    )
    corrected_drawdown = float((1.0 - with_initial / with_initial.cummax()).max())
    return {
        "daily_session_count": len(series),
        "risk_failure_session_count": len(failures),
        "risk_failure_sessions": failures,
        "old_engine_drawdown_without_initial_capital_peak": old_drawdown,
        "corrected_drawdown_with_initial_capital_peak": corrected_drawdown,
        "initial_capital_usd": portfolio_cash_usd,
        "drawdown_metrics_are_reported_separately": True,
        "first_session_value_after_trade_and_fees_usd": float(series.iloc[0]),
        "terminal_value_usd": float(series.iloc[-1]),
        "daily_path_records": daily_records,
        "daily_path_sha256": _sha256_bytes(
            json.dumps(
                daily_records, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ),
    }


def _failure_classes(summary: Mapping[str, Any], audit: Mapping[str, Any]) -> list[str]:
    classes: list[str] = []
    if any(
        quantity == 0
        for record in audit["daily_path_records"]
        for quantity in record["shares"].values()
    ):
        classes.append("ZERO_SHARE")
    if summary.get("whole_lot_cash_buffer_preserved") is not True:
        classes.append("CASH_BUFFER")
    if int(audit["risk_failure_session_count"]) > 0:
        classes.append("DAILY_RISK_DRIFT")
    return classes


def diagnose_equal_weight_schedule_ab(
    prices: pd.DataFrame,
    original_schedule: Iterable[tuple[pd.Timestamp, Mapping[str, float]]],
    *,
    risk_chain_by_ticker: Mapping[str, str],
    portfolio_cash_usd: float,
    minimum_cash_buffer_usd: float,
    transaction_cost_bps: float,
    max_single_weight: float,
    min_single_weight: float,
    top_weight_cap: float,
    minimum_effective_n_ratio: float,
    risk_chain_top1_cap: float,
    expected_original_summary: Mapping[str, Any] | None = None,
    cadence_sessions: int = 21,
) -> dict[str, Any]:
    """Run B (stored schedule) and A (continued equal-weight cadence)."""

    schedule = [(pd.Timestamp(day).normalize(), dict(weights)) for day, weights in original_schedule]
    if tuple(prices.columns) != USER_PREFERENCE_TICKERS or not _weights_are_equal(
        schedule, list(prices.columns)
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "diagnostic accepts only AMAT/AVGO/CDNS/GOOG equal weight"
        )
    kwargs = {
        "risk_chain_by_ticker": dict(risk_chain_by_ticker),
        "portfolio_cash_usd": portfolio_cash_usd,
        "minimum_cash_buffer_usd": minimum_cash_buffer_usd,
        "transaction_cost_bps": transaction_cost_bps,
        "max_single_weight": max_single_weight,
        "min_single_weight": min_single_weight,
        "top_weight_cap": top_weight_cap,
        "minimum_effective_n_ratio": minimum_effective_n_ratio,
        "risk_chain_top1_cap": risk_chain_top1_cap,
    }
    original_summary, original_ledger = simulate_continuous_whole_lot_rebalance(
        prices, schedule, **kwargs
    )
    original_match: dict[str, bool] = {}
    if expected_original_summary is not None:
        for field in ORIGINAL_SUMMARY_FIELDS:
            expected = expected_original_summary.get(field)
            actual = original_summary[field]
            if isinstance(actual, float):
                matches = math.isclose(actual, _finite(expected, field), rel_tol=1e-12, abs_tol=1e-10)
            elif isinstance(actual, bool):
                matches = actual is expected
            else:
                matches = str(actual) == str(expected)
            original_match[field] = matches
        if not all(original_match.values()):
            raise NdxUserPreferenceWholeLotDiagnosticError(
                "original replay does not reproduce the stored trace/summary"
            )
    original_audit = _daily_path_audit(
        prices, schedule, original_ledger, **{
            key: kwargs[key] for key in (
                "risk_chain_by_ticker", "portfolio_cash_usd", "max_single_weight",
                "min_single_weight", "top_weight_cap", "minimum_effective_n_ratio",
                "risk_chain_top1_cap",
            )
        }
    )
    if not math.isclose(
        original_audit["old_engine_drawdown_without_initial_capital_peak"],
        original_summary["whole_lot_path_max_drawdown"],
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("original daily value path disagrees")
    extended_schedule = extend_equal_weight_schedule(
        prices, schedule, cadence_sessions=cadence_sessions
    )
    continued_summary, continued_ledger = simulate_continuous_whole_lot_rebalance(
        prices, extended_schedule, **kwargs
    )
    continued_audit = _daily_path_audit(
        prices, extended_schedule, continued_ledger, **{
            key: kwargs[key] for key in (
                "risk_chain_by_ticker", "portfolio_cash_usd", "max_single_weight",
                "min_single_weight", "top_weight_cap", "minimum_effective_n_ratio",
                "risk_chain_top1_cap",
            )
        }
    )
    if not math.isclose(
        continued_audit["old_engine_drawdown_without_initial_capital_peak"],
        continued_summary["whole_lot_path_max_drawdown"],
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("continued daily value path disagrees")
    added_schedule = extended_schedule[len(schedule):]
    first_added_date = added_schedule[0][0] if added_schedule else None
    original_prefix = [
        record for record in original_audit["daily_path_records"]
        if first_added_date is None
        or pd.Timestamp(record["session_date"]) < first_added_date
    ]
    continued_prefix = [
        record for record in continued_audit["daily_path_records"]
        if first_added_date is None
        or pd.Timestamp(record["session_date"]) < first_added_date
    ]
    prefix_identical = original_prefix == continued_prefix
    if not prefix_identical:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "A path changed history before its first added rebalance"
        )
    original_failures = _failure_classes(original_summary, original_audit)
    continued_failures = _failure_classes(continued_summary, continued_audit)
    fee_relation_verified = all(
        math.isclose(
            path_summary["whole_lot_total_transaction_cost_usd"],
            path_summary["whole_lot_total_trade_notional_usd"]
            * transaction_cost_bps / 10_000.0,
            rel_tol=1e-12,
            abs_tol=1e-10,
        )
        for path_summary in (original_summary, continued_summary)
    )
    if not fee_relation_verified:
        raise NdxUserPreferenceWholeLotDiagnosticError("two-sided fee accounting changed")
    return {
        "original_schedule_b": {
            "mechanism": "STORED_FULL_FORWARD_WINDOWS_ONLY",
            "schedule_dates": [day.date().isoformat() for day, _ in schedule],
            "last_rebalance_date": schedule[-1][0].date().isoformat(),
            "path_end_date": prices.index[-1].date().isoformat(),
            "tail_sessions_after_last_rebalance": len(prices.loc[schedule[-1][0]:]) - 1,
            "summary": original_summary,
            "daily_risk_attribution": original_audit,
            "stored_summary_field_matches": original_match,
            "stored_summary_and_trace_fully_reproduced": bool(
                expected_original_summary is not None and all(original_match.values())
            ),
            "constraint_failure_classes": original_failures,
            "research_constraint_status": "PASS" if not original_failures else "FAIL",
        },
        "continued_cadence_a": {
            "mechanism": "EQUAL_WEIGHT_21_SESSION_CADENCE_CONTINUED_TO_PATH_END",
            "cadence_sessions": cadence_sessions,
            "risk_triggered_trades": False,
            "added_rebalance_dates": [day.date().isoformat() for day, _ in added_schedule],
            "schedule_dates": [day.date().isoformat() for day, _ in extended_schedule],
            "last_rebalance_date": extended_schedule[-1][0].date().isoformat(),
            "path_end_date": prices.index[-1].date().isoformat(),
            "summary": continued_summary,
            "daily_risk_attribution": continued_audit,
            "constraint_failure_classes": continued_failures,
            "research_constraint_status": "PASS" if not continued_failures else "FAIL",
        },
        "comparison": {
            "risk_failure_session_change": (
                continued_audit["risk_failure_session_count"]
                - original_audit["risk_failure_session_count"]
            ),
            "continued_cadence_removed_all_observed_risk_breaches": (
                original_audit["risk_failure_session_count"] > 0
                and continued_audit["risk_failure_session_count"] == 0
            ),
            "single_candidate_only": True,
            "generalization_to_other_candidates_or_weight_rules_allowed": False,
            "risk_threshold_changed": False,
            "risk_triggered_trading_added": False,
            "daily_path_before_first_added_rebalance_identical": prefix_identical,
            "pre_extension_session_count": len(original_prefix),
            "fee_model": "TWO_SIDED_BUY_PLUS_SELL_NOTIONAL_X_TRANSACTION_COST_BPS",
            "fee_relation_verified_both_paths": fee_relation_verified,
            "schedule_extension_uses_session_index_not_future_prices": True,
        },
    }


def _load_expected_candidate(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    summary_manifest_path = (root / SUMMARY_BUNDLE_RELATIVE).resolve()
    bundle = verify_summary_bundle(summary_manifest_path)
    summary_path = summary_manifest_path.parent / "summary.json"
    summary_descriptor = (bundle.get("artifacts") or {}).get("summary_json") or {}
    if summary_descriptor.get("filename") != summary_path.name:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical summary JSON path changed"
        )
    summary, summary_sha256 = _read_bound_json(
        summary_path,
        label="canonical summary JSON",
        expected_sha256=str(summary_descriptor.get("sha256") or ""),
    )
    groups = [
        group for group in summary.get("evaluator_groups", [])
        if group.get("source_batch") == SOURCE_BATCH
        and group.get("job_search_class") == "EXACT_ENUMERATION"
        and group.get("universe_track") == UNIVERSE_TRACK
        and group.get("latest_selection_date") == SELECTION_DATE
    ]
    if len(groups) != 1:
        raise NdxUserPreferenceWholeLotDiagnosticError("canonical summary group is missing")
    reference = groups[0].get("latest_user_preference_reference") or {}
    candidate = reference.get("candidate")
    if (
        reference.get("status") != "PRESENT_SOURCE_REPORTED_REPLAY_INELIGIBLE"
        or not isinstance(candidate, Mapping)
        or tuple(candidate.get("tickers") or []) != USER_PREFERENCE_TICKERS
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical USER_PREFERENCE historical row changed"
        )
    per_start = [
        item for item in groups[0].get("per_start", [])
        if item.get("selection_date") == SELECTION_DATE
    ]
    if len(per_start) != 1:
        raise NdxUserPreferenceWholeLotDiagnosticError("canonical child evidence is missing")
    return dict(candidate), {
        "summary_bundle_manifest": {
            "path": summary_manifest_path.as_posix(),
            "sha256": _file_sha256(summary_manifest_path),
        },
        "summary_json": {
            "path": summary_path.as_posix(), "sha256": summary_sha256,
        },
        "source_top_manifest": bundle["source_top_manifest"],
        "child": per_start[0],
    }


def _capture_single_canonical_replay(root: Path) -> tuple[
    dict[str, Any], pd.DataFrame, list[tuple[pd.Timestamp, Mapping[str, float]]], dict[str, Any]
]:
    captured: list[tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, list[Any], dict[str, Any]]] = []
    original = discovery.simulate_continuous_whole_lot_rebalance

    def capture(prices: pd.DataFrame, schedule: Iterable[Any], **kwargs: Any):
        schedule_rows = list(schedule)
        result, ledger = original(prices, schedule_rows, **kwargs)
        captured.append((result, ledger.copy(), prices.copy(), schedule_rows, dict(kwargs)))
        return result, ledger

    protected_paths = [
        root / "config/config.yaml", root / "data/state.json", root / "data/broker_positions.json",
    ]
    before = {path.as_posix(): _file_sha256(path) for path in protected_paths if path.is_file()}
    caught: BaseException | None = None
    try:
        with tempfile.TemporaryDirectory() as temporary_name:
            temporary = Path(temporary_name)
            candidate_path = temporary / "candidate.csv"
            with candidate_path.open("x", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "source_batch", "universe_track", "selection_date", "holding_count",
                    "tickers", "weight_spec",
                ])
                writer.writeheader()
                writer.writerow({
                    "source_batch": "diagnostic_existing_historical_row",
                    "universe_track": UNIVERSE_TRACK,
                    "selection_date": SELECTION_DATE,
                    "holding_count": 4,
                    "tickers": ";".join(USER_PREFERENCE_TICKERS),
                    "weight_spec": "equal_weight",
                })
            args = argparse.Namespace(
                track=UNIVERSE_TRACK, selection_date=SELECTION_DATE, holding_count=4,
                candidate_sets_file=str(candidate_path), source_batch="",
                portfolio_cash_usd=25_000.0,
                spec="config/ndx_cardinality_discovery_v1.yaml",
                input_readiness_manifest=(
                    "data/cache/research/ndx_variable_cardinality_input_readiness_v3/manifest.json"
                ),
                discovery_manifest=(
                    "data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json"
                ),
                security_lifecycle="config/ndx_security_lifecycle.yaml",
                execution_price_manifest=(
                    "data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json"
                ),
                return_cache_dir="data/cache", target_nav="data/cache/funds/012922.csv",
                state="data/state.json", config="config/config.yaml",
                output_dir=str(temporary / "smoke_output"),
                minimum_price_rows_before_selection=252, training_lookback_days=504,
                fit_days=126, window_days=126, step_days=21, beam_width=64,
                transaction_cost_bps=10.0, search_method="two_stage",
            )
            discovery.simulate_continuous_whole_lot_rebalance = capture
            real_smoke.run(args)
    except BaseException as exc:
        caught = exc
    finally:
        discovery.simulate_continuous_whole_lot_rebalance = original
        after = {
            path.as_posix(): _file_sha256(path)
            for path in protected_paths if path.is_file()
        }
    if before != after:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "single-candidate diagnostic changed a protected file"
        ) from caught
    if caught is not None:
        raise caught
    if len(captured) != 1:
        raise NdxUserPreferenceWholeLotDiagnosticError("single-candidate capture count changed")
    summary, _ledger, prices, schedule, kwargs = captured[0]
    return summary, prices, schedule, kwargs


def _source_binding_paths(
    root: Path, evidence: Mapping[str, Any],
) -> tuple[list[Path], dict[str, str]]:
    paths: list[Path] = [
        root / "backtest/ndx_whole_lot_rebalance.py",
        root / "backtest/ndx_cardinality_discovery.py",
        root / "scripts/ndx_cardinality_real_smoke.py",
        root / "backtest/ndx_user_preference_whole_lot_diagnostic.py",
        root / "scripts/ndx_user_preference_whole_lot_diagnostic.py",
        root / "data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json",
        root / "data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json",
    ]
    consumed_hashes: dict[str, str] = {}

    def remember(path: Path, sha256: str) -> None:
        consumed_hashes[path.resolve().as_posix()] = sha256

    child = evidence["child"]
    paths.extend(Path(item["path"]) for item in child["artifacts"].values())
    paths.extend(Path(item["path"]) for item in child["source_inputs"].values())
    paths.extend((Path(evidence["summary_bundle_manifest"]["path"]), Path(evidence["summary_json"]["path"])))

    # The adjusted source inventory determines the common session index, so
    # bind every source it actually names rather than only the inventory CSV.
    price_inventory_path = Path(child["artifacts"]["price_inventory"]["path"])
    price_inventory, price_inventory_sha256 = _read_bound_csv(
        price_inventory_path,
        label="adjusted price inventory",
        expected_sha256=str(
            child["artifacts"]["price_inventory"].get("historical_sha256") or ""
        ),
    )
    remember(price_inventory_path, price_inventory_sha256)
    for column in ("path", "source_files"):
        if column in price_inventory:
            for value in price_inventory[column].dropna().astype(str):
                paths.extend(Path(item) for item in value.split(";") if item)

    # Bind the four nominal close files and sidecars actually consumed for
    # whole-share sizing/fills, not merely their parent manifest.
    execution_manifest_path = (
        root / "data/cache/research/ndx_cardinality_execution_prices_all_ready_v1/manifest.json"
    ).resolve()
    execution_manifest_descriptor = child["source_inputs"]["execution_price_manifest"]
    execution_manifest, execution_manifest_sha256 = _read_bound_json(
        execution_manifest_path,
        label="nominal execution manifest",
        expected_sha256=str(execution_manifest_descriptor.get("historical_sha256") or ""),
    )
    remember(execution_manifest_path, execution_manifest_sha256)
    inventory_descriptor = (execution_manifest.get("artifacts") or {}).get("inventory") or {}
    execution_inventory_path = Path(str(inventory_descriptor.get("path") or "")).resolve()
    expected_inventory_hash = str(inventory_descriptor.get("sha256") or "")
    child_inventory_hash = str(
        child["source_inputs"]["execution_price_inventory"].get("historical_sha256") or ""
    )
    if expected_inventory_hash != child_inventory_hash:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "nominal execution inventory binding changed"
        )
    execution_inventory, execution_inventory_sha256 = _read_bound_csv(
        execution_inventory_path,
        label="nominal execution inventory",
        expected_sha256=expected_inventory_hash,
    )
    remember(execution_inventory_path, execution_inventory_sha256)
    paths.append(execution_inventory_path)
    selected = execution_inventory.loc[
        execution_inventory["ticker"].astype(str).isin(USER_PREFERENCE_TICKERS)
    ]
    if set(selected["ticker"].astype(str)) != set(USER_PREFERENCE_TICKERS):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "nominal execution inventory lacks preference tickers"
        )
    for row in selected.to_dict("records"):
        for column, hash_column in (
            ("path", "sha256"), ("sidecar_path", "sidecar_sha256"),
        ):
            source_path = Path(str(row[column])).resolve()
            try:
                source_raw = source_path.read_bytes()
            except OSError as exc:
                raise NdxUserPreferenceWholeLotDiagnosticError(
                    "nominal execution price source is missing"
                ) from exc
            source_sha256 = _sha256_bytes(source_raw)
            if source_sha256 != str(row[hash_column]):
                raise NdxUserPreferenceWholeLotDiagnosticError(
                    "nominal execution price source hash changed"
                )
            remember(source_path, source_sha256)
            paths.append(source_path)

    discovery_manifest_path = (
        root / "data/cache/research/ndx_variable_cardinality_discovery_v1/manifest.json"
    ).resolve()
    discovery_manifest, discovery_manifest_sha256 = _read_bound_json(
        discovery_manifest_path, label="discovery manifest",
    )
    remember(discovery_manifest_path, discovery_manifest_sha256)
    eligible_descriptor = (discovery_manifest.get("artifacts") or {}).get(
        "eligible_securities"
    ) or {}
    eligible_path = Path(str(eligible_descriptor.get("path") or "")).resolve()
    _eligible, eligible_sha256 = _read_bound_csv(
        eligible_path,
        label="eligible security universe",
        expected_sha256=str(eligible_descriptor.get("sha256") or ""),
    )
    remember(eligible_path, eligible_sha256)
    paths.append(eligible_path)
    return paths, consumed_hashes


def _source_bindings(root: Path, evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths, consumed_hashes = _source_binding_paths(root, evidence)
    unique: dict[str, dict[str, Any]] = {}
    for path in paths:
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise NdxUserPreferenceWholeLotDiagnosticError("source binding escapes root") from exc
        if not resolved.is_file():
            raise NdxUserPreferenceWholeLotDiagnosticError(f"source binding missing: {resolved}")
        raw = resolved.read_bytes()
        actual_sha256 = _sha256_bytes(raw)
        consumed_sha256 = consumed_hashes.get(resolved.as_posix())
        if consumed_sha256 is not None and actual_sha256 != consumed_sha256:
            raise NdxUserPreferenceWholeLotDiagnosticError(
                "source evidence changed while its descriptor was consumed"
            )
        unique[resolved.as_posix()] = {
            "path": resolved.as_posix(), "sha256": actual_sha256,
        }
    return [unique[key] for key in sorted(unique)]


def _serialize_replay_capture(
    prices: pd.DataFrame,
    schedule: Sequence[tuple[pd.Timestamp, Mapping[str, float]]],
    kwargs: Mapping[str, Any],
    expected_original_summary: Mapping[str, Any],
    *,
    cadence_sessions: int = 21,
) -> dict[str, Any]:
    if type(cadence_sessions) is not int or cadence_sessions != 21:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical replay cadence must be exactly 21 sessions"
        )
    if tuple(prices.columns) != USER_PREFERENCE_TICKERS:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical replay price columns changed"
        )
    risk_chains = kwargs.get("risk_chain_by_ticker")
    if not isinstance(risk_chains, Mapping) or any(
        risk_chains.get(ticker) != CANONICAL_RISK_CHAINS[ticker]
        for ticker in USER_PREFERENCE_TICKERS
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical replay risk chains changed"
        )
    for key, expected_value in CANONICAL_EXECUTION_CONTRACT.items():
        actual_value = kwargs.get(key)
        if isinstance(actual_value, bool) or _finite(
            actual_value, f"canonical {key}"
        ) != expected_value:
            raise NdxUserPreferenceWholeLotDiagnosticError(
                f"canonical replay {key} changed"
            )
    return {
        "schema_version": 1,
        "capture_type": "ndx_user_preference_whole_lot_replay_input",
        "price_columns": list(prices.columns),
        "price_rows": [
            {
                "session_date": pd.Timestamp(session).date().isoformat(),
                "closes": {ticker: float(row[ticker]) for ticker in prices.columns},
            }
            for session, row in prices.iterrows()
        ],
        "original_schedule": [
            {
                "session_date": pd.Timestamp(session).date().isoformat(),
                "weights": {ticker: float(weights[ticker]) for ticker in prices.columns},
            }
            for session, weights in schedule
        ],
        "execution_contract": {
            "risk_chain_by_ticker": dict(CANONICAL_RISK_CHAINS),
            **dict(CANONICAL_EXECUTION_CONTRACT),
        },
        "expected_original_summary": dict(expected_original_summary),
        "cadence_sessions": cadence_sessions,
        "price_source_role": "UNADJUSTED_NOMINAL_HISTORICAL_CLOSE_EXECUTION_ONLY",
    }


def _rebuild_ab_from_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version", "capture_type", "price_columns", "price_rows",
        "original_schedule", "execution_contract", "expected_original_summary",
        "cadence_sessions", "price_source_role",
    }
    if (
        set(capture) != required
        or capture.get("schema_version") != 1
        or capture.get("capture_type")
        != "ndx_user_preference_whole_lot_replay_input"
        or capture.get("price_source_role")
        != "UNADJUSTED_NOMINAL_HISTORICAL_CLOSE_EXECUTION_ONLY"
        or tuple(capture.get("price_columns") or []) != USER_PREFERENCE_TICKERS
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("replay capture schema changed")
    cadence_sessions = capture.get("cadence_sessions")
    if type(cadence_sessions) is not int or cadence_sessions != 21:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "captured cadence is not the canonical 21-session cadence"
        )
    price_rows = capture.get("price_rows")
    schedule_rows = capture.get("original_schedule")
    contract = capture.get("execution_contract")
    if (
        not isinstance(price_rows, list) or not price_rows
        or not isinstance(schedule_rows, list) or not schedule_rows
        or not isinstance(contract, Mapping)
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("replay capture is incomplete")
    dates: list[pd.Timestamp] = []
    values: list[list[float]] = []
    for row in price_rows:
        if not isinstance(row, Mapping) or set(row) != {"session_date", "closes"}:
            raise NdxUserPreferenceWholeLotDiagnosticError("captured price row changed")
        day = pd.Timestamp(_strict_date(row["session_date"], "captured price session"))
        closes = row["closes"]
        if not isinstance(closes, Mapping) or list(closes) != list(USER_PREFERENCE_TICKERS):
            raise NdxUserPreferenceWholeLotDiagnosticError("captured price columns changed")
        row_values = [_finite(closes[ticker], "captured close") for ticker in USER_PREFERENCE_TICKERS]
        if any(value <= 0 for value in row_values):
            raise NdxUserPreferenceWholeLotDiagnosticError("captured close is not positive")
        dates.append(day)
        values.append(row_values)
    if dates != sorted(set(dates)):
        raise NdxUserPreferenceWholeLotDiagnosticError("captured sessions are not unique/sorted")
    prices = pd.DataFrame(values, index=dates, columns=USER_PREFERENCE_TICKERS)
    schedule: list[tuple[pd.Timestamp, dict[str, float]]] = []
    for row in schedule_rows:
        if not isinstance(row, Mapping) or set(row) != {"session_date", "weights"}:
            raise NdxUserPreferenceWholeLotDiagnosticError("captured schedule row changed")
        weights = row["weights"]
        if not isinstance(weights, Mapping) or list(weights) != list(USER_PREFERENCE_TICKERS):
            raise NdxUserPreferenceWholeLotDiagnosticError("captured schedule weights changed")
        schedule.append((
            pd.Timestamp(_strict_date(row["session_date"], "captured schedule session")),
            {ticker: _finite(weights[ticker], "captured weight") for ticker in USER_PREFERENCE_TICKERS},
        ))
    expected_contract_keys = {
        "risk_chain_by_ticker", "portfolio_cash_usd", "minimum_cash_buffer_usd",
        "transaction_cost_bps", "max_single_weight", "min_single_weight",
        "top_weight_cap", "minimum_effective_n_ratio", "risk_chain_top1_cap",
    }
    if set(contract) != expected_contract_keys:
        raise NdxUserPreferenceWholeLotDiagnosticError("captured execution contract changed")
    risk_chains = contract["risk_chain_by_ticker"]
    if not isinstance(risk_chains, Mapping) or dict(risk_chains) != CANONICAL_RISK_CHAINS:
        raise NdxUserPreferenceWholeLotDiagnosticError("captured risk chains changed")
    numeric_contract: dict[str, float] = {}
    for key, expected_value in CANONICAL_EXECUTION_CONTRACT.items():
        raw_value = contract.get(key)
        if isinstance(raw_value, bool):
            raise NdxUserPreferenceWholeLotDiagnosticError(f"captured {key} changed")
        numeric_contract[key] = _finite(raw_value, f"captured {key}")
        if numeric_contract[key] != expected_value:
            raise NdxUserPreferenceWholeLotDiagnosticError(f"captured {key} changed")
    return diagnose_equal_weight_schedule_ab(
        prices,
        schedule,
        risk_chain_by_ticker={ticker: str(risk_chains[ticker]) for ticker in USER_PREFERENCE_TICKERS},
        **numeric_contract,
        expected_original_summary=capture["expected_original_summary"],
        cadence_sessions=cadence_sessions,
    )


def _expected_original_from_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    whole_lot = candidate["continuous_whole_lot_path"]
    return {
        "whole_lot_rebalance_count": int(whole_lot["whole_lot_rebalance_count"]),
        "whole_lot_initial_shares": ";".join(
            f"{ticker}:{whole_lot['initial_shares'][ticker]}"
            for ticker in USER_PREFERENCE_TICKERS
        ),
        "whole_lot_terminal_shares": ";".join(
            f"{ticker}:{whole_lot['terminal_shares'][ticker]}"
            for ticker in USER_PREFERENCE_TICKERS
        ),
        "whole_lot_share_change_count": int(whole_lot["whole_lot_share_change_count"]),
        "whole_lot_total_trade_notional_usd": whole_lot[
            "whole_lot_total_trade_notional_usd"
        ],
        "whole_lot_total_transaction_cost_usd": whole_lot[
            "whole_lot_total_transaction_cost_usd"
        ],
        "whole_lot_min_cash_usd": whole_lot["whole_lot_min_cash_usd"],
        "whole_lot_cash_buffer_preserved": whole_lot["cash_buffer_preserved"],
        "whole_lot_constraints_preserved_all_days": whole_lot[
            "constraints_preserved_all_days"
        ],
        "whole_lot_terminal_value_usd": whole_lot["whole_lot_terminal_value_usd"],
        "whole_lot_path_return_net": whole_lot["whole_lot_path_return_net"],
        "whole_lot_path_max_drawdown": whole_lot["whole_lot_path_max_drawdown"],
        "whole_lot_rebalance_trace_sha256": whole_lot["rebalance_trace_sha256"],
    }


def build_canonical_user_preference_diagnostic(
    *, repository_root: str | Path,
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    expected, evidence = _load_expected_candidate(root)
    source_bindings_before = _source_bindings(root, evidence)
    captured_summary, prices, schedule, kwargs = _capture_single_canonical_replay(root)
    source_bindings_after = _source_bindings(root, evidence)
    if source_bindings_before != source_bindings_after:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "source evidence changed while the single candidate was consumed"
        )
    expected_original = _expected_original_from_candidate(expected)
    for field in ORIGINAL_SUMMARY_FIELDS:
        actual = captured_summary[field]
        expected_value = expected_original[field]
        if isinstance(actual, float):
            matches = math.isclose(actual, float(expected_value), rel_tol=1e-12, abs_tol=1e-10)
        else:
            matches = actual == expected_value
        if not matches:
            raise NdxUserPreferenceWholeLotDiagnosticError(
                f"captured historical replay changed: {field}"
            )
    ab = diagnose_equal_weight_schedule_ab(
        prices, schedule, expected_original_summary=expected_original, **kwargs
    )
    replay_capture = _serialize_replay_capture(
        prices, schedule, kwargs, expected_original
    )
    if _rebuild_ab_from_capture(replay_capture) != ab:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "sealed replay input does not rebuild the A/B diagnostic"
        )
    return {
        "schema_version": 1,
        "manifest_type": "ndx_user_preference_whole_lot_schedule_diagnostic",
        "status": "RESEARCH_DIAGNOSTIC_COMPLETE",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "selection_date": SELECTION_DATE,
        "source_batch": SOURCE_BATCH,
        "universe_track": UNIVERSE_TRACK,
        "portfolio_id": expected["portfolio_id"],
        "tickers": list(USER_PREFERENCE_TICKERS),
        "target_weights": {ticker: 0.25 for ticker in USER_PREFERENCE_TICKERS},
        "portfolio_cash_usd": 25_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        "execution_evidence_scope": "HISTORICAL_CLOSE_EXECUTION_DIAGNOSTIC_ONLY",
        "same_close_sizing_and_fill_is_not_a_strict_live_order_model": True,
        "next_session_open_execution_added": False,
        "risk_contract": {
            key: kwargs[key] for key in (
                "max_single_weight", "min_single_weight", "top_weight_cap",
                "minimum_effective_n_ratio", "risk_chain_top1_cap",
            )
        },
        "replay_input_capture": replay_capture,
        "ab_diagnostic": ab,
        "source_bindings": source_bindings_before,
        "source_bindings_unchanged_during_capture": True,
        "evidence": evidence,
        "fresh_oos_consumed": False,
        "search_run": False,
        "risk_threshold_changed": False,
        "risk_triggered_trades_added": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
        "generalization_claimed": False,
    }


def render_diagnostic_markdown(result: Mapping[str, Any]) -> str:
    original = result["ab_diagnostic"]["original_schedule_b"]
    continued = result["ab_diagnostic"]["continued_cadence_a"]
    failures = original["daily_risk_attribution"]["risk_failure_sessions"]
    lines = [
        "# AMAT / AVGO / CDNS / GOOG 等权整股路径 A/B 诊断",
        "",
        "结论：历史行并非现金或费用不可执行。旧日程仅在尾段两个日线收盘轻微突破"
        "单名 Top3 80% 上限；A 路径只延续原有每 21 会话等权再平衡节奏，不改变风险门。",
        "",
        f"旧 trace：`{original['summary']['whole_lot_rebalance_trace_sha256']}`；"
        f"存档 13 项重证：`{original['stored_summary_and_trace_fully_reproduced']}`。",
        "",
        f"B 旧日程：最后再平衡 {original['last_rebalance_date']}，路径结束 "
        f"{original['path_end_date']}，尾段 {original['tail_sessions_after_last_rebalance']} 个会话；"
        f"风险失败 {original['daily_risk_attribution']['risk_failure_session_count']} 个会话。",
        "",
    ]
    for failure in failures:
        lines.append(
            f"- {failure['session_date']}：{','.join(failure['failed_constraints'])}；"
            f"Top3={100 * failure['top3_weight']:.6f}%，超限 "
            f"{failure['top3_excess_bps']:.4f} bp；各股权重 "
            + ", ".join(
                f"{ticker}={100 * weight:.4f}%"
                for ticker, weight in failure["weights"].items()
            ) + "。"
        )
    lines.extend([
        "",
        f"A 延续日程：新增 {len(continued['added_rebalance_dates'])} 次再平衡 "
        f"({', '.join(continued['added_rebalance_dates']) or '无'})；"
        f"风险失败 {continued['daily_risk_attribution']['risk_failure_session_count']} 个会话。",
        "",
        "| 路径 | 旧引擎回撤口径（未加入初始资金峰值） | 修正口径（加入初始 25,000 美元峰值） | 净收益 | 最低现金 |",
        "|---|---:|---:|---:|---:|",
        f"| B 旧日程 | {100 * original['daily_risk_attribution']['old_engine_drawdown_without_initial_capital_peak']:.4f}% | "
        f"{100 * original['daily_risk_attribution']['corrected_drawdown_with_initial_capital_peak']:.4f}% | "
        f"{100 * original['summary']['whole_lot_path_return_net']:.4f}% | "
        f"${original['summary']['whole_lot_min_cash_usd']:.2f} |",
        f"| A 延续日程 | {100 * continued['daily_risk_attribution']['old_engine_drawdown_without_initial_capital_peak']:.4f}% | "
        f"{100 * continued['daily_risk_attribution']['corrected_drawdown_with_initial_capital_peak']:.4f}% | "
        f"{100 * continued['summary']['whole_lot_path_return_net']:.4f}% | "
        f"${continued['summary']['whole_lot_min_cash_usd']:.2f} |",
        "",
        "证据边界：这里只诊断一个已存历史等权候选；不外推到其他组合或权重规则，"
        "不新增风险触发交易，不放宽 80% 上限，不构成准入、实盘建议或订单。",
    ])
    return "\n".join(lines) + "\n"


def _bundle_manifest(json_raw: bytes, markdown_raw: bytes, result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "ndx_user_preference_whole_lot_diagnostic_bundle",
        "status": result["status"],
        "artifacts": {
            "diagnostic_json": {"filename": "diagnostic.json", "sha256": _sha256_bytes(json_raw)},
            "diagnostic_markdown": {"filename": "diagnostic.md", "sha256": _sha256_bytes(markdown_raw)},
        },
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def write_diagnostic_bundle(result: Mapping[str, Any], *, output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    json_raw = _json_bytes(result)
    markdown_raw = render_diagnostic_markdown(result).encode("utf-8")
    manifest = _bundle_manifest(json_raw, markdown_raw, result)
    files = {
        "diagnostic.json": json_raw,
        "diagnostic.md": markdown_raw,
        "manifest.json": _json_bytes(manifest),
    }
    if output.exists():
        if not output.is_dir() or set(item.name for item in output.iterdir()) != set(files):
            raise NdxUserPreferenceWholeLotDiagnosticError("immutable bundle collision")
        if any((output / name).read_bytes() != raw for name, raw in files.items()):
            raise NdxUserPreferenceWholeLotDiagnosticError("immutable bundle collision")
        verify_diagnostic_bundle(output / "manifest.json")
        return manifest
    temporary = output.with_name(f"{output.name}.tmp.{uuid.uuid4().hex}")
    try:
        temporary.mkdir()
        for name, raw in files.items():
            with (temporary / name).open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    verify_diagnostic_bundle(output / "manifest.json")
    return manifest


def verify_diagnostic_bundle(manifest_path: str | Path) -> dict[str, Any]:
    """Verify immutable artifact bytes and sealed replay math only.

    This offline verifier deliberately does not claim that the sealed prices or
    contract came from the current canonical repository sources. Use
    :func:`verify_canonical_diagnostic_bundle` for that stronger check.
    """
    path = Path(manifest_path).resolve()
    try:
        manifest_raw = path.read_bytes()
        manifest = json.loads(manifest_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError("cannot read bundle manifest") from exc
    expected_keys = {
        "schema_version", "manifest_type", "status", "artifacts", "admission_claimed",
        "promotion_allowed", "live_mutation_allowed", "order_creation_allowed",
    }
    if (
        set(manifest) != expected_keys
        or manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "ndx_user_preference_whole_lot_diagnostic_bundle"
        or any(manifest.get(key) is not False for key in (
            "admission_claimed", "promotion_allowed", "live_mutation_allowed",
            "order_creation_allowed",
        ))
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("bundle manifest boundary changed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "diagnostic_json", "diagnostic_markdown",
    }:
        raise NdxUserPreferenceWholeLotDiagnosticError("bundle artifacts changed")
    artifact_bytes: dict[str, bytes] = {}
    for key, filename in (
        ("diagnostic_json", "diagnostic.json"),
        ("diagnostic_markdown", "diagnostic.md"),
    ):
        descriptor = artifacts[key]
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"filename", "sha256"}:
            raise NdxUserPreferenceWholeLotDiagnosticError("artifact descriptor changed")
        artifact = path.parent / filename
        if descriptor["filename"] != filename or not artifact.is_file():
            raise NdxUserPreferenceWholeLotDiagnosticError("artifact path changed")
        raw = artifact.read_bytes()
        if _sha256_bytes(raw) != descriptor["sha256"]:
            raise NdxUserPreferenceWholeLotDiagnosticError("artifact hash changed")
        artifact_bytes[key] = raw
    try:
        result = json.loads(artifact_bytes["diagnostic_json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxUserPreferenceWholeLotDiagnosticError("diagnostic JSON is invalid") from exc
    if (
        result.get("manifest_type") != "ndx_user_preference_whole_lot_schedule_diagnostic"
        or result.get("status") != manifest.get("status")
        or result.get("admission_claimed") is not False
        or result.get("promotion_allowed") is not False
        or result.get("live_mutation_allowed") is not False
        or result.get("order_creation_allowed") is not False
    ):
        raise NdxUserPreferenceWholeLotDiagnosticError("diagnostic boundary changed")
    if render_diagnostic_markdown(result).encode("utf-8") != artifact_bytes[
        "diagnostic_markdown"
    ]:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "diagnostic Markdown does not regenerate from JSON"
        )
    capture = result.get("replay_input_capture")
    if not isinstance(capture, Mapping):
        raise NdxUserPreferenceWholeLotDiagnosticError("sealed replay input is missing")
    if _rebuild_ab_from_capture(capture) != result.get("ab_diagnostic"):
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "sealed replay input does not reproduce the stored A/B result"
        )
    return manifest


def verify_canonical_diagnostic_bundle(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Freshly recapture canonical inputs and reproduce the complete result."""

    root = Path(repository_root).resolve()
    manifest = verify_diagnostic_bundle(manifest_path)
    diagnostic_path = Path(manifest_path).resolve().parent / "diagnostic.json"
    stored, _stored_sha256 = _read_bound_json(
        diagnostic_path,
        label="canonical diagnostic JSON",
        expected_sha256=str(manifest["artifacts"]["diagnostic_json"]["sha256"]),
    )
    if stored.get("source_bindings_unchanged_during_capture") is not True:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "source capture TOCTOU guard is absent"
        )
    rebuilt = build_canonical_user_preference_diagnostic(repository_root=root)
    if stored != rebuilt:
        raise NdxUserPreferenceWholeLotDiagnosticError(
            "canonical single-candidate recapture does not reproduce the stored diagnostic"
        )
    return manifest


__all__ = [
    "NdxUserPreferenceWholeLotDiagnosticError", "OUTPUT_RELATIVE",
    "SUMMARY_BUNDLE_RELATIVE", "build_canonical_user_preference_diagnostic",
    "diagnose_equal_weight_schedule_ab", "extend_equal_weight_schedule",
    "render_diagnostic_markdown", "verify_canonical_diagnostic_bundle",
    "verify_diagnostic_bundle", "write_diagnostic_bundle",
]
