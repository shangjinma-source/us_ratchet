"""One bounded sequential batch. Never restart a task with existing evidence."""
import argparse
import hashlib
import types
import json
import os
from pathlib import Path
import sys
import time

SOURCE = Path(__file__).resolve()
ROOT = SOURCE.parents[1]
sys.path.insert(0, str(ROOT))
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/dated_batch_20261003_v1'
ATTEMPTS = ROOT / 'data/cache/research/dated_single_task_20261003_v1'
PINS = {
    'runner': ('scripts/ndx_dated_single_task_20261003.py', '2561779479a7a2373204540d85f86095d6096a53ff899058929035d9a1703fcf'),
    'reader': ('scripts/ndx_dated_single_task_independent_readback_20261003.py', 'bd63ce1541c63d3f38e90a7313666d37abcbb9b51cc9d2291f702ee8fad43cea'),
    'initial': ('research_contracts/dated_initial_completed_tasks_20261003_v1.json', '72ba335644c6fec313d31692d317d1df63a425d91eee0a50d3586f6ab865ab9c'),
}
PREPARATION_REFERENCE = dict(path=str(ROOT/'data/cache/research/dated_fixed_task_preparation_20261003_v1/preparation.json'),
    sha256='ff24a6b732bc55ea6dbb7b453a41ff58d0f2ee316e3f2120aa4006f3b82d3d0e')
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
    require(value['schema'] == 'DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1', 'New dated independent schema required')
    require(value['numerical_task_id'] == task_id and value['status'] == 'PASSED', 'Independent evidence validation did not pass')
    outcome = value['attempt_outcome']
    require(outcome in ('RISK_PASSED', 'RISK_FAILED', 'NUMERICAL_EXCEPTION', 'VALIDATION_FAILURE'), 'Unknown terminal outcome')
    return outcome


def execute_queue(task_ids, *, run_task, read_task, verify_sources, output, initial_rows, batch_context=None):
    """Dispatch only an explicit unique remainder; fail closed without retry."""
    require(type(task_ids) is list and all(type(t) is str and len(t)==64 and all(c in '0123456789abcdef' for c in t) for t in task_ids) and len(task_ids) == len(set(task_ids)), 'Unique canonical task order')
    require(not output.exists(), 'Immutable batch namespace exists')
    verify_sources()
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'started.json', dict(schema='DATED_BATCH_STARTED_V1',
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
    value = dict(schema='DATED_BATCH_RESULT_V1', status='STOPPED_WITH_EVIDENCE' if failure else 'BUDGETED_QUEUE_FINISHED',
        initial_completed_rows=initial_rows, newly_readback_rows=rows, new_outcome_counts=counts,
        new_readback_count=len(rows), planned_remaining_dispatch_count=len(task_ids),
        undispatched_task_ids=task_ids[len(rows)+(1 if failure and failure.get('dispatch_invoked') else 0):],
        unresolved_dispatched_task_ids=[failure['numerical_task_id']] if failure and failure.get('dispatch_invoked') else [],
        failure=failure, batch_context=batch_context, elapsed_seconds=round(time.monotonic()-started_time, 3), **FALSE)
    if failure:
        save(output / 'failure.json', failure)
    return save(output / 'result.json', value)


def load_module(role):
    """Compile the exact checked current bytes; never trust a cached module."""
    relative, expected = PINS[role]
    path = (ROOT/relative).resolve()
    raw = path.read_bytes()
    require(type(expected) is str and sha(raw) == expected, 'Module pin pending or changed')
    module = types.ModuleType('_dated_batch_' + role)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(Path(module.__file__).resolve() == path, 'Loaded module path differs')
    require(sha(path.read_bytes()) == expected, 'Module source changed during load')
    return module


def validate_initial(initial, order):
    require(type(order) is list and len(order) == len(set(order)) == 1632, 'Complete unique saved queue')
    require(initial['schema'] == 'DATED_INITIAL_COMPLETED_TASKS_V1' and
            initial['preparation_reference'] == PREPARATION_REFERENCE, 'New cutoff initial contract')
    rows = initial['rows']
    require(type(rows) is list and 0 < len(rows) <= len(order), 'Explicit nonempty completed prefix')
    ids = [row['numerical_task_id'] for row in rows]
    require(ids == order[:len(ids)], 'Only explicit saved-order prefix may be skipped')
    for row in rows:
        require(set(row) == {'numerical_task_id','postcheck_reference','independent_readback_reference'}, 'Exact initial row')
        task_id = row['numerical_task_id']
        require(inspect_readback(row['independent_readback_reference'], task_id) in
                ('RISK_PASSED', 'RISK_FAILED'), 'Initial task not a validated risk terminal state')
        post = reference_load(row['postcheck_reference'])
        report = reference_load(row['independent_readback_reference'])
        require(post['schema'] == 'DATED_SINGLE_TASK_POSTCHECK_V1' and post['numerical_task_id'] == task_id, 'Dated initial postcheck')
        require(report['postcheck_reference'] == row['postcheck_reference'], 'Initial cross-reference')
        expected = 'ORIGINAL_RISKS_' + ('PASSED' if report['attempt_outcome']=='RISK_PASSED' else 'FAILED') + '_PENDING_INDEPENDENT_READBACK'
        require(post['status'] == expected, 'Initial postcheck/readback outcome differs')
    return ids


def run(*, execute=False):
    require(type(execute) is bool and execute, 'Explicit execute=True required; pending pins forbid startup')
    require(not OUTPUT.exists(), 'Immutable batch namespace exists; no resume or retry')
    guard()
    initial_reference = dict(path=str(ROOT / PINS['initial'][0]), sha256=PINS['initial'][1])
    initial = reference_load(initial_reference)
    runner = load_module('runner')
    reader = load_module('reader')
    common = runner.load_common()
    reader_common = reader.load_common()
    order = common['ordered_task_ids']
    initial_ids = validate_initial(initial, order)
    require(ATTEMPTS.is_dir() and {path.name for path in ATTEMPTS.iterdir()} == set(initial_ids),
            'Unexpected existing attempt; no automatic skipping or restarting')
    guard()
    context = dict(source_hashes={str(SOURCE): LOADED_SHA, **{str(ROOT / path): expected for path, expected in PINS.values()}},
        initial_completed_reference=initial_reference, preparation_reference=PREPARATION_REFERENCE,
        planned_total_task_count=1632, prior_completed_task_count=len(initial_ids),
        ordered_task_ids_sha256=sha(json.dumps(order, separators=(',', ':')).encode()),
        old_cutoff_completion_reused=False)
    return execute_queue(order[len(initial_ids):], run_task=lambda task_id: runner.run(task_id, execute=True, common=common),
        read_task=lambda task_id, reference: reader.readback(task_id, postcheck_reference=reference, common=reader_common),
        verify_sources=guard, output=OUTPUT, initial_rows=initial['rows'], batch_context=context)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)), flush=True)
