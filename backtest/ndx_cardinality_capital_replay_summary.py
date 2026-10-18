"""Rebuild a reviewable historical summary of the completed $25k replay.

The source replay is historical training evidence.  This module never runs a
search, reads a broker account, or grants admission.  It deliberately keeps
different search/evaluator lineages and universe tracks in separate groups.
"""
from __future__ import annotations

import csv
import base64
import hashlib
import json
import math
import os
import shutil
import uuid
from collections import Counter
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any, Mapping, Sequence


TOP_MANIFEST_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_replay_v1/manifest.json"
)
CAPITAL_MANIFEST_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_sensitivity_v1/manifest.json"
)
SHORTLIST_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_sensitivity_v1/"
    "capital_replay_shortlist.csv"
)
OUTPUT_RELATIVE = Path(
    "data/cache/research/ndx_cardinality_capital_replay_summary_v1"
)

ROLE_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("RETURN", "return_p50", False),
    ("BAD_TAIL", "return_p10", False),
    ("DRAWDOWN", "max_drawdown_p90", True),
    ("012922_DISTANCE", "target_012922_distance", True),
)
USER_PREFERENCE_TICKERS = ("AMAT", "AVGO", "CDNS", "GOOG")
USER_PREFERENCE_WEIGHT = 0.25

JOB_COLUMNS = {
    "source_batch", "universe_track", "selection_date", "holding_counts",
    "shortlist_rows", "output_dir", "status",
}
CHILD_INPUT_NAMES = {
    "spec", "input_readiness_manifest", "security_lifecycle",
    "execution_price_manifest", "execution_price_inventory", "membership_audit",
    "identity_audit", "job_audit", "target_nav", "state", "config",
}
CHILD_ARTIFACT_NAMES = {
    "candidates", "frontiers", "price_inventory", "lifecycle_coverage", "workbook",
}

IDENTITY_COLUMNS = {
    "selection_date", "decision_data_end", "portfolio_id", "holding_count",
    "weight_spec", "tickers", "weights", "security_ids", "issuer_ids", "risk_chains",
}
ROLLING_COLUMNS = {
    "rolling_fit_window_count", "fit_strictly_before_evaluation",
    "last_fit_evaluation_boundary", "return_p50", "return_p10",
    "max_drawdown_p50", "max_drawdown_p90",
    "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent",
    "paired_drawdown_cost_p50_vs_incumbent",
    "paired_drawdown_cost_p90_vs_incumbent", "return_p50_vs_012922",
    "return_p10_vs_012922", "max_drawdown_p50_vs_012922",
    "max_drawdown_p90_vs_012922", "target_012922_distance", "turnover",
    "initial_turnover", "initial_transaction_cost", "transaction_cost", "return_basis",
}
RISK_COLUMNS = {
    "risk_chain_top1", "risk_chain_top1_p50", "risk_chain_top1_p90",
    "risk_chain_top3", "risk_chain_top3_p50", "risk_chain_top3_p90", "issuer_top1",
    "weight_top1_p50", "weight_top1_p90", "weight_top3_p50", "weight_top3_p90",
    "weight_top3_max", "effective_n", "effective_n_min", "effective_n_p10",
    "effective_n_p50", "declared_max_single_weight", "declared_max_single_passed",
    "declared_security_top3_weight_cap", "declared_security_top3_weight_passed",
    "declared_risk_chain_top1_weight_cap", "declared_risk_chain_top1_weight_passed",
    "declared_minimum_effective_n", "declared_effective_n_passed",
}
EXECUTION_COLUMNS = {
    "portfolio_cash_usd", "minimum_cash_buffer_usd", "liquidity_constraint_passed",
    "whole_lot_executable_all_windows", "whole_lot_rebalance_count",
    "whole_lot_initial_shares", "whole_lot_terminal_shares",
    "whole_lot_share_change_count", "whole_lot_total_trade_notional_usd",
    "whole_lot_total_transaction_cost_usd", "whole_lot_min_cash_usd",
    "whole_lot_cash_buffer_preserved", "whole_lot_constraints_preserved_all_days",
    "whole_lot_terminal_value_usd", "whole_lot_path_return_net",
    "whole_lot_path_max_drawdown", "whole_lot_rebalance_trace_sha256",
    "whole_lot_execution_mode", "declared_constraints_passed",
    "constraint_failure_reasons", "search_mode", "promotion_allowed",
}
REQUIRED_CANDIDATE_COLUMNS = (
    IDENTITY_COLUMNS | ROLLING_COLUMNS | RISK_COLUMNS | EXECUTION_COLUMNS
)

ROLLING_NUMBER_COLUMNS = (
    "return_p50", "return_p10", "max_drawdown_p50", "max_drawdown_p90",
    "paired_return_p50_vs_incumbent", "paired_return_p10_vs_incumbent",
    "paired_drawdown_cost_p50_vs_incumbent",
    "paired_drawdown_cost_p90_vs_incumbent", "return_p50_vs_012922",
    "return_p10_vs_012922", "max_drawdown_p50_vs_012922",
    "max_drawdown_p90_vs_012922", "target_012922_distance", "turnover",
    "initial_turnover", "initial_transaction_cost", "transaction_cost",
)
RISK_NUMBER_COLUMNS = (
    "risk_chain_top1", "risk_chain_top1_p50", "risk_chain_top1_p90",
    "risk_chain_top3", "risk_chain_top3_p50", "risk_chain_top3_p90", "issuer_top1",
    "weight_top1_p50", "weight_top1_p90", "weight_top3_p50", "weight_top3_p90",
    "weight_top3_max", "effective_n", "effective_n_min", "effective_n_p10",
    "effective_n_p50", "declared_max_single_weight",
    "declared_security_top3_weight_cap", "declared_risk_chain_top1_weight_cap",
    "declared_minimum_effective_n",
)
EXECUTION_NUMBER_COLUMNS = (
    "portfolio_cash_usd", "minimum_cash_buffer_usd", "whole_lot_rebalance_count",
    "whole_lot_share_change_count", "whole_lot_total_trade_notional_usd",
    "whole_lot_total_transaction_cost_usd", "whole_lot_min_cash_usd",
    "whole_lot_terminal_value_usd", "whole_lot_path_return_net",
    "whole_lot_path_max_drawdown",
)
BOOLEAN_COLUMNS = (
    "fit_strictly_before_evaluation", "declared_max_single_passed",
    "declared_security_top3_weight_passed", "declared_risk_chain_top1_weight_passed",
    "declared_effective_n_passed", "liquidity_constraint_passed",
    "whole_lot_executable_all_windows", "whole_lot_cash_buffer_preserved",
    "whole_lot_constraints_preserved_all_days", "declared_constraints_passed",
    "promotion_allowed",
)


class NdxCardinalityCapitalReplaySummaryError(ValueError):
    """Raised when the historical replay evidence cannot be safely summarized."""


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _read_json_bytes(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"cannot read {label}: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} must be a mapping")
    return raw, value


def _inside(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"{label} escapes repository root"
        ) from exc
    return resolved


def _descriptor(
    value: Any, *, expected: Path, label: str, require_current_hash: bool = True,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in ({"path", "sha256"}, {"path", "sha256", "rows"}):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} descriptor is invalid")
    path = Path(str(value.get("path") or "")).resolve()
    if path != expected.resolve():
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} path is not canonical")
    expected_hash = str(value.get("sha256") or "")
    if len(expected_hash) != 64:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} hash is invalid")
    exists = path.is_file()
    current_hash = _file_sha256(path) if exists else None
    matches = bool(exists and current_hash == expected_hash)
    if require_current_hash and not matches:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} hash changed")
    return {
        "path": path.as_posix(),
        "historical_sha256": expected_hash,
        "current_file_exists": exists,
        "current_hash_matches_historical": matches,
    }


def _verified_descriptor_bytes(
    value: Any, *, expected: Path, label: str,
) -> tuple[dict[str, Any], bytes]:
    """Read a result artifact once, then bind both hash and parser to those bytes."""

    if (
        not isinstance(value, Mapping)
        or set(value) not in ({"path", "sha256"}, {"path", "sha256", "rows"})
        or Path(str(value.get("path") or "")).resolve() != expected.resolve()
    ):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} descriptor is invalid")
    historical_hash = str(value.get("sha256") or "")
    if len(historical_hash) != 64:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} hash is invalid")
    try:
        raw = expected.read_bytes()
    except OSError as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"cannot read {label}: {expected}"
        ) from exc
    if _sha256_bytes(raw) != historical_hash:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} hash changed")
    return ({
        "path": expected.resolve().as_posix(),
        "historical_sha256": historical_hash,
        "current_file_exists": True,
        "current_hash_matches_historical": True,
    }, raw)


def _observed_descriptor_bytes(
    value: Any, *, expected: Path, label: str,
) -> tuple[dict[str, Any], bytes | None]:
    """Observe a mutable historical input once without masking hash drift."""

    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256"}
        or Path(str(value.get("path") or "")).resolve() != expected.resolve()
    ):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} descriptor is invalid")
    historical_hash = str(value.get("sha256") or "")
    if len(historical_hash) != 64:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} hash is invalid")
    try:
        raw = expected.read_bytes()
    except OSError:
        raw = None
    current_hash = _sha256_bytes(raw) if raw is not None else None
    matches = bool(raw is not None and current_hash == historical_hash)
    return ({
        "path": expected.resolve().as_posix(),
        "historical_sha256": historical_hash,
        "current_file_exists": raw is not None,
        "current_hash_matches_historical": matches,
    }, raw)


def _exact_historical_csv_prefix(
    current_raw: bytes, historical_sha256: str, label: str,
) -> bytes | None:
    """Recover only a byte-exact, complete-line prefix; never reserialize rows."""

    digest = hashlib.sha256()
    position = 0
    for line in current_raw.splitlines(keepends=True):
        digest.update(line)
        position += len(line)
        if digest.hexdigest() != historical_sha256:
            continue
        candidate = current_raw[:position]
        fields, rows = _csv_rows(candidate, label)
        if not fields or not rows or not candidate.endswith((b"\n", b"\r")):
            raise NdxCardinalityCapitalReplaySummaryError(
                f"{label} historical prefix is not a complete CSV row boundary"
            )
        return candidate
    return None


def _csv_rows(raw: bytes, label: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise NdxCardinalityCapitalReplaySummaryError(f"cannot parse {label}") from exc
    fields = list(reader.fieldnames or [])
    if not fields or len(fields) != len(set(fields)):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} columns are invalid")
    return fields, rows


def _boolean(value: object, label: str) -> bool:
    if value == "True" or value is True:
        return True
    if value == "False" or value is False:
        return False
    raise NdxCardinalityCapitalReplaySummaryError(f"{label} must be boolean")


def _number(value: object, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} is not numeric") from exc
    if not math.isfinite(result):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} is not finite")
    return result


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    result = _number(value, label)
    if not result.is_integer() or result < minimum:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} is not a valid integer")
    return int(result)


def _iso_date(value: object, label: str) -> date:
    text = str(value or "")
    try:
        result = date.fromisoformat(text)
    except ValueError as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"{label} is not a strict ISO date"
        ) from exc
    if result.isoformat() != text:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"{label} is not a strict ISO date"
        )
    return result


def _fit_evaluation_boundary(value: object) -> tuple[date, date]:
    text = str(value or "")
    if text.count("<") != 1:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate last_fit_evaluation_boundary must be FIT_END<EVALUATION_START"
        )
    fit_end_text, evaluation_start_text = text.split("<")
    fit_end = _iso_date(fit_end_text, "candidate last fit end")
    evaluation_start = _iso_date(
        evaluation_start_text, "candidate last evaluation start"
    )
    if fit_end >= evaluation_start:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate last fit/evaluation boundary is not strictly ordered"
        )
    return fit_end, evaluation_start


def _items(value: object, label: str) -> list[str]:
    result = [item.strip() for item in str(value or "").split(";") if item.strip()]
    if not result or len(result) != len(set(result)):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} is empty or duplicated")
    return result


def _sequence_items(value: object, label: str) -> list[str]:
    result = [item.strip() for item in str(value or "").split(";") if item.strip()]
    if not result:
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} is empty")
    return result


def _weights(value: object, tickers: Sequence[str], label: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in _items(value, label):
        ticker, separator, raw = item.rpartition(":")
        if not separator or not ticker or ticker in result:
            raise NdxCardinalityCapitalReplaySummaryError(f"{label} is malformed")
        weight = _number(raw, label)
        if weight <= 0.0 or weight > 1.0:
            raise NdxCardinalityCapitalReplaySummaryError(f"{label} is outside (0, 1]")
        result[ticker] = weight
    if list(result) != list(tickers) or not math.isclose(
        sum(result.values()), 1.0, abs_tol=1e-6
    ):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} does not match tickers")
    return result


def _shares(value: object, tickers: Sequence[str], label: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in _items(value, label):
        ticker, separator, raw = item.rpartition(":")
        if not separator or not ticker or ticker in result:
            raise NdxCardinalityCapitalReplaySummaryError(f"{label} is malformed")
        result[ticker] = _integer(raw, label)
    if list(result) != list(tickers):
        raise NdxCardinalityCapitalReplaySummaryError(f"{label} does not match tickers")
    return result


def _source_lineages(
    capital: Mapping[str, Any], *, repository_root: Path,
) -> dict[str, dict[str, Any]]:
    if (
        capital.get("schema_version") != 1
        or capital.get("manifest_type") != "ndx_cardinality_capital_sensitivity"
        or capital.get("research_track") != "portfolio_optimization"
        or capital.get("migration_control_included") is not False
        or capital.get("cross_runner_semantics_compatible") is not False
        or capital.get("cross_runner_merge_allowed") is not False
        or float(capital.get("target_replay_cash_usd") or 0.0) != 25_000.0
        or float(capital.get("minimum_cash_buffer_usd") or 0.0) != 100.0
        or float(capital.get("transaction_cost_bps") or 0.0) != 10.0
        or capital.get("fresh_oos_consumed") is not False
        or capital.get("promotion_allowed") is not False
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            "capital sensitivity safety contract changed"
        )
    sources = capital.get("source_runs")
    if not isinstance(sources, list) or not sources:
        raise NdxCardinalityCapitalReplaySummaryError("capital source runs are missing")
    result: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise NdxCardinalityCapitalReplaySummaryError("capital source run is invalid")
        batch = str(source.get("source_batch") or "")
        if not batch or batch in result:
            raise NdxCardinalityCapitalReplaySummaryError("capital source batch is duplicated")
        semantics = source.get("evaluation_semantics")
        semantics_hash = str(source.get("evaluation_semantics_sha256") or "")
        if not isinstance(semantics, Mapping) or _canonical_sha256(semantics) != semantics_hash:
            raise NdxCardinalityCapitalReplaySummaryError(
                f"evaluation semantics hash changed: {batch}"
            )
        run_path = _inside(
            repository_root, Path(str(source.get("run_manifest") or "")),
            f"source run {batch}",
        )
        descriptor = _descriptor(
            {"path": run_path.as_posix(), "sha256": source.get("run_manifest_sha256")},
            expected=run_path, label=f"source run {batch}",
        )
        _, run = _read_json_bytes(run_path, f"source run {batch}")
        contract = run.get("run_contract")
        if (
            run.get("manifest_type") != "ndx_cardinality_real_training_runner"
            or run.get("research_track") != "portfolio_optimization"
            or run.get("migration_control_included") is not False
            or run.get("failed") != 0
            or run.get("fresh_oos_consumed") is not False
            or run.get("promotion_allowed") is not False
            or not isinstance(contract, Mapping)
        ):
            raise NdxCardinalityCapitalReplaySummaryError(
                f"source runner boundary changed: {batch}"
            )
        search_classes = contract.get("job_search_classes")
        if not isinstance(search_classes, list) or len(search_classes) != 1:
            raise NdxCardinalityCapitalReplaySummaryError(
                f"source runner search class is ambiguous: {batch}"
            )
        search_class = str(search_classes[0])
        for key, value in semantics.items():
            if key in contract and contract[key] != value:
                raise NdxCardinalityCapitalReplaySummaryError(
                    f"source runner semantics disagree: {batch}/{key}"
                )
        identity = (search_class, semantics_hash)
        if identity in identities:
            raise NdxCardinalityCapitalReplaySummaryError(
                "source evaluator lineage is duplicated"
            )
        identities.add(identity)
        result[batch] = {
            "source_batch": batch,
            "job_search_class": search_class,
            "evaluation_semantics_sha256": semantics_hash,
            "evaluation_semantics": dict(semantics),
            "source_run_contract": dict(contract),
            "source_run_manifest": descriptor,
        }
    if len({item["job_search_class"] for item in result.values()}) != len(result):
        raise NdxCardinalityCapitalReplaySummaryError(
            "search classes cannot silently share source batches"
        )
    return result


def _verify_top(
    manifest_path: str | Path, repository_root: str | Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    root = Path(repository_root).resolve()
    source = Path(manifest_path).resolve()
    expected = (root / TOP_MANIFEST_RELATIVE).resolve()
    if source != expected:
        raise NdxCardinalityCapitalReplaySummaryError("top manifest path is not canonical")
    top_raw, top = _read_json_bytes(source, "capital replay top manifest")
    if (
        top.get("schema_version") != 1
        or top.get("manifest_type") != "ndx_cardinality_capital_replay_runner"
        or top.get("status") != "CAPITAL_REPLAY_COMPLETE"
        or top.get("research_track") != "portfolio_optimization"
        or top.get("migration_control_included") is not False
        or float(top.get("target_portfolio_cash_usd") or 0.0) != 25_000.0
        or int(top.get("planned_job_count") or -1) != int(top.get("completed") or -2)
        or int(top.get("failed") or 0) != 0
        or top.get("fresh_oos_consumed") is not False
        or top.get("promotion_allowed") is not False
        or top.get("live_mutation_allowed") is not False
    ):
        raise NdxCardinalityCapitalReplaySummaryError("top replay safety contract changed")
    inputs = top.get("inputs")
    artifacts = top.get("artifacts")
    if not isinstance(inputs, Mapping) or set(inputs) != {"capital_manifest", "shortlist"}:
        raise NdxCardinalityCapitalReplaySummaryError("top replay inputs changed")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"job_index"}:
        raise NdxCardinalityCapitalReplaySummaryError("top replay artifacts changed")
    capital_path = (root / CAPITAL_MANIFEST_RELATIVE).resolve()
    capital_descriptor = _descriptor(
        inputs["capital_manifest"], expected=capital_path, label="capital manifest",
    )
    _, capital = _read_json_bytes(capital_path, "capital sensitivity manifest")
    shortlist_path = (root / SHORTLIST_RELATIVE).resolve()
    shortlist_descriptor = _descriptor(
        inputs["shortlist"], expected=shortlist_path, label="capital shortlist",
    )
    capital_shortlist = ((capital.get("artifacts") or {}).get("shortlist") or {})
    if (
        str(capital_shortlist.get("sha256") or "")
        != shortlist_descriptor["historical_sha256"]
        or int(capital_shortlist.get("rows") or -1)
        != int((capital.get("counts") or {}).get("capital_replay_shortlist_rows") or -2)
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            "capital shortlist lineage is inconsistent"
        )
    lineages = _source_lineages(capital, repository_root=root)
    index_path = expected.parent / "job_index.csv"
    index_descriptor = _descriptor(
        artifacts["job_index"], expected=index_path, label="capital replay job index",
    )
    index_raw = index_path.read_bytes()
    fields, jobs = _csv_rows(index_raw, "capital replay job index")
    if set(fields) != JOB_COLUMNS or len(jobs) != int(top["planned_job_count"]):
        raise NdxCardinalityCapitalReplaySummaryError("job index schema/count changed")
    evidence = {
        "top_manifest": {
            "path": source.as_posix(), "sha256": _sha256_bytes(top_raw),
        },
        "capital_manifest": capital_descriptor,
        "shortlist": shortlist_descriptor,
        "job_index": index_descriptor,
    }
    return top, lineages, jobs, evidence


def _validate_candidate(
    raw: Mapping[str, str], *, selection_date: str, training_end: str,
) -> dict[str, Any]:
    booleans = {
        column: _boolean(raw.get(column), f"candidate {column}")
        for column in BOOLEAN_COLUMNS
    }
    tickers = _items(raw.get("tickers"), "candidate tickers")
    securities = _items(raw.get("security_ids"), "candidate security_ids")
    issuers = _items(raw.get("issuer_ids"), "candidate issuer_ids")
    # Several issuers may legitimately map to the same historical contract risk
    # chain.  Security and issuer identities must remain unique; risk labels need
    # only preserve ticker-aligned cardinality.
    risk_chains = _sequence_items(raw.get("risk_chains"), "candidate risk_chains")
    holding_count = _integer(raw.get("holding_count"), "candidate holding_count", minimum=1)
    if not (
        holding_count == len(tickers) == len(securities) == len(issuers) == len(risk_chains)
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate identity cardinalities disagree"
        )
    weights = _weights(raw.get("weights"), tickers, "candidate weights")
    initial_shares = _shares(
        raw.get("whole_lot_initial_shares"), tickers, "candidate initial shares"
    )
    terminal_shares = _shares(
        raw.get("whole_lot_terminal_shares"), tickers, "candidate terminal shares"
    )
    if raw.get("selection_date") != selection_date or raw.get("decision_data_end") != training_end:
        raise NdxCardinalityCapitalReplaySummaryError("candidate time coordinate changed")
    selection_day = _iso_date(selection_date, "candidate selection_date")
    training_day = _iso_date(training_end, "candidate decision_data_end")
    last_fit_day, last_evaluation_start_day = _fit_evaluation_boundary(
        raw.get("last_fit_evaluation_boundary")
    )
    if not (last_fit_day < last_evaluation_start_day <= training_day < selection_day):
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate training coordinate is not strictly before selection"
        )
    if not str(raw.get("portfolio_id") or "").strip() or not str(raw.get("weight_spec") or "").strip():
        raise NdxCardinalityCapitalReplaySummaryError("candidate identity is blank")
    if raw.get("return_basis") != "NET_OF_MODELED_ENTRY_TURNOVER_COST":
        raise NdxCardinalityCapitalReplaySummaryError("candidate return basis changed")
    if raw.get("search_mode") != "LOCKED_CANDIDATE_CAPITAL_REPLAY":
        raise NdxCardinalityCapitalReplaySummaryError("candidate replay mode changed")
    if _boolean(raw.get("promotion_allowed"), "candidate promotion_allowed"):
        raise NdxCardinalityCapitalReplaySummaryError("candidate promotion boundary changed")
    rolling = {key: _number(raw.get(key), f"candidate {key}") for key in ROLLING_NUMBER_COLUMNS}
    risk = {key: _number(raw.get(key), f"candidate {key}") for key in RISK_NUMBER_COLUMNS}
    execution = {
        key: _number(raw.get(key), f"candidate {key}")
        for key in EXECUTION_NUMBER_COLUMNS
    }
    if any(risk[key] < 0.0 for key in risk) or any(
        rolling[key] < 0.0 for key in ("max_drawdown_p50", "max_drawdown_p90", "target_012922_distance")
    ):
        raise NdxCardinalityCapitalReplaySummaryError("candidate risk metric is negative")
    if not math.isclose(execution["portfolio_cash_usd"], 25_000.0, abs_tol=1e-9):
        raise NdxCardinalityCapitalReplaySummaryError("candidate replay capital changed")
    if not math.isclose(execution["minimum_cash_buffer_usd"], 100.0, abs_tol=1e-9):
        raise NdxCardinalityCapitalReplaySummaryError("candidate cash buffer changed")
    if raw.get("whole_lot_execution_mode") != "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES":
        raise NdxCardinalityCapitalReplaySummaryError("candidate whole-lot mode changed")
    if len(str(raw.get("whole_lot_rebalance_trace_sha256") or "")) != 64:
        raise NdxCardinalityCapitalReplaySummaryError("candidate trace hash is invalid")
    try:
        int(str(raw.get("whole_lot_rebalance_trace_sha256")), 16)
    except ValueError as exc:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate trace hash is invalid"
        ) from exc
    declared = booleans["declared_constraints_passed"]
    executable = booleans["whole_lot_executable_all_windows"]
    preserved = booleans["whole_lot_constraints_preserved_all_days"]
    liquidity = booleans["liquidity_constraint_passed"]
    cash_preserved = booleans["whole_lot_cash_buffer_preserved"]
    fit_before_evaluation = booleans["fit_strictly_before_evaluation"]
    if not fit_before_evaluation:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate fit is not strictly before evaluation"
        )
    component_constraints = all(booleans[key] for key in (
        "declared_max_single_passed", "declared_security_top3_weight_passed",
        "declared_risk_chain_top1_weight_passed", "declared_effective_n_passed",
    ))
    if declared and not component_constraints:
        raise NdxCardinalityCapitalReplaySummaryError(
            "aggregate declared constraint status contradicts its components"
        )
    for key in (
        "portfolio_cash_usd", "minimum_cash_buffer_usd",
        "whole_lot_total_trade_notional_usd",
        "whole_lot_total_transaction_cost_usd", "whole_lot_min_cash_usd",
    ):
        if execution[key] < 0.0:
            raise NdxCardinalityCapitalReplaySummaryError(
                f"candidate {key} is negative"
            )
    for key in ("whole_lot_rebalance_count", "whole_lot_share_change_count"):
        if not execution[key].is_integer():
            raise NdxCardinalityCapitalReplaySummaryError(
                f"candidate {key} is not an integer"
            )
        execution[key] = int(execution[key])
    expected_cost = execution["whole_lot_total_trade_notional_usd"] * 10.0 / 10_000.0
    if not math.isclose(
        execution["whole_lot_total_transaction_cost_usd"],
        expected_cost,
        rel_tol=1e-12,
        abs_tol=1e-8,
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate whole-lot transaction cost is inconsistent with 10 bps"
        )
    if not 0.0 <= execution["whole_lot_path_max_drawdown"] <= 1.0:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate whole-lot max drawdown is outside [0, 1]"
        )
    if execution["whole_lot_path_return_net"] < -1.0:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate whole-lot return is below -100%"
        )
    if execution["whole_lot_terminal_value_usd"] <= 0.0:
        raise NdxCardinalityCapitalReplaySummaryError(
            "candidate whole-lot terminal value is not positive"
        )
    source_reported_eligible = (
        declared and executable and preserved and cash_preserved and liquidity
    )
    if source_reported_eligible and (
        execution["whole_lot_min_cash_usd"] < execution["minimum_cash_buffer_usd"]
        or sum(initial_shares.values()) <= 0
        or sum(terminal_shares.values()) <= 0
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            "source-reported eligible candidate has an impossible whole-lot path"
        )
    reasons = [
        item for item in str(raw.get("constraint_failure_reasons") or "").split(";") if item
    ]
    if not source_reported_eligible and not reasons:
        raise NdxCardinalityCapitalReplaySummaryError(
            "ineligible candidate lacks an explicit failure reason"
        )
    if source_reported_eligible and reasons:
        raise NdxCardinalityCapitalReplaySummaryError(
            "eligible candidate retains a failure reason"
        )
    return {
        "portfolio_id": str(raw["portfolio_id"]),
        "holding_count": holding_count,
        "weight_spec": str(raw["weight_spec"]),
        "tickers": tickers,
        "weights": weights,
        "security_ids": securities,
        "issuer_ids": issuers,
        "risk_chains": risk_chains,
        "rolling_fit_window_count": _integer(
            raw.get("rolling_fit_window_count"), "rolling fit window count", minimum=1
        ),
        "fit_strictly_before_evaluation": fit_before_evaluation,
        "last_fit_evaluation_boundary": str(raw.get("last_fit_evaluation_boundary") or ""),
        "rolling_training_statistics": rolling,
        "risk_statistics": risk,
        "continuous_whole_lot_path": {
            **execution,
            "initial_shares": initial_shares,
            "terminal_shares": terminal_shares,
            "cash_buffer_preserved": cash_preserved,
            "constraints_preserved_all_days": preserved,
            "executable_all_windows": executable,
            "execution_mode": str(raw["whole_lot_execution_mode"]),
            "rebalance_trace_sha256": str(raw["whole_lot_rebalance_trace_sha256"]),
        },
        "source_reported_replay_eligible": source_reported_eligible,
        "economic_path_independently_replayed_by_summary": False,
        "failure_reasons": reasons,
        "paired_fields_used_directly_not_recomputed_from_marginal_summaries": True,
    }


def _role_winner(candidates: Sequence[dict[str, Any]], spec: tuple[str, str, bool]) -> dict[str, Any]:
    role, metric, ascending = spec
    ordered = sorted(
        candidates,
        key=lambda item: (
            item["rolling_training_statistics"][metric]
            if ascending else -item["rolling_training_statistics"][metric],
            ";".join(item["tickers"]), item["weight_spec"], item["portfolio_id"],
        ),
    )
    winner = dict(ordered[0])
    winner["selection_role"] = role
    winner["role_metric"] = metric
    winner["role_direction"] = "MINIMUM" if ascending else "MAXIMUM"
    return winner


def _four_gate_dominates(candidate: Mapping[str, Any]) -> bool:
    # These are already paired row statistics.  Never substitute a difference
    # between independently summarized candidate/incumbent quantiles.
    rolling = candidate["rolling_training_statistics"]
    return bool(
        rolling["paired_return_p50_vs_incumbent"] > 0.0
        and rolling["paired_return_p10_vs_incumbent"] > 0.0
        and rolling["paired_drawdown_cost_p50_vs_incumbent"] <= 0.0
        and rolling["paired_drawdown_cost_p90_vs_incumbent"] <= 0.0
    )


def _user_preference_reference(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    matches = [
        candidate for candidate in candidates
        if tuple(candidate["tickers"]) == USER_PREFERENCE_TICKERS
        and all(
            math.isclose(
                candidate["weights"].get(ticker, -1.0),
                USER_PREFERENCE_WEIGHT,
                abs_tol=1e-10,
            )
            for ticker in USER_PREFERENCE_TICKERS
        )
    ]
    boundary = {
        "reference_type": "USER_PREFERENCE",
        "target_tickers": list(USER_PREFERENCE_TICKERS),
        "target_weights": {
            ticker: USER_PREFERENCE_WEIGHT for ticker in USER_PREFERENCE_TICKERS
        },
        "reference_is_fixed_answer": False,
        "reference_is_current_admission": False,
    }
    if not matches:
        return {**boundary, "status": "NOT_PRESENT_IN_LOCKED_REPLAY", "candidate": None}
    if len(matches) != 1:
        raise NdxCardinalityCapitalReplaySummaryError(
            "equal-weight USER_PREFERENCE reference is duplicated"
        )
    match = matches[0]
    return {
        **boundary,
        "status": (
            "PRESENT_SOURCE_REPORTED_REPLAY_ELIGIBLE"
            if match["source_reported_replay_eligible"]
            else "PRESENT_SOURCE_REPORTED_REPLAY_INELIGIBLE"
        ),
        "candidate": match,
    }


def _verify_child(
    job: Mapping[str, str], *, root: Path, replay_root: Path,
    shortlist_path: Path, shortlist_sha256: str, lineage: Mapping[str, Any],
) -> dict[str, Any]:
    batch = str(job["source_batch"])
    track = str(job["universe_track"])
    selection_date = str(job["selection_date"])
    if not batch or not track or len(selection_date) != 10:
        raise NdxCardinalityCapitalReplaySummaryError("job identity is invalid")
    holding_counts = [
        _integer(value, "job holding count", minimum=1)
        for value in _items(job["holding_counts"], "job holding counts")
    ]
    if holding_counts != sorted(set(holding_counts)):
        raise NdxCardinalityCapitalReplaySummaryError("job holding counts are not unique/sorted")
    if _integer(job["shortlist_rows"], "job shortlist rows", minimum=1) <= 0:
        raise NdxCardinalityCapitalReplaySummaryError("job shortlist is empty")
    if job["status"] not in {"COMPLETED", "RESUMED_COMPLETED"}:
        raise NdxCardinalityCapitalReplaySummaryError("top manifest contains an incomplete job")
    expected_dir = (replay_root / batch / track / selection_date).resolve()
    if Path(job["output_dir"]).resolve() != expected_dir:
        raise NdxCardinalityCapitalReplaySummaryError("job output path is not canonical")
    manifest_path = expected_dir / "manifest.json"
    manifest_raw, manifest = _read_json_bytes(manifest_path, "replay child manifest")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("manifest_type") != "ndx_cardinality_real_training_smoke"
        or manifest.get("status") != "TRAINING_DISCOVERY_ONLY_NOT_ADMISSION"
        or manifest.get("research_track") != "portfolio_optimization"
        or manifest.get("migration_control_included") is not False
        or manifest.get("universe_track") != track
        or manifest.get("selection_date") != selection_date
        or manifest.get("holding_count") != 0
        or list(manifest.get("holding_counts") or []) != holding_counts
        or manifest.get("candidate_replay_mode") is not True
        or float(manifest.get("portfolio_cash_usd") or 0.0) != 25_000.0
        or manifest.get("fit_strictly_before_selection") is not True
        or manifest.get("return_data_read") is not True
        or manifest.get("selection_date_or_later_returns_read") is not False
        or manifest.get("portfolio_returns_calculated") is not True
        or manifest.get("fresh_oos_consumed") is not False
        or manifest.get("promotion_allowed") is not False
        or manifest.get("live_config_changed") is not False
        or manifest.get("state_changed") is not False
        or manifest.get("today_advice_changed") is not False
        or manifest.get("whole_lot_execution_mode")
        != "CONTINUOUS_SELF_FINANCING_PERIODIC_REBALANCE_REAL_CLOSES"
        or manifest.get("whole_lot_execution_price_basis") != "unadjusted_nominal_trade_price"
        or manifest.get("adjusted_return_prices_used_for_whole_lot_shares") is not False
        or manifest.get("selection_date_or_later_execution_prices_used") is not False
        or manifest.get("whole_lot_shares_and_cash_carried_between_rebalances") is not True
        or manifest.get("whole_lot_transaction_costs_deducted_from_cash") is not True
        or manifest.get("whole_lot_constraints_checked_daily") is not True
    ):
        raise NdxCardinalityCapitalReplaySummaryError(
            f"child replay safety contract changed: {batch}/{track}/{selection_date}"
        )
    replay = manifest.get("candidate_replay_source")
    if (
        not isinstance(replay, Mapping)
        or Path(str(replay.get("path") or "")).resolve() != shortlist_path
        or replay.get("sha256") != shortlist_sha256
        or replay.get("source_batches") != [batch]
        or float(replay.get("target_portfolio_cash_usd") or 0.0) != 25_000.0
    ):
        raise NdxCardinalityCapitalReplaySummaryError("child replay source changed")
    audit = manifest.get("search_audit")
    if (
        not isinstance(audit, Mapping)
        or audit.get("search_mode") != "LOCKED_CANDIDATE_CAPITAL_REPLAY"
        or audit.get("search_exhaustive") is not False
        or audit.get("optimality_claim_allowed") is not False
        or audit.get("holding_counts") != holding_counts
    ):
        raise NdxCardinalityCapitalReplaySummaryError("child search audit changed")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != CHILD_INPUT_NAMES:
        raise NdxCardinalityCapitalReplaySummaryError("child source fields are incomplete")
    input_observations: dict[str, Any] = {}
    recovered_source_bytes: dict[str, bytes] = {}
    for name in sorted(CHILD_INPUT_NAMES):
        value = inputs[name]
        if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
            raise NdxCardinalityCapitalReplaySummaryError(
                f"child source descriptor is invalid: {name}"
            )
        source_path = _inside(root, Path(str(value.get("path") or "")), f"child input {name}")
        if name == "target_nav" and source_path != (
            root / "data/cache/funds/012922.csv"
        ).resolve():
            raise NdxCardinalityCapitalReplaySummaryError(
                "child target_nav is not the canonical 012922 source"
            )
        observation, current_raw = _observed_descriptor_bytes(
            value, expected=source_path, label=f"child input {name}",
        )
        observation["source_file_changed"] = not observation[
            "current_hash_matches_historical"
        ]
        observation["historical_bytes_recoverable"] = observation[
            "current_hash_matches_historical"
        ]
        observation["historical_recovery_status"] = (
            "CURRENT_FILE_EXACT_HASH_MATCH"
            if observation["current_hash_matches_historical"]
            else "HISTORICAL_BYTES_UNAVAILABLE"
        )
        if name == "target_nav" and observation["source_file_changed"]:
            recovered = (
                _exact_historical_csv_prefix(
                    current_raw,
                    observation["historical_sha256"],
                    "target_nav exact historical prefix",
                )
                if current_raw is not None else None
            )
            if recovered is not None:
                recovery_id = _canonical_sha256({
                    "path": source_path.as_posix(),
                    "sha256": observation["historical_sha256"],
                })[:20]
                observation.update({
                    "historical_bytes_recoverable": True,
                    "historical_recovery_status":
                        "EXACT_HASH_MATCHED_HISTORICAL_PREFIX_AVAILABLE",
                    "historical_prefix_byte_count": len(recovered),
                    "historical_prefix_sha256": _sha256_bytes(recovered),
                    "historical_recovery_id": recovery_id,
                })
                recovered_source_bytes[recovery_id] = recovered
        input_observations[name] = observation
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != CHILD_ARTIFACT_NAMES:
        raise NdxCardinalityCapitalReplaySummaryError("child artifact registry changed")
    artifact_evidence: dict[str, Any] = {}
    candidate_raw: bytes | None = None
    for name in sorted(CHILD_ARTIFACT_NAMES):
        value = artifacts[name]
        expected_name = {
            "candidates": "training_candidates.csv",
            "frontiers": "training_frontiers.csv",
            "price_inventory": "price_input_inventory.csv",
            "lifecycle_coverage": "lifecycle_coverage.csv",
            "workbook": "ndx_cardinality_real_training_smoke.xlsx",
        }[name]
        expected_path = expected_dir / expected_name
        evidence, raw = _verified_descriptor_bytes(
            value, expected=expected_path, label=f"child artifact {name}",
        )
        if name != "workbook":
            _, rows = _csv_rows(raw, f"child artifact {name}")
            if int(value.get("rows") or -1) != len(rows):
                raise NdxCardinalityCapitalReplaySummaryError(
                    f"child artifact row count changed: {name}"
                )
            evidence["rows"] = len(rows)
            if name == "candidates":
                candidate_raw = raw
        artifact_evidence[name] = evidence
    assert candidate_raw is not None
    fields, candidate_rows = _csv_rows(candidate_raw, "child candidates")
    missing = sorted(REQUIRED_CANDIDATE_COLUMNS - set(fields))
    if missing:
        raise NdxCardinalityCapitalReplaySummaryError(
            f"child candidate risk/source fields are missing: {missing}"
        )
    training_end = str(manifest.get("training_end") or "")
    if not training_end or _integer(
        manifest.get("training_return_rows"), "training return rows", minimum=1
    ) <= 0:
        raise NdxCardinalityCapitalReplaySummaryError("child training sample is invalid")
    candidates = [
        _validate_candidate(row, selection_date=selection_date, training_end=training_end)
        for row in candidate_rows
    ]
    if sorted({item["holding_count"] for item in candidates}) != holding_counts:
        raise NdxCardinalityCapitalReplaySummaryError("child candidate k coverage changed")
    eligible = [
        item for item in candidates if item["source_reported_replay_eligible"]
    ]
    reasons = Counter(
        reason for item in candidates for reason in item["failure_reasons"]
    )
    roles = [_role_winner(eligible, spec) for spec in ROLE_SPECS] if eligible else []
    drift = [
        {"input_name": name, **evidence}
        for name, evidence in sorted(input_observations.items())
        if not evidence["current_hash_matches_historical"]
    ]
    return {
        "source_batch": batch,
        "job_search_class": lineage["job_search_class"],
        "evaluation_semantics_sha256": lineage["evaluation_semantics_sha256"],
        "universe_track": track,
        "selection_date": selection_date,
        "training_end": training_end,
        "training_return_rows": int(manifest["training_return_rows"]),
        "holding_counts": holding_counts,
        "candidate_rows": len(candidates),
        "source_reported_replay_eligible_rows": len(eligible),
        "four_gate_incumbent_dominance_rows": sum(
            _four_gate_dominates(item) for item in eligible
        ),
        "user_preference_reference": _user_preference_reference(candidates),
        "infeasible_reason_counts": dict(sorted(reasons.items())),
        "frontiers": roles,
        "source_manifest": {
            "path": manifest_path.as_posix(), "sha256": _sha256_bytes(manifest_raw),
        },
        "source_inputs": input_observations,
        "source_input_drift": drift,
        "artifacts": artifact_evidence,
        "raw_historical_input_bytes_all_currently_recoverable": all(
            evidence["historical_bytes_recoverable"]
            for evidence in input_observations.values()
        ),
        "_recovered_source_bytes": recovered_source_bytes,
    }


def build_capital_replay_summary(
    manifest_path: str | Path, *, repository_root: str | Path,
) -> dict[str, Any]:
    """Rebuild the historical summary without running or writing a backtest."""

    root = Path(repository_root).resolve()
    top, lineages, jobs, evidence = _verify_top(manifest_path, root)
    replay_root = (root / TOP_MANIFEST_RELATIVE).parent
    shortlist_path = (root / SHORTLIST_RELATIVE).resolve()
    seen: set[tuple[str, str, str]] = set()
    children = []
    recovered_sources: dict[str, dict[str, Any]] = {}
    for job in jobs:
        key = (job["source_batch"], job["universe_track"], job["selection_date"])
        if key in seen:
            raise NdxCardinalityCapitalReplaySummaryError("job coordinate is duplicated")
        seen.add(key)
        lineage = lineages.get(job["source_batch"])
        if lineage is None:
            raise NdxCardinalityCapitalReplaySummaryError("job source batch is unregistered")
        child = _verify_child(
            job, root=root, replay_root=replay_root, shortlist_path=shortlist_path,
            shortlist_sha256=evidence["shortlist"]["historical_sha256"], lineage=lineage,
        )
        for recovery_id, raw in child.pop("_recovered_source_bytes").items():
            encoded = base64.b64encode(raw).decode("ascii")
            descriptor = {
                "historical_recovery_id": recovery_id,
                "encoding": "BASE64_OF_EXACT_SOURCE_BYTES",
                "byte_count": len(raw),
                "sha256": _sha256_bytes(raw),
                "raw_bytes_base64": encoded,
            }
            existing = recovered_sources.get(recovery_id)
            if existing is not None and existing != descriptor:
                raise NdxCardinalityCapitalReplaySummaryError(
                    "historical source prefix recovery is inconsistent"
                )
            recovered_sources[recovery_id] = descriptor
        children.append(child)
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for child in children:
        key = (
            child["source_batch"], child["job_search_class"],
            child["evaluation_semantics_sha256"], child["universe_track"],
        )
        groups.setdefault(key, []).append(child)
    group_rows = []
    all_drifts: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key, values in sorted(groups.items()):
        ordered = sorted(values, key=lambda item: item["selection_date"])
        source_batch, search_class, semantics_hash, track = key
        reason_counts = Counter()
        for item in ordered:
            reason_counts.update(item["infeasible_reason_counts"])
            for drift in item["source_input_drift"]:
                drift_key = (
                    drift["input_name"], drift["path"], drift["historical_sha256"]
                )
                all_drifts[drift_key] = drift
        dominance_dates = [
            item["selection_date"] for item in ordered
            if item["four_gate_incumbent_dominance_rows"] > 0
        ]
        preference_by_start = [
            {
                "selection_date": item["selection_date"],
                **item["user_preference_reference"],
            }
            for item in ordered
        ]
        group_rows.append({
            "group_id": _canonical_sha256({
                "source_batch": source_batch, "job_search_class": search_class,
                "evaluation_semantics_sha256": semantics_hash, "universe_track": track,
            })[:20],
            "source_batch": source_batch,
            "job_search_class": search_class,
            "evaluation_semantics_sha256": semantics_hash,
            "universe_track": track,
            "cross_group_selection_allowed": False,
            "selection_dates_are_independent_historical_coordinates": True,
            "start_count": len(ordered),
            "selection_dates": [item["selection_date"] for item in ordered],
            "latest_selection_date": ordered[-1]["selection_date"],
            "candidate_rows": sum(item["candidate_rows"] for item in ordered),
            "source_reported_replay_eligible_rows": sum(
                item["source_reported_replay_eligible_rows"] for item in ordered
            ),
            "four_gate_incumbent_dominance_rows": sum(
                item["four_gate_incumbent_dominance_rows"] for item in ordered
            ),
            "four_gate_incumbent_dominance_start_count": len(dominance_dates),
            "four_gate_incumbent_dominance_selection_dates": dominance_dates,
            "latest_four_gate_incumbent_dominance_rows": ordered[-1][
                "four_gate_incumbent_dominance_rows"
            ],
            "infeasible_reason_counts": dict(sorted(reason_counts.items())),
            "latest_frontiers": ordered[-1]["frontiers"],
            "user_preference_reference_by_start": preference_by_start,
            "latest_user_preference_reference": preference_by_start[-1],
            "per_start": ordered,
        })
    drifts = list(all_drifts.values())
    unrecoverable = [
        drift for drift in drifts if not drift["historical_bytes_recoverable"]
    ]
    return {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_capital_replay_historical_summary",
        "status": (
            "HISTORICAL_SUMMARY_COMPLETE_WITH_UNRECOVERABLE_SOURCE_DRIFT"
            if unrecoverable
            else "HISTORICAL_SUMMARY_COMPLETE_WITH_EXACT_PREFIX_RECOVERY"
            if drifts
            else "HISTORICAL_SUMMARY_COMPLETE"
        ),
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "summary_scope": "COMPLETED_25000_USD_HISTORICAL_TRAINING_REPLAY_ONLY",
        "target_portfolio_cash_usd": 25_000.0,
        "minimum_cash_buffer_usd": 100.0,
        "transaction_cost_bps": 10.0,
        "source_generated_at": top["generated_at"],
        "planned_job_count": int(top["planned_job_count"]),
        "verified_child_job_count": len(children),
        "incomplete_job_count": int(top["planned_job_count"]) - len(children),
        "evaluator_group_count": len(group_rows),
        "evaluator_groups": group_rows,
        "role_definitions": [
            {"role": role, "metric": metric, "direction": "MINIMUM" if asc else "MAXIMUM"}
            for role, metric, asc in ROLE_SPECS
        ],
        "role_selection_tie_break": ["tickers", "weight_spec", "portfolio_id"],
        "comprehensive_six_axis_pareto_status": "NOT_COMPUTED_IN_THIS_BUNDLE",
        "user_preference_reference": {
            "tickers": list(USER_PREFERENCE_TICKERS),
            "weights": {
                ticker: USER_PREFERENCE_WEIGHT for ticker in USER_PREFERENCE_TICKERS
            },
            "must_be_displayed_when_present": True,
            "missing_status": "NOT_PRESENT_IN_LOCKED_REPLAY",
            "fixed_answer": False,
            "current_admission": False,
        },
        "paired_incumbent_statistics_read_directly_from_candidate_rows": True,
        "paired_statistics_recomputed_from_separate_quantiles": False,
        "rolling_training_statistics_and_continuous_whole_lot_path_separated": True,
        "exact_and_bounded_cross_selection_allowed": False,
        "cross_evaluator_hash_selection_allowed": False,
        "cross_universe_track_selection_allowed": False,
        "cross_start_global_ranking_allowed": False,
        "source_input_drift_count": len(drifts),
        "source_input_drift": drifts,
        "source_file_change_count": len(drifts),
        "historical_input_unrecoverable_count": len(unrecoverable),
        "raw_historical_input_bytes_currently_recoverable": not unrecoverable,
        "historical_source_prefix_recoveries": list(recovered_sources.values()),
        "summary_rebuilt_from_hash_verified_child_result_artifacts": True,
        "top_manifest_originally_bound_child_manifest_hashes": False,
        "historical_child_manifest_authenticity_reconstructable_from_top": False,
        "new_summary_records_child_manifest_hashes": True,
        "universe_track_labels_are_historical_contract_definitions": True,
        "strict_technology_is_not_current_gics_technology_admission": True,
        "historical_taxonomy_is_not_current_ticker_admission": True,
        "fresh_oos_consumed": False,
        "optimality_claimed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
        "evidence": {
            **evidence,
            "source_lineages": lineages,
        },
    }


def render_summary_markdown(summary: Mapping[str, Any]) -> str:
    """Render the deterministic human-review view."""

    lines = [
        "# NDX 25,000 美元动态持仓数量历史回放摘要",
        "",
        f"状态：`{summary['status']}`。这是历史训练研究摘要，不是当前持仓建议，"
        "也不是候选准入结论。",
        "",
        f"已核验作业：{summary['verified_child_job_count']}/{summary['planned_job_count']}；"
        f"评估器/历史池分组：{summary['evaluator_group_count']}；"
        f"源文件变化：{summary['source_input_drift_count']}。",
        "",
        "收益配对差值大于零较好，回撤成本配对差值小于等于零较好。下列原八只差值"
        "全部直接取自候选行内的同期配对统计，绝不是两个独立分位数相减。",
        "",
    ]

    def pct(value: float) -> str:
        return f"{100.0 * value:.2f}%"

    def signed_pct(value: float) -> str:
        return f"{100.0 * value:+.2f}pp"

    for group in summary["evaluator_groups"]:
        lines.extend([
            f"## {group['job_search_class']} / {group['universe_track']}",
            "",
            f"评估器 `{group['evaluation_semantics_sha256']}`；覆盖 "
            f"{group['start_count']} 个历史起点（{group['selection_dates'][0]} 至 "
            f"{group['selection_dates'][-1]}）；源结果报告可执行候选 "
            f"{group['source_reported_replay_eligible_rows']}/{group['candidate_rows']}；"
            f"跨全部起点四门同时优于原八只的行数为 "
            f"{group['four_gate_incumbent_dominance_rows']}，分布于 "
            f"{group['four_gate_incumbent_dominance_start_count']} 个起点；"
            f"最新起点为 {group['latest_four_gate_incumbent_dominance_rows']} 行。",
            "",
            f"最新独立历史坐标：`{group['latest_selection_date']}`。",
            "",
            "| 角色 | k / 标的 / 权重 | 滚动收益 P50/P10 | 同期配对相对原八只收益 | "
            "滚动回撤 P50/P90 | 同期配对相对原八只回撤 | 相对 012922 收益 / 回撤 | "
            "012922 距离 | 连续整股路径收益 / 回撤 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ])
        for item in group["latest_frontiers"]:
            rolling = item["rolling_training_statistics"]
            path = item["continuous_whole_lot_path"]
            composition = ", ".join(
                f"{ticker} {100.0 * item['weights'][ticker]:.2f}%"
                for ticker in item["tickers"]
            )
            lines.append(
                f"| {item['selection_role']} | k={item['holding_count']}: {composition} | "
                f"{pct(rolling['return_p50'])} / {pct(rolling['return_p10'])} | "
                f"{signed_pct(rolling['paired_return_p50_vs_incumbent'])} / "
                f"{signed_pct(rolling['paired_return_p10_vs_incumbent'])} | "
                f"{pct(rolling['max_drawdown_p50'])} / {pct(rolling['max_drawdown_p90'])} | "
                f"{signed_pct(rolling['paired_drawdown_cost_p50_vs_incumbent'])} / "
                f"{signed_pct(rolling['paired_drawdown_cost_p90_vs_incumbent'])} | "
                f"{signed_pct(rolling['return_p50_vs_012922'])} / "
                f"{signed_pct(rolling['return_p10_vs_012922'])}; "
                f"{signed_pct(rolling['max_drawdown_p50_vs_012922'])} / "
                f"{signed_pct(rolling['max_drawdown_p90_vs_012922'])} | "
                f"{rolling['target_012922_distance']:.4f} | "
                f"{pct(path['whole_lot_path_return_net'])} / "
                f"{pct(path['whole_lot_path_max_drawdown'])} |"
            )
        reasons = group["infeasible_reason_counts"]
        preference = group["latest_user_preference_reference"]
        preference_candidate = preference["candidate"]
        lines.extend([
            "",
            f"最新起点 USER_PREFERENCE（AMAT/AVGO/CDNS/GOOG 等权）参照："
            f"`{preference['status']}`.",
        ])
        if preference_candidate is not None:
            rolling = preference_candidate["rolling_training_statistics"]
            path = preference_candidate["continuous_whole_lot_path"]
            lines.extend([
                f"历史行：滚动收益 P50/P10 {pct(rolling['return_p50'])} / "
                f"{pct(rolling['return_p10'])}；同期配对相对原八只收益 "
                f"{signed_pct(rolling['paired_return_p50_vs_incumbent'])} / "
                f"{signed_pct(rolling['paired_return_p10_vs_incumbent'])}; whole-lot R/DD "
                f"{pct(path['whole_lot_path_return_net'])} / "
                f"{pct(path['whole_lot_path_max_drawdown'])}；不合规原因 "
                + (
                    ", ".join(f"`{reason}`" for reason in preference_candidate["failure_reasons"])
                    if preference_candidate["failure_reasons"] else "无"
                ) + ".",
            ])
        lines.extend([
            "",
            "不合规原因计数：" + (
                ", ".join(f"`{key}`={value}" for key, value in reasons.items())
                if reasons else "无"
            ) + ".",
            "",
        ])
    lines.extend([
        "## 证据边界",
        "",
        "- EXACT、bounded、评估器哈希、历史池和历史起点之间不交叉排名、不合并。",
        "- 历史池名称保留旧契约分类；`strict_technology` 明确包含 "
        "`energy_technology` 等旧风险链，不等同于当前 GICS 科技行业准入名单。",
        "- 滚动训练收益/回撤分布与连续、自融资、逐期整股路径结果分栏报告。",
        "- 本回放只使用冻结 shortlist，不声称穷举搜索或全局最优；综合六轴 Pareto "
        "在本版标记为 `NOT_COMPUTED_IN_THIS_BUNDLE`。",
        "- fresh OOS、准入、晋级、实盘写入和订单生成全部为 false。",
        "- 原顶层 manifest 未绑定每个 child manifest；本摘要只能封存当前哈希自洽的"
        "历史结果，不能补做原始真实性认证。",
    ])
    if summary["source_input_drift"]:
        lines.extend([
            "- 当前 012922 源文件比历史版本多出追加行；历史 SHA 已在完整行边界的"
            "原始字节前缀中精确命中。本摘要区分‘当前文件已变化’与‘历史字节仍可恢复’，"
            "不把前缀恢复误写成当前完整文件哈希一致。",
        ])
    return "\n".join(lines) + "\n"


def _bundle_payload(summary_bytes: bytes, markdown_bytes: bytes, source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_type": "ndx_cardinality_capital_replay_summary_bundle",
        "status": source["status"],
        "research_track": "portfolio_optimization",
        "migration_control_included": False,
        "source_top_manifest": source["evidence"]["top_manifest"],
        "verified_child_job_count": source["verified_child_job_count"],
        "artifacts": {
            "summary_json": {
                "filename": "summary.json", "sha256": _sha256_bytes(summary_bytes),
            },
            "summary_markdown": {
                "filename": "summary.md", "sha256": _sha256_bytes(markdown_bytes),
            },
        },
        "fresh_oos_consumed": False,
        "optimality_claimed": False,
        "admission_claimed": False,
        "promotion_allowed": False,
        "live_mutation_allowed": False,
        "order_creation_allowed": False,
    }


def write_summary_bundle(
    summary: Mapping[str, Any], *, output_dir: str | Path,
) -> dict[str, Any]:
    """Atomically publish an immutable JSON/Markdown research bundle."""

    output = Path(output_dir).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_bytes = _json_bytes(summary)
    markdown_bytes = render_summary_markdown(summary).encode("utf-8")
    manifest = _bundle_payload(summary_bytes, markdown_bytes, summary)
    manifest_bytes = _json_bytes(manifest)
    expected = {
        "summary.json": summary_bytes,
        "summary.md": markdown_bytes,
        "manifest.json": manifest_bytes,
    }
    if output.exists():
        if not output.is_dir() or set(path.name for path in output.iterdir()) != set(expected):
            raise NdxCardinalityCapitalReplaySummaryError("immutable summary bundle collision")
        if any((output / name).read_bytes() != raw for name, raw in expected.items()):
            raise NdxCardinalityCapitalReplaySummaryError("immutable summary bundle collision")
        verify_summary_bundle(output / "manifest.json")
        return manifest
    temporary = output.with_name(f"{output.name}.tmp.{uuid.uuid4().hex}")
    try:
        temporary.mkdir()
        for name, raw in expected.items():
            path = temporary / name
            with path.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    verify_summary_bundle(output / "manifest.json")
    return manifest


def verify_summary_bundle(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    _, manifest = _read_json_bytes(path, "historical summary bundle manifest")
    expected_keys = {
        "schema_version", "manifest_type", "status", "research_track",
        "migration_control_included", "source_top_manifest", "verified_child_job_count",
        "artifacts", "fresh_oos_consumed", "optimality_claimed", "admission_claimed",
        "promotion_allowed", "live_mutation_allowed", "order_creation_allowed",
    }
    if set(manifest) != expected_keys:
        raise NdxCardinalityCapitalReplaySummaryError("summary bundle manifest schema changed")
    if (
        manifest["schema_version"] != 1
        or manifest["manifest_type"] != "ndx_cardinality_capital_replay_summary_bundle"
        or manifest["research_track"] != "portfolio_optimization"
        or manifest["migration_control_included"] is not False
        or any(manifest[key] is not False for key in (
            "fresh_oos_consumed", "optimality_claimed", "admission_claimed",
            "promotion_allowed", "live_mutation_allowed", "order_creation_allowed",
        ))
    ):
        raise NdxCardinalityCapitalReplaySummaryError("summary bundle boundary changed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"summary_json", "summary_markdown"}:
        raise NdxCardinalityCapitalReplaySummaryError("summary bundle artifacts changed")
    for key, filename in (("summary_json", "summary.json"), ("summary_markdown", "summary.md")):
        descriptor = artifacts[key]
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"filename", "sha256"}:
            raise NdxCardinalityCapitalReplaySummaryError("summary artifact descriptor changed")
        if descriptor["filename"] != filename:
            raise NdxCardinalityCapitalReplaySummaryError("summary artifact filename changed")
        artifact = path.parent / filename
        if not artifact.is_file() or _file_sha256(artifact) != descriptor["sha256"]:
            raise NdxCardinalityCapitalReplaySummaryError("summary artifact hash changed")
    _, summary = _read_json_bytes(path.parent / "summary.json", "historical summary")
    if (
        summary.get("manifest_type")
        != "ndx_cardinality_capital_replay_historical_summary"
        or summary.get("status") != manifest.get("status")
        or summary.get("verified_child_job_count") != manifest.get("verified_child_job_count")
        or summary.get("evidence", {}).get("top_manifest") != manifest.get("source_top_manifest")
        or summary.get("fresh_oos_consumed") is not False
        or summary.get("optimality_claimed") is not False
        or summary.get("admission_claimed") is not False
        or summary.get("promotion_allowed") is not False
        or summary.get("live_mutation_allowed") is not False
        or summary.get("order_creation_allowed") is not False
    ):
        raise NdxCardinalityCapitalReplaySummaryError("summary JSON boundary changed")
    return manifest


__all__ = [
    "CAPITAL_MANIFEST_RELATIVE", "NdxCardinalityCapitalReplaySummaryError",
    "OUTPUT_RELATIVE", "SHORTLIST_RELATIVE", "TOP_MANIFEST_RELATIVE",
    "build_capital_replay_summary", "render_summary_markdown", "verify_summary_bundle",
    "write_summary_bundle",
]
