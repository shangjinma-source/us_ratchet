"""Add a complete BASE correction cohort to an immutable partial overlay."""
from collections import Counter
from copy import deepcopy
import math

from backtest.ndx_corrected_cohort_overlay_research import ECONOMIC_KEYS, digest


def extend_base_overlay(*, parent, replacements, expected_base_job_ids):
    """Pure merge; the I/O caller must independently bind all input artifacts."""
    if parent['schema'] != 'ndx_corrected_cohort_overlay_v1':
        raise ValueError('Original partial overlay required')
    if parent['promotion_allowed'] is not False or parent['selection_performed'] is not False:
        raise ValueError('Unselected research overlay required')
    expected = set(expected_base_job_ids)
    if not expected or len(expected) != len(expected_base_job_ids):
        raise ValueError('Unique complete BASE task denominator required')
    pending_base = {record['task']['job_id'] for record in parent['records']
                    if record['origin'] == 'NON_EQUAL_BASE' and record['status'] == 'PENDING_NUMERICAL_DELTA'}
    if expected != pending_base:
        raise ValueError('Every pending BASE task in the original date must be replaced')
    by_job = {}
    for replacement in replacements:
        job = replacement['task']['job_id']
        if job in by_job:
            raise ValueError('Duplicate BASE replacement')
        by_job[job] = replacement
    if set(by_job) != expected:
        raise ValueError('Complete BASE date replacements required')
    output = deepcopy(parent)
    seen = set()
    original_counts = Counter()
    for record in output['records']:
        job = record['task']['job_id']
        if job in seen:
            raise ValueError('Duplicate original task')
        seen.add(job)
        original_counts[record['origin']] += 1
        if job not in by_job:
            continue
        replacement = by_job[job]
        if (record['origin'] != 'NON_EQUAL_BASE' or record['status'] != 'PENDING_NUMERICAL_DELTA'
                or record['result'] is not None or record['task'] != replacement['task']):
            raise ValueError('BASE replacement task/state differs')
        result = replacement['result']
        if any(result.get(key) != record['task'][key] for key in ('tickers', 'holding_count', 'weight_spec')):
            raise ValueError('Replacement numerical identity differs')
        if any(key.startswith('whole_lot_') for key in result):
            raise ValueError('Fractional BASE must not acquire whole-lot fields')
        if any(type(result.get(key)) not in (int, float) or not math.isfinite(result[key]) for key in ECONOMIC_KEYS):
            raise ValueError('Complete finite twenty-metric replacement required')
        record['result'] = deepcopy(result)
        record['status'] = 'AVAILABLE'
        record['overlay_mode'] = 'BASE_WINDOW_DELTA_COMPLETE_DATE'
        record['lineage']['completed_base_delta'] = deepcopy(replacement['lineage'])
    if not expected <= seen or sum(original_counts.values()) != parent['original_count']:
        raise ValueError('Original/replacement denominator differs')
    available = Counter(r['origin'] for r in output['records'] if r['status'] == 'AVAILABLE')
    pending = Counter(r['origin'] for r in output['records'] if r['status'] == 'PENDING_NUMERICAL_DELTA')
    if sum(available.values()) != parent['available_count'] + len(expected):
        raise ValueError('Available-count reconciliation differs')
    if any(r['result'] is not None for r in output['records'] if r['status'] == 'PENDING_NUMERICAL_DELTA'):
        raise ValueError('Remaining pending records expose stale metrics')
    output.update(schema='ndx_corrected_base_overlay_v2',
        available_count=sum(available.values()), pending_count=sum(pending.values()),
        counts={origin:dict(planned=count, available=available[origin], pending=pending[origin])
                for origin, count in original_counts.items()},
        economic_inputs_complete=not pending, base_delta_added=len(expected),
        records_sha256=digest(output['records']), input_artifact_binding_verified=False,
        selection_performed=False, winner=None, promotion_allowed=False)
    return output
