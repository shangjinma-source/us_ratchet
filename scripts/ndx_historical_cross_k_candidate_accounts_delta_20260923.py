"""V2 delta producer: sealed account-prefix reuse; only new tasks may run."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_historical_cross_k_candidate_accounts_20260923 as legacy
from scripts import ndx_historical_cross_k_accounts_incremental_audit_20260923 as seed_reader

SOURCE = Path(__file__).resolve()
OUTPUT = ROOT / 'data/cache/research/historical_cross_k_candidate_accounts_delta_20260923_v2'
# Root accepted this exact 121 audit; caller-supplied hashes are not authority.
SEED_AUTHORITY = dict(path=str(seed_reader.BASE / 'completed_121_incremental_independent_audit.json'),
                      sha256='e209229ccca4cd8e55f02ba02fee4fa69d13a9c98c4e9964cc0c5ec31cd96296')
FIT_AUTHORITY = deepcopy(seed_reader.FIT)
LOADED = dict(legacy.LOADED)
legacy.archive.merge(LOADED, {str(SOURCE): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                            str(Path(seed_reader.__file__).resolve()): hashlib.sha256(Path(seed_reader.__file__).resolve().read_bytes()).hexdigest()})
PRODUCER = dict(path=str(SOURCE), sha256=LOADED[str(SOURCE)])


def budget(value):
    if type(value) is not int or not 0 <= value <= 10:
        raise ValueError('Delta budget must be integer 0..10')


def guard(auth, fingerprint):
    if legacy.digest(auth) != fingerprint or legacy.prefix.runtime() != auth['runtime']:
        raise ValueError('Prepared delta inputs or runtime changed')
    for path, checksum in auth['sources'].items():
        if Path(path).suffix == '.py' and legacy.sha(path) != checksum:
            raise ValueError('Loaded delta source changed')


def authority():
    if SEED_AUTHORITY is None:
        raise ValueError('BLOCKED_AWAITING_ROOT_REVIEWED_121_ACCOUNT_AUDIT_SHA')
    sources = dict(LOADED)
    seed = legacy.read(SEED_AUTHORITY, sources)
    index = legacy.read(seed['index_reference'], sources)
    fit = legacy.read(FIT_AUTHORITY, sources)
    fit_index = legacy.read(fit['index_reference'], sources)
    if (seed['schema'] != 'HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INCREMENTAL_INDEPENDENT_AUDIT_V1'
            or seed['completed_account_task_count'] != 121 or len(seed['details']) != 121
            or seed['reused_independent_account_count'] != 111
            or seed['newly_independently_audited_account_count'] != 10
            or seed['raw_marker_result_chain_verified'] is not True
            or index['finalized_after_full_source_verification'] is not True
            or index['completed_account_task_count'] != 121 or len(index['entries']) != 121
            or fit['completed_new_count'] != 5001 or len(fit['details']) != 5001
            or fit['complete_marker_raw_checkpoint_chain_verified'] is not True
            or len(fit_index['entries']) != 5001):
        raise ValueError('Exact reviewed 121-account/5001-fit prefix required')
    if any(document['plan_reference'] != legacy.PLAN for document in (seed, index, fit, fit_index)):
        raise ValueError('Original historical plan differs')
    if seed['fit_prefix_audit_reference'] != FIT_AUTHORITY or index['fit_prefix_audit_reference'] != FIT_AUTHORITY:
        raise ValueError('Seed uses another historical fit authority')
    identifiers = [row['task_id'] for row in fit['details']]
    if (len(set(identifiers)) != 5001 or identifiers != [entry['task_id'] for entry in fit_index['entries']]
            or identifiers[:121] != [entry['task_id'] for entry in index['entries']]
            or identifiers[:121] != [row['task_id'] for row in seed['details']]):
        raise ValueError('Complete monotone reviewed task prefix required')
    for entry, detail in zip(index['entries'], seed['details'], strict=True):
        if any(entry[key] != detail[key] for key in ('result_reference', 'raw_reference')):
            raise ValueError('Old prefix result/raw identity differs')
    for document in (seed, fit):
        legacy.archive.merge(sources, document['historical_expected_source_hashes'])
    contract = legacy.archive.load_contract()
    legacy.archive.verify_expected_sources(sources, contract)
    for document in (seed, index, fit, fit_index):
        if legacy.digest(document['archive_resolution']) != legacy.digest(legacy.prefix.partition_subset(document['historical_expected_source_hashes'], contract)):
            raise ValueError('Reviewed source partition differs')
    inputs = legacy.read(legacy.INPUT, sources)
    plan = legacy.read(legacy.PLAN, sources)
    tasks = {row['task_id']: row for row in plan['tasks']}
    queue = []
    for entry, detail in zip(fit_index['entries'], fit['details'], strict=True):
        row = tasks[entry['task_id']]
        if row['status'] != 'PENDING_HISTORICAL_FIT' or entry['task_id'] == legacy.prefix.plan_reader.target_reader.JOB:
            raise ValueError('External or unsupported task cannot be newly executed')
        queue.append(dict(task_id=entry['task_id'], task=dict(row['task'], task_id=entry['task_id']),
                          fit_checkpoint_reference=entry['result_reference'], audited_detail=detail))
    runtime = legacy.prefix.runtime()
    marker = legacy.read(index['entries'][0]['started_reference'], sources)
    if marker['runtime'] != runtime:
        raise ValueError('Reviewed account runtime differs')
    value = dict(audit_reference=deepcopy(FIT_AUTHORITY), seed_audit_reference=deepcopy(SEED_AUTHORITY),
                 seed_index_reference=deepcopy(seed['index_reference']), seed_completed_count=121,
                 queue=queue, inputs=inputs, numerical=plan['numerical_source_hashes'],
                 sources=sources, runtime=runtime, producer_reference=deepcopy(PRODUCER))
    guard(value, legacy.digest(value))
    return value


def envelope(kind, payload, auth, ordinal):
    return dict(schema='HISTORICAL_CROSS_K_DELTA_' + kind + '_V2',
                producer_reference=deepcopy(auth['producer_reference']),
                seed_account_audit_reference=deepcopy(auth['seed_audit_reference']),
                global_task_ordinal_zero_based=ordinal,
                reused_payload_schema_is_not_producer_identity=True,
                payload_sha256=legacy.digest(payload), payload=payload)


def execute_delta(auth, folder, max_new):
    """Internal kernel; production caller must obtain auth via authority().

    No automatic resume of a failed/unreviewed delta. Its artifacts must first
    receive an external independent audit before becoming any later seed.
    """
    budget(max_new)
    folder = Path(folder).resolve()
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Existing delta evidence or orphan prohibits replay')
    fingerprint = legacy.digest(auth)
    guard(auth, fingerprint)
    if max_new == 0:
        return dict(status='PRECHECK_ONLY', engine_calls=0, new_accounts=0,
                    new_execution_count=0, new_skipped_risk_count=0,
                    seed_accounts_referenced=auth['seed_completed_count'], real_execution_performed=False)
    legacy.full(auth['sources'])
    first = auth['seed_completed_count']
    rows = auth['queue'][first:first + max_new]
    if len(rows) != max_new:
        raise ValueError('Requested delta exceeds reviewed fit queue')
    sources = dict(auth['sources'])
    entries = []
    execution_count = 0
    skipped_risk_count = 0
    for offset, row in enumerate(rows):
        ordinal = first + offset
        prepared = legacy.bind_task(auth, row)  # Exclusively a NEW task.
        prepared_hash = legacy.digest(prepared)
        directory = folder / row['task_id']
        guard(auth, fingerprint)
        if directory.exists():
            raise ValueError('Existing task attempt prohibits replay')
        marker = envelope('ATTEMPT', legacy.marker_value(auth, row), auth, ordinal)
        started = legacy.publish(directory / 'started.json', marker)
        local = dict(auth['sources'])
        legacy.archive.merge(local, {started['path']: started['sha256']})
        raw_reference = None
        raw = None
        try:
            guard(auth, fingerprint)
            if legacy.digest(prepared) != prepared_hash or legacy.sha(started['path']) != started['sha256']:
                raise ValueError('Prepared arguments or durable marker changed')
            if prepared['status'] == 'READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT':
                arguments = deepcopy(prepared['account']['selected']['arguments'])
                arguments_hash = legacy.digest(arguments)
                raw = legacy.single.candidate.simulate_dynamic_frozen_execution_research(**arguments)
                execution_count += 1
                payload = legacy.raw_value(auth, row, prepared, started, raw)
                raw_reference = legacy.publish(directory / 'raw.json', envelope('RAW_ACCOUNT', payload, auth, ordinal))
                legacy.archive.merge(local, {raw_reference['path']: raw_reference['sha256']})
                if legacy.digest(arguments) != arguments_hash:
                    raise ValueError('Engine mutated supplied arguments')
            else:
                skipped_risk_count += 1
            guard(auth, fingerprint)
            if legacy.digest(prepared) != prepared_hash:
                raise ValueError('Prepared delta binding changed')
            # Frozen restore/Decimal accounting applies only to this new result.
            payload = legacy.result_value(auth, row, prepared, started, raw_reference, raw, local)
            result = legacy.publish(directory / 'result.json', envelope('ACCOUNT_RESULT', payload, auth, ordinal))
            guard(auth, fingerprint)
            for reference in (started, raw_reference, result):
                if reference and legacy.sha(reference['path']) != reference['sha256']:
                    raise ValueError('Published delta artifact changed')
            entries.append(dict(task_id=row['task_id'], global_task_ordinal_zero_based=ordinal,
                                started_reference=started, raw_reference=raw_reference, result_reference=result))
            legacy.archive.merge(sources, local)
            legacy.archive.merge(sources, {result['path']: result['sha256']})
        except BaseException as error:
            legacy.publish(directory / 'failure.json', dict(schema='HISTORICAL_CROSS_K_DELTA_FAILURE_V2',
                producer_reference=auth['producer_reference'], task_id=row['task_id'],
                started_reference=started, raw_reference=raw_reference, error_type=type(error).__name__,
                automatic_retry_allowed=False, failure_is_economic_infeasibility=False))
            raise
    guard(auth, fingerprint)
    partition = legacy.full(sources)
    value = dict(schema='HISTORICAL_CROSS_K_FINALIZED_DELTA_INDEX_V2', producer_reference=auth['producer_reference'],
        seed_account_audit_reference=auth['seed_audit_reference'], seed_index_reference=auth['seed_index_reference'],
        fit_prefix_audit_reference=auth['audit_reference'], plan_reference=legacy.PLAN, folder=str(folder),
        seed_account_count=first, newly_completed_account_count=len(entries), combined_account_count=first+len(entries),
        new_execution_count=execution_count, new_skipped_risk_count=skipped_risk_count,
        real_execution_performed=execution_count>0,
        audited_fit_task_count=len(auth['queue']), pending_account_count=len(auth['queue'])-first-len(entries),
        entries=entries, old_accounts_copied=False, old_account_numerical_audit_repeated=False,
        old_fit_numerical_audit_repeated=False, independent_delta_audit_completed=False,
        finalized_after_full_source_verification=True, historical_expected_source_hashes=sources,
        archive_resolution=partition, fit_performed=False, control_executed=False, promotion_allowed=False,
        point_in_time_verified=False, formal_dual_benchmark_admission=False)
    reference = legacy.publish(folder / ('index_' + legacy.digest(value) + '.json'), value)
    if legacy.digest(legacy.read(reference, {})) != legacy.digest(value):
        raise ValueError('Published delta index readback differs')
    if legacy.digest(legacy.full(sources)) != legacy.digest(partition):
        raise ValueError('Source partition changed after publication')
    return dict(index_reference=reference, seed_accounts_referenced=first, new_accounts=len(entries),
                combined_accounts=first+len(entries), independent_delta_audit_completed=False,
                engine_calls=execution_count, new_execution_count=execution_count,
                new_skipped_risk_count=skipped_risk_count,
                real_execution_performed=execution_count>0, promotion_allowed=False)


def run(*, max_new=0, execute=False):
    budget(max_new)
    if type(execute) is not bool:
        raise ValueError('Execute must be an exact boolean')
    if SEED_AUTHORITY is None:
        if execute:
            raise ValueError('BLOCKED_AWAITING_ROOT_REVIEWED_121_ACCOUNT_AUDIT_SHA')
        return dict(status='BLOCKED_AWAITING_ROOT_REVIEWED_121_ACCOUNT_AUDIT_SHA',
                    engine_calls=0, real_execution_performed=False, promotion_allowed=False)
    if not execute and max_new != 0:
        raise ValueError('Nonzero budget requires explicit execute')
    return execute_delta(authority(), OUTPUT, max_new if execute else 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-new', type=int, default=0)
    parser.add_argument('--execute', action='store_true')
    arguments = parser.parse_args()
    print(json.dumps(run(**vars(arguments))))
