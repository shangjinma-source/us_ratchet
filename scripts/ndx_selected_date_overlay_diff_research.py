"""Independent ordered record comparison for a complete selected date; no merge/fit."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_selected_date_overlay_research as producer
from scripts import ndx_selected_completed_queue_independent_audit_20260919 as scalar
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts.ndx_base_three_cell_window_delta_research import publish


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


LOADED = {str(p): drift.file_sha(p) for p in (Path(__file__).resolve(), Path(producer.__file__).resolve(),
    Path(scalar.__file__).resolve(), drift.SOURCE, Path(publish.__code__.co_filename).resolve())}
LINEAGE_KEYS = {'checkpoint_path', 'checkpoint_sha256', 'complete_prefix_index_path',
    'complete_prefix_index_sha256', 'independent_audit_path', 'independent_audit_sha256'}


def compare_records(parent, output, expected_tasks, load_checkpoint):
    """Caller supplies externally bound checkpoint reader, not replacement records."""
    if output['schema'] != 'ndx_selected_complete_date_overlay_v1':
        raise ValueError('Complete selected date schema required')
    expected = {t['job_id']: t for t in expected_tasks}
    before_pending = {r['task']['job_id']: r['task'] for r in parent['records'] if r['status'] == 'PENDING_NUMERICAL_DELTA'}
    if not expected or len(expected) != len(expected_tasks) or digest(expected) != digest(before_pending):
        raise ValueError('Exact whole-date original pending denominator required')
    if len(parent['records']) != len(output['records']):
        raise ValueError('Ordered original record denominator changed')
    seen = set(); changed = 0
    for before, after in zip(parent['records'], output['records']):
        job = before['task']['job_id']
        if job in seen: raise ValueError('Duplicate original task')
        seen.add(job)
        if job not in expected:
            if digest(before) != digest(after): raise ValueError('Unrelated record changed')
            continue
        if (before['origin'] != 'DELTA' or before['result'] is not None
                or digest(before['task']) != digest(expected[job]) or after['status'] != 'AVAILABLE'
                or after['overlay_mode'] != 'SELECTED_DELTA_COMPLETE_DATE'
                or after['original_historical_provenance_verified'] is not False):
            raise ValueError('Selected original task/status differs')
        lineage = after['lineage']['completed_selected_delta']
        if set(lineage) != LINEAGE_KEYS: raise ValueError('Exact reviewed lineage fields required')
        saved = load_checkpoint(lineage, expected[job])
        if digest(saved['result']['original_task']) != digest(expected[job]) or digest(after['result']) != digest(saved['result']['result']):
            raise ValueError('Selected result differs from reviewed full new checkpoint')
        restored = deepcopy(after)
        restored['lineage'].pop('completed_selected_delta')
        for key in ('result', 'status', 'overlay_mode', 'original_historical_provenance_verified'):
            if key in before: restored[key] = deepcopy(before[key])
            else: restored.pop(key, None)
        if digest(before) != digest(restored): raise ValueError('Other selected record fields changed')
        changed += 1
    if changed != len(expected) or len(seen) != parent['original_count']: raise ValueError('Full selected replacement count differs')
    counts = Counter((r['origin'], r['status']) for r in output['records'])
    expected_counts = {o: dict(planned=sum(n for (origin, _), n in counts.items() if origin == o),
        available=counts[(o, 'AVAILABLE')], pending=counts[(o, 'PENDING_NUMERICAL_DELTA')]) for o, _ in counts}
    if (output['original_count'] != len(seen) or output['available_count'] != len(seen) or output['pending_count'] != 0
            or output['selected_delta_added'] != changed or parent['available_count'] + changed != len(seen)
            or parent['pending_count'] != changed or output['counts'] != expected_counts
            or output['records_sha256'] != digest(output['records']) or output['economic_inputs_complete'] is not True
            or output['winner'] is not None):
        raise ValueError('Complete counts or record digest differs')
    return dict(original_count=len(seen), selected_replaced=changed, unrelated_records_exact=len(seen)-changed,
        whole_date_task_map_verified=True, ordered_full_record_diff_verified=True, full_new_results_match_external_checkpoints=True)


def audit(*, date, output_path, output_sha256, index_path, index_sha256, audit_path, audit_sha256):
    sources = dict(LOADED)
    def read(path, sha):
        path = str(Path(path).resolve()); raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha: raise ValueError('External reviewed artifact changed')
        if path in sources and sources[path] != sha: raise ValueError('Conflicting source')
        sources[path] = sha
        return json.loads(raw)
    inventory = read(producer.INVENTORY, producer.INVENTORY_SHA)
    ref, = [r for r in inventory['dates'] if r['date'] == date.replace('-', '')]
    parent = read(ref['overlay_path'], ref['overlay_sha256'])
    output = read(output_path, output_sha256)
    if (parent['coordinate']['selection_date'] != date or output['coordinate'] != parent['coordinate']
            or output['parent_overlay_path'] != ref['overlay_path'] or output['parent_overlay_sha256'] != ref['overlay_sha256']):
        raise ValueError('Hard final inventory parent coordinate differs')
    producer.verify(output)  # Source partitions only; never invokes producer merge.
    if output['input_artifact_binding_verified'] is not True: raise ValueError('Source-bound reader output required')
    manifest = read(producer.MANIFEST, producer.MANIFEST_SHA)
    index = read(index_path, index_sha256); numerical = read(audit_path, audit_sha256)
    ids = scalar.check_index(index, manifest, [manifest['tasks'][0]['new_job_id']])
    if (numerical['schema'] != 'SELECTED_COMPLETED_QUEUE_INDEPENDENT_SCALAR_DECIMAL_AUDIT_V1'
            or numerical['completed_queue_all_tasks_audited'] is not True or numerical['completed'] != len(ids)
            or numerical['planned'] != manifest['planned'] or numerical['status'] != index['status']
            or [r['new_job_id'] for r in numerical['tasks']] != ids
            or numerical['verified_source_hashes'].get(str(Path(index_path).resolve())) != index_sha256):
        raise ValueError('External index and full prefix independent audit differ')
    scalar.verify_report(numerical)
    date_rows = [r for r in manifest['tasks'] if r['task']['selection_date'] == date]
    if not date_rows or not {r['new_job_id'] for r in date_rows} <= set(ids): raise ValueError('Date not fully completed')
    rows = {r['task']['job_id']: r for r in date_rows}
    entries = dict(zip(ids, index['completed']))
    numerical_rows = {r['new_job_id']: r for r in numerical['tasks']}
    def load(lineage, task):
        row = rows[task['job_id']]; entry = entries[row['new_job_id']]
        expected = dict(checkpoint_path=entry['path'], checkpoint_sha256=entry['sha256'],
            complete_prefix_index_path=str(Path(index_path).resolve()), complete_prefix_index_sha256=index_sha256,
            independent_audit_path=str(Path(audit_path).resolve()), independent_audit_sha256=audit_sha256)
        if (lineage != expected or Path(entry['path']).resolve() != scalar.FOLDER/'tasks'/(row['new_job_id']+'.json')
                or numerical['verified_source_hashes'].get(entry['path']) != entry['sha256']
                or digest(numerical_rows[row['new_job_id']]['task']) != digest(task)):
            raise ValueError('Exact external checkpoint/index/audit lineage differs')
        saved = read(entry['path'], entry['sha256'])
        if (saved['new_job_id'] != row['new_job_id'] or digest(saved['original']) != digest(row)
                or saved['manifest_path'] != str(producer.MANIFEST) or saved['manifest_sha256'] != producer.MANIFEST_SHA):
            raise ValueError('Checkpoint full manifest task binding differs')
        return saved
    result = compare_records(parent, output, [r['task'] for r in date_rows], load)
    for path, sha in sources.items():
        if drift.file_sha(path) != sha: raise ValueError('Diff source changed')
    producer.verify(output)
    return dict(schema='SELECTED_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1', date=date, **result,
        output_path=str(Path(output_path).resolve()), output_sha256=output_sha256, source_hashes=sources,
        output_source_partitions_reverified=True, numerical_recomputation_performed=False, merger_called=False,
        historical_full_source_closure_verified=False, point_in_time_verified=False, promotion_allowed=False,
        selection_performed=False, training_performed=False)


def publish_verified(path, report):
    if Path(path).exists(): raise FileExistsError('Create-only audit')
    def verify():
        if any(report['source_hashes'].get(p) != h for p, h in LOADED.items()):
            raise ValueError('Missing loaded audit dependency')
        if report['source_hashes'].get(report['output_path']) != report['output_sha256']:
            raise ValueError('Output external SHA omitted')
        for p, h in report['source_hashes'].items():
            if drift.file_sha(p) != h: raise ValueError('Diff publication source changed')
        value = json.loads(Path(report['output_path']).read_bytes())
        producer.verify(value)
    verify(); result = publish(path, report); verify(); return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('date', 'output-path', 'output-sha256', 'index-path', 'index-sha256', 'audit-path', 'audit-sha256', 'report'):
        parser.add_argument('--'+key, required=True)
    args = vars(parser.parse_args()); report_path = args.pop('report')
    print(json.dumps(publish_verified(report_path, audit(**args))))
