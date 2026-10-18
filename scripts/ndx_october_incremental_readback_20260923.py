"""Authenticate the sealed 201 October checks; numerically audit only new rows."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_october_cutoff_snapshot_independent_readback_20260923 as original

SEED = ROOT / 'data/cache/research/corrected_cutoff_snapshot_20260923_v1/20231002_completed201_independent_readback.json'
SEED_SHA = 'f680ab31cc6289c61d7eaf60e08d0b813117afd34b68b4880ba0d27f8c9cdb1e'
READER_SHA = '641142493919885565d35181c8eb88d35d50ccc14bbfaf2a5753fd1386aef022'
SOURCE = Path(__file__).resolve()
LOADED = dict(original.LOADED, **{str(SOURCE): original.archive.drift.file_sha(SOURCE)})


def check_prefix(seed, previous, current):
    if (seed['schema'] != original.SCHEMA or type(seed['completed']) is not int
            or seed['completed'] != 201 or len(seed['details']) != 201
            or previous['completed'] != current['completed'][:201]
            or len(current['completed']) <= 201
            or [row['job_id'] for row in seed['details']] != [row['job_id'] for row in previous['completed']]):
        raise ValueError('Unchanged externally audited 201 prefix required')
    for detail, entry in zip(seed['details'], previous['completed'], strict=True):
        if detail['result_reference'] != entry['result']:
            raise ValueError('Reused numerical detail reference differs')


def build(index_path, index_sha256):
    if original.archive.drift.file_sha(Path(original.__file__)) != READER_SHA:
        raise ValueError('Frozen independent reader source differs')
    sources = dict(LOADED)

    def read(path, checksum):
        path = Path(path).resolve()
        raw = path.read_bytes()
        if original.hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError('External artifact SHA differs')
        original.archive.merge(sources, {str(path): checksum})
        return json.loads(raw)

    seed = read(SEED, SEED_SHA)
    previous = read(seed['index']['path'], seed['index']['sha256'])
    queue = read(original.QUEUE, original.QUEUE_SHA)
    context = read(original.CONTEXT, original.CONTEXT_SHA)
    index = read(index_path, index_sha256)
    candidates = original.validate_index(index, queue)
    original.validate_index(previous, queue)
    check_prefix(seed, previous, index)
    if (queue['context'] != dict(path=str(original.CONTEXT), sha256=original.CONTEXT_SHA)
            or queue['original_runtime'] != context['runtime'] or queue['historical_cutoff'] != '2023-09-29'):
        raise ValueError('Original October cutoff or runtime differs')
    final = index['finalization']
    if final['historical_loader_gap_observations'] != queue['historical_loader_gap_observations']:
        raise ValueError('Historical gaps differ')
    required = dict(queue['historical_expected_source_hashes'], **{
        str(original.QUEUE): original.QUEUE_SHA,
        str(original.CORE): LOADED[str(original.CORE)], str(original.RUNNER): LOADED[str(original.RUNNER)]})
    original.archive.merge(required, previous['finalization']['historical_expected_source_hashes'])
    for path, checksum in required.items():
        if final['historical_expected_source_hashes'].get(path) != checksum:
            raise ValueError('Final source closure omitted or changed an original source')
    contract = original.archive.load_contract()
    for document in (seed, queue, final):
        original.archive.merge(sources, document['historical_expected_source_hashes'])
        if original.archive.verify_expected_sources(document['historical_expected_source_hashes'], contract) != document['archive_resolution']:
            raise ValueError('Source partition differs')
    original.verify_gaps(queue['historical_loader_gap_observations'])
    details = deepcopy(seed['details'])
    folder = Path(index_path).resolve().parent
    for ordinal, entry in enumerate(index['completed']):
        job = entry['job_id']
        if set(entry) != {'job_id', 'started', 'result'}:
            raise ValueError('Exact completed entry required')
        for key, name in (('result', job + '.json'), ('started', job + '.started.json')):
            if (set(entry[key]) != {'path', 'sha256'} or entry[key]['path'] != str(folder / name)
                    or final['historical_expected_source_hashes'].get(entry[key]['path']) != entry[key]['sha256']):
                raise ValueError('Complete checkpoint source linkage differs')
        if ordinal < 201:
            continue
        value = read(entry['result']['path'], entry['result']['sha256'])
        attempt = read(entry['started']['path'], entry['started']['sha256'])
        result = original.validate_task(value, attempt, queue, index, candidates)
        if value['job_id'] != job:
            raise ValueError('Saved task and index differ')
        detail = dict(job_id=job, status=result['status'], result_reference=entry['result'], typed_decimal=None)
        if result['refit'] is not None:
            detail['typed_decimal'] = original.pure.inspect_context(context, queue, result)
            checks = detail['typed_decimal']['decimal_risks']['checks']
            if (original.pure.digest(checks) != original.pure.digest(result['independently_recomputed_five_checks'])
                    or result['status'] != ('FITTED_FIVE_RISKS_PASSED' if all(checks.values()) else 'FITTED_FIVE_RISKS_FAILED')):
                raise ValueError('New independent October risks differ')
        else:
            detail.update(error_type=result['error_type'], error=result['error'], numerical_failure_is_economic_infeasibility=False)
        details.append(detail)
    return dict(schema='OCTOBER_INCREMENTAL_INDEPENDENT_READBACK_V1',
                seed_audit_reference=dict(path=str(SEED), sha256=SEED_SHA),
                index=dict(path=str(Path(index_path).resolve()), sha256=index_sha256),
                reused_independently_audited_count=201, newly_numerically_audited_count=len(details)-201,
                planned=425, completed=len(details), status=index['status'], details=details,
                fitted_count=sum(detail['typed_decimal'] is not None for detail in details),
                numerical_failure_count=sum(detail['typed_decimal'] is None for detail in details),
                historical_expected_source_hashes=sources,
                archive_resolution=original.archive.verify_expected_sources(sources, contract),
                fitter_called=False, owner_check_fitted_called=False, old_numerical_audits_repeated=False,
                historical_full_source_closure_verified=False,
                projection_metadata_independently_recomputed=False, optimizer_optimality_proved=False,
                point_in_time_verified=False, promotion_allowed=False, performance_or_dual_benchmark_pass_claimed=False)


def publish_verified(path, value):
    if original.pure.digest(value) != original.pure.digest(build(value['index']['path'], value['index']['sha256'])):
        raise ValueError('Complete incremental readback differs')
    reference = original.publish(path, value)
    if original.archive.verify_expected_sources(value['historical_expected_source_hashes'], original.archive.load_contract()) != value['archive_resolution']:
        raise ValueError('Sources changed after publication')
    return reference


def build_and_publish(path, index_path, index_sha256):
    """No caller payload accepted; compute new numerical checks exactly once."""
    value = build(index_path, index_sha256)
    sources = value['historical_expected_source_hashes']
    contract = original.archive.load_contract()
    if original.archive.verify_expected_sources(sources, contract) != value['archive_resolution']:
        raise ValueError('Sources changed before publication')
    reference = original.publish(path, value)
    if (original.archive.drift.file_sha(Path(reference['path'])) != reference['sha256']
            or original.archive.verify_expected_sources(sources, contract) != value['archive_resolution']):
        raise ValueError('Published bytes or sources changed')
    return reference


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('index-path', 'index-sha256', 'output'):
        parser.add_argument('--' + name, required=True)
    arguments = parser.parse_args()
    print(json.dumps(build_and_publish(arguments.output, arguments.index_path, arguments.index_sha256)))
