"""Independent ordered full-record diff for the explicit-parent-gap BASE overlay."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift

SOURCE = Path(__file__).resolve()
LOADED = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE, Path(drift.__file__).resolve())}
INVENTORY = ROOT / 'data/cache/research/base_window_snapshot_20260912_v1/all15_independent_readback_inventory_20260919.json'
INVENTORY_SHA = 'd5248a0776afc75097e174cce45e434455553b170c5657e58c0be03e8f59099f'


def records_digest(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check_records(old, new, read_checkpoint, indexed_pairs, task_by_new_job):
    if old['coordinate'] != new['coordinate'] or len(old['records']) != len(new['records']):
        raise ValueError('Coordinate/original denominator changed')
    expected = {r['task']['job_id'] for r in old['records'] if r['origin'] == 'NON_EQUAL_BASE' and r['status'] == 'PENDING_NUMERICAL_DELTA'}
    seen, changed = set(), set()
    for before, after in zip(old['records'], new['records']):
        job = before['task']['job_id']
        if job in seen:
            raise ValueError('Duplicate original job')
        seen.add(job)
        if job not in expected:
            if records_digest(before) != records_digest(after):
                raise ValueError('Unrelated ordered record changed')
            continue
        if before['result'] is not None or after['status'] != 'AVAILABLE' or after['overlay_mode'] != 'BASE_WINDOW_DELTA_COMPLETE_DATE':
            raise ValueError('Pending replacement missing')
        lineage = after['lineage']['completed_base_delta']
        if set(lineage) != {'checkpoint_path', 'checkpoint_sha256', 'complete_index_path', 'complete_index_sha256',
                            'independent_audit_path', 'independent_audit_sha256'}:
            raise ValueError('Unexpected replacement lineage fields')
        if (lineage['checkpoint_path'], lineage['checkpoint_sha256']) not in indexed_pairs:
            raise ValueError('Replacement absent from external complete index')
        checkpoint = read_checkpoint(lineage)
        if task_by_new_job.get(checkpoint['new_job_id']) != before['task']:
            raise ValueError('Checkpoint complete task identity differs')
        if (records_digest(after['result']) != records_digest(checkpoint['result']['evaluation']['result'])
                or checkpoint['result']['cache_checkpoint_sha256'] != before['lineage']['original_checkpoint_sha256']):
            raise ValueError('Saved checkpoint result differs')
        restored = dict(after, result=before['result'], status=before['status'], overlay_mode=before['overlay_mode'])
        restored['lineage'] = dict(after['lineage'])
        del restored['lineage']['completed_base_delta']
        if records_digest(restored) != records_digest(before):
            raise ValueError('Other fields changed inside replaced BASE record')
        changed.add(job)
        del checkpoint
    if not changed or changed != expected:
        raise ValueError('Incomplete BASE replacement denominator')
    counts = Counter((r['origin'], r['status']) for r in new['records'])
    available = sum(n for (_, state), n in counts.items() if state == 'AVAILABLE')
    pending = sum(n for (_, state), n in counts.items() if state == 'PENDING_NUMERICAL_DELTA')
    if (available + pending != len(seen) or new['original_count'] != len(seen)
            or available != new['available_count'] or pending != new['pending_count']
            or available != old['available_count'] + len(changed) or pending != old['pending_count'] - len(changed)
            or new['base_delta_added'] != len(changed)):
        raise ValueError('Count reconciliation differs')
    expected_counts = {origin: dict(planned=sum(n for (o, _), n in counts.items() if o == origin),
        available=counts[(origin, 'AVAILABLE')], pending=counts[(origin, 'PENDING_NUMERICAL_DELTA')]) for origin, _ in counts}
    if new['counts'] != expected_counts:
        raise ValueError('Per-origin counts differ')
    if any(r['result'] is not None for r in new['records'] if r['status'] == 'PENDING_NUMERICAL_DELTA'):
        raise ValueError('Pending metrics present')
    if old['records_sha256'] != records_digest(old['records']) or new['records_sha256'] != records_digest(new['records']):
        raise ValueError('Record digest differs')
    return dict(original_count=len(seen), replaced_base_pending=len(changed), other_records_exact=len(seen)-len(changed),
                available_count=available, pending_count=pending)


def verify_report_sources(value):
    observed = drift.verify_expected_sources(value['historical_expected_source_hashes'], drift.load_contract())
    if observed['historical_gap_observations'] != value['historical_price_cache_gap_observations']:
        raise ValueError('Gap partition differs')
    if any(value['verified_source_hashes'].get(p) != h for p, h in observed['verified_source_hashes'].items()):
        raise ValueError('Verified historical dependency omitted')
    for p, h in value['verified_source_hashes'].items():
        if drift.file_sha(p) != h:
            raise ValueError('Strict source changed: ' + p)


def audit(path, expected):
    sources = dict(LOADED)
    def read(p, h):
        p = str(Path(p).resolve())
        if p in sources and sources[p] != h:
            raise ValueError('Source conflict')
        raw = Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest() != h:
            raise ValueError('External SHA differs')
        sources[p] = h
        return json.loads(raw)
    new = read(path, expected)
    old = read(new['parent_overlay_path'], new['parent_overlay_sha256'])
    if new['schema'] != 'ndx_corrected_base_overlay_limited_drift_v3' or 'source_hashes' in new:
        raise ValueError('Explicit limited BASE schema required')
    if any(new[k] is not False for k in ('historical_full_source_closure_verified', 'original_historical_provenance_verified',
        'point_in_time_verified', 'promotion_allowed', 'selection_performed', 'whole_lot_executed')) or new['winner'] is not None:
        raise ValueError('Unsupported provenance/execution claim')
    if new['base_numerical_source_closure_verified'] is not True or new['input_artifact_binding_verified'] is not True:
        raise ValueError('Strict BASE binding missing')
    if new['historical_expected_source_hashes'] != old['source_hashes'] or len(new['historical_price_cache_gap_observations']) != 26:
        raise ValueError('Original historical dependency mapping changed')
    verify_report_sources(new)
    for p, h in new['verified_source_hashes'].items():
        if p in sources and sources[p] != h:
            raise ValueError('Strict dependency conflict')
        sources[p] = h
    inventory = read(INVENTORY, INVENTORY_SHA)
    row, = [r for r in inventory['dates'] if r['date'] == new['coordinate']['selection_date'].replace('-', '')]
    reference = new['base_completed_audit_reference']
    if any(reference[k] != row[k] for k in ('index_path', 'index_sha256', 'audit_path', 'audit_sha256')):
        raise ValueError('Hard date index/audit authority differs')
    index = read(row['index_path'], row['index_sha256'])
    independent = read(row['audit_path'], row['audit_sha256'])
    if index['status'] != 'COMPLETE' or index['finalization']['status'] != 'COMPLETE' or independent['complete_task_count'] != row['completed']:
        raise ValueError('Complete audited index required')
    pairs = {(e['path'], e['sha256']) for e in index['completed']}
    if len(pairs) != row['completed']:
        raise ValueError('Complete unique index denominator differs')
    manifest = read(index['manifest']['path'], index['manifest']['sha256'])
    task_by_new_job = {r['new_job_id']: r['task'] for r in manifest['tasks']}
    if len(task_by_new_job) != len(manifest['tasks']) or len(task_by_new_job) != len(pairs):
        raise ValueError('Manifest complete task denominator differs')
    def checkpoint(lineage):
        if (lineage['complete_index_path'] != row['index_path'] or lineage['complete_index_sha256'] != row['index_sha256']
                or lineage['independent_audit_path'] != row['audit_path'] or lineage['independent_audit_sha256'] != row['audit_sha256']):
            raise ValueError('Per-record external lineage differs')
        value = read(lineage['checkpoint_path'], lineage['checkpoint_sha256'])
        if value['manifest_path'] != index['manifest']['path'] or value['manifest_sha256'] != index['manifest']['sha256']:
            raise ValueError('Checkpoint manifest binding differs')
        return value
    counts = check_records(old, new, checkpoint, pairs, task_by_new_job)
    if counts['replaced_base_pending'] != row['completed'] or new['economic_inputs_complete'] is not (counts['pending_count'] == 0):
        raise ValueError('Final completeness differs')
    report = dict(schema='ndx_base_limited_overlay_full_diff_audit_v1', **counts, date=new['coordinate']['selection_date'],
        verified_source_hashes=sources, historical_expected_source_hashes=new['historical_expected_source_hashes'],
        historical_price_cache_gap_observations=new['historical_price_cache_gap_observations'],
        full_ordered_record_diff_verified=True, exact_new_results_against_external_checkpoints=True,
        checkpoint_documents_cached=False, historical_full_source_closure_verified=False,
        training_performed=False, point_in_time_verified=False, promotion_allowed=False)
    verify_report_sources(report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('path', 'sha256', 'output'):
        parser.add_argument('--' + key, required=True)
    options = parser.parse_args()
    value = audit(options.path, options.sha256)
    with Path(options.output).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
    verify_report_sources(value)
    print(json.dumps(dict(path=str(Path(options.output).resolve()), sha256=drift.file_sha(options.output),
                         replaced=value['replaced_base_pending'])))
