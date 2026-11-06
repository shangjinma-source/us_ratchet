"""Prepare a new bounded attempt, preserving the failed attempt. No task execution."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from scripts.run_local_roa_monthly_preparation import make_descriptor, run


def prepare_retry(*, root, descriptor, failure, output_directory, reason, prepare=False):
    root = Path(root).resolve()
    checked = {}

    def path(name):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in str(name):
            raise ValueError('PATH_OUTSIDE_ROOT')
        value = (root / relative).resolve()
        if value == root or not value.is_relative_to(root):
            raise ValueError('PATH_OUTSIDE_ROOT')
        return value

    def read(reference):
        raw = path(reference['path']).read_bytes()
        if sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('SOURCE_CHANGED:' + reference['path'])
        checked[reference['path']] = reference['sha256']
        return json.loads(raw)

    def recheck():
        for name, digest in checked.items():
            if sha256(path(name).read_bytes()).hexdigest() != digest:
                raise ValueError('SOURCE_CHANGED_DURING_PREPARATION:' + name)
        for lock in locks:
            if lock.exists():
                raise ValueError('LOCK_RECONCILIATION_REQUIRED')

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('REVIEW_REASON_REQUIRED')
    old = read(descriptor)
    run(root=root, descriptor_path=descriptor['path'],
        descriptor_sha256=descriptor['sha256'], execute=False)
    logs = path(old['log_directory'])
    if path(failure['path']) != logs / 'blocked.json':
        raise ValueError('FAILURE_NOT_FROM_DESCRIPTOR')
    failed = read(failure)
    if failed.get('descriptor_sha256') != descriptor['sha256']:
        raise ValueError('FAILED_DESCRIPTOR_MISMATCH')
    if (logs / 'prepared.json').exists():
        raise ValueError('COMPLETED_ATTEMPT_REQUIRES_ADOPTION_REVIEW')
    locks = (logs / 'running.lock', root / 'tmp/roa_monthly_pipeline_execution.lock')
    request = read(old['request'])
    read(request['active'])
    plan = read(request['capture']['plan'])
    output = path(output_directory)
    allowed = (root / 'tmp', root / 'data/strategy_archives')
    if not any(output != prefix and output.is_relative_to(prefix) for prefix in allowed):
        raise ValueError('NEW_ATTEMPT_OUTPUT_SCOPE')
    if output.exists():
        raise ValueError('NEW_ATTEMPT_MUST_NOT_EXIST')
    old_outputs = [logs, path(plan['output_directory']), path(request['capture']['output_directory']),
                   path(request['coordination_directory']), path(request['publication_directory'])]
    if any(output.is_relative_to(previous) for previous in old_outputs):
        raise ValueError('NEW_ATTEMPT_OVERLAPS_OLD_OUTPUT')
    recheck()
    result = dict(status='NEW_ATTEMPT_PREVIEW', previous_descriptor=descriptor,
                  failure=failure, reviewed_reason=reason.strip(),
                  expected_month=request['package']['expected_month'],
                  output_directory=output_directory, tasks_changed=False,
                  account_writes=False, capture_started=False, old_evidence_preserved=True)
    if not prepare:
        return result
    output.mkdir(parents=True, exist_ok=False)

    def save(name, value):
        target = output / name
        raw = (json.dumps(value, indent=2) + '\n').encode()
        with target.open('xb') as stream:
            stream.write(raw)
        return dict(path=target.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest())

    def child(name):
        return (output / name).relative_to(root).as_posix()

    try:
        next_plan = deepcopy(plan)
        next_plan['output_directory'] = child('capture')
        plan_ref = save('capture_plan.json', next_plan)
        next_request = deepcopy(request)
        next_request['capture'].update(plan=plan_ref, output_directory=child('training'))
        next_request['coordination_directory'] = child('coordination')
        next_request['publication_directory'] = child('publication')
        request_ref = save('request.json', next_request)
        launcher = make_descriptor(root=root, python_path=old['python_path'],
                                   request=request_ref, log_directory=child('logs'))
        launcher_ref = save('launcher.json', launcher)
        run(root=root, descriptor_path=launcher_ref['path'],
            descriptor_sha256=launcher_ref['sha256'], execute=False)
        recheck()
        result.update(status='NEW_ATTEMPT_PREPARED_NOT_SCHEDULED', descriptor=launcher_ref)
        save('retry_receipt.json', result)
        return result
    except Exception as error:
        save('preparation_failure.json', dict(status='FAILED_RETAINED_NEW_OUTPUT', reason=str(error)))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('descriptor-path', 'descriptor-sha256', 'failure-path',
                 'failure-sha256', 'output-directory', 'reason'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    result = prepare_retry(root=Path(__file__).resolve().parents[1],
                           descriptor=dict(path=args.descriptor_path, sha256=args.descriptor_sha256),
                           failure=dict(path=args.failure_path, sha256=args.failure_sha256),
                           output_directory=args.output_directory, reason=args.reason, prepare=args.prepare)
    print(json.dumps(result, ensure_ascii=False, indent=2))
