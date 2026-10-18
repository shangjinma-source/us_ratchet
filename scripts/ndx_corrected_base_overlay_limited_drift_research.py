"""Complete BASE results with a separately declared historical parent CSV gap."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_corrected_base_overlay_research as merger
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts.ndx_base_three_cell_window_delta_research import publish

LOADED = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
    Path(__file__).resolve(), Path(merger.__file__).resolve(),
    Path(merger.digest.__code__.co_filename).resolve(), Path(publish.__code__.co_filename).resolve(),
    Path(drift.__file__).resolve())}
AUDIT_INVENTORY = ROOT / 'data/cache/research/base_window_snapshot_20260912_v1/all15_independent_readback_inventory_20260919.json'
AUDIT_INVENTORY_SHA = 'd5248a0776afc75097e174cce45e434455553b170c5657e58c0be03e8f59099f'


def audit_authority(date, index_path, index_sha256, audit_path, audit_sha256):
    if drift.file_sha(AUDIT_INVENTORY) != AUDIT_INVENTORY_SHA:
        raise ValueError('Hard completed-audit inventory SHA differs')
    inventory = json.loads(AUDIT_INVENTORY.read_bytes())
    if (inventory['schema'] != 'ndx_base_snapshot_all15_readback_inventory_20260919_v1'
            or inventory['date_count'] != 15 or inventory['completed'] != 15578
            or len(inventory['dates']) != 15 or len({r['date'] for r in inventory['dates']}) != 15):
        raise ValueError('Hard full fifteen-date audit inventory required')
    rows = [r for r in inventory['dates'] if r['date'] == date.replace('-', '')]
    if len(rows) != 1:
        raise ValueError('Unknown externally audited date')
    row = rows[0]
    if (row['index_path'] != str(Path(index_path).resolve()) or row['index_sha256'] != index_sha256
            or row['audit_path'] != str(Path(audit_path).resolve()) or row['audit_sha256'] != audit_sha256):
        raise ValueError('Caller index/audit differs from hard fifteen-date inventory')


def verify_partitions(*, verified, historical, contract):
    """The exception applies only to historical parent dependencies."""
    observed = drift.verify_expected_sources(historical, contract)
    for path, sha in verified.items():
        if drift.file_sha(path) != sha:
            raise ValueError('Strict BASE/artifact source changed: ' + path)
        if path in historical and historical[path] != sha:
            raise ValueError('Conflicting historical and verified source')
    return observed


def publish_verified(output, value):
    def verify():
        if (value.get('schema') != 'ndx_corrected_base_overlay_limited_drift_v3'
                or any(value.get(key) is not False for key in ('historical_full_source_closure_verified',
                    'original_historical_provenance_verified', 'point_in_time_verified', 'promotion_allowed', 'selection_performed'))
                or 'source_hashes' in value or len(value['historical_price_cache_gap_observations']) != 26):
            raise ValueError('Explicit limited-provenance output required')
        observed = verify_partitions(verified=value['verified_source_hashes'],
                                    historical=value['historical_expected_source_hashes'], contract=drift.load_contract())
        if observed['historical_gap_observations'] != value['historical_price_cache_gap_observations']:
            raise ValueError('Historical gap observations changed')
        required = dict(observed['verified_source_hashes'], **LOADED)
        required[str(AUDIT_INVENTORY)] = AUDIT_INVENTORY_SHA
        if any(value['verified_source_hashes'].get(p) != h for p, h in required.items()):
            raise ValueError('Verified source partition omitted or changed')
        audit_authority(value['coordinate']['selection_date'], **value['base_completed_audit_reference'])
    verify()
    saved = publish(output, value)
    verify()
    return saved


def build(*, parent_path, parent_sha256, index_path, index_sha256, audit_path, audit_sha256):
    sources = dict(LOADED)
    contract = drift.load_contract()

    def add(path, sha):
        path = str(Path(path).resolve())
        if path in sources and sources[path] != sha:
            raise ValueError('Conflicting strict source')
        sources[path] = sha

    def read(path, sha):
        add(path, sha)
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('External artifact SHA mismatch')
        return json.loads(raw)

    parent = read(parent_path, parent_sha256)
    # Original parent only. Already-merged BASE records must never be replaced twice.
    if parent['schema'] != 'ndx_corrected_cohort_overlay_v1':
        raise ValueError('Original partial parent overlay required')
    historical = {str(Path(p).resolve()): h for p, h in parent['source_hashes'].items()}
    if len(historical) != len(parent['source_hashes']):
        raise ValueError('Duplicate normalized historical path')
    if set(historical) & set(contract['exceptions']) != set(contract['exceptions']):
        raise ValueError('Parent must declare the exact recorded 26-file gap')
    index = read(index_path, index_sha256)
    audit = read(audit_path, audit_sha256)
    if (index['schema'] != 'ndx_base_window_snapshot_completion_index_v1' or index['status'] != 'COMPLETE'
            or index['finalization']['status'] != 'COMPLETE'
            or index['finalization']['source_closure_verified'] is not True):
        raise ValueError('Strict completed BASE date required')
    if (audit['schema'] != 'ndx_snapshot_completed_date_independent_audit_v1'
            or audit['source_hashes'].get(str(Path(index_path).resolve())) != index_sha256
            or audit['complete_task_lineage_verified'] is not True
            or audit['all_sampled_windows_independently_recomputed'] is not True
            or audit['no_fitter_or_evaluator_called'] is not True
            or audit['promotion_allowed'] is not False or audit['point_in_time_verified'] is not False):
        raise ValueError('Strict independent completed-index audit required')
    manifest = read(index['manifest']['path'], index['manifest']['sha256'])
    audit_authority(manifest['date'], index_path, index_sha256, audit_path, audit_sha256)
    add(AUDIT_INVENTORY, AUDIT_INVENTORY_SHA)
    for document in (manifest, index['finalization'], audit):
        for path, sha in document['source_hashes'].items():
            add(path, sha)
    if (parent['records_sha256'] != merger.digest(parent['records'])
            or parent['coordinate']['selection_date'] != manifest['date'] or audit['date'] != manifest['date']):
        raise ValueError('Parent records/date differs')
    tasks = {r['new_job_id']: r for r in manifest['tasks']}
    if (len(tasks) != len(manifest['tasks']) or len(tasks) != len(index['completed'])
            or len(tasks) != index['planned'] or len(tasks) != audit['complete_task_count']
            or len(tasks) != index['finalization']['completed'] or len(tasks) != index['finalization']['planned']):
        raise ValueError('Complete BASE date denominator differs')
    observation = verify_partitions(verified=sources, historical=historical, contract=contract)
    for path, sha in observation['verified_source_hashes'].items():
        add(path, sha)
    parent_by_job = {r['task']['job_id']: r for r in parent['records']}
    if len(parent_by_job) != len(parent['records']):
        raise ValueError('Duplicate parent task')
    seen, replacements = set(), []
    for entry in index['completed']:
        value = read(entry['path'], entry['sha256'])
        identifier = value['new_job_id']
        if identifier not in tasks or identifier in seen:
            raise ValueError('Unknown/duplicate completed BASE task')
        seen.add(identifier)
        row = tasks[identifier]
        old = parent_by_job[row['task']['job_id']]
        result = value['result']
        if (value['manifest_path'] != index['manifest']['path'] or value['manifest_sha256'] != index['manifest']['sha256']
                or result['cache_checkpoint_sha256'] != row['checkpoint_sha256'] or old['task'] != row['task']
                or old['lineage']['original_checkpoint_sha256'] != row['checkpoint_sha256']
                or old['lineage']['original_checkpoint_path'] != row['checkpoint_path'] or value['promotion_allowed'] is not False):
            raise ValueError('Completed BASE task lineage differs')
        if any(sources.get(p) != h for p, h in result['source_hashes'].items()):
            raise ValueError('Task dependency absent from strict finalized BASE closure')
        replacements.append(dict(task=row['task'], result=result['evaluation']['result'], lineage=dict(
            checkpoint_path=entry['path'], checkpoint_sha256=entry['sha256'],
            complete_index_path=str(Path(index_path).resolve()), complete_index_sha256=index_sha256,
            independent_audit_path=str(Path(audit_path).resolve()), independent_audit_sha256=audit_sha256)))
        del result, value
    output = merger.extend_base_overlay(parent=parent, replacements=replacements,
        expected_base_job_ids=[r['task']['job_id'] for r in manifest['tasks']])
    changed = {r['task']['job_id'] for r in replacements}
    if any(a != b for a, b in zip(parent['records'], output['records']) if a['task']['job_id'] not in changed):
        raise ValueError('Unrelated parent record changed')
    observation = verify_partitions(verified=sources, historical=historical, contract=contract)
    output.pop('source_hashes', None)
    output.update(schema='ndx_corrected_base_overlay_limited_drift_v3', verified_source_hashes=sources,
        historical_expected_source_hashes=historical,
        historical_price_cache_gap_observations=observation['historical_gap_observations'],
        historical_full_source_closure_verified=False, original_historical_provenance_verified=False,
        base_numerical_source_closure_verified=True, input_artifact_binding_verified=True,
        point_in_time_verified=False, promotion_allowed=False, selection_performed=False, winner=None,
        parent_overlay_path=str(Path(parent_path).resolve()), parent_overlay_sha256=parent_sha256,
        base_completed_audit_reference=dict(index_path=str(Path(index_path).resolve()), index_sha256=index_sha256,
            audit_path=str(Path(audit_path).resolve()), audit_sha256=audit_sha256),
        numerical_audit_scope='COMPLETE_TASK_LINEAGE_AND_STRUCTURAL_SAMPLED_SCALAR_WINDOWS',
        provenance_scope='STRICT_BASE_NUMERICAL_CLOSURE_WITH_EXPLICIT_PARENT_26_PRICE_CACHE_GAP')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent-path', 'parent-sha256', 'index-path', 'index-sha256', 'audit-path', 'audit-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    options = vars(parser.parse_args())
    output = options.pop('output')
    value = build(**options)
    print(json.dumps(dict(**publish_verified(output, value), available=value['available_count'], pending=value['pending_count'])))
