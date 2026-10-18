"""Pure helpers for capital-consistent dynamic-cardinality replay shortlists."""
from __future__ import annotations

import hashlib
import json
from math import isfinite
from typing import Iterable, Mapping


WHOLE_LOT_FAILURE = "WHOLE_LOT_EXECUTABILITY_FAILED"


def _number(row: Mapping, key: str, default: float) -> float:
    try:
        value = float(row.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if isfinite(value) else default


def failure_codes(row: Mapping) -> set[str]:
    return {
        item.strip()
        for item in str(row.get("constraint_failure_reasons") or "").split(";")
        if item.strip()
    }


def noncapital_constraints_passed(
    row: Mapping, *, whole_lot_failure_code: str = WHOLE_LOT_FAILURE,
) -> bool:
    """True when whole-lot capital is the only declared constraint failure."""
    return not (failure_codes(row) - {whole_lot_failure_code})


def capital_replay_reason(row: Mapping, source_cash_usd: float, target_cash_usd: float) -> str:
    codes = failure_codes(row)
    if WHOLE_LOT_FAILURE in codes:
        return "SOURCE_CAPITAL_WHOLE_LOT_FAILURE_REQUIRES_REPLAY"
    if abs(float(source_cash_usd) - float(target_cash_usd)) > 0.01:
        return "CAPITAL_SCALE_CHANGED_REQUIRES_REPLAY"
    return "SOURCE_CAPITAL_CLASSIFICATION_REUSABLE"


def is_user_preference(row: Mapping, tickers: Iterable[str]) -> bool:
    observed = {
        item.strip().upper()
        for item in str(row.get("tickers") or "").replace(",", ";").split(";")
        if item.strip()
    }
    return observed == {str(item).upper() for item in tickers}


def _pareto(rows: list[dict]) -> list[dict]:
    metrics = [
        ("return_p50", True), ("return_p10", True),
        ("max_drawdown_p50", False), ("max_drawdown_p90", False),
        ("target_012922_distance", False), ("turnover", False),
    ]
    out = []
    for i, row in enumerate(rows):
        dominated = False
        for j, other in enumerate(rows):
            if i == j:
                continue
            weak = []
            strict = []
            for key, maximize in metrics:
                left = _number(other, key, float("-inf") if maximize else float("inf"))
                right = _number(row, key, float("-inf") if maximize else float("inf"))
                weak.append(left >= right if maximize else left <= right)
                strict.append(left > right if maximize else left < right)
            if all(weak) and any(strict):
                dominated = True
                break
        if not dominated:
            out.append(row)
    return out


def shortlist_coordinate_rows(
    rows: Iterable[Mapping],
    *,
    per_frontier: int,
    user_preference_tickers: Iterable[str],
) -> list[dict]:
    """Select a bounded replay set without recomputing historical returns."""
    eligible = [dict(row) for row in rows if noncapital_constraints_passed(row)]
    limit = max(1, int(per_frontier))
    selected: dict[tuple[str, str, str, str], dict] = {}

    def add(frontier: str, candidates: Iterable[dict]) -> None:
        for rank, row in enumerate(candidates, 1):
            key = (
                str(row.get("portfolio_id") or ""), str(row.get("weight_spec") or ""),
                str(row.get("tickers") or ""), str(row.get("weights") or ""),
            )
            item = selected.setdefault(key, dict(row))
            tags = {tag for tag in str(item.get("capital_replay_frontiers") or "").split(";") if tag}
            tags.add(frontier)
            item["capital_replay_frontiers"] = ";".join(sorted(tags))
            item[f"{frontier.lower()}_replay_rank"] = rank

    add("RETURN", sorted(eligible, key=lambda row: -_number(row, "return_p50", float("-inf")))[:limit])
    add("BAD_TAIL", sorted(eligible, key=lambda row: -_number(row, "return_p10", float("-inf")))[:limit])
    add("DRAWDOWN", sorted(eligible, key=lambda row: _number(row, "max_drawdown_p90", float("inf")))[:limit])
    add("012922_DISTANCE", sorted(eligible, key=lambda row: _number(row, "target_012922_distance", float("inf")))[:limit])
    pareto = _pareto(eligible)
    pareto.sort(key=lambda row: (
        -_number(row, "return_p50", float("-inf")),
        -_number(row, "return_p10", float("-inf")),
        _number(row, "max_drawdown_p90", float("inf")),
        _number(row, "target_012922_distance", float("inf")),
    ))
    add("PARETO", pareto[:limit])
    add("USER_PREFERENCE", [
        row for row in eligible if is_user_preference(row, user_preference_tickers)
    ])
    return list(selected.values())


def evaluation_semantics_payload(run_manifest: Mapping) -> dict:
    contract = run_manifest.get("run_contract") or {}
    return {
        key: contract.get(key)
        for key in (
            "spec_sha256", "discovery_manifest_sha256", "security_lifecycle_sha256",
            "execution_price_manifest_sha256", "discovery_module_sha256",
            "whole_lot_module_sha256", "search_method", "minimum_price_rows_before_selection",
            "training_lookback_days", "fit_days", "window_days", "step_days",
            "transaction_cost_bps",
        )
    }


def evaluation_semantics_sha256(run_manifest: Mapping) -> str:
    raw = json.dumps(
        evaluation_semantics_payload(run_manifest),
        ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "WHOLE_LOT_FAILURE", "capital_replay_reason", "evaluation_semantics_payload",
    "evaluation_semantics_sha256", "failure_codes", "is_user_preference",
    "noncapital_constraints_passed", "shortlist_coordinate_rows",
]
