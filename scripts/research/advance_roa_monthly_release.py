"""Explicit, resumable monthly adoption and loaded-runtime verification.

Default preview does not mutate account, service, active pointer or task.
Use the existing formal adopter and Windows adapter; never bypass their gates.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import uuid4

from scripts.research.adopt_roa_monthly_registration import adopt
from scripts.research.finish_roa_monthly_adoption import finish
from scripts.research.finish_roa_monthly_windows import WindowsAdapter
from core.strategy_account_store import StrategyAccountStore
from scripts.research.finish_roa_next_month import finish_next


def advance(*, root, request, output_directory, execute=False, adapter_factory=WindowsAdapter):
    root = Path(root).resolve()
    def bounded(name):
        path = (root / name).resolve()
        if Path(name).is_absolute() or path == root or not path.is_relative_to(root):
            raise ValueError('PATH_OUTSIDE_ROOT')
        return path
    def read(reference):
        raw = bounded(reference['path']).read_bytes()
        if sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('INPUT_CHANGED:' + reference['path'])
        return json.loads(raw)
    required = {'active', 'registration', 'publication', 'month', 'epoch', 'expected_process'}
    if set(request) not in (required, required | {'successor'}):
        raise ValueError('REQUEST_FIELDS')
    publication = read(request['publication'])
    registration = read(request['registration'])
    if (publication.get('status') != 'VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED'
            or publication.get('registration') != request['registration']
            or publication.get('expected_active') != request['active']
            or registration.get('expected_active') != request['active']
            or registration.get('month') != request['month']
            or publication.get('month') != request['month']):
        raise ValueError('PREPARED_PUBLICATION_BINDING_REQUIRED')
    receipt = read(registration['receipt'])
    if receipt.get('month') != request['month'] or receipt.get('status') != 'PREPARED_VERIFIED_NOT_REGISTERED':
        raise ValueError('MONTH_RECEIPT_REQUIRED')
    out = bounded(output_directory)
    if not out.is_relative_to(root / 'tmp'):
        raise ValueError('PRIVATE_TMP_OUTPUT_REQUIRED')
    active_path = bounded(request['active']['path'])
    request_bytes = json.dumps(request, sort_keys=True).encode()
    saved_request = out / 'request.json'
    if out.exists() and (not saved_request.is_file() or saved_request.read_bytes() != request_bytes):
        raise ValueError('EXISTING_ATTEMPT_SCOPE_CONFLICT')
    adoption_path = out / 'adoption/adoption.json'
    if adoption_path.exists():
        previous = json.loads(adoption_path.read_bytes())
        if (previous.get('status') != 'ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED'
                or previous.get('expected_active') != request['active']
                or previous.get('registration') != request['registration']
                or sha256(active_path.read_bytes()).hexdigest() != previous.get('active_sha256')):
            raise ValueError('ADOPTION_RECONCILIATION_REQUIRED')
    elif sha256(active_path.read_bytes()).hexdigest() != request['active']['sha256']:
        raise ValueError('ACTIVE_CHANGED_RECONCILE_NO_REPEAT_ADOPTION')
    if not execute:
        return dict(status='PREVIEW_NO_ADOPTION_OR_RESTART', month=request['month'],
                    adopted=adoption_path.exists(), task_changed=False, account_writes=False)
    if not out.exists():
        out.mkdir(parents=True, exist_ok=False)
        saved_request.write_bytes(request_bytes)
    token = uuid4().hex
    lock = out / 'advance.lock'
    with lock.open('x') as stream:
        stream.write(token)
    def save(name, value):
        staged = out / (name + '.' + token + '.staged')
        with staged.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(staged, out / name)
    try:
        if not adoption_path.exists():
            if (out / 'adoption-intent.json').exists():
                raise ValueError('ADOPTION_INTENT_UNRESOLVED_NO_REPEAT')
            save('adoption-intent.json', dict(registration=request['registration'], active=request['active']))
            adopt(root=root, active=request['active'], registration=request['registration'],
                  output_directory=output_directory + '/adoption', execute=True)
        adapter = adapter_factory(root, request['expected_process'], request['month'],
                                  receipt['runtime_sha256'], state_path=out / 'runtime/process-state.json')
        observed = adapter.inspect()
        if (out / 'runtime/restart-intent.json').exists() and not observed.get('healthy'):
            result = dict(status='WAIT_RUNTIME_RECONCILIATION_NO_REPEAT_RESTART', runtime=observed)
            save('progress.json', result)
            return result
        if 'active_sha256' not in observed:
            raise ValueError('LOADED_RUNTIME_EVIDENCE_REQUIRED_BEFORE_RESTART')
        result = finish(root=root, adoption_directory=output_directory + '/adoption',
                        evidence_directory=output_directory + '/runtime', expected_month=request['month'],
                        expected_epoch=request['epoch'], read_account=lambda: adapter.get_json('/api/strategy-account'),
                        read_ledger=lambda: StrategyAccountStore(root / 'data/strategy_account/real_strategy.sqlite3').read(),
                        inspect_runtime=adapter.inspect, restart=adapter.restart)
        result = dict(status='MONTH_ADOPTED_RUNTIME_VERIFIED_NEXT_TASK_PENDING', runtime_result=result,
                      task_changed=False, account_writes=False, page_verified=False)
        save('progress.json', result)
        if 'successor' in request:
            def reference(path):
                return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
            successor = request['successor']
            inputs = dict(successor['inputs'], active=reference(active_path),
                          runtime_success=reference(out / 'runtime/success.json'),
                          adoption=reference(adoption_path),
                          publication=reference(out / 'adoption/validated.json'))
            next_result = finish_next(root=root, request=inputs,
                                      output_directory=output_directory + '/successor',
                                      python_path=successor['python_path'],
                                      expected_task_sha256=successor['expected_task_sha256'])
            result = dict(result, status='MONTH_RUNTIME_AND_NEXT_TASK_VERIFIED',
                          next_month=next_result, task_changed=True)
            save('progress.json', result)
        return result
    finally:
        if lock.exists() and lock.read_text() == token:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('request', 'request-sha256', 'output-directory'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    raw = Path(args.request).read_bytes()
    if sha256(raw).hexdigest() != args.request_sha256:
        raise ValueError('REQUEST_CHANGED')
    print(json.dumps(advance(root=Path(__file__).resolve().parents[2], request=json.loads(raw),
                             output_directory=args.output_directory, execute=args.execute)))

if __name__ == '__main__':
    main()
