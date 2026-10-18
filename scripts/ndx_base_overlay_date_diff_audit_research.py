"""Read-only, complete ordered comparison of a BASE date overlay."""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()


def audit(path, expected):
    sources = {str(SOURCE): LOADED}
    documents = {}

    def include(mapping):
        for name, digest in mapping.items():
            name = str(Path(name).resolve())
            if name in sources and sources[name] != digest:
                raise ValueError('Conflicting source reference')
            sources[name] = digest

    def read(name, digest):
        name = str(Path(name).resolve())
        include({name: digest})
        if name in documents:
            return documents[name]
        raw = Path(name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('External content SHA differs')
        documents[name] = json.loads(raw)
        return documents[name]

    def verify():
        for name, digest in sources.items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise ValueError('Source changed during independent readback')

    new = read(path, expected)
    old = read(new['parent_overlay_path'], new['parent_overlay_sha256'])
    include(old['source_hashes'])
    include(new['source_hashes'])
    verify()
    if new['coordinate'] != old['coordinate'] or len(new['records']) != len(old['records']):
        raise ValueError('Date or original denominator changed')
    expected_jobs = {row['task']['job_id'] for row in old['records']
                     if row['origin'] == 'NON_EQUAL_BASE' and row['status'] == 'PENDING_NUMERICAL_DELTA'}
    seen, changed = set(), set()
    for before, after in zip(old['records'], new['records']):
        job = before['task']['job_id']
        if job in seen:
            raise ValueError('Duplicate original job')
        seen.add(job)
        if job not in expected_jobs:
            if before != after:
                raise ValueError('Unrelated record changed')
            continue
        if (before['result'] is not None or after['status'] != 'AVAILABLE'
                or after['overlay_mode'] != 'BASE_WINDOW_DELTA_COMPLETE_DATE'):
            raise ValueError('Pending BASE replacement missing')
        lineage = after['lineage']['completed_base_delta']
        checkpoint = read(lineage['checkpoint_path'], lineage['checkpoint_sha256'])
        index = read(lineage['complete_index_path'], lineage['complete_index_sha256'])
        if (index['status'] != 'COMPLETE' or index['finalization']['status'] != 'COMPLETE'
                or not any(row['path'] == lineage['checkpoint_path'] and row['sha256'] == lineage['checkpoint_sha256']
                           for row in index['completed'])):
            raise ValueError('Replacement absent from completed external index')
        if (after['result'] != checkpoint['result']['evaluation']['result']
                or checkpoint['result']['cache_checkpoint_sha256'] != before['lineage']['original_checkpoint_sha256']):
            raise ValueError('Replacement result or original lineage differs')
        restored = dict(after, result=before['result'], status=before['status'], overlay_mode=before['overlay_mode'])
        restored['lineage'] = dict(after['lineage'])
        del restored['lineage']['completed_base_delta']
        if restored != before:
            raise ValueError('Other fields changed within BASE record')
        changed.add(job)
    if changed != expected_jobs or not changed:
        raise ValueError('Incomplete BASE date replacement')
    available = sum(row['status'] == 'AVAILABLE' for row in new['records'])
    pending = sum(row['status'] == 'PENDING_NUMERICAL_DELTA' for row in new['records'])
    if (available + pending != len(seen) or new['original_count'] != len(seen)
            or new['available_count'] != available or new['pending_count'] != pending
            or available != old['available_count'] + len(changed)
            or pending != old['pending_count'] - len(changed)):
        raise ValueError('Full date counts differ')
    if any(row['result'] is not None for row in new['records'] if row['status'] == 'PENDING_NUMERICAL_DELTA'):
        raise ValueError('Pending record retains economic result')
    if (any(new[flag] is not False for flag in ('point_in_time_verified', 'promotion_allowed',
                                              'selection_performed', 'whole_lot_executed'))
            or new['winner'] is not None or new['economic_inputs_complete'] is not (pending == 0)):
        raise ValueError('Unsupported execution or promotion claim')
    verify()
    return dict(schema='ndx_base_overlay_date_diff_audit_v2', source_hashes=sources,
                date=new['coordinate']['selection_date'], original_count=len(seen),
                replaced_base_pending=len(changed), other_records_exact=len(seen)-len(changed),
                available_count=available, pending_count=pending,
                complete_ordered_record_diff_verified=True, pending_results_all_none=True,
                training_performed=False, point_in_time_verified=False, promotion_allowed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--output', required=True)
    options = parser.parse_args()
    report = audit(options.path, options.sha256)
    with Path(options.output).open('x', encoding='utf8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    for name, digest in report['source_hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError('Source changed during report publication')
    print(json.dumps(dict(path=str(Path(options.output).resolve()),
        sha256=hashlib.sha256(Path(options.output).read_bytes()).hexdigest(),
        sources=len(report['source_hashes']), replaced=report['replaced_base_pending'])))
