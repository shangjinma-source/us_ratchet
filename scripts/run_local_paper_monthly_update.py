"""Paper-only monthly launcher, preview by default. Does not initialize simulation.

This is not installed or a replacement for the existing Codex schedule until
the paper daily bootstrap and local equivalence have been separately verified.
"""
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
REQUIRED_SOURCE_PATHS = {
    'scripts/run_local_paper_monthly_update.py', 'scripts/run_rolling_monthly_simulation.py',
    'scripts/run_monthly_simulation_pipeline.py', 'scripts/materialize_monthly_successor.py',
    'scripts/coordinate_monthly_simulation.py', 'scripts/collect_monthly_automatic_review_evidence.py',
    'scripts/build_monthly_automatic_review_request.py', 'scripts/build_monthly_successor_plan.py',
    'scripts/monthly_experimental_domain_capture.py', 'scripts/prepare_monthly_captured_training.py',
    'scripts/publish_monthly_market_configuration.py', 'scripts/bind_monthly_simulation_runtime.py',
    'scripts/monthly_runtime_routes.py', 'scripts/run_current_quantity_v2_simulation.py',
    'scripts/current_research_official_alert_capture.py', 'scripts/current_research_close_capture.py',
    'scripts/run_real_monthly_market_preparation.py',
    'backtest/current_quantity_v2_simulation_store.py', 'backtest/current_quantity_v2_close_capture_simulation.py',
    'data/current_quantity_v2_monthly_known_source_review.py', 'data/current_quantity_v2_monthly_training.py',
    'data/current_quantity_v2_monthly_composition.py', 'data/current_quantity_v2_monthly_origins.py',
    'data/current_quantity_v2_simulation_origin_files.py', 'data/current_quantity_v2_late_unit_review.py',
    'data/current_quantity_v2_paper_action_sources.py',
}
FIELDS = {'schema', 'root', 'python_path', 'rolling_config', 'rolling_sha256', 'log_directory', 'source_pins'}
WAITING = {'WAITING_SESSION_CLOSE', 'WAITING_TRAINING_CAPTURE', 'DUE_READ_ONLY'}
EXPLANATIONS = {
    'WAITING_ACCOUNT': 'Paper simulation has not been initialized; the daily 10:00 New York bootstrap must complete first.',
    'RESELECT_REQUIRED': 'The initial execution month expired; a separately reviewed bootstrap is required, with no historical backfill.',
    'RECOVERY_REQUIRED': 'The preparation window was missed; do not fabricate a past month from current data.',
    'WAITING_REVIEW': 'Retained evidence needs review; do not delete it or retry blindly.',
    'MONTHLY_COMPLETE_NEXT_PLAN_BLOCKED': 'The paper monthly release completed but its successor did not; inspect retained receipts.',
}


def classify(child, exit_code):
    require(type(child) is dict, 'LAUNCHER_CHILD_JSON_INVALID')
    status = child.get('status')
    reason = child.get('reason')
    nested = child.get('result', {})
    require(type(nested) is dict, 'LAUNCHER_CHILD_JSON_INVALID')
    codes = {value for value in (status, reason, nested.get('status'), nested.get('reason')) if isinstance(value, str)}
    if 'RESELECT_REQUIRED' in codes:
        outcome, code = 'NEEDS_REVIEW', 'RESELECT_REQUIRED'
    elif 'WAITING_ACCOUNT' in codes:
        outcome, code = 'NEEDS_INITIALIZATION', 'WAITING_ACCOUNT'
    elif status == 'RECOVERY_REQUIRED':
        outcome, code = 'NEEDS_RECOVERY', status
    elif status in {'WAITING_REVIEW', 'MONTHLY_COMPLETE_NEXT_PLAN_BLOCKED'}:
        outcome, code = 'NEEDS_REVIEW', status
    elif exit_code != 0 or status == 'BLOCKED':
        outcome, code = 'FAILED', safe_reason(ValueError(str(reason or 'CHILD_NONZERO_EXIT')))
    elif status in WAITING:
        outcome, code = 'WAITING', status
    elif status == 'MONTHLY_COMPLETE_NEXT_PLAN_READY':
        require(nested.get('status') == 'MONTHLY_RUNTIME_PUBLISHED'
                and child.get('successor', {}).get('status') == 'SUCCESSOR_COORDINATOR_MATERIALIZED',
                'LAUNCHER_MONTHLY_SUCCESS_EVIDENCE_MISSING')
        outcome, code = 'SUCCESS', status
    else:
        raise ValueError('LAUNCHER_CHILD_STATUS_UNKNOWN')
    return dict(status=outcome, reason=code, explanation=EXPLANATIONS.get(code, ''),
                child_result=child, child_exit_code=exit_code)


def now():
    return datetime.now(timezone.utc).isoformat()


def run(*, config_path, config_sha256, execute=False):
    descriptor = json.loads(read(config_path, config_sha256))
    require(set(descriptor) == FIELDS and descriptor['schema'] == 'LOCAL_PAPER_MONTHLY_LAUNCHER_V1', 'LAUNCHER_CONFIG_INVALID')
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
        require(rolling['schema'] == 'ROLLING_MONTHLY_SIMULATION_V1' and Path(rolling['root']).resolve() == root,
                'LAUNCHER_ROLLING_ROOT_MISMATCH')
        dependencies = []
        for key in ('first_coordinator', 'bootstrap', 'policy'):
            binding = rolling[key]
            require(set(binding) == {'path', 'sha256'}, 'LAUNCHER_BINDING_INVALID')
            path = bounded(root, binding['path'])
            read(path, binding['sha256']); dependencies.append(path)
        coordinator = json.loads(read(dependencies[0], rolling['first_coordinator']['sha256']))
        settings_path = bounded(root, coordinator['settings_path'])
        settings = json.loads(read(settings_path, coordinator['settings_sha256']))
        initial = json.loads(read(dependencies[1], rolling['bootstrap']['sha256']))
        dependencies.extend([settings_path, bounded(root, coordinator['stage_directory']),
            bounded(root, settings['capture_index_path']).parent,
            bounded(root, settings['preparation_output']), bounded(root, settings['publish_output']),
            bounded(root, initial['database_path']), bounded(root, initial['audit_directory'])])
        for source in [config_file, rolling_file, bounded(root, rolling['rolling_output_directory']),
                       bounded(root, rolling['first_evidence_directory']), *dependencies, *[bounded(root, p) for p in pins]]:
            require(logs != source and logs not in source.parents and source not in logs.parents, 'LAUNCHER_LOG_OVERLAP')
    gate()
    command = [str(interpreter), '-X', 'utf8', '-E', '-B', '-m', 'scripts.run_rolling_monthly_simulation',
               '--config-path', str(rolling_file), '--config-sha256', descriptor['rolling_sha256'], '--execute']
    if not execute:
        return dict(status='VALIDATED_PREVIEW', command=command, working_directory=str(root),
                    log_directory=str(logs), timeout_seconds=7200, account_writes=False,
                    initializes_simulation=False, cutover_ready=False,
                    cutover_requirement='Verify daily bootstrap and local equivalence before replacing only the monthly duty of automation11; preserve follow-up duty.')
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
            result = classify(child, completed.returncode)
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
    return 0 if result['status'] in {'VALIDATED_PREVIEW', 'WAITING', 'SUCCESS', 'SKIPPED'} else 2


if __name__ == '__main__':
    raise SystemExit(main())
