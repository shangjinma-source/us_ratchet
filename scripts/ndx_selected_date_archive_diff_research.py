"""Independent ordered full-record diff with explicit immutable archive binding."""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_selected_date_overlay_diff_research as pure
from scripts import ndx_selected_archive_completed_independent_audit_20260919 as scalar
from backtest import ndx_root_price_archive_contract_research as archive

SCHEMA = 'SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1'
SOURCE = Path(__file__).resolve()
LOADED = dict(pure.LOADED)
archive.merge(LOADED, scalar.LOADED)
archive.merge(LOADED, {str(SOURCE): archive.drift.file_sha(SOURCE), str(archive.SOURCE): archive.LOADED})
FLAGS = ('numerical_recomputation_performed', 'merger_called', 'historical_full_source_closure_verified',
         'point_in_time_verified', 'promotion_allowed', 'selection_performed', 'training_performed',
         'original_live_price_paths_verified')


def check_audit(index, manifest, numerical, *, index_path, index_sha256):
    reference = index['manifest']
    identifiers = scalar.check_index(index, manifest, reference)
    if (numerical.get('schema') != scalar.SCHEMA or numerical.get('manifest') != reference
            or numerical.get('completed_index') != dict(path=str(Path(index_path).resolve()), sha256=index_sha256)
            or numerical.get('completed_queue_all_tasks_audited') is not True
            or type(numerical.get('completed')) is not int or numerical['completed'] != len(identifiers)
            or numerical.get('planned') != manifest['planned'] or numerical.get('status') != index['status']
            or [r['new_job_id'] for r in numerical['tasks']] != identifiers
            or numerical['historical_expected_source_hashes'].get(str(Path(index_path).resolve())) != index_sha256):
        raise ValueError('Exact independent audited prefix required')
    return identifiers


def verify(report):
    if report.get('schema') != SCHEMA:
        raise ValueError('Archive diff schema required')
    scalar.original.require_false(report, FLAGS)
    sources = report['historical_expected_source_hashes']
    if any(sources.get(p) != h for p, h in LOADED.items()):
        raise ValueError('Independent loaded source omitted')
    if sources.get(report['output_path']) != report['output_sha256']:
        raise ValueError('External output SHA binding omitted')
    actual = archive.verify_expected_sources(sources, archive.load_contract())
    if not scalar.original.exact(actual, report['archive_resolution']):
        raise ValueError('Archive source partition differs')
    scalar.original.verify_gaps(report['historical_loader_gap_observations'])


def audit(*, date, output_path, output_sha256, index_path, index_sha256, audit_path, audit_sha256):
    # The producer verifier authenticates source partitions only; its merger is never called.
    from scripts import ndx_selected_date_archive_overlay_research as producer
    sources = dict(LOADED)
    archive.merge(sources, producer.LOADED)
    def read(path, sha):
        path = str(Path(path).resolve()); raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('External artifact SHA differs')
        archive.merge(sources, {path: sha})
        return json.loads(raw)
    inventory = read(pure.producer.INVENTORY, pure.producer.INVENTORY_SHA)
    reference, = [r for r in inventory['dates'] if r['date'] == date.replace('-', '')]
    parent = read(reference['overlay_path'], reference['overlay_sha256'])
    output = read(output_path, output_sha256)
    if (parent['coordinate']['selection_date'] != date or output['coordinate'] != parent['coordinate']
            or output['parent_overlay_path'] != reference['overlay_path']
            or output['parent_overlay_sha256'] != reference['overlay_sha256']
            or output.get('input_artifact_binding_verified') is not True):
        raise ValueError('Hard final inventory parent coordinate differs')
    producer.verify(output)
    index = read(index_path, index_sha256)
    manifest = read(index['manifest']['path'], index['manifest']['sha256'])
    numerical = read(audit_path, audit_sha256)
    identifiers = check_audit(index, manifest, numerical, index_path=index_path, index_sha256=index_sha256)
    scalar.verify_report(numerical)
    for mapping in (output['historical_expected_source_hashes'], numerical['historical_expected_source_hashes']):
        archive.merge(sources, mapping)
    rows = [r for r in manifest['tasks'] if r['task']['selection_date'] == date]
    if not rows or not {r['new_job_id'] for r in rows} <= set(identifiers):
        raise ValueError('Whole selected date not completed')
    by_job = {r['task']['job_id']: r for r in rows}
    if len(by_job) != len(rows):
        raise ValueError('Duplicate original job')
    entries = dict(zip(identifiers, index['completed']))
    reviewed = {r['new_job_id']: r for r in numerical['tasks']}
    def load(lineage, task):
        row = by_job[task['job_id']]; entry = entries[row['new_job_id']]
        expected = dict(checkpoint_path=entry['path'], checkpoint_sha256=entry['sha256'],
            complete_prefix_index_path=str(Path(index_path).resolve()), complete_prefix_index_sha256=index_sha256,
            independent_audit_path=str(Path(audit_path).resolve()), independent_audit_sha256=audit_sha256)
        if (lineage != expected or Path(entry['path']).resolve() != Path(index_path).resolve().parent / (row['new_job_id'] + '.json')
                or numerical['historical_expected_source_hashes'].get(entry['path']) != entry['sha256']
                or not scalar.original.exact(reviewed[row['new_job_id']]['task'], task)):
            raise ValueError('Exact external checkpoint/index/audit lineage differs')
        saved = read(entry['path'], entry['sha256'])
        if (saved.get('schema') != 'SELECTED_ARCHIVE_RESOLUTION_TASK_V1' or saved['new_job_id'] != row['new_job_id']
                or not scalar.original.exact(saved['original'], row)
                or saved['manifest_path'] != index['manifest']['path'] or saved['manifest_sha256'] != index['manifest']['sha256']):
            raise ValueError('Complete archive checkpoint binding differs')
        return saved
    result = pure.compare_records(parent, output, [r['task'] for r in rows], load)
    producer.verify(output)
    partition = archive.verify_expected_sources(sources, archive.load_contract())
    report = dict(schema=SCHEMA, date=date, **result, output_path=str(Path(output_path).resolve()),
        output_sha256=output_sha256, historical_expected_source_hashes=sources, archive_resolution=partition,
        historical_loader_gap_observations=output['historical_loader_gap_observations'],
        output_source_partitions_reverified=True, **dict.fromkeys(FLAGS, False))
    verify(report)
    return report


def publish_verified(path, report):
    verify(report); path = Path(path).resolve()
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        verify(report)
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    verify(report)
    return dict(path=str(path), sha256=archive.drift.file_sha(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('date', 'output-path', 'output-sha256', 'index-path', 'index-sha256', 'audit-path', 'audit-sha256', 'report'):
        parser.add_argument('--' + key, required=True)
    arguments = vars(parser.parse_args()); target = arguments.pop('report')
    print(json.dumps(publish_verified(target, audit(**arguments))))
