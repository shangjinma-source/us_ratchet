"""Adopt a fully reviewed profiled monthly package, never select a target."""
from hashlib import sha256
from pathlib import Path
import os
from core.strategy_account_ledger import canonical, require
from scripts.prepare_real_monthly_release import _safe, _read
from scripts.prepare_profiled_monthly_publication_v1 import prepare


def update(*, root, entry, output_directory, activation, snapshot_provider,
           validate_code, clock, execute=False, market_capture=None, action_capture=None):
    root = Path(root).absolute(); output = _safe(root, output_directory)
    validate_code(); snapshot = snapshot_provider()
    if not execute:
        return dict(status='PROFILED_UPDATE_PREFLIGHT', target_month=entry['target_month'],
                    release_revision=snapshot['revision'], account_writes=False, target_created=False)
    require(output.parent.is_dir(), 'PROFILE_UPDATE_PARENT_REQUIRED')
    binding = dict(entry=entry, output_directory=output_directory)
    def put(name, value):
        with (output/name).open('xb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    def read_existing(name):
        raw = (output/name).read_bytes()
        return _read(root, (Path(output_directory)/name).as_posix(), sha256(raw).hexdigest())
    if output.exists():
        require((output/'started.json').is_file() and not (output/'failed.json').exists(),
                'PROFILE_UPDATE_RECOVERY_REQUIRED')
        started = read_existing('started.json')
        require(started['binding'] == binding, 'PROFILE_UPDATE_BINDING_CHANGED')
        ready_path = output/'publication/ready.json'
        require(ready_path.is_file(), 'PROFILE_UPDATE_RECOVERY_REQUIRED')
        original = started['snapshot']
    else:
        output.mkdir(exist_ok=False); original = snapshot
        put('started.json', dict(binding=binding, snapshot=original, at=clock().isoformat()))
        try:
            prepare(root=root, snapshot=original, new_entry=entry,
                output_directory=(Path(output_directory)/'publication').as_posix(),
                validate_code=validate_code, clock=clock,
                market_capture=market_capture, action_capture=action_capture)
        except Exception:
            put('failed.json', dict(status='PROFILE_UPDATE_RECOVERY_REQUIRED', automatic_retry=False)); raise
        ready_path = output/'publication/ready.json'
    validate_code()
    reference = dict(receipt_path=ready_path.relative_to(root).as_posix(),
                     receipt_sha256=sha256(ready_path.read_bytes()).hexdigest())
    # Exact receipt retries are reconciled by the store before stale revision checks.
    result = activation.adopt(**reference, expected_release_revision=original['revision'])
    validate_code()
    successor = snapshot_provider()
    require(successor['revision'] == result['revision'] and
            all(successor[k] == result['payload'][k] for k in
                ('registry_path','registry_sha256','archive_path','archive_sha256')),
            'PROFILE_UPDATE_HANDOFF_MISMATCH')
    terminal = dict(status='PROFILED_MONTHLY_DATA_ADOPTED', release_revision=result['revision'],
                    target_month=entry['target_month'], ready=reference,
                    account_writes=False, target_created=False, orders_created=False)
    if (output/'complete.json').exists():
        require(read_existing('complete.json') == terminal, 'PROFILE_UPDATE_TERMINAL_CHANGED')
    else: put('complete.json', terminal)
    return terminal
