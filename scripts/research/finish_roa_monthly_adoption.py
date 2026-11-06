"""Resume a formally adopted monthly release; no concrete service adapter or CLI.

Call adopt_roa_monthly_registration.adopt first. This coordinator does not replace
its validation/CAS. Adapters must observe the loaded runtime (not disk config),
read the complete account/ledger, and restart only the observed process identity.
"""
import json
import os
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


def finish(*, root, adoption_directory, evidence_directory, expected_month,
           expected_epoch, read_account, read_ledger, inspect_runtime, restart):
    root = Path(root).resolve()
    def bounded(name):
        path = (root / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(root) or path == root:
            raise ValueError('PATH_OUTSIDE_ROOT')
        return path
    adoption_path = bounded(adoption_directory) / 'adoption.json'
    adoption_bytes = adoption_path.read_bytes()
    adoption = json.loads(adoption_bytes)
    if adoption['status'] != 'ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED':
        raise ValueError('FORMAL_ADOPTION_REQUIRED')
    active_path = bounded(adoption['expected_active']['path'])
    release = adoption['active_sha256']
    publication = json.loads((adoption_path.parent / 'validated.json').read_bytes())
    if (publication.get('status') != 'VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED'
            or publication.get('month') != expected_month
            or publication.get('next_active', {}).get('sha256') != release):
        raise ValueError('ADOPTED_MONTH_PUBLICATION_CONFLICT')
    scope = dict(adoption_sha256=sha256(adoption_bytes).hexdigest(),
                 active_sha256=release, month=expected_month, epoch=expected_epoch)
    out = bounded(evidence_directory)
    out.mkdir(parents=True, exist_ok=True)
    lock = out / 'running.lock'
    token = uuid4().hex
    try:
        with lock.open('x') as stream:
            stream.write(token)
    except FileExistsError:
        raise ValueError('COORDINATOR_BUSY_OR_RECONCILE')
    def save(name, value):
        staged = out / (name + '.' + token + '.staged')
        with staged.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, out / name)
    def active_unchanged():
        if sha256(active_path.read_bytes()).hexdigest() != release:
            raise ValueError('ACTIVE_CHANGED_NO_RESTART_OR_ROLLBACK')
    def matched(runtime):
        return (runtime.get('healthy') is True and
                all(runtime.get(key) == value for key, value in
                    [('active_sha256', release), ('month', expected_month),
                     ('epoch', expected_epoch)]))
    try:
        active_unchanged()
        baseline_path = out / 'baseline.json'
        if baseline_path.exists():
            baseline = json.loads(baseline_path.read_bytes())
            if baseline['scope'] != scope:
                raise ValueError('EVIDENCE_RELEASE_SCOPE_CONFLICT')
        else:
            baseline = dict(scope=scope, account=read_account(), ledger=read_ledger())
            active_unchanged()
            save('baseline.json', baseline)
        def unchanged():
            active_unchanged()
            if read_account() != baseline['account'] or read_ledger() != baseline['ledger']:
                raise ValueError('ACCOUNT_OR_LEDGER_CHANGED_RECONCILE')
        unchanged()
        runtime = inspect_runtime()
        save('runtime-observed.json', runtime)
        if not matched(runtime):
            # A restart may have happened before a crash/timeout. Never repeat it
            # merely because an acknowledgment or success receipt is absent.
            if (out / 'restart-intent.json').exists() or (out / 'success.json').exists():
                raise ValueError('RUNTIME_NOT_VERIFIED_RECONCILE_NO_REPEAT_RESTART')
            if not runtime.get('process_identity'):
                raise ValueError('PROCESS_IDENTITY_REQUIRED')
            unchanged()
            save('restart-intent.json', dict(scope=scope, process_identity=runtime['process_identity']))
            restart(expected_process_identity=runtime['process_identity'], expected_active_sha256=release)
            runtime = inspect_runtime()
            save('runtime-after.json', runtime)
            if not matched(runtime):
                raise ValueError('RESTARTED_RUNTIME_NOT_VERIFIED')
        unchanged()
        result = dict(status='MONTH_RUNTIME_VERIFIED', scope=scope,
                      runtime=runtime, account_and_ledger_unchanged=True,
                      automatic_rollback=False, page_verified=False,
                      cash_write_verified=False, fill_verified=False)
        save('success.json', result)
        return result
    except Exception as error:
        save('failure-' + uuid4().hex + '.json', dict(
            status='FAILED_RECONCILE_RUNTIME', error=str(error), scope=scope,
            active_sha256=sha256(active_path.read_bytes()).hexdigest() if active_path.exists() else None,
            restart_intent_recorded=(out / 'restart-intent.json').exists(),
            automatic_rollback=False))
        raise
    finally:
        if lock.exists() and lock.read_text() == token:
            lock.unlink()
