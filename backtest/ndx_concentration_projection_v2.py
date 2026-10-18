"""Research-only concentration projection with complete analytic derivatives.

This independent solver is not wired into any historical or live evaluator.
It preserves the supplied envelope; failed optimization is never a result.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize


class ProjectionError(ValueError):
    pass


def _require(value, message):
    if not value:
        raise ProjectionError(message)


def _box_simplex_projection(target, floor, cap):
    """Exact scalar-dual projection, with bisection to machine precision."""
    lower = float(np.min(target - cap))
    upper = float(np.max(target - floor))
    for _ in range(100):
        threshold = (lower + upper) / 2.
        if np.clip(target - threshold, floor, cap).sum() > 1.:
            lower = threshold
        else:
            upper = threshold
    threshold = (lower + upper) / 2.
    return np.clip(target - threshold, floor, cap), threshold


def _box_simplex_hhi_projection(target, floor, cap, effective_floor):
    """Project onto box/simplex/HHI using the monotone nonnegative HHI dual.

    For alpha=1/(1+lambda), the Lagrangian minimizer is the box-simplex
    projection of alpha*target. The zero-dual solution is tried first. If HHI
    binds, bisection selects its unique primal optimum from the feasible side.
    """
    candidate, threshold = _box_simplex_projection(target, floor, cap)
    if effective_floor is None or candidate @ candidate <= 1. / effective_floor:
        return candidate, 1., threshold
    lower, upper = 0., 1.
    candidate = np.full(len(target), 1. / len(target))
    threshold = -1. / len(target)
    for _ in range(100):
        alpha = (lower + upper) / 2.
        weights, trial_threshold = _box_simplex_projection(alpha * target, floor, cap)
        if weights @ weights <= 1. / effective_floor:
            lower, candidate, threshold = alpha, weights, trial_threshold
        else:
            upper = alpha
    return candidate, lower, threshold


def project_concentration_envelope_weights_v2(
        raw, *, max_weight, min_weight, top_weight_count, top_weight_cap,
        min_effective_n=None, group_labels=None, max_group_weight=None,
        tolerance=1e-9):
    """Project normalized nonnegative targets onto an explicit convex envelope.

    No single-name, group, Top-k, or effective-name bound is relaxed. Callers
    must supply a feasible envelope; a numerical failure remains an exception.
    """
    _require(isinstance(raw, pd.Series) and len(raw) > 1 and raw.index.is_unique,
             'A unique nonempty multi-security Series is required')
    array = raw.to_numpy()
    _require(all(isinstance(x, (int, float, np.integer, np.floating))
                 and not isinstance(x, (bool, np.bool_)) for x in array), 'Invalid raw number')
    target = array.astype(float)
    _require(np.isfinite(target).all(), 'Nonfinite raw weights')
    target = np.maximum(target, 0.)
    if target.sum() <= 0:
        target = np.ones(len(target))
    target /= target.sum()
    count = len(target)
    _require(type(top_weight_count) is int and 1 <= top_weight_count < count,
             'Invalid top_weight_count')
    for value in (max_weight, min_weight, top_weight_cap, tolerance):
        _require(isinstance(value, (int, float)) and not isinstance(value, bool)
                 and np.isfinite(value), 'Invalid constraint number')
    floor, cap = float(min_weight), float(max_weight)
    top_cap = float(top_weight_cap)
    _require(0 <= floor <= 1. / count <= cap <= 1.
             and top_weight_count / count <= top_cap <= 1.
             and 0 < tolerance <= 1e-9, 'Infeasible or invalid explicit envelope')
    effective_floor = None
    if min_effective_n is not None:
        _require(isinstance(min_effective_n, (int, float)) and not isinstance(min_effective_n, bool)
                 and np.isfinite(min_effective_n) and 1 <= min_effective_n <= count,
                 'Invalid effective-name floor')
        effective_floor = float(min_effective_n)
    _require((group_labels is None) == (max_group_weight is None), 'Incomplete group envelope')
    groups = []
    if group_labels is not None:
        _require(isinstance(group_labels, dict) and all(name in group_labels for name in raw.index),
                 'Missing group labels')
        labels = [group_labels[name] for name in raw.index]
        _require(all(isinstance(label, str) and label and label == label.strip() for label in labels),
                 'Invalid group labels')
        _require(isinstance(max_group_weight, (int, float)) and not isinstance(max_group_weight, bool)
                 and np.isfinite(max_group_weight) and 0 < max_group_weight <= 1., 'Invalid group cap')
        groups = [np.flatnonzero(np.asarray(labels) == label) for label in sorted(set(labels))]

    def validate(weights):
        _require(np.isfinite(weights).all() and abs(weights.sum() - 1.) <= tolerance,
                 'Projected simplex violated')
        _require(weights.min() >= floor - tolerance and weights.max() <= cap + tolerance,
                 'Projected single-name bounds violated')
        _require(np.sort(weights)[-top_weight_count:].sum() <= top_cap + tolerance,
                 'Projected Top-k bound violated')
        if effective_floor is not None:
            _require(1. / float(weights @ weights) >= effective_floor - tolerance,
                     'Projected effective-name floor violated')
        for indexes in groups:
            _require(weights[indexes].sum() <= max_group_weight + tolerance,
                     'Projected group bound violated')

    # These exact boundaries imply a unique feasible security-weight vector.
    if cap == 1. / count or floor == 1. / count or effective_floor == count:
        result = np.full(count, 1. / count)
        validate(result)
        return pd.Series(result, index=raw.index, dtype=float)

    # The affine-simplex/HHI-ball projection has a closed-form global optimum.
    # If it also satisfies every remaining envelope constraint, it is the
    # optimum of their intersection too, not a feasible-point fallback. This
    # avoids numerical line-search failures on the curved HHI boundary.
    uniform = np.full(count, 1. / count)
    unconstrained = target.copy()
    if effective_floor is not None:
        radius_squared = 1. / effective_floor - 1. / count
        displacement = target - uniform
        norm_squared = float(displacement @ displacement)
        if norm_squared > radius_squared:
            unconstrained = uniform + np.sqrt(radius_squared / norm_squared) * displacement
    try:
        validate(unconstrained)
    except ProjectionError:
        pass
    else:
        return pd.Series(unconstrained, index=raw.index, dtype=float)

    # The more general box/simplex/HHI dual also handles active floors and
    # caps. Accept it only if Top-k and all declared group bounds hold: then
    # its optimality on a superset proves optimality for the full envelope.
    bounded, _, _ = _box_simplex_hhi_projection(target, floor, cap, effective_floor)
    try:
        validate(bounded)
    except ProjectionError:
        pass
    else:
        return pd.Series(bounded, index=raw.index, dtype=float)

    dimensions = 2 * count + 1
    weight_slice = slice(0, count)
    excess_slice = slice(count + 1, dimensions)
    sum_jac = np.r_[np.ones(count), np.zeros(count + 1)]
    top_jac = np.r_[np.zeros(count), -float(top_weight_count), -np.ones(count)]
    excess_jac = np.c_[-np.eye(count), np.ones(count), np.eye(count)]

    def objective(vector):
        delta = vector[weight_slice] - target
        return float(delta @ delta)

    def objective_jac(vector):
        return np.r_[2. * (vector[weight_slice] - target), np.zeros(count + 1)]

    constraints = [
        dict(type='eq', fun=lambda x: float(x[:count].sum() - 1.), jac=lambda x: sum_jac),
        dict(type='ineq', fun=lambda x: float(top_cap - top_weight_count * x[count] - x[excess_slice].sum()),
             jac=lambda x: top_jac),
        dict(type='ineq', fun=lambda x: x[excess_slice] - x[:count] + x[count],
             jac=lambda x: excess_jac),
    ]
    if effective_floor is not None:
        constraints.append(dict(type='ineq', fun=lambda x: float(1. / effective_floor - x[:count] @ x[:count]),
                                jac=lambda x: np.r_[-2. * x[:count], np.zeros(count + 1)]))
    for indexes in groups:
        gradient = np.zeros(dimensions)
        gradient[indexes] = -1.
        constraints.append(dict(type='ineq', fun=lambda x, indexes=indexes: float(max_group_weight - x[indexes].sum()),
                                jac=lambda x, gradient=gradient: gradient))
    initial = np.r_[np.full(count, 1. / count), 1. / count, np.zeros(count)]
    result = minimize(objective, initial, jac=objective_jac, method='SLSQP',
                      bounds=[(floor, cap)] * count + [(0., cap)] * (count + 1),
                      constraints=constraints, options=dict(maxiter=1000, ftol=1e-13, disp=False))
    _require(result.success and np.isfinite(result.x).all(), 'Projection failed: ' + str(result.message))
    weights = np.asarray(result.x[:count], dtype=float)
    validate(weights)
    return pd.Series(weights, index=raw.index, dtype=float)
