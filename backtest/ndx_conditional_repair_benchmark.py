"""Same-calendar original-eight and 012922 research benchmarks for repair C.

This module consumes only the locked historical execution-price bundle, the
frozen original-eight definition, and an exact recoverable byte prefix of the
012922 NAV cache.  It neither searches portfolios nor grants admission.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

import pandas as pd

from backtest import ndx_equal_weight_schedule_extension_runner as source_runner
from backtest.ndx_whole_lot_repair_path import (
    simulate_conditional_whole_lot_repair_path,
)


OUTPUT_RELATIVE = Path("data/cache/research/eqrepair_benchmark_v1")
ORIGINAL8_RELATIVE = Path("data/cache/research/ndx_original_8_control_v1/manifest.json")
PRICE_BUNDLE_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_execution_prices_walkforward_v2"
)
TARGET_NAV_RELATIVE = Path("data/cache/funds/012922.csv")
MODULE_RELATIVE = Path("backtest/ndx_conditional_repair_benchmark.py")
SCRIPT_RELATIVE = Path("scripts/ndx_conditional_repair_benchmark.py")
REPAIR_PATH_RELATIVE = Path("backtest/ndx_whole_lot_repair_path.py")
REPAIR_KERNEL_RELATIVE = Path("backtest/ndx_whole_lot_repair_diagnostic.py")
SOURCE_RUNNER_RELATIVE = Path("backtest/ndx_equal_weight_schedule_extension_runner.py")

LOCKED_SOURCE_HASHES = {
    "original8_manifest": "2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260",
    "price_bundle_manifest": "04a307a171e9304245a6f82a032a1b789b77274fb05b044d88a67e2ce10a8c29",
    "price_inventory": "6e16c3fea22421e650663f617e2bf2d6c6cc87db52bf1303f7a3380e6b600961",
    "target_nav_historical_prefix": "f1249fdd8e16d38db1668afb0a6b87b03f794a37f3b137451457d26190bc9245",
}
TARGET_NAV_PREFIX_BYTES = 47_663
ORIGINAL8_TICKERS = ("NVDA", "TXN", "ASML", "CDNS", "TSM", "MU", "MSFT", "GOOG")
WINDOW_START = "2022-11-29"
WINDOW_END = "2024-05-31"
EXPECTED_SESSIONS = 378
CADENCE_SESSIONS = 21
EXPECTED_REBALANCES = 18
CONTRACT = {
    "portfolio_cash_usd": 25_000.0,
    "minimum_cash_buffer_usd": 100.0,
    "transaction_cost_bps": 10.0,
    "max_single_weight": 0.45,
    "min_single_weight": 0.05,
    "top_weight_cap": 0.80,
    "minimum_effective_n_ratio": 0.70,
    "risk_chain_top1_cap": 0.55,
}
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class NdxConditionalRepairBenchmarkError(ValueError):
    """Raised when benchmark lineage or mechanics fail closed."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return _sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _capture(path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    target = path.resolve()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise NdxConditionalRepairBenchmarkError(
            f"cannot capture benchmark source: {target}"
        ) from exc
    digest = _sha256(raw)
    if expected_sha256 is not None and digest != expected_sha256:
        raise NdxConditionalRepairBenchmarkError(
            f"locked benchmark source hash changed: {target}"
        )
    return {"path": target, "raw": raw, "sha256": digest}


def _parse_json(capture: Mapping[str, Any], label: str) -> dict[str, Any]:
    try:
        value = json.loads(capture["raw"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxConditionalRepairBenchmarkError(f"invalid {label} JSON") from exc
    if not isinstance(value, dict):
        raise NdxConditionalRepairBenchmarkError(f"{label} must be an object")
    return value


def _parse_csv(capture: Mapping[str, Any], label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(capture["raw"]), low_memory=False)
    except Exception as exc:
        raise NdxConditionalRepairBenchmarkError(f"invalid {label} CSV") from exc


def _strict_dates(values: pd.Series, label: str) -> pd.DatetimeIndex:
    raw = values.astype(str)
    if not raw.map(lambda value: bool(_DATE_PATTERN.fullmatch(value))).all():
        raise NdxConditionalRepairBenchmarkError(f"{label} dates are not YYYY-MM-DD")
    try:
        parsed = pd.DatetimeIndex(pd.to_datetime(raw, format="%Y-%m-%d", errors="raise"))
    except (TypeError, ValueError) as exc:
        raise NdxConditionalRepairBenchmarkError(f"{label} dates are invalid") from exc
    if parsed.has_duplicates or not parsed.is_monotonic_increasing:
        raise NdxConditionalRepairBenchmarkError(
            f"{label} dates must be unique and ascending"
        )
    return parsed


def _capture_descriptor(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path": Path(capture["path"]).resolve().as_posix(),
        "sha256": str(capture["sha256"]),
        "bytes": len(capture["raw"]),
    }


def _validated_ohlcv(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    expected = {"Date", "Open", "High", "Low", "Close", "Volume"}
    if set(frame.columns) != expected:
        raise NdxConditionalRepairBenchmarkError(f"{ticker} OHLCV schema changed")
    numeric = frame[["Open", "High", "Low", "Close", "Volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if (
        numeric.isna().any().any()
        or (~numeric.map(lambda value: math.isfinite(float(value))).all()).any()
        or (numeric[["Open", "High", "Low", "Close"]] <= 0).any().any()
        or (numeric["Volume"] < 0).any()
        or (numeric["High"] < numeric[["Open", "Low", "Close"]].max(axis=1)).any()
        or (numeric["Low"] > numeric[["Open", "High", "Close"]].min(axis=1)).any()
    ):
        raise NdxConditionalRepairBenchmarkError(f"{ticker} OHLCV is invalid")
    return numeric


def _resolve_declared_path(root: Path, value: Any, label: str) -> Path:
    text = str(value or "")
    if not text:
        raise NdxConditionalRepairBenchmarkError(f"{label} path is missing")
    path = Path(text)
    if not path.is_absolute():
        path = root / path
    target = path.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise NdxConditionalRepairBenchmarkError(
            f"{label} path is outside repository"
        ) from exc
    return target


def _verify_descriptor_input(
    root: Path, descriptor: Mapping[str, Any], label: str
) -> dict[str, Any]:
    if not isinstance(descriptor, Mapping):
        raise NdxConditionalRepairBenchmarkError(f"{label} descriptor is missing")
    path = _resolve_declared_path(root, descriptor.get("path"), label)
    capture = _capture(path, expected_sha256=str(descriptor.get("sha256") or ""))
    if "rows" in descriptor:
        rows = len(_parse_csv(capture, label))
        if isinstance(descriptor.get("rows"), bool) or rows != int(descriptor["rows"]):
            raise NdxConditionalRepairBenchmarkError(f"{label} row count changed")
    return capture


def _load_original8(
    root: Path,
) -> tuple[
    dict[str, Any], dict[str, float], dict[str, str], dict[str, dict[str, str]],
    dict[str, Any], dict[str, Mapping[str, Any]],
]:
    capture = _capture(
        root / ORIGINAL8_RELATIVE,
        expected_sha256=LOCKED_SOURCE_HASHES["original8_manifest"],
    )
    manifest = _parse_json(capture, "original-eight manifest")
    definition = manifest.get("definition")
    securities = definition.get("securities") if isinstance(definition, Mapping) else None
    if (
        manifest.get("manifest_type") != "ndx_original_8_frozen_research_control"
        or manifest.get("status") != "FROZEN_RESEARCH_CONTROL_NOT_CURRENT_BROKER_OVERLAY"
        or manifest.get("research_track") != "portfolio_optimization"
        or manifest.get("migration_control_included") is not False
        or manifest.get("broker_current_overlay_included") is not False
        or manifest.get("weight_source") != "CAPITAL_REPLAY_CHILD_MANIFEST_CONSENSUS"
        or not isinstance(definition, Mapping)
        or _canonical_sha256(definition) != manifest.get("definition_sha256")
        or not isinstance(securities, list)
        or len(securities) != len(ORIGINAL8_TICKERS)
        or [str(row.get("ticker") or "") for row in securities] != list(ORIGINAL8_TICKERS)
        or float(definition.get("starting_capital_usd", -1)) != CONTRACT["portfolio_cash_usd"]
        or float(definition.get("minimum_cash_buffer_usd", -1)) != CONTRACT["minimum_cash_buffer_usd"]
        or float(definition.get("transaction_cost_bps", -1)) != CONTRACT["transaction_cost_bps"]
    ):
        raise NdxConditionalRepairBenchmarkError("original-eight contract changed")
    identities: dict[str, dict[str, str]] = {}
    weights: dict[str, float] = {}
    chains: dict[str, str] = {}
    for row in securities:
        ticker = row["ticker"]
        weight = float(row.get("target_weight"))
        identity = {
            "security_id": str(row.get("security_id") or ""),
            "issuer_id": str(row.get("issuer_id") or ""),
            "risk_chain": str(row.get("risk_chain") or ""),
        }
        if (
            not math.isfinite(weight)
            or weight <= 0
            or any(not value or value != value.strip() for value in identity.values())
        ):
            raise NdxConditionalRepairBenchmarkError("original-eight row changed")
        weights[ticker] = weight
        chains[ticker] = identity["risk_chain"]
        identities[ticker] = identity
    if (
        not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12)
        or len({row["security_id"] for row in identities.values()}) != 8
        or len({row["issuer_id"] for row in identities.values()}) != 8
    ):
        raise NdxConditionalRepairBenchmarkError("original-eight identity/weight changed")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {
        "dynamic_walkforward_manifest", "identity_manifest", "identity_projection"
    }:
        raise NdxConditionalRepairBenchmarkError("original-eight input registry changed")
    input_captures = {
        key: _verify_descriptor_input(root, value, f"original-eight {key}")
        for key, value in inputs.items()
    }
    return (
        capture,
        weights,
        chains,
        identities,
        {key: _capture_descriptor(value) for key, value in input_captures.items()},
        input_captures,
    )


def _load_prices(
    root: Path,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Mapping[str, Any]]]:
    bundle = root / PRICE_BUNDLE_RELATIVE
    manifest_capture = _capture(
        bundle / "manifest.json",
        expected_sha256=LOCKED_SOURCE_HASHES["price_bundle_manifest"],
    )
    inventory_capture = _capture(
        bundle / "execution_price_inventory.csv",
        expected_sha256=LOCKED_SOURCE_HASHES["price_inventory"],
    )
    manifest = _parse_json(manifest_capture, "price-bundle manifest")
    inventory = _parse_csv(inventory_capture, "price inventory")
    artifact = (manifest.get("artifacts") or {}).get("inventory") or {}
    if (
        manifest.get("manifest_type") != "ndx_cardinality_whole_lot_execution_price_bundle"
        or manifest.get("status") != "READY"
        or manifest.get("whole_lot_execution_use_only") is not True
        or manifest.get("return_data_read") is not False
        or manifest.get("fresh_oos_consumed") is not False
        or artifact.get("sha256") != inventory_capture["sha256"]
        or int(artifact.get("rows", -1)) != len(inventory)
        or Path(str(artifact.get("path") or "")).resolve() != inventory_capture["path"]
        or inventory["ticker"].astype(str).duplicated().any()
    ):
        raise NdxConditionalRepairBenchmarkError("price-bundle registry changed")
    reuse = (manifest.get("inputs") or {}).get("reuse_bundle_manifest")
    reuse_capture = _verify_descriptor_input(root, reuse, "price reuse bundle")
    by_ticker = inventory.set_index(inventory["ticker"].astype(str), drop=False)
    if not set(ORIGINAL8_TICKERS).issubset(by_ticker.index):
        raise NdxConditionalRepairBenchmarkError("original-eight price rows are missing")
    frames: dict[str, pd.Series] = {}
    raw_descriptors: dict[str, Any] = {}
    all_captures: dict[str, Mapping[str, Any]] = {
        "price_bundle_manifest": manifest_capture,
        "price_inventory": inventory_capture,
        "price_reuse_bundle_manifest": reuse_capture,
    }
    expected_dates: pd.DatetimeIndex | None = None
    for ticker in ORIGINAL8_TICKERS:
        row = by_ticker.loc[ticker]
        if isinstance(row, pd.DataFrame):
            raise NdxConditionalRepairBenchmarkError("duplicate price inventory ticker")
        price_path = _resolve_declared_path(root, row["path"], f"{ticker} price")
        sidecar_path = _resolve_declared_path(root, row["sidecar_path"], f"{ticker} sidecar")
        if sidecar_path != Path(str(price_path) + ".manifest.json").resolve():
            raise NdxConditionalRepairBenchmarkError(f"{ticker} sidecar path changed")
        price_capture = _capture(price_path, expected_sha256=str(row["sha256"]))
        sidecar_capture = _capture(sidecar_path, expected_sha256=str(row["sidecar_sha256"]))
        frame = _parse_csv(price_capture, f"{ticker} price")
        sidecar = _parse_json(sidecar_capture, f"{ticker} price sidecar")
        if (
            str(row["status"]) != "FETCHED"
            or int(row["rows"]) != len(frame)
            or sidecar.get("content_sha256") != price_capture["sha256"]
            or int(sidecar.get("row_count", -1)) != len(frame)
            or sidecar.get("price_basis") != "unadjusted_nominal_trade_price"
            or sidecar.get("whole_lot_execution_use_only") is not True
            or sidecar.get("return_usage_allowed") is not False
        ):
            raise NdxConditionalRepairBenchmarkError(f"{ticker} price evidence changed")
        numeric = _validated_ohlcv(frame, ticker)
        dates = _strict_dates(frame["Date"], f"{ticker} price")
        close = numeric["Close"]
        series = pd.Series(close.to_numpy(dtype=float), index=dates, name=ticker)
        series = series.loc[WINDOW_START:WINDOW_END]
        if len(series) != EXPECTED_SESSIONS:
            raise NdxConditionalRepairBenchmarkError(f"{ticker} session coverage changed")
        if expected_dates is None:
            expected_dates = series.index
        elif not series.index.equals(expected_dates):
            raise NdxConditionalRepairBenchmarkError("original-eight calendars differ")
        frames[ticker] = series
        all_captures[f"price_{ticker}"] = price_capture
        all_captures[f"price_sidecar_{ticker}"] = sidecar_capture
        raw_descriptors[ticker] = {
            "price": _capture_descriptor(price_capture),
            "sidecar": _capture_descriptor(sidecar_capture),
            "source_mode": str(row["source_mode"]),
        }
    prices = pd.DataFrame(frames, index=expected_dates)
    if (
        prices.index[0].date().isoformat() != WINDOW_START
        or prices.index[-1].date().isoformat() != WINDOW_END
        or prices.isna().any().any()
    ):
        raise NdxConditionalRepairBenchmarkError("same-calendar price panel changed")
    source_registry = {
        "price_bundle_manifest": _capture_descriptor(manifest_capture),
        "price_inventory": _capture_descriptor(inventory_capture),
        "price_reuse_bundle_manifest": _capture_descriptor(reuse_capture),
        "ticker_sources": raw_descriptors,
    }
    return prices, source_registry, all_captures


def _load_target_nav(
    root: Path, sessions: pd.DatetimeIndex
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    path = (root / TARGET_NAV_RELATIVE).resolve()
    try:
        full_raw = path.read_bytes()
    except OSError as exc:
        raise NdxConditionalRepairBenchmarkError("cannot read 012922 NAV source") from exc
    if (
        len(full_raw) < TARGET_NAV_PREFIX_BYTES
        or full_raw[TARGET_NAV_PREFIX_BYTES - 1:TARGET_NAV_PREFIX_BYTES] != b"\n"
    ):
        raise NdxConditionalRepairBenchmarkError("012922 historical prefix boundary changed")
    prefix = full_raw[:TARGET_NAV_PREFIX_BYTES]
    if _sha256(prefix) != LOCKED_SOURCE_HASHES["target_nav_historical_prefix"]:
        raise NdxConditionalRepairBenchmarkError(
            "012922 exact historical byte prefix is unavailable"
        )
    capture = {"path": path, "raw": prefix, "sha256": _sha256(prefix)}
    frame = _parse_csv(capture, "012922 historical prefix")
    if set(frame.columns) != {"Date", "UnitNav", "AccumNav", "DailyPct", "Close"}:
        raise NdxConditionalRepairBenchmarkError("012922 prefix schema changed")
    dates = _strict_dates(frame["Date"], "012922 NAV")
    close = pd.to_numeric(frame["Close"], errors="coerce")
    if close.isna().any() or (~close.map(lambda value: math.isfinite(float(value)) and float(value) > 0)).any():
        raise NdxConditionalRepairBenchmarkError("012922 close is invalid")
    nav = pd.DataFrame({"source_date": dates, "close": close.to_numpy(dtype=float)})
    session_frame = pd.DataFrame({"session_date": sessions})
    aligned = pd.merge_asof(
        session_frame,
        nav,
        left_on="session_date",
        right_on="source_date",
        direction="backward",
        allow_exact_matches=True,
    )
    if aligned[["source_date", "close"]].isna().any().any():
        raise NdxConditionalRepairBenchmarkError("012922 backward-asof alignment is incomplete")
    if (aligned["source_date"] > aligned["session_date"]).any():
        raise NdxConditionalRepairBenchmarkError("012922 future NAV value was used")
    aligned["lag_days"] = (aligned["session_date"] - aligned["source_date"]).dt.days
    normalized = aligned["close"] / float(aligned.iloc[0]["close"])
    aligned["normalized_close"] = normalized
    if (
        len(aligned) != EXPECTED_SESSIONS
        or float(aligned.iloc[0]["close"]) != 0.8772
        or not math.isclose(float(normalized.iloc[0]), 1.0, rel_tol=0.0, abs_tol=1e-15)
        or int((aligned["lag_days"] > 0).sum()) != 28
    ):
        raise NdxConditionalRepairBenchmarkError("012922 alignment contract changed")
    descriptor = {
        "path": path.as_posix(),
        "prefix_bytes": TARGET_NAV_PREFIX_BYTES,
        "prefix_sha256": capture["sha256"],
        "source_file_changed_from_historical_prefix": len(full_raw) != len(prefix),
        "historical_bytes_recoverable": True,
        "recovery_mode": "EXACT_HASH_MATCHED_COMPLETE_ROW_PREFIX",
    }
    return aligned, descriptor, capture


def _assert_captures_unchanged(captures: Mapping[str, Mapping[str, Any]]) -> None:
    for label, capture in captures.items():
        path = Path(capture["path"])
        raw = path.read_bytes()
        expected_raw = capture["raw"]
        if label == "target_nav_historical_prefix":
            raw = raw[:len(expected_raw)]
        if raw != expected_raw:
            raise NdxConditionalRepairBenchmarkError(
                f"benchmark source changed during calculation: {label}"
            )


def _capture_inputs(root: Path) -> dict[str, Any]:
    (
        original, weights, chains, identities, original_inputs,
        original_input_captures,
    ) = _load_original8(root)
    prices, price_registry, price_captures = _load_prices(root)
    target, target_descriptor, target_capture = _load_target_nav(root, prices.index)
    code_captures = {
        key: _capture(root / relative)
        for key, relative in {
            "benchmark_module": MODULE_RELATIVE,
            "benchmark_cli": SCRIPT_RELATIVE,
            "repair_path": REPAIR_PATH_RELATIVE,
            "repair_kernel": REPAIR_KERNEL_RELATIVE,
            "source_runner": SOURCE_RUNNER_RELATIVE,
        }.items()
    }
    captures = {
        "original8_manifest": original,
        "target_nav_historical_prefix": target_capture,
        **{
            f"original8_input_{key}": value
            for key, value in original_input_captures.items()
        },
        **price_captures,
        **{f"code_{key}": value for key, value in code_captures.items()},
    }
    payload = {
        "schema_version": 1,
        "plan_type": "ndx_conditional_repair_same_calendar_dual_benchmark",
        "status": "LOCKED_HISTORICAL_RESEARCH_PLAN",
        "research_track": "portfolio_optimization_execution_diagnostic",
        "session_window": {
            "start": WINDOW_START,
            "end": WINDOW_END,
            "sessions": EXPECTED_SESSIONS,
            "cadence_sessions": CADENCE_SESSIONS,
            "rebalance_count": EXPECTED_REBALANCES,
        },
        "execution_contract": dict(CONTRACT),
        "original8": {
            "manifest": _capture_descriptor(original),
            "definition_sha256": _parse_json(original, "original-eight manifest")["definition_sha256"],
            "weights": weights,
            "risk_chains": chains,
            "identities": identities,
            "upstream_inputs": original_inputs,
            "identity_evidence_limitation": {
                "status": "RETROSPECTIVE_RESEARCH_ATTRIBUTION_NOT_CONTEMPORANEOUS_PIT",
                "control_frozen_generated_at": _parse_json(
                    original, "original-eight manifest"
                )["generated_at"],
                "projected_identity_date": _parse_json(
                    original, "original-eight manifest"
                )["identity_projection_date"],
                "tsm_identity_source": "REVIEWED_INCUMBENT_OVERLAY",
                "candidate_selection_evidence_claimed": False,
            },
        },
        "prices": price_registry,
        "target_012922": {
            **target_descriptor,
            "alignment": "BACKWARD_ASOF_ON_EACH_STOCK_SESSION_NO_FUTURE_VALUES",
            "currency_basis": "REPORTED_CNY_NAV_NO_USD_FX_ADJUSTMENT",
            "execution_comparability": "RETURN_DRAWDOWN_REFERENCE_NOT_TRADABLE_USD_EXECUTION_PATH",
        },
        "code_bindings": {
            key: _capture_descriptor(value) for key, value in code_captures.items()
        },
        "candidate_set_or_weight_search_run": False,
        "benchmark_weights_changed": False,
        "fresh_oos_consumed": False,
        "cross_benchmark_currency_adjustment_performed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    plan = {**payload, "plan_fingerprint": _canonical_sha256(payload)}
    return {
        "plan": plan,
        "prices": prices,
        "target": target,
        "weights": weights,
        "chains": chains,
        "captures": captures,
    }


def build_conditional_repair_benchmark_plan(
    *, repository_root: str | Path
) -> dict[str, Any]:
    captured = _capture_inputs(Path(repository_root).resolve())
    _assert_captures_unchanged(captured["captures"])
    return captured["plan"]


def _target_result(aligned: pd.DataFrame) -> dict[str, Any]:
    normalized = aligned["normalized_close"].astype(float)
    drawdown = 1.0 - normalized / normalized.cummax()
    records = [
        {
            "session_date": row.session_date.date().isoformat(),
            "source_date": row.source_date.date().isoformat(),
            "close": float(row.close),
            "normalized_close": float(row.normalized_close),
            "lag_days": int(row.lag_days),
        }
        for row in aligned.itertuples(index=False)
    ]
    return {
        "benchmark_id": "target_012922_backward_asof_v1",
        "session_count": len(records),
        "start_close": float(aligned.iloc[0]["close"]),
        "end_close": float(aligned.iloc[-1]["close"]),
        "path_return": float(normalized.iloc[-1] - 1.0),
        "max_drawdown_with_initial_normalized_peak": float(drawdown.max()),
        "sessions_without_direct_nav": int((aligned["lag_days"] > 0).sum()),
        "maximum_source_lag_days": int(aligned["lag_days"].max()),
        "source_date_trace_sha256": _canonical_sha256(records),
        "source_date_trace": records,
        "alignment": "BACKWARD_ASOF_ON_EACH_STOCK_SESSION_NO_FUTURE_VALUES",
        "currency_basis": "REPORTED_CNY_NAV_NO_USD_FX_ADJUSTMENT",
        "not_an_execution_path": True,
    }


def _rebuild_report(captured: Mapping[str, Any]) -> dict[str, Any]:
    prices = captured["prices"]
    weights = captured["weights"]
    schedule = [
        (date, dict(weights)) for date in prices.index[::CADENCE_SESSIONS]
    ]
    if len(schedule) != EXPECTED_REBALANCES:
        raise NdxConditionalRepairBenchmarkError("benchmark schedule changed")
    original8, ledger = simulate_conditional_whole_lot_repair_path(
        prices,
        schedule,
        risk_chain_by_ticker=captured["chains"],
        max_repair_evaluations=262_144,
        **CONTRACT,
    )
    if not original8.get("search_complete") or original8.get("summary") is None:
        raise NdxConditionalRepairBenchmarkError("original-eight repair path is incomplete")
    ledger_records = ledger.to_dict("records")
    target = _target_result(captured["target"])
    corrected_drawdown = original8["daily_risk_audit"][
        "corrected_drawdown_with_initial_capital_peak"
    ]
    result = {
        "schema_version": 1,
        "result_type": "ndx_conditional_repair_same_calendar_dual_benchmark",
        "status": "COMPLETE_RESEARCH_ONLY",
        "plan": captured["plan"],
        "original8_execution_control": {
            "status": original8["status"],
            "execution_eligible": original8["execution_eligible"],
            "summary": original8["summary"],
            "daily_risk_audit": original8["daily_risk_audit"],
            "repair_invocation_count": original8["repair_invocation_count"],
            "successful_repair_count": original8["successful_repair_count"],
            "unresolved_rebalance_count": original8["unresolved_rebalance_count"],
            "rebalance_ledger_sha256": _canonical_sha256(ledger_records),
            "rebalance_ledger": ledger_records,
            "identity_evidence_limitation": captured["plan"]["original8"][
                "identity_evidence_limitation"
            ],
        },
        "target_012922_reference": target,
        "same_calendar_comparison": {
            "return_original8_minus_012922": float(
                original8["summary"]["whole_lot_path_return_net"] - target["path_return"]
            ),
            "corrected_drawdown_cost_original8_minus_012922": float(
                corrected_drawdown - target["max_drawdown_with_initial_normalized_peak"]
            ),
            "currency_adjusted": False,
            "paired_execution_claimed": False,
        },
        "candidate_set_or_weight_search_run": False,
        "ranking_or_winner_selected": False,
        "fresh_oos_consumed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    return {**result, "result_sha256": _canonical_sha256(result)}


def build_conditional_repair_benchmark(
    *, repository_root: str | Path
) -> dict[str, Any]:
    captured = _capture_inputs(Path(repository_root).resolve())
    result = _rebuild_report(captured)
    _assert_captures_unchanged(captured["captures"])
    return result


def _resolve_output(root: Path, output_root: str | Path | None) -> Path:
    output = (
        Path(output_root).resolve()
        if output_root is not None
        else (root / OUTPUT_RELATIVE).resolve()
    )
    try:
        output.relative_to((root / "data/cache/research").resolve())
    except ValueError as exc:
        raise NdxConditionalRepairBenchmarkError(
            "benchmark output is outside research namespace"
        ) from exc
    return output


def write_conditional_repair_benchmark(
    *, repository_root: str | Path, output_root: str | Path | None = None
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    output = _resolve_output(root, output_root)
    captured = _capture_inputs(root)
    report = _rebuild_report(captured)
    run_dir = output / "runs" / report["plan"]["plan_fingerprint"]
    report_raw = _json_bytes(report)
    manifest_payload = {
        "schema_version": 1,
        "manifest_type": "ndx_conditional_repair_same_calendar_dual_benchmark_bundle",
        "status": "COMPLETE_RESEARCH_ONLY",
        "plan_fingerprint": report["plan"]["plan_fingerprint"],
        "report": {
            "path": (run_dir / "report.json").resolve().as_posix(),
            "sha256": _sha256(report_raw),
        },
        "research_track": "portfolio_optimization_execution_diagnostic",
        "candidate_set_or_weight_search_run": False,
        "ranking_or_winner_selected": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    manifest = {**manifest_payload, "manifest_sha256": _canonical_sha256(manifest_payload)}
    artifacts = {
        run_dir / "report.json": report_raw,
        run_dir / "manifest.json": _json_bytes(manifest),
    }
    with source_runner._single_instance_lock(run_dir / ".runner.lock"):
        _assert_captures_unchanged(captured["captures"])
        for path, raw in artifacts.items():
            if path.exists() and path.read_bytes() != raw:
                raise NdxConditionalRepairBenchmarkError(
                    "immutable benchmark artifact collision"
                )
        for path, raw in artifacts.items():
            if not path.exists():
                source_runner._atomic_write(path, raw)
    return manifest


def verify_conditional_repair_benchmark(
    *, repository_root: str | Path, output_root: str | Path | None = None
) -> dict[str, Any]:
    root = Path(repository_root).resolve()
    output = _resolve_output(root, output_root)
    captured = _capture_inputs(root)
    expected_report = _rebuild_report(captured)
    run_dir = output / "runs" / expected_report["plan"]["plan_fingerprint"]
    report_path = run_dir / "report.json"
    manifest_path = run_dir / "manifest.json"
    lock_path = run_dir / ".runner.lock"
    if not run_dir.is_dir() or not lock_path.is_file():
        raise NdxConditionalRepairBenchmarkError("benchmark bundle is missing")
    expected_report_raw = _json_bytes(expected_report)
    manifest_payload = {
        "schema_version": 1,
        "manifest_type": "ndx_conditional_repair_same_calendar_dual_benchmark_bundle",
        "status": "COMPLETE_RESEARCH_ONLY",
        "plan_fingerprint": expected_report["plan"]["plan_fingerprint"],
        "report": {"path": report_path.resolve().as_posix(), "sha256": _sha256(expected_report_raw)},
        "research_track": "portfolio_optimization_execution_diagnostic",
        "candidate_set_or_weight_search_run": False,
        "ranking_or_winner_selected": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }
    expected_manifest = {
        **manifest_payload,
        "manifest_sha256": _canonical_sha256(manifest_payload),
    }
    with source_runner._single_instance_lock(lock_path):
        _assert_captures_unchanged(captured["captures"])
        if not report_path.is_file() or report_path.read_bytes() != expected_report_raw:
            raise NdxConditionalRepairBenchmarkError("benchmark report does not rebuild")
        if (
            not manifest_path.is_file()
            or manifest_path.read_bytes() != _json_bytes(expected_manifest)
        ):
            raise NdxConditionalRepairBenchmarkError("benchmark manifest does not rebuild")
    return {
        "status": "VERIFIED_COMPLETE_RESEARCH_ONLY",
        "plan_fingerprint": expected_report["plan"]["plan_fingerprint"],
        "session_count": EXPECTED_SESSIONS,
        "rebalance_count": EXPECTED_REBALANCES,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


__all__ = [
    "NdxConditionalRepairBenchmarkError",
    "OUTPUT_RELATIVE",
    "build_conditional_repair_benchmark",
    "build_conditional_repair_benchmark_plan",
    "verify_conditional_repair_benchmark",
    "write_conditional_repair_benchmark",
]
