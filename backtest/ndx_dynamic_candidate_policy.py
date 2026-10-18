"""Point-in-time policy lanes for dynamic-cardinality portfolio paths."""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pandas as pd


class NdxDynamicCandidatePolicyError(ValueError):
    pass


POLICY_ROLES = (
    "RETURN",
    "BAD_TAIL",
    "DRAWDOWN",
    "TARGET_ENVELOPE",
    "USER_PREFERENCE",
)


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1"}:
        return True
    if text in {"false", "0"}:
        return False
    raise NdxDynamicCandidatePolicyError(f"invalid boolean value: {value!r}")


def _items(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(";") if item.strip()]


def _weights(value: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in _items(value):
        ticker, separator, raw_weight = item.rpartition(":")
        if not separator or not ticker or ticker in result:
            raise NdxDynamicCandidatePolicyError("candidate weights are malformed")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise NdxDynamicCandidatePolicyError("candidate weight is not numeric") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise NdxDynamicCandidatePolicyError("candidate weights must be positive finite")
        result[ticker] = weight
    total = sum(result.values())
    if not result or not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise NdxDynamicCandidatePolicyError("candidate weights must sum to one")
    return result


def _validated_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "selection_date", "decision_data_end", "holding_count", "portfolio_id",
        "weight_spec", "tickers", "weights", "security_ids", "issuer_ids",
        "declared_constraints_passed", "return_p50", "return_p10",
        "max_drawdown_p50", "max_drawdown_p90", "target_012922_distance",
    }
    if frame.empty or not required.issubset(frame.columns):
        raise NdxDynamicCandidatePolicyError("dynamic candidate policy input is incomplete")
    result = frame.copy()
    result["selection_date"] = pd.to_datetime(result["selection_date"], errors="raise").dt.normalize()
    result["decision_data_end"] = pd.to_datetime(result["decision_data_end"], errors="raise").dt.normalize()
    result["declared_constraints_passed"] = result["declared_constraints_passed"].map(_truth)
    numeric = [
        "holding_count", "return_p50", "return_p10", "max_drawdown_p50",
        "max_drawdown_p90", "target_012922_distance",
    ]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="raise")
        if not result[column].map(math.isfinite).all():
            raise NdxDynamicCandidatePolicyError(f"candidate metric is not finite: {column}")
    if bool((result["holding_count"] <= 0).any()):
        raise NdxDynamicCandidatePolicyError("candidate holding_count must be positive")
    if bool((result["decision_data_end"] >= result["selection_date"]).any()):
        raise NdxDynamicCandidatePolicyError("decision data must end before selection execution")
    for row in result.itertuples(index=False):
        tickers = _items(row.tickers)
        security_ids = _items(row.security_ids)
        issuer_ids = _items(row.issuer_ids)
        weights = _weights(row.weights)
        if (
            len(tickers) != int(row.holding_count)
            or len(security_ids) != len(tickers)
            or len(issuer_ids) != len(tickers)
            or len(set(tickers)) != len(tickers)
            or len(set(security_ids)) != len(security_ids)
            or len(set(issuer_ids)) != len(issuer_ids)
            or set(weights) != set(tickers)
        ):
            raise NdxDynamicCandidatePolicyError("candidate identity/weight cardinality mismatch")
    return result


def select_dynamic_candidate_policy(
    candidates: pd.DataFrame,
    *,
    policy_role: str,
    user_preference_tickers: Iterable[str] = ("AMAT", "AVGO", "CDNS", "GOOG"),
) -> pd.DataFrame:
    """Select one deterministic, training-only candidate for each decision date.

    Each role is a separate diagnostic lane.  TARGET_ENVELOPE may use the
    reported scalar distance for training selection, but no role is an
    admission gate and scalar distance can never satisfy the componentwise
    012922 forward gate.
    """
    role = str(policy_role).strip().upper()
    if role not in POLICY_ROLES:
        raise NdxDynamicCandidatePolicyError(f"unsupported policy role: {policy_role}")
    frame = _validated_candidates(candidates)
    frame = frame.loc[frame["declared_constraints_passed"]].copy()
    if frame.empty:
        raise NdxDynamicCandidatePolicyError("no capital-consistent candidates are compliant")
    preference = {str(item).strip().upper() for item in user_preference_tickers}
    selected: list[pd.Series] = []
    for selection_date, group in frame.groupby("selection_date", sort=True):
        scoped = group.copy()
        if role == "USER_PREFERENCE":
            scoped = scoped.loc[
                scoped["tickers"].map(lambda value: set(_items(value)) == preference)
                & scoped["weight_spec"].astype(str).eq("equal_weight")
            ]
            if scoped.empty:
                raise NdxDynamicCandidatePolicyError(
                    f"USER_PREFERENCE is absent on {selection_date.date()}"
                )
            columns = ["tickers", "portfolio_id"]
            ascending = [True, True]
        elif role == "RETURN":
            columns = [
                "return_p50", "return_p10", "max_drawdown_p90",
                "target_012922_distance", "holding_count", "tickers", "weight_spec",
            ]
            ascending = [False, False, True, True, True, True, True]
        elif role == "BAD_TAIL":
            columns = [
                "return_p10", "return_p50", "max_drawdown_p90",
                "target_012922_distance", "holding_count", "tickers", "weight_spec",
            ]
            ascending = [False, False, True, True, True, True, True]
        elif role == "DRAWDOWN":
            columns = [
                "max_drawdown_p90", "max_drawdown_p50", "return_p10",
                "target_012922_distance", "holding_count", "tickers", "weight_spec",
            ]
            ascending = [True, True, False, True, True, True, True]
        else:
            columns = [
                "target_012922_distance", "return_p10", "max_drawdown_p90",
                "return_p50", "holding_count", "tickers", "weight_spec",
            ]
            ascending = [True, False, True, False, True, True, True]
        chosen = scoped.sort_values(columns, ascending=ascending, kind="stable").iloc[0].copy()
        chosen["policy_role"] = role
        chosen["training_selection_only"] = True
        chosen["scalar_target_distance_used_for_admission"] = False
        chosen["promotion_allowed"] = False
        selected.append(chosen)
    result = pd.DataFrame(selected).sort_values("selection_date", kind="stable").reset_index(drop=True)
    if result["selection_date"].duplicated().any():
        raise NdxDynamicCandidatePolicyError("policy selected multiple candidates for one date")
    return result


def select_user_preference_reference_policy(
    candidates: pd.DataFrame,
    *,
    user_preference_tickers: Iterable[str] = ("AMAT", "AVGO", "CDNS", "GOOG"),
) -> pd.DataFrame:
    """Keep the preregistered preference reference visible without admitting it.

    Unlike competitive policy lanes, this reference is intentionally not
    filtered by the old per-coordinate ``declared_constraints_passed`` flag.
    That flag and its failure reason remain on every selected row, so a
    historical reference path can be inspected without becoming a compliant
    candidate or an admission result.
    """
    frame = _validated_candidates(candidates)
    preference = {str(item).strip().upper() for item in user_preference_tickers}
    selected: list[pd.Series] = []
    for selection_date, group in frame.groupby("selection_date", sort=True):
        scoped = group.loc[
            group["tickers"].map(lambda value: set(_items(value)) == preference)
            & group["weight_spec"].astype(str).eq("equal_weight")
        ]
        if len(scoped) != 1:
            raise NdxDynamicCandidatePolicyError(
                "USER_PREFERENCE reference must have exactly one equal-weight row on "
                f"{selection_date.date()}; found {len(scoped)}"
            )
        chosen = scoped.iloc[0].copy()
        chosen["policy_role"] = "USER_PREFERENCE"
        chosen["reference_role"] = "REFERENCE_NOT_FIXED_ANSWER"
        chosen["reference_declared_constraints_passed"] = bool(
            chosen["declared_constraints_passed"]
        )
        chosen["training_selection_only"] = True
        chosen["scalar_target_distance_used_for_admission"] = False
        chosen["admission_allowed"] = False
        chosen["promotion_allowed"] = False
        selected.append(chosen)
    return pd.DataFrame(selected).sort_values(
        "selection_date", kind="stable"
    ).reset_index(drop=True)


def build_dynamic_policy_schedule(
    selected: pd.DataFrame,
    *,
    execution_dates: dict[pd.Timestamp, pd.Timestamp] | None = None,
) -> list[dict[str, Any]]:
    frame = _validated_candidates(selected)
    schedule: list[dict[str, Any]] = []
    for row in frame.sort_values("selection_date", kind="stable").itertuples(index=False):
        tickers = _items(row.tickers)
        security_ids = _items(row.security_ids)
        issuer_ids = _items(row.issuer_ids)
        weights = _weights(row.weights)
        execution_date = row.selection_date
        if execution_dates is not None:
            try:
                execution_date = pd.Timestamp(execution_dates[row.selection_date]).normalize()
            except (KeyError, TypeError, ValueError) as exc:
                raise NdxDynamicCandidatePolicyError(
                    f"next-session execution date missing for {row.selection_date.date()}"
                ) from exc
            if execution_date <= row.selection_date:
                raise NdxDynamicCandidatePolicyError(
                    "future shadow execution must follow the completed decision session"
                )
        schedule.append({
            "decision_date": (
                row.selection_date if execution_dates is not None else row.decision_data_end
            ),
            "execution_date": execution_date,
            "targets": {
                security_id: {
                    "ticker": ticker,
                    "issuer_id": issuer_id,
                    "target_weight": weights[ticker],
                }
                for ticker, security_id, issuer_id in zip(tickers, security_ids, issuer_ids)
            },
        })
    return schedule


__all__ = [
    "NdxDynamicCandidatePolicyError",
    "POLICY_ROLES",
    "build_dynamic_policy_schedule",
    "select_dynamic_candidate_policy",
    "select_user_preference_reference_policy",
]
