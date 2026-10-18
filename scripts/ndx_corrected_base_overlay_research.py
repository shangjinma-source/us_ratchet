"""Merge a completed, independently audited BASE date into its prior overlay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_corrected_base_overlay_research as merger
from scripts.ndx_base_three_cell_window_delta_research import publish

LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
          for path in (Path(__file__).resolve(), Path(merger.__file__).resolve(),
                       Path(merger.digest.__code__.co_filename).resolve(),
                       Path(publish.__code__.co_filename).resolve())}


def publish_verified(output, value):
    saved = publish(output, value)
    for path, sha in value['source_hashes'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise ValueError('Source changed during overlay publication')
    return saved


def build(*, parent_path, parent_sha256, index_path, index_sha256, audit_path, audit_sha256):
    sources = {}

    def add(path, sha):
        path = str(Path(path).resolve())
        if path in sources and sources[path] != sha:
            raise ValueError('Conflicting source content')
        sources[path] = sha

    def read(path, sha):
        add(path, sha)
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('External artifact SHA mismatch')
        return json.loads(raw)

    def include(document):
        for path, sha in document['source_hashes'].items():
            add(path, sha)

    def verify():
        for path, sha in sources.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
                raise ValueError('Source changed during completed-date merge')

    parent = read(parent_path, parent_sha256)
    index = read(index_path, index_sha256)
    audit = read(audit_path, audit_sha256)
    if (index['schema'] != 'ndx_base_window_snapshot_completion_index_v1' or index['status'] != 'COMPLETE'
            or index['finalization']['status'] != 'COMPLETE'
            or index['finalization']['source_closure_verified'] is not True):
        raise ValueError('Completed and finalized BASE date required')
    if (audit['schema'] != 'ndx_snapshot_completed_date_independent_audit_v1'
            or audit['source_hashes'].get(str(Path(index_path).resolve())) != index_sha256
            or audit['complete_task_lineage_verified'] is not True
            or audit['all_sampled_windows_independently_recomputed'] is not True
            or audit['no_fitter_or_evaluator_called'] is not True
            or audit['promotion_allowed'] is not False):
        raise ValueError('Independent completed-index audit required')
    manifest = read(index['manifest']['path'], index['manifest']['sha256'])
    for value in (parent, manifest, index['finalization'], audit):
        include(value)
    for module_path, sha in LOADED.items():
        add(module_path, sha)
    if (parent['records_sha256'] != merger.digest(parent['records'])
            or parent['coordinate']['selection_date'] != manifest['date'] or audit['date'] != manifest['date']):
        raise ValueError('Parent records/date differs')
    tasks = {row['new_job_id']: row for row in manifest['tasks']}
    if (len(tasks) != len(manifest['tasks']) or len(tasks) != len(index['completed'])
            or len(tasks) != index['planned'] or len(tasks) != audit['complete_task_count']
            or len(tasks) != index['finalization']['completed']):
        raise ValueError('Complete BASE date denominator differs')
    verify()
    seen = set()
    replacements = []
    parent_by_job = {record['task']['job_id']: record for record in parent['records']}
    for entry in index['completed']:
        value = read(entry['path'], entry['sha256'])
        identifier = value['new_job_id']
        if identifier not in tasks or identifier in seen:
            raise ValueError('Unknown or duplicate completed task')
        seen.add(identifier)
        row = tasks[identifier]
        old = parent_by_job[row['task']['job_id']]
        result = value['result']
        if (value['manifest_path'] != index['manifest']['path']
                or value['manifest_sha256'] != index['manifest']['sha256']
                or result['cache_checkpoint_sha256'] != row['checkpoint_sha256']
                or old['task'] != row['task']
                or old['lineage']['original_checkpoint_sha256'] != row['checkpoint_sha256']
                or old['lineage']['original_checkpoint_path'] != row['checkpoint_path']
                or value['promotion_allowed'] is not False):
            raise ValueError('Completed BASE task lineage differs')
        for path, sha in result['source_hashes'].items():
            if sources.get(path) != sha:
                raise ValueError('Task dependency absent from finalized closure')
        replacements.append(dict(task=row['task'], result=result['evaluation']['result'],
            lineage=dict(checkpoint_path=entry['path'], checkpoint_sha256=entry['sha256'],
                         complete_index_path=str(Path(index_path).resolve()), complete_index_sha256=index_sha256,
                         independent_audit_path=str(Path(audit_path).resolve()), independent_audit_sha256=audit_sha256)))
    output = merger.extend_base_overlay(parent=parent, replacements=replacements,
        expected_base_job_ids=[row['task']['job_id'] for row in manifest['tasks']])
    output.update(source_hashes=sources, input_artifact_binding_verified=True,
        parent_overlay_path=str(Path(parent_path).resolve()), parent_overlay_sha256=parent_sha256,
        numerical_audit_scope='COMPLETE_TASK_LINEAGE_AND_STRUCTURAL_SAMPLED_SCALAR_WINDOWS')
    verify()
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-path', 'parent-sha256', 'index-path', 'index-sha256', 'audit-path', 'audit-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    options = vars(parser.parse_args())
    output = options.pop('output')
    value = build(**options)
    print(json.dumps(dict(**publish_verified(output, value), available=value['available_count'], pending=value['pending_count'])))
