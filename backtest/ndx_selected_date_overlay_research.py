"""Pure complete-date selected DELTA replacement; no source authentication."""
from collections import Counter
from copy import deepcopy
import math
from backtest.ndx_corrected_cohort_overlay_research import ECONOMIC_KEYS, digest


def extend_selected_date(*, parent, replacements, expected_tasks):
    if parent['schema'] not in ('ndx_corrected_delta_paired_overlay_limited_drift_v2', 'ndx_corrected_base_overlay_limited_drift_v3'):
        raise ValueError('Final corrected parent date required')
    if any(parent[k] is not False for k in ('historical_full_source_closure_verified', 'point_in_time_verified', 'promotion_allowed', 'selection_performed')):
        raise ValueError('Unpromoted limited-provenance parent required')
    expected = {t['job_id']: t for t in expected_tasks}
    pending = {r['task']['job_id']: r['task'] for r in parent['records'] if r['status'] == 'PENDING_NUMERICAL_DELTA'}
    if not expected or len(expected) != len(expected_tasks) or digest(expected) != digest(pending):
        raise ValueError('Whole pending selected date task map required')
    supplied = {r['task']['job_id']: r for r in replacements}
    if len(supplied) != len(replacements) or set(supplied) != set(expected):
        raise ValueError('Complete unique selected date replacements required')
    output = deepcopy(parent)
    seen = set()
    for record in output['records']:
        job = record['task']['job_id']
        if job in seen:
            raise ValueError('Duplicate original task')
        seen.add(job)
        if job not in supplied:
            continue
        row = supplied[job]
        if set(row['lineage']) != {'checkpoint_path', 'checkpoint_sha256', 'complete_prefix_index_path',
                'complete_prefix_index_sha256', 'independent_audit_path', 'independent_audit_sha256'}:
            raise ValueError('Exact reviewed checkpoint/index/audit lineage required')
        if (record['origin'] != 'DELTA' or record['status'] != 'PENDING_NUMERICAL_DELTA' or record['result'] is not None
                or digest(record['task']) != digest(row['task']) or digest(row['task']) != digest(expected[job])):
            raise ValueError('Original selected pending task differs')
        result, original = row['result'], row['original_result']
        if set(result) != set(original):
            raise ValueError('Complete original v3 result field set required')
        if any(result.get(k) != row['task'][k] or original.get(k) != row['task'][k] for k in ('tickers', 'holding_count', 'weight_spec')):
            raise ValueError('Full numerical result identity differs')
        if any(type(result.get(k)) not in (int, float) or not math.isfinite(result[k]) for k in ECONOMIC_KEYS):
            raise ValueError('Finite complete twenty metrics required')
        digest(result)  # All other numeric fields must also be JSON-finite.
        if not any(k.startswith('whole_lot_') for k in result):
            raise ValueError('Full v3 nominal result required')
        record.update(result=deepcopy(result), status='AVAILABLE', overlay_mode='SELECTED_DELTA_COMPLETE_DATE',
                      original_historical_provenance_verified=False)
        record['lineage'] = dict(record['lineage'], completed_selected_delta=deepcopy(row['lineage']))
    for before, after in zip(parent['records'], output['records']):
        if before['task']['job_id'] not in expected and digest(before) != digest(after):
            raise ValueError('Unrelated original record changed')
    counts = Counter((r['origin'], r['status']) for r in output['records'])
    available = sum(n for (_, s), n in counts.items() if s == 'AVAILABLE')
    pending_count = sum(n for (_, s), n in counts.items() if s == 'PENDING_NUMERICAL_DELTA')
    if (len(seen) != parent['original_count'] or available != parent['available_count'] + len(expected)
            or pending_count != 0 or parent['pending_count'] != len(expected) or available != len(seen)):
        raise ValueError('Complete date count reconciliation differs')
    output.update(schema='ndx_selected_complete_date_overlay_v1', available_count=available, pending_count=0,
        selected_delta_added=len(expected), economic_inputs_complete=True, input_artifact_binding_verified=False,
        records_sha256=digest(output['records']), counts={o: dict(planned=sum(n for (origin, _), n in counts.items() if origin == o),
            available=counts[(o, 'AVAILABLE')], pending=0) for o, _ in counts},
        historical_full_source_closure_verified=False, original_historical_provenance_verified=False,
        saved_non20_fields_independently_recomputed=False, binary_float_ledger_hash_independently_verified=False,
        nominal_quote_authenticity_verified=False, dynamic_next_open_execution_validated=False,
        point_in_time_verified=False, promotion_allowed=False, selection_performed=False, winner=None)
    return output
