"""Approved local rolling launcher. Preview by default; retained logs on execution."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

from core.strategy_account_ledger import canonical, require
from scripts.coordinate_monthly_simulation import read, safe_reason
from scripts.run_real_monthly_market_preparation import bounded
from scripts.run_rolling_real_monthly_update import REQUIRED_SOURCE_PATHS as ROLLING_PATHS

REQUIRED_SOURCE_PATHS = ROLLING_PATHS | {'scripts/run_local_real_monthly_update.py'}
FIELDS = {'schema', 'root', 'python_path', 'rolling_config', 'rolling_sha256', 'log_directory', 'source_pins'}
WAITING = {'WAITING_SESSION_CLOSE', 'WAITING_REGULAR_REVIEW_WINDOW', 'NEXT_MONTH_READY'}
FAILED = {'BLOCKED', 'MISSED_PREPARATION_WINDOW', 'WAITING_REVIEW'}


def now():
    return datetime.now(timezone.utc).isoformat()


def run(*, config_path, config_sha256, execute=False):
    descriptor = json.loads(read(config_path, config_sha256))
    require(set(descriptor) == FIELDS and descriptor['schema'] == 'LOCAL_REAL_MONTHLY_LAUNCHER_V1', 'LAUNCHER_CONFIG_INVALID')
    root = Path(descriptor['root']).resolve()
    config_file = bounded(root, config_path)
    rolling_file = bounded(root, descriptor['rolling_config'])
    logs = bounded(root, descriptor['log_directory'])
    interpreter = Path(descriptor['python_path'])
    require(interpreter.is_absolute() and interpreter.is_file() and not interpreter.is_symlink(), 'LAUNCHER_PYTHON_UNAVAILABLE')
    pins = descriptor['source_pins']
    require(type(pins) is dict and REQUIRED_SOURCE_PATHS <= set(pins) and len(pins) <= 2000, 'LAUNCHER_SOURCE_PINS_REQUIRED')
    executing = Path(__file__).resolve().parents[1]
    def gate():
        read(config_file, config_sha256)
        for path, digest in pins.items():
            require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'LAUNCHER_PIN_PATH_INVALID')
            read(bounded(root, path), digest)
            read(bounded(executing, path), digest)
        rolling = json.loads(read(rolling_file, descriptor['rolling_sha256']))
        require(rolling['schema'] == 'ROLLING_REAL_MONTHLY_UPDATE_V1' and Path(rolling['root']).resolve() == root,
                'LAUNCHER_ROLLING_ROOT_MISMATCH')
        require(all(pins.get(path) == digest for path, digest in rolling['source_pins'].items()), 'LAUNCHER_CHILD_PIN_MISMATCH')
        for source in [config_file, rolling_file, bounded(root, rolling['output_directory']), *[bounded(root, p) for p in pins]]:
            require(logs != source and logs not in source.parents and source not in logs.parents, 'LAUNCHER_LOG_OVERLAP')
    gate()
    command = [str(interpreter), '-X', 'utf8', '-E', '-B', '-m', 'scripts.run_rolling_real_monthly_update',
               '--config-path', str(rolling_file), '--config-sha256', descriptor['rolling_sha256'], '--execute']
    if not execute:
        return dict(status='VALIDATED_PREVIEW', command=command, working_directory=str(root),
                    log_directory=str(logs), timeout_seconds=7200, account_writes=False)
    logs.mkdir(parents=True, exist_ok=True)
    attempt = logs/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex)
    attempt.mkdir(exist_ok=False)
    def save(name, value):
        with (attempt/name).open('xb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    save('started.json', dict(at=now(), config_sha256=config_sha256, rolling_sha256=descriptor['rolling_sha256']))
    owned = False
    lock = logs/'running.lock'
    try:
        try:
            with lock.open('xb') as stream:
                stream.write(canonical(dict(pid=os.getpid(), config_sha256=config_sha256)))
                stream.flush(); os.fsync(stream.fileno())
            owned = True
        except FileExistsError:
            result = dict(status='SKIPPED', reason='RUN_LOCK_PRESENT_REVIEW_IF_STALE')
        if owned:
            gate()
            with (attempt/'stdout.txt').open('xb') as stdout, (attempt/'stderr.txt').open('xb') as stderr:
                completed = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=7200)
            raw = (attempt/'stdout.txt').read_bytes()
            require(len(raw) <= 1024*1024, 'LAUNCHER_CHILD_OUTPUT_TOO_LARGE')
            try:
                child = json.loads(raw.decode('utf-8').strip().splitlines()[-1])
            except (ValueError, IndexError, UnicodeError):
                raise ValueError('LAUNCHER_CHILD_JSON_INVALID') from None
            require(type(child) is dict, 'LAUNCHER_CHILD_JSON_INVALID')
            status = child.get('status')
            require(status in WAITING | FAILED | {'MARKET_PREPARATION_PHASE', 'RELEASE_UPDATE_PHASE'}, 'LAUNCHER_CHILD_STATUS_UNKNOWN')
            if status in FAILED or completed.returncode != 0:
                outcome = 'FAILED'
            elif status in WAITING:
                outcome = 'WAITING'
            else:
                outcome = 'SUCCESS'
            result = dict(status=outcome, child_result=child, child_exit_code=completed.returncode)
            gate()
    except subprocess.TimeoutExpired:
        result = dict(status='FAILED', reason='CHILD_TIMEOUT_RECONCILE_BEFORE_RETRY', automatic_retry=False)
    except Exception as error:
        result = dict(status='FAILED', reason=safe_reason(error), automatic_retry=False)
    finally:
        if owned:
            lock.unlink()
    result['finished_at'] = now()
    save('finished.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path', required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result = dict(status='FAILED', reason=safe_reason(error), automatic_retry=False)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'FAILED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
