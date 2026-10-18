"""Independent numerical KKT certificates for a fixed convex projection only.

This is not a projection solver, evaluator, or admission gate. Failure to find
a certificate says nothing about primal infeasibility. Tolerances are disclosed;
the result is floating-point evidence, not an exact arithmetic proof.
"""
import itertools
import math

import numpy as np
import pandas as pd
from scipy.optimize import nnls


def certify_projection_candidate(raw, candidate, *, max_weight, min_weight,
        top_weight_count, top_weight_cap, min_effective_n=None,
        group_labels=None, max_group_weight=None, max_top_subsets=100000,
        primal_tolerance=1e-10, active_tolerance=1e-9,
        stationarity_tolerance=1e-9, complementarity_tolerance=1e-10):
    """Check a supplied point against the original envelope and squared loss.

    Top-k is represented by every k-subset halfspace, including all tied active
    subsets. Equality multipliers are free; inequality multipliers are found
    nonnegative without relying on the signs of an arbitrary pseudoinverse.
    """
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def finite_number(value):
        return (isinstance(value, (int, float, np.integer, np.floating))
                and not isinstance(value, (bool, np.bool_)) and math.isfinite(value))

    require(isinstance(raw, pd.Series) and len(raw) > 1 and raw.index.is_unique
            and all(isinstance(t, str) and t and t == t.strip() for t in raw.index),
            'Unique explicit ticker Series required')
    require(isinstance(candidate, pd.Series) and candidate.index.equals(raw.index),
            'Candidate ticker order must exactly match target')
    require(all(finite_number(x) for x in raw.to_numpy())
            and all(finite_number(x) for x in candidate.to_numpy()), 'Invalid numeric vector')
    names = list(raw.index)
    n = len(names)
    require(type(top_weight_count) is int and 1 <= top_weight_count < n, 'Invalid Top-k count')
    require(type(max_top_subsets) is int and max_top_subsets > 0, 'Invalid subset budget')
    for value in (max_weight, min_weight, top_weight_cap):
        require(finite_number(value), 'Invalid risk bound')
    require(0 <= min_weight <= max_weight <= 1 and 0 < top_weight_cap <= 1,
            'Invalid explicit risk bounds')
    for value in (primal_tolerance, active_tolerance, stationarity_tolerance,
                  complementarity_tolerance):
        require(finite_number(value) and 0 < value <= 1e-9, 'Invalid certificate tolerance')
    require(primal_tolerance <= active_tolerance, 'Active tolerance below primal tolerance')
    if min_effective_n is not None:
        require(finite_number(min_effective_n) and 1 <= min_effective_n <= n,
                'Invalid effective-name floor')
    require((group_labels is None) == (max_group_weight is None), 'Incomplete group contract')
    groups = []
    if group_labels is not None:
        require(isinstance(group_labels, dict) and set(group_labels) == set(names)
                and all(isinstance(x, str) and x and x == x.strip() for x in group_labels.values()),
                'Invalid group identities')
        require(finite_number(max_group_weight) and 0 < max_group_weight <= 1, 'Invalid group cap')
        groups = [(label, [i for i, name in enumerate(names) if group_labels[name] == label])
                  for label in sorted(set(group_labels.values()))]
    target = np.maximum(raw.to_numpy(dtype=float), 0.)
    # Same declared objective preprocessing as v2, implemented independently.
    if target.max() == 0:
        target = np.ones(n)
    with np.errstate(over='ignore'):
        target_sum = target.sum()
    require(math.isfinite(target_sum), 'Target sum is not finite in v2 normalization')
    target /= target_sum
    weights = candidate.to_numpy(dtype=float)
    loss_gradient = 2. * (weights - target)
    total_subsets = math.comb(n, top_weight_count)
    result = dict(schema='ndx_projection_kkt_certificate_research_v1',
        scope='FIXED_TARGET_CONVEX_PROJECTION_ONLY', certified=False,
        certification_kind='NUMERICAL_KKT_WITH_DISCLOSED_ABSOLUTE_TOLERANCES',
        target_preprocessing='CLIP_NEGATIVE_NORMALIZE_OR_UNIFORM_IF_ALL_NONPOSITIVE',
        target={t: float(target[i]) for i, t in enumerate(names)},
        candidate={t: float(weights[i]) for i, t in enumerate(names)},
        constraints=dict(max_weight=float(max_weight), min_weight=float(min_weight),
                         top_weight_count=top_weight_count, top_weight_cap=float(top_weight_cap),
                         min_effective_n=None if min_effective_n is None else float(min_effective_n),
                         group_labels=None if group_labels is None else dict(group_labels),
                         max_group_weight=None if max_group_weight is None else float(max_group_weight)),
        objective_value=float((weights-target) @ (weights-target)),
        objective='SUM_SQUARED_DISTANCE_TO_NORMALIZED_TARGET',
        top_subset_count=total_subsets, max_top_subsets=max_top_subsets,
        tolerances=dict(primal=primal_tolerance, active=active_tolerance,
                        stationarity=stationarity_tolerance, complementarity=complementarity_tolerance),
        task_recomputed=False, primal_infeasibility_proven=False,
        promotion_allowed=False, order_generation_allowed=False)
    # Original feasibility checks do not depend on the active-set search.
    residuals = {'simplex_abs': abs(float(weights.sum()-1.)),
                 'lower': float(min_weight-weights.min()),
                 'upper': float(weights.max()-max_weight),
                 'top_k': float(np.sort(weights)[-top_weight_count:].sum()-top_weight_cap)}
    if min_effective_n is not None:
        residuals['hhi'] = float(weights @ weights-1./min_effective_n)
        residuals['effective_n_deficit'] = float(min_effective_n-1./float(weights @ weights)) if weights @ weights > 0 else float('inf')
    for label, indexes in groups:
        residuals['group:'+label] = float(weights[indexes].sum()-max_group_weight)
    result['primal_residuals'] = residuals
    result['individual_bound_residuals'] = {
        t: dict(lower=float(min_weight-weights[i]), upper=float(weights[i]-max_weight))
        for i, t in enumerate(names)}
    result['primal_passed'] = all(math.isfinite(x) and x <= primal_tolerance for x in residuals.values())
    if not result['primal_passed']:
        return dict(result, status='PRIMAL_REJECTED')
    if total_subsets > max_top_subsets:
        return dict(result, status='SUBSET_BUDGET_EXCEEDED')
    active = []

    def consider(label, value, gradient):
        if value >= -active_tolerance:
            active.append((label, float(value), np.asarray(gradient, dtype=float)))

    eye = np.eye(n)
    for i, ticker in enumerate(names):
        consider('LOWER:'+ticker, min_weight-weights[i], -eye[i])
        consider('UPPER:'+ticker, weights[i]-max_weight, eye[i])
    for indexes in itertools.combinations(range(n), top_weight_count):
        row = np.zeros(n)
        row[list(indexes)] = 1.
        consider('TOP:'+','.join(names[i] for i in indexes),
                 row @ weights-top_weight_cap, row)
    if min_effective_n is not None:
        consider('HHI', weights @ weights-1./min_effective_n, 2.*weights)
    for label, indexes in groups:
        row = np.zeros(n)
        row[indexes] = 1.
        consider('GROUP:'+label, row @ weights-max_group_weight, row)
    gradients = np.column_stack([a[2] for a in active]) if active else np.empty((n, 0))
    centered = gradients-gradients.mean(axis=0)
    rhs = -loss_gradient+loss_gradient.mean()
    try:
        multipliers = nnls(centered, rhs, maxiter=max(1000, 20*len(active)))[0] if active else np.empty(0)
    except (RuntimeError, ValueError) as error:
        return dict(result, status='MULTIPLIER_SEARCH_UNRESOLVED', multiplier_search_error=str(error))
    if (not isinstance(multipliers, np.ndarray) or multipliers.shape != (len(active),)
            or not np.isfinite(multipliers).all()):
        return dict(result, status='INVALID_MULTIPLIER_OUTPUT')
    # Do not trust solver status/residual. Check the original, uncentered KKT.
    combined = loss_gradient+gradients @ multipliers
    equality_multiplier = -float(combined.mean())
    stationarity = float(np.max(np.abs(combined+equality_multiplier)))
    complementary = max((abs(float(multiplier*item[1]))
                         for multiplier, item in zip(multipliers, active)), default=0.)
    dual_passed = bool(np.isfinite(multipliers).all() and (multipliers >= 0).all())
    result.update(active_constraints=[dict(name=a[0], residual=a[1], multiplier=float(m),
                                          complementarity_residual=float(a[1]*m))
                                     for a, m in zip(active, multipliers)],
                  equality_multiplier=equality_multiplier,
                  stationarity_residuals={t: float(combined[i]+equality_multiplier)
                                         for i, t in enumerate(names)},
                  stationarity_max_abs=stationarity, complementarity_max_abs=complementary,
                  dual_passed=dual_passed, all_top_subsets_examined=True)
    passed = (dual_passed and math.isfinite(stationarity) and math.isfinite(complementary)
              and stationarity <= stationarity_tolerance and complementary <= complementarity_tolerance)
    return dict(result, certified=passed, status='NUMERICAL_KKT_CERTIFIED' if passed else 'KKT_NOT_CERTIFIED')
