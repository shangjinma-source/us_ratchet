"""Independent componentwise coverage proof for saved complete-cohort frontiers."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_corrected_complete_date_frontier_archive_research as source
from scripts.ndx_base_three_cell_window_delta_research import publish

SOURCE = Path(__file__).resolve()
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
    SOURCE, Path(source.__file__).resolve(), Path(publish.__code__.co_filename).resolve())}


def prove(rows, selected, columns, directions):
    """Every omitted row is strictly dominated; every included row is not.

    This is an independent broadcast comparison, not the production Pareto kernel.
    Coverage plus non-dominance inside the returned set proves global non-dominance
    by transitivity. Equal vectors never dominate, so all tied rows must be kept.
    """
    by_id = {r['job_id']: r for r in rows}
    chosen = {r['job_id']: r for r in selected}
    if len(by_id) != len(rows) or len(chosen) != len(selected) or not set(chosen) <= set(by_id):
        raise ValueError('Unique full candidate/frontier identifiers required')
    for identifier, row in chosen.items():
        if source.core.digest(row) != source.core.digest(by_id[identifier]):
            raise ValueError('Frontier row differs from complete candidate')
    if len(columns) != 8 or len(set(columns)) != 8 or len(directions) != 8 or any(isinstance(d, (bool, np.bool_)) or d not in (-1, 1) for d in directions):
        raise ValueError('Explicit eight comparison dimensions required')
    def matrix(items):
        values = [[r['benchmark_differences'][column] for column in columns] for r in items]
        if any(type(v) not in (int, float) or not math.isfinite(v) for row in values for v in row):
            raise ValueError('Finite nonboolean comparison metrics required')
        return np.asarray(values, dtype=float).reshape((-1, 8)) * np.asarray(directions)
    all_values, front = matrix(rows), matrix(selected)
    if rows and not selected: raise ValueError('Nonempty finite set needs a frontier')
    covered = 0
    for start in range(0, len(rows), 256):
        chunk = all_values[start:start+256]
        dominant = (front[:, None, :] >= chunk[None, :, :]).all(axis=2)
        dominant &= (front[:, None, :] > chunk[None, :, :]).any(axis=2)
        found = dominant.any(axis=0)
        for offset, flag in enumerate(found):
            included = rows[start+offset]['job_id'] in chosen
            if bool(flag) == included:
                raise ValueError('Included candidate dominated or omitted candidate uncovered')
            covered += int(flag)
    return dict(candidate_count=len(rows), frontier_count=len(selected), strictly_dominated_omissions=covered,
                full_componentwise_coverage_verified=True, all_equal_vector_ties_retained=True,
                production_pareto_kernel_called=False)


def audit(frontier_path, frontier_sha256):
    path = Path(frontier_path).resolve(); raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != frontier_sha256: raise ValueError('External frontier SHA differs')
    value = json.loads(raw); source.verify(value)
    columns = list(source.core.previous.ECONOMIC_COLUMNS)
    directions = list(source.core.previous._DIRECTIONS)
    if value['economic_columns'] != columns: raise ValueError('Original eight dimensions changed')
    candidates = value['candidate_diagnostics']
    if len(candidates) != value['original_count']: raise ValueError('Complete candidate denominator differs')
    raw_proof = prove(candidates, value['raw_frontier'], columns, directions)
    eligible = [r for r in candidates if r['fractional_risk_liquidity_passed'] is True]
    risk_proof = prove(eligible, value['risk_liquidity_frontier'], columns, directions)
    source.verify(value)
    if hashlib.sha256(path.read_bytes()).hexdigest() != frontier_sha256: raise ValueError('Frontier changed during audit')
    for p, digest in LOADED.items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest: raise ValueError('Audit source changed')
    return dict(schema='CORRECTED_FRONTIER_INDEPENDENT_DOMINANCE_PROOF_V1',
        frontier=dict(path=str(path), sha256=frontier_sha256), raw_frontier=raw_proof,
        risk_liquidity_frontier=risk_proof, economic_columns=columns, directions=directions,
        numpy_version=np.__version__, source_hashes=dict(LOADED, **{str(path): frontier_sha256}),
        numerical_metrics_recomputed=False, risk_flags_recomputed=False, training_performed=False,
        point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('frontier-path', 'frontier-sha256', 'output'): parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    if Path(args.output).exists(): raise FileExistsError('Create-only independent audit')
    report = audit(args.frontier_path, args.frontier_sha256)
    saved = publish(args.output, report)
    for p, digest in report['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest: raise ValueError('Published audit input changed')
    source.verify(json.loads(Path(args.frontier_path).read_bytes()))
    print(json.dumps(saved))
