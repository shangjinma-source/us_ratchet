"""One bounded sequential batch. Never restart a task with existing evidence."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[1]
sys.path.insert(0, str(ROOT))
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/bulk_budgeted_batch_20261003_v1'
ATTEMPTS = ROOT / 'data/cache/research/bulk_budgeted_single_task_20261003_v1'
PINS = {
    'runner': ('scripts/ndx_bulk_budgeted_single_task_20261003.py', '8f3fdfc587a9ee7e168c22f6eddf33e66fdfb249f342fcb69cb9fbaba4485c46'),
    'reader': ('scripts/ndx_bulk_budgeted_single_task_independent_readback_20261003.py', '083be5c315c09275a8c2ae299e95593769779b28bcb22bbb7b305c254136e7ff'),
    'initial': ('research_contracts/bulk_budgeted_first_two_completed_20261003_v1.json', '6007612374872316d61cded15a9e654f16a72f1899743266221acfdb20b64b9b'),
}
FIRST_IDS = [
    '7f2dfbafd0fe2faa7b6289c336271eebbad83e2d584d7486fcc8ebe6fd297c73',
    'e47e3990e5fdb6badd038956aa3421d9b3cb956ef62f5374b671111b56c0a970',
]
FALSE = dict.fromkeys(('promotion_allowed', 'execution_authorized', 'point_in_time_verified',
    'legal_training_input_admitted', 'all_plan_tasks_completed', 'economic_comparison_performed',
    'retry_allowed'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def reference_load(reference):
    require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'Exact external reference')
    raw = Path(reference['path']).read_bytes()
    require(sha(raw) == reference['sha256'], 'External evidence drift')
    return strict_load(raw)


def guard():
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded batch source drift')
    for relative, expected in PINS.values():
        require(type(expected) is str and len(expected) == 64, 'Source pin pending')
        require(sha((ROOT / relative).read_bytes()) == expected, 'Pinned batch input drift')


def save(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Saved evidence drift')
    return dict(path=str(path), sha256=sha(raw))


def record(stream, value):
    raw = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    stream.write(raw)
    stream.flush()
    os.fsync(stream.fileno())


def inspect_readback(reference, task_id):
    value = reference_load(reference)
    require(value['numerical_task_id'] == task_id and value['status'] == 'PASSED', 'Independent evidence validation did not pass')
    outcome = value['attempt_outcome']
    require(outcome in ('RISK_PASSED', 'RISK_FAILED', 'NUMERICAL_EXCEPTION', 'VALIDATION_FAILURE'), 'Unknown terminal outcome')
    return outcome


def execute_queue(task_ids, *, run_task, read_task, verify_sources, output, initial_rows, batch_context=None):
    """Dispatch only an explicit unique remainder; fail closed without retry."""
    require(type(task_ids) is list and len(task_ids) == len(set(task_ids)), 'Unique task order')
    require(not output.exists(), 'Immutable batch namespace exists')
    verify_sources()
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'started.json', dict(schema='BULK_BUDGETED_BATCH_STARTED_V1',
        planned_remaining_dispatch_count=len(task_ids), ordered_remaining_task_ids=task_ids,
        initial_completed_rows=initial_rows, batch_context=batch_context, **FALSE))
    rows = []
    failure = None
    started_time = time.monotonic()
    with (output / 'progress.jsonl').open('xb') as stream:
        for ordinal, task_id in enumerate(task_ids):
            postcheck_reference = None
            readback_reference = None
            dispatch_invoked = False
            try:
                verify_sources()
                dispatch_invoked = True
                postcheck_reference = run_task(task_id)
                readback_reference = read_task(task_id, postcheck_reference)
                outcome = inspect_readback(readback_reference, task_id)
                verify_sources()
                row = dict(ordinal=ordinal, numerical_task_id=task_id, attempt_outcome=outcome,
                    postcheck_reference=postcheck_reference, independent_readback_reference=readback_reference)
                rows.append(row)
                record(stream, row)
                if ordinal % 25 == 0 or ordinal == len(task_ids)-1:
                    print(json.dumps(dict(readback_count=len(rows), remaining=len(task_ids)-len(rows),
                        outcome=outcome, elapsed_seconds=round(time.monotonic()-started_time, 3))), flush=True)
                if outcome in ('NUMERICAL_EXCEPTION', 'VALIDATION_FAILURE'):
                    failure = dict(numerical_task_id=task_id, reason=outcome, task_readback_saved=True)
                    break
            except Exception as error:
                failure = dict(numerical_task_id=task_id, reason='DISPATCH_OR_READBACK_FAILURE',
                    error_type=type(error).__name__, error=str(error), postcheck_reference=postcheck_reference,
                    independent_readback_reference=readback_reference, dispatch_invoked=dispatch_invoked,
                    saved_readback_not_accepted=readback_reference is not None, retry_allowed=False)
                record(stream, dict(ordinal=ordinal, **failure))
                break
    counts = {status: sum(row['attempt_outcome'] == status for row in rows) for status in
              ('RISK_PASSED', 'RISK_FAILED', 'NUMERICAL_EXCEPTION', 'VALIDATION_FAILURE')}
    value = dict(schema='BULK_BUDGETED_BATCH_RESULT_V1', status='STOPPED_WITH_EVIDENCE' if failure else 'BUDGETED_QUEUE_FINISHED',
        initial_completed_rows=initial_rows, newly_readback_rows=rows, new_outcome_counts=counts,
        new_readback_count=len(rows), planned_remaining_dispatch_count=len(task_ids),
        undispatched_task_ids=task_ids[len(rows)+(1 if failure and failure.get('dispatch_invoked') else 0):],
        unresolved_dispatched_task_ids=[failure['numerical_task_id']] if failure and failure.get('dispatch_invoked') else [],
        failure=failure, batch_context=batch_context, elapsed_seconds=round(time.monotonic()-started_time, 3), **FALSE)
    return save(output / 'result.json', value)


def run():
    require(not OUTPUT.exists(), 'Immutable batch namespace exists; poll the original live session instead')
    guard()
    initial_reference = dict(path=str(ROOT / PINS['initial'][0]), sha256=PINS['initial'][1])
    initial = reference_load(initial_reference)
    require(initial['schema'] == 'BULK_BUDGETED_FIRST_TWO_COMPLETED_V1' and
            [row['numerical_task_id'] for row in initial['rows']] == FIRST_IDS, 'Only fixed first two may be skipped')
    for row in initial['rows']:
        require(inspect_readback(row['independent_readback_reference'], row['numerical_task_id']) in
                ('RISK_PASSED', 'RISK_FAILED'), 'First-two validation did not complete')
        post = reference_load(row['postcheck_reference'])
        require(post['numerical_task_id'] == row['numerical_task_id'], 'First-two postcheck ID')
        report = reference_load(row['independent_readback_reference'])
        require(report['postcheck_reference'] == row['postcheck_reference'], 'First-two cross-reference')
    require(ATTEMPTS.is_dir() and {path.name for path in ATTEMPTS.iterdir()} == set(FIRST_IDS),
            'Unexpected existing attempt; no automatic skipping or restarting')
    runner = importlib.import_module('scripts.ndx_bulk_budgeted_single_task_20261003')
    reader = importlib.import_module('scripts.ndx_bulk_budgeted_single_task_independent_readback_20261003')
    common = runner.load_common()
    reader_common = reader.load_common()
    order = common['ordered_task_ids']
    require(len(order) == len(set(order)) == 1632 and order[:2] == FIRST_IDS, 'Complete immutable saved queue order')
    guard()
    context = dict(source_hashes={str(SOURCE): LOADED_SHA, **{str(ROOT / path): expected for path, expected in PINS.values()}},
        first_two_reference=initial_reference, planned_total_task_count=1632, prior_completed_task_count=2,
        ordered_task_ids_sha256=sha(json.dumps(order, separators=(',', ':')).encode()))
    return execute_queue(order[2:], run_task=lambda task_id: runner.run(task_id, execute=True, common=common),
        read_task=lambda task_id, reference: reader.readback(task_id, postcheck_reference=reference, common=reader_common),
        verify_sources=guard, output=OUTPUT, initial_rows=initial['rows'], batch_context=context)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    require(parser.parse_args().execute, 'Explicit --execute required')
    print(json.dumps(run()), flush=True)
