"""Pinned single-month local phase runner; never submits orders or creates targets."""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import os

from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
from core.strategy_account_ledger import require, canonical
from scripts.run_real_monthly_market_preparation import run as produce, bounded
from scripts.run_real_monthly_release_update import run as update
from scripts.coordinate_monthly_simulation import read, safe_reason

REQUIRED_SOURCE_PATHS = ROLLING_SOURCE_PATHS | {
    'scripts/run_scheduled_real_monthly_update.py',
    'scripts/run_real_monthly_market_preparation.py',
    'scripts/build_monthly_market_review_request.py',
    'scripts/build_real_monthly_release_entry.py',
    'scripts/run_real_monthly_release_update.py',
    'scripts/coordinate_monthly_simulation.py',
    'scripts/monthly_experimental_domain_capture.py',
    'scripts/build_monthly_successor_plan.py',
    'scripts/prepare_monthly_captured_training.py',
    'scripts/publish_monthly_market_configuration.py',
    'scripts/current_research_official_alert_capture.py',
    'data/current_quantity_v2_monthly_known_source_review.py',
}
FIELDS = {'schema', 'root', 'coordinator_config', 'coordinator_sha256',
          'bootstrap_config', 'bootstrap_sha256', 'policy_path', 'policy_sha256',
          'descriptor_path', 'descriptor_sha256', 'market_output_directory',
          'update_output_directory', 'run_directory', 'source_pins'}


def run(*, config_path, config_sha256, execute=False, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    config = json.loads(read(config_path, config_sha256))
    require(set(config) == FIELDS and config['schema'] == 'SCHEDULED_REAL_MONTHLY_UPDATE_V1',
            'SCHEDULED_CONFIG_INVALID')
    root = Path(config['root']).resolve()
    for key in ('descriptor_path', 'policy_path', 'market_output_directory',
                'update_output_directory', 'run_directory'):
        value = config[key]
        require(isinstance(value, str) and value and not Path(value).is_absolute()
                and '..' not in Path(value).parts, 'SCHEDULED_RELATIVE_PATH_REQUIRED')
    dependencies = {bounded(root, config_path): config_sha256}
    def load(path, digest):
        path = bounded(root, path)
        value = json.loads(read(path, digest))
        dependencies[path] = digest
        return value
    pins = config['source_pins']
    require(isinstance(pins, dict) and REQUIRED_SOURCE_PATHS <= set(pins) and len(pins) <= 2000,
            'SCHEDULED_SOURCE_PINS_REQUIRED')
    executing_root = Path(__file__).resolve().parents[1]
    def gate():
        for name, digest in pins.items():
            require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                    'SCHEDULED_PIN_PATH_INVALID')
            read(bounded(root, name), digest)
            read(bounded(executing_root, name), digest)
        for path, digest in dependencies.items():
            read(path, digest)
    gate()
    for path_key, hash_key in (('bootstrap_config', 'bootstrap_sha256'),
                               ('policy_path', 'policy_sha256'),
                               ('descriptor_path', 'descriptor_sha256')):
        load(config[path_key], config[hash_key])
    coordinator = load(config['coordinator_config'], config['coordinator_sha256'])
    require(Path(coordinator['root']).resolve() == root, 'SCHEDULED_ROOT_MISMATCH')
    settings = load(coordinator['settings_path'], coordinator['settings_sha256'])
    boundary = load(settings['calendar_path'], settings['fixed_source_hashes'][settings['calendar_path']])
    schedule = load(settings['schedule_path'], settings['fixed_source_hashes'][settings['schedule_path']])
    def stamp(value):
        value = datetime.fromisoformat(value) if isinstance(value, str) else value
        require(isinstance(value, datetime) and value.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
        return value
    closing, opening = stamp(boundary['decision_close_at']), stamp(boundary['active_open_at'])
    require(closing < opening, 'INVALID_PREPARATION_WINDOW')
    sessions = [(stamp(row['open_at']), stamp(row['close_at'])) for row in schedule['sessions']]
    require(any(start == opening for start, end in sessions), 'SCHEDULE_OPENING_MISMATCH')
    require(all(start < end for start, end in sessions), 'INVALID_SCHEDULE_SESSION')
    outputs = [bounded(root, config[k]) for k in ('market_output_directory', 'update_output_directory', 'run_directory')]
    others = [bounded(root, settings[k]) for k in ('preparation_output', 'publish_output')]
    others += [bounded(root, coordinator['stage_directory']), bounded(root, settings['capture_index_path']).parent]
    for i, one in enumerate(outputs):
        for two in outputs[i+1:] + others:
            require(one != two and one not in two.parents and two not in one.parents, 'OUTPUT_DIRECTORIES_OVERLAP')
    producer_arguments = {k:config[k] for k in ('coordinator_config', 'coordinator_sha256',
        'bootstrap_config', 'bootstrap_sha256', 'policy_path', 'policy_sha256')}
    producer_arguments['coordinator_config'] = str(bounded(root, config['coordinator_config']))
    producer_arguments['bootstrap_config'] = str(bounded(root, config['bootstrap_config']))
    producer_arguments.update(output_directory=config['market_output_directory'], clock=clock)
    def phase():
        current = stamp(clock())
        if current < closing:
            result = produce(**producer_arguments)
            return dict(status='WAITING_SESSION_CLOSE', preparation=result)
        if current < opening:
            result = produce(**producer_arguments, execute=execute)
            return dict(status='MARKET_PREPARATION_PHASE', preparation=result)
        complete = outputs[0]/'complete.json'
        if not complete.is_file():
            return dict(status='MISSED_PREPARATION_WINDOW', automatic_retry=False)
        # Producer revalidates all retained output hashes, never fetches after open.
        market = produce(**producer_arguments)
        if market.get('status') == 'WAITING_REVIEW':
            return dict(status='WAITING_REVIEW', preparation=market, automatic_retry=False)
        ready = outputs[1]/'review/ready.json'
        started = outputs[1]/'started.json'
        regular = any(start + timedelta(minutes=30) <= current < end for start, end in sessions)
        if execute and not ready.is_file() and not started.exists() and not regular:
            return dict(status='WAITING_REGULAR_REVIEW_WINDOW', preparation=market)
        # Fix the freshness requirement before update creates its started receipt.
        fresh = not ready.is_file() and not started.exists()
        def guarded_clock():
            gate()
            value = stamp(clock())
            if fresh and execute:
                require(any(start + timedelta(minutes=30) <= value < end for start, end in sessions),
                        'REGULAR_REVIEW_WINDOW_ELAPSED')
            return value
        arguments = dict(root=root, complete_path=complete.relative_to(root).as_posix(),
            complete_sha256=sha256(read(complete)).hexdigest(),
            descriptor_path=config['descriptor_path'], descriptor_sha256=config['descriptor_sha256'],
            output_directory=config['update_output_directory'], execute=execute, clock=guarded_clock)
        return dict(status='RELEASE_UPDATE_PHASE', update=update(**arguments))
    def checked_phase():
        gate()
        result = phase()
        gate()
        return dict(**result, account_writes=False, target_created=False, orders_created=False)
    if not execute:
        return checked_phase()
    logs = outputs[2]
    logs.mkdir(parents=True, exist_ok=True)
    lock = logs/'running.lock'
    # An interrupted process leaves this lock for explicit reconciliation.
    with lock.open('xb') as stream:
        stream.write(canonical(dict(pid=os.getpid(), config_sha256=config_sha256)))
        stream.flush(); os.fsync(stream.fileno())
    attempt = logs/uuid4().hex
    attempt.mkdir(exist_ok=False)
    def save(name, value):
        with (attempt/name).open('xb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    try:
        save('started.json', dict(config_sha256=config_sha256, at=stamp(clock()).isoformat()))
        result = checked_phase()
        save('complete.json', result)
        return result
    except Exception as error:
        save('failed.json', dict(status='BLOCKED', error_type=type(error).__name__, automatic_retry=False))
        raise
    finally:
        lock.unlink()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path', required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result = dict(status='BLOCKED', reason=safe_reason(error), automatic_retry=False)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['status'] in {'MISSED_PREPARATION_WINDOW', 'BLOCKED', 'WAITING_REVIEW'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
