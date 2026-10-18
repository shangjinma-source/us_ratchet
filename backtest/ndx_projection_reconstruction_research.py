"""Reconstruct a proposed active face, then independently certify its optimum.

No active-set subset search, live wiring, or solver-success override is done.
A missed face or missing certificate is unresolved, never infeasibility proof.
"""
import hashlib
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.ndx_projection_certificate_research import certify_projection_candidate


_SOURCE_PATHS = (Path(__file__).resolve(), Path(__file__).with_name('ndx_projection_certificate_research.py').resolve())


def _source_hashes():
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in _SOURCE_PATHS}


_LOADED_SOURCES = _source_hashes()


def reconstruct_projection_candidate(raw, proposed_candidate, *, max_weight,
        min_weight, top_weight_count, top_weight_cap, min_effective_n=None,
        group_labels=None, max_group_weight=None, activity_tolerance=1e-6,
        max_top_subsets=100000, rank_relative_tolerance=1e-12):
    """Build all near-active affine rows and project into their HHI ball.

    ``weights`` is populated only after independent numerical KKT certification.
    ``activity_tolerance`` selects a face; it never relaxes the risk envelope or
    the independently fixed certificate tolerances.
    """
    for value, limit in ((activity_tolerance, 1e-3), (rank_relative_tolerance, 1e-8)):
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= limit:
            raise ValueError('Invalid explicit reconstruction tolerance')
    sources = _source_hashes()
    if sources != _LOADED_SOURCES:
        raise ValueError('Reconstruction source drift')
    bounds = dict(max_weight=max_weight, min_weight=min_weight,
                  top_weight_count=top_weight_count, top_weight_cap=top_weight_cap,
                  min_effective_n=min_effective_n, group_labels=group_labels,
                  max_group_weight=max_group_weight)
    # Reuse only its public validation/normalized objective contract. The
    # proposed point is never accepted, even if this preliminary check passes.
    proposed_check = certify_projection_candidate(raw, proposed_candidate,
                                                  max_top_subsets=max_top_subsets, **bounds)
    names = list(raw.index)
    n = len(names)
    target = np.array([proposed_check['target'][t] for t in names])
    proposed = proposed_candidate.to_numpy(dtype=float)
    result = dict(schema='ndx_projection_reconstruction_research_v1',
        scope='PROPOSED_ACTIVE_FACE_PROJECTION_ONLY', certified=False, weights=None,
        proposed_candidate={t: float(proposed[i]) for i, t in enumerate(names)},
        raw_target={t: float(raw.iloc[i]) for i, t in enumerate(names)},
        constraints=proposed_check['constraints'],
        proposed_certificate=proposed_check, source_hashes=sources,
        activity_tolerance=activity_tolerance, rank_relative_tolerance=rank_relative_tolerance,
        max_top_subsets=max_top_subsets, active_subset_search_performed=False,
        primal_infeasibility_proven=False, promotion_allowed=False,
        task_recomputed=False, order_generation_allowed=False)

    def finish(status, **values):
        if _source_hashes() != sources:
            raise ValueError('Reconstruction sources changed during evaluation')
        return dict(result, status=status, **values)

    subset_count = math.comb(n, top_weight_count)
    if subset_count > max_top_subsets:
        return finish('SUBSET_BUDGET_EXCEEDED')
    rows = [np.ones(n)]
    rhs = [1.]
    labels = ['SIMPLEX']

    def near(label, row, bound):
        if abs(float(row @ proposed-bound)) <= activity_tolerance:
            labels.append(label)
            rows.append(row)
            rhs.append(float(bound))

    eye = np.eye(n)
    for i, ticker in enumerate(names):
        near('LOWER:'+ticker, eye[i], min_weight)
        near('UPPER:'+ticker, eye[i], max_weight)
    for indexes in itertools.combinations(range(n), top_weight_count):
        row = np.zeros(n)
        row[list(indexes)] = 1.
        near('TOP:'+','.join(names[i] for i in indexes), row, top_weight_cap)
    if group_labels is not None:
        for label in sorted(set(group_labels.values())):
            row = np.array([float(group_labels[t] == label) for t in names])
            near('GROUP:'+label, row, max_group_weight)
    matrix = np.vstack(rows)
    affine_rhs = np.array(rhs)
    try:
        left, singular, right = np.linalg.svd(matrix, full_matrices=False)
    except np.linalg.LinAlgError:
        return finish('AFFINE_SVD_UNRESOLVED')
    rank = int(np.sum(singular > singular[0]*rank_relative_tolerance))
    basis = right[:rank]
    center = basis.T @ ((left[:, :rank].T @ affine_rhs)/singular[:rank])
    null_target = target-basis.T @ (basis @ target)
    affine_residual = matrix @ center-affine_rhs
    result.update(affine_constraints=labels, affine_rows=matrix.tolist(),
                  affine_rhs=affine_rhs.tolist(), affine_rank=rank,
                  affine_singular_values=singular.tolist(),
                  affine_center=center.tolist(), nullspace_target=null_target.tolist(),
                  affine_center_residuals=affine_residual.tolist())
    if not np.isfinite(center).all() or np.max(np.abs(affine_residual)) > 1e-10:
        return finish('PROPOSED_AFFINE_FACE_UNRESOLVED')
    candidate = center+null_target
    if min_effective_n is not None:
        radius_squared = float(1./min_effective_n-center @ center)
        result['hhi_radius_squared'] = radius_squared
        if radius_squared < -1e-12:
            return finish('PROPOSED_FACE_HHI_INTERSECTION_UNRESOLVED')
        # A tiny negative roundoff is handled as zero, but the independent
        # original effective-name check must still accept the resulting point.
        radius_squared = max(0., radius_squared)
        displacement_squared = float(null_target @ null_target)
        if displacement_squared > radius_squared:
            candidate = center+math.sqrt(radius_squared/displacement_squared)*null_target
    if not np.isfinite(candidate).all():
        return finish('NONFINITE_RECONSTRUCTION')
    certificate = certify_projection_candidate(raw, pd.Series(candidate, index=raw.index),
                                               max_top_subsets=max_top_subsets, **bounds)
    result['certificate'] = certificate
    result['reconstructed_candidate'] = {t: float(candidate[i]) for i, t in enumerate(names)}
    result['reconstructed_affine_residuals'] = (matrix @ candidate-affine_rhs).tolist()
    if not certificate['certified']:
        return finish('RECONSTRUCTION_NOT_CERTIFIED')
    # Certificate contains the exact same candidate, normalized objective,
    # original bounds, tolerances, and independently verified KKT residuals.
    result['certified'] = True
    result['weights'] = dict(certificate['candidate'])
    return finish('RECONSTRUCTED_NUMERICAL_KKT_CERTIFIED')
