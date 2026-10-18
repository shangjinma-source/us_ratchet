"""Deterministic portfolio-weight constraint helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


class WeightConstraintError(ValueError):
    """Raised when bounded portfolio weights cannot be constructed safely."""


def bounded_proportional_weights(
    raw: pd.Series,
    *,
    max_weight: float,
    min_weight: float,
    tolerance: float = 1e-12,
) -> pd.Series:
    """Scale positive raw weights onto a bounded simplex.

    Free weights retain their relative proportions. Lower bounds are fixed
    before upper bounds, avoiding residual cap violations from finite clipping
    loops followed by normalization.
    """
    values = raw.astype(float).copy()
    if values.empty:
        return values
    if not values.index.is_unique:
        raise WeightConstraintError("weight index must be unique")
    array = values.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise WeightConstraintError("raw weights must be finite")
    array = np.clip(array, 0.0, None)
    if float(array.sum()) <= 0:
        array = np.ones(len(array), dtype=float)

    count = len(array)
    equal_weight = 1.0 / count
    floor = min(max(0.0, float(min_weight)), equal_weight)
    cap = min(1.0, max(float(max_weight), equal_weight))
    if not np.isfinite(floor) or not np.isfinite(cap) or floor > cap:
        raise WeightConstraintError("weight bounds are not finite or feasible")

    weights = np.zeros(count, dtype=float)
    free = np.ones(count, dtype=bool)
    remaining = 1.0
    for _ in range(count * 2 + 2):
        free_indexes = np.flatnonzero(free)
        if not len(free_indexes):
            break
        free_raw = array[free_indexes]
        raw_total = float(free_raw.sum())
        proposal = (
            np.repeat(remaining / len(free_indexes), len(free_indexes))
            if raw_total <= 0
            else free_raw / raw_total * remaining
        )

        below = proposal < floor - tolerance
        if bool(below.any()):
            fixed = free_indexes[below]
            weights[fixed] = floor
            free[fixed] = False
            remaining -= floor * len(fixed)
            continue

        above = proposal > cap + tolerance
        if bool(above.any()):
            fixed = free_indexes[above]
            weights[fixed] = cap
            free[fixed] = False
            remaining -= cap * len(fixed)
            continue

        weights[free_indexes] = proposal
        remaining = 0.0
        free[free_indexes] = False
        break

    residual = 1.0 - float(weights.sum())
    if abs(residual) > tolerance:
        if residual > 0:
            candidates = np.flatnonzero(weights < cap - tolerance)
            room = cap - weights[candidates]
        else:
            candidates = np.flatnonzero(weights > floor + tolerance)
            room = weights[candidates] - floor
        amount = abs(residual)
        for index, available in zip(candidates, room):
            adjustment = min(amount, float(available))
            weights[index] += adjustment if residual > 0 else -adjustment
            amount -= adjustment
            if amount <= tolerance:
                break

    if not np.isclose(float(weights.sum()), 1.0, atol=1e-10, rtol=0.0):
        raise WeightConstraintError("bounded weights do not sum to one")
    if float(weights.min()) < floor - 1e-10:
        raise WeightConstraintError("bounded weights violate the effective floor")
    if float(weights.max()) > cap + 1e-10:
        raise WeightConstraintError("bounded weights violate the effective cap")
    return pd.Series(weights, index=values.index, dtype=float)


def project_concentration_envelope_weights(
    raw: pd.Series,
    *,
    max_weight: float,
    min_weight: float,
    top_weight_count: int,
    top_weight_cap: float,
    min_effective_n: float | None = None,
    group_labels: dict[str, str] | None = None,
    max_group_weight: float | None = None,
    tolerance: float = 1e-9,
) -> pd.Series:
    """Minimize source-weight tracking error inside an explicit risk envelope.

    The largest-k constraint is evaluated on the resulting weights, so the
    optimizer cannot evade it by changing which names occupy the top group.
    """
    values = raw.astype(float).copy()
    if values.empty:
        return values
    if not values.index.is_unique:
        raise WeightConstraintError("weight index must be unique")
    raw_values = values.to_numpy(dtype=float)
    if not np.isfinite(raw_values).all():
        raise WeightConstraintError("raw weights must be finite")
    raw_values = np.clip(raw_values, 0.0, None)
    if float(raw_values.sum()) <= 0:
        raw_values = np.ones(len(raw_values), dtype=float)
    target = raw_values / float(raw_values.sum())

    count = len(target)
    top_count = int(top_weight_count)
    if not 1 <= top_count < count:
        raise WeightConstraintError(
            "top_weight_count must be between one and the portfolio size"
        )
    equal_weight = 1.0 / count
    floor = min(max(0.0, float(min_weight)), equal_weight)
    cap = min(1.0, max(float(max_weight), equal_weight))
    security_top_group_cap = float(top_weight_cap)
    if (
        not np.isfinite(floor)
        or not np.isfinite(cap)
        or not np.isfinite(security_top_group_cap)
        or floor > cap
        or not top_count / count <= security_top_group_cap <= 1.0
    ):
        raise WeightConstraintError("concentration bounds are not finite or feasible")

    effective_n_floor = None
    if min_effective_n is not None:
        effective_n_floor = float(min_effective_n)
        if (
            not np.isfinite(effective_n_floor)
            or not 1.0 <= effective_n_floor <= count
        ):
            raise WeightConstraintError(
                "min_effective_n must be between one and the portfolio size"
            )

    group_indexes: list[np.ndarray] = []
    risk_group_cap = None
    if (group_labels is None) != (max_group_weight is None):
        raise WeightConstraintError("group_labels and max_group_weight must be provided together")
    if group_labels is not None:
        missing_labels = [str(name) for name in values.index if str(name) not in group_labels]
        if missing_labels:
            raise WeightConstraintError(f"group labels missing for: {missing_labels}")
        labels = [str(group_labels[str(name)]).strip() for name in values.index]
        if any(not label for label in labels):
            raise WeightConstraintError("group labels must be non-blank")
        risk_group_cap = float(max_group_weight)
        if not np.isfinite(risk_group_cap) or not 0.0 < risk_group_cap <= 1.0:
            raise WeightConstraintError("max_group_weight must be in (0,1]")
        for label in sorted(set(labels)):
            group_indexes.append(np.asarray([i for i, value in enumerate(labels) if value == label]))

    # When the effective cap equals 1 / n, the simplex has exactly one
    # feasible security-weight vector.  Returning it directly avoids an SLSQP
    # singular-boundary failure (notably for k=2 with a declared cap < 50%).
    if cap <= equal_weight + tolerance:
        weights = np.repeat(equal_weight, count)
        if top_count * equal_weight > security_top_group_cap + tolerance:
            raise WeightConstraintError("equal-weight solution violates the top-group cap")
        if effective_n_floor is not None and count < effective_n_floor - tolerance:
            raise WeightConstraintError("equal-weight solution violates the effective-name floor")
        if risk_group_cap is not None:
            for indexes in group_indexes:
                if float(weights[indexes].sum()) > risk_group_cap + tolerance:
                    raise WeightConstraintError("equal-weight solution violates the group cap")
        return pd.Series(weights, index=values.index, dtype=float)

    def largest_group_sum(weights: np.ndarray) -> float:
        return float(np.partition(weights, -top_count)[-top_count:].sum())

    # The auxiliary threshold representation is equivalent to a largest-k
    # constraint and avoids passing a non-smooth sort operation to SLSQP:
    # sum_largest_k(w) = min_t k*t + sum(max(w_i - t, 0)).
    weight_slice = slice(0, count)
    threshold_index = count
    excess_slice = slice(count + 1, count * 2 + 1)

    def objective(vector: np.ndarray) -> float:
        delta = vector[weight_slice] - target
        return float(np.dot(delta, delta))

    def sum_constraint(vector: np.ndarray) -> float:
        return float(vector[weight_slice].sum() - 1.0)

    def top_group_constraint(vector: np.ndarray) -> float:
        threshold = float(vector[threshold_index])
        excess = vector[excess_slice]
        return float(security_top_group_cap - top_count * threshold - excess.sum())

    def excess_constraints(vector: np.ndarray) -> np.ndarray:
        weights = vector[weight_slice]
        threshold = float(vector[threshold_index])
        excess = vector[excess_slice]
        return excess - weights + threshold

    constraints: list[dict] = [
        {"type": "eq", "fun": sum_constraint},
        {"type": "ineq", "fun": top_group_constraint},
        {"type": "ineq", "fun": excess_constraints},
    ]
    if effective_n_floor is not None:
        max_hhi = 1.0 / effective_n_floor
        constraints.append({
            "type": "ineq",
            "fun": lambda vector: float(
                max_hhi
                - np.dot(vector[weight_slice], vector[weight_slice])
            ),
        })
    if risk_group_cap is not None:
        for indexes in group_indexes:
            constraints.append({
                "type": "ineq",
                "fun": lambda vector, indexes=indexes: float(
                    risk_group_cap - vector[weight_slice][indexes].sum()
                ),
            })

    initial = np.concatenate([
        np.repeat(equal_weight, count),
        np.asarray([equal_weight]),
        np.zeros(count, dtype=float),
    ])
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=(
            [(floor, cap)] * count
            + [(0.0, cap)]
            + [(0.0, cap)] * count
        ),
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-13, "disp": False},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise WeightConstraintError(
            f"concentration-envelope projection failed: {result.message}"
        )
    weights = np.asarray(result.x[weight_slice], dtype=float)
    if not np.isclose(float(weights.sum()), 1.0, atol=tolerance, rtol=0.0):
        raise WeightConstraintError("projected weights do not sum to one")
    if float(weights.min()) < floor - tolerance:
        raise WeightConstraintError("projected weights violate the effective floor")
    if float(weights.max()) > cap + tolerance:
        raise WeightConstraintError("projected weights violate the effective cap")
    if largest_group_sum(weights) > security_top_group_cap + tolerance:
        raise WeightConstraintError("projected weights violate the top-group cap")
    if effective_n_floor is not None:
        effective_n = 1.0 / float(np.dot(weights, weights))
        if effective_n < effective_n_floor - tolerance:
            raise WeightConstraintError(
                "projected weights violate the effective-name floor"
            )
    if risk_group_cap is not None:
        for indexes in group_indexes:
            if float(weights[indexes].sum()) > risk_group_cap + tolerance:
                raise WeightConstraintError("projected weights violate the group cap")
    return pd.Series(weights, index=values.index, dtype=float)
