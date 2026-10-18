"""Pinned, bounded real monthly chain; no broker, account or target writes."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from core.strategy_account_ledger import canonical, require
from data.strategy_account_release_activation import MonthlyReleaseActivation, SNAPSHOT_FIELDS
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from scripts.coordinate_monthly_simulation import read, safe_reason
from scripts.build_real_monthly_release_entry import build as build_entry
from scripts.materialize_real_monthly_successor import run as successor
from scripts.run_real_monthly_market_preparation import bounded
from scripts.run_scheduled_real_monthly_update import run as scheduled, REQUIRED_SOURCE_PATHS as SCHEDULED_PATHS

REQUIRED_SOURCE_PATHS = SCHEDULED_PATHS | {
    'scripts/run_rolling_real_monthly_update.py', 'scripts/materialize_real_monthly_successor.py'}
FIELDS = {'schema', 'root', 'scheduled_config', 'scheduled_sha256', 'output_directory', 'source_pins'}


def run(*, config_path, config_sha256, execute=False, clock=None):
    clock = clock or (lambda: datetime.now(timezone.utc))
    config = json.loads(read(config_path, config_sha256))
    require(set(config) == FIELDS and config['schema'] == 'ROLLING_REAL_MONTHLY_UPDATE_V1', 'ROLLING_CONFIG_INVALID')
    root = Path(config['root']).resolve()
    directory = bounded(root, config['output_directory'])
    pins = config['source_pins']
    require(type(pins) is dict and REQUIRED_SOURCE_PATHS <= set(pins) and len(pins) <= 2000,
            'ROLLING_SOURCE_PINS_REQUIRED')
    executing = Path(__file__).resolve().parents[1]
    fixed = {bounded(root, config_path): config_sha256}
    def load(path, digest):
        target = bounded(root, path)
        value = json.loads(read(target, digest))
        require(target not in fixed or fixed[target] == digest, 'ROLLING_INPUT_PIN_CONFLICT')
        fixed[target] = digest
        return value
    def gate():
        for path, digest in pins.items():
            require(not Path(path).is_absolute() and '..' not in Path(path).parts, 'ROLLING_SOURCE_PATH_INVALID')
            read(bounded(root, path), digest)
            read(bounded(executing, path), digest)
        for path, digest in fixed.items():
            read(path, digest)
    first = load(config['scheduled_config'], config['scheduled_sha256'])
    require(Path(first['root']).resolve() == root, 'ROLLING_ROOT_MISMATCH')
    require(all(pins.get(path) == digest for path, digest in first['source_pins'].items()), 'ROLLING_CHILD_PINS_MISMATCH')
    require(all(directory != path and directory not in path.parents for path in fixed), 'ROLLING_OUTPUT_OVERLAP')
    for key in ('market_output_directory', 'update_output_directory', 'run_directory'):
        prior = bounded(root, first[key])
        require(directory != prior and directory not in prior.parents and prior not in directory.parents,
                'ROLLING_OUTPUT_OVERLAP')
    gate()
    descriptor = load(first['descriptor_path'], first['descriptor_sha256'])
    activation = MonthlyReleaseActivation(root=root,
        initial_snapshot={key: descriptor[key] for key in SNAPSHOT_FIELDS},
        validate_code=bind_dynamic_source_gate(root=root, source_pins=descriptor['source_pins']), clock=clock)

    def adopted(child):
        path = bounded(root, child['market_output_directory'])/'complete.json'
        if not path.is_file():
            return None
        digest = sha256(read(path)).hexdigest()
        receipt = json.loads(read(path, digest))
        if receipt.get('result', {}).get('status') != 'MARKET_PUBLICATION_READY_NOT_ACTIVATED':
            return None
        entry = build_entry(root=root, complete_path=path.relative_to(root).as_posix(), complete_sha256=digest,
                            descriptor_path=child['descriptor_path'], descriptor_sha256=child['descriptor_sha256'])
        snapshot = activation.snapshot()
        registry = json.loads(read(bounded(root, snapshot['registry_path']), snapshot['registry_sha256']))
        rows = [row for row in registry['entries'] if row.get('target_month') == entry['target_month']]
        if not rows:
            return None
        require(snapshot['revision'] > 0 and rows == [entry], 'ROLLING_ADOPTED_ENTRY_MISMATCH')
        require(activation.snapshot() == snapshot, 'ROLLING_ACTIVE_RELEASE_CHANGED')
        return path.relative_to(root).as_posix(), digest, entry['target_month']

    def save(path, raw):
        with path.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())

    def drive():
        child = first
        child_path, child_hash = config['scheduled_config'], config['scheduled_sha256']
        visited = []
        for _ in range(24):
            gate()
            evidence = adopted(child)
            if evidence is None:
                result = scheduled(config_path=str(bounded(root, child_path)), config_sha256=child_hash,
                                   execute=execute, clock=clock)
                gate()
                if execute and result.get('update', {}).get('status') == 'MONTHLY_DATA_RELEASE_ADOPTED':
                    evidence = adopted(child)
                    require(evidence is not None, 'ROLLING_ADOPTION_NOT_VISIBLE')
                else:
                    status = result['status']
                    if any(result.get(key, {}).get('status') in {'WAITING_REVIEW', 'BLOCKED'}
                           for key in ('preparation', 'update')):
                        status = next(result[key]['status'] for key in ('preparation', 'update')
                                      if result.get(key, {}).get('status') in {'WAITING_REVIEW', 'BLOCKED'})
                    return dict(status=status, phase=result, completed_months=visited,
                                account_writes=False, target_created=False, orders_created=False)
            complete_path, complete_hash, month = evidence
            require(month not in visited and (not visited or month > visited[-1]), 'ROLLING_MONTH_ORDER_INVALID')
            visited.append(month)
            month_directory = directory/month
            plan_directory = (month_directory/'plan').relative_to(root).as_posix()
            # The pure successor independently validates current adopted history.
            generated = successor(root=root, complete_path=complete_path, complete_sha256=complete_hash,
                descriptor_path=child['descriptor_path'], descriptor_sha256=child['descriptor_sha256'],
                output_directory=plan_directory, execute=execute, clock=clock)
            next_config = dict(child, coordinator_config=generated['coordinator_path'],
                coordinator_sha256=generated['coordinator_sha256'],
                market_output_directory=(month_directory/'market').relative_to(root).as_posix(),
                update_output_directory=(month_directory/'update').relative_to(root).as_posix(),
                run_directory=(month_directory/'runs').relative_to(root).as_posix())
            raw = canonical(next_config)
            next_path = month_directory/'scheduled.json'
            digest = sha256(raw).hexdigest()
            binding = dict(previous_scheduled_path=child_path, previous_scheduled_sha256=child_hash,
                complete_path=complete_path, complete_sha256=complete_hash,
                scheduled_path=next_path.relative_to(root).as_posix(), scheduled_sha256=digest)
            marker = month_directory/'chain.complete.json'
            if next_path.exists() or marker.exists():
                require(next_path.is_file() and marker.is_file(), 'ROLLING_PARTIAL_CHAIN_NO_RETRY')
                require(read(next_path, digest) == raw and json.loads(read(marker)) == binding, 'ROLLING_CHAIN_CHANGED')
            elif execute:
                gate()
                month_directory.mkdir(parents=True, exist_ok=True)
                save(next_path, raw)
                save(marker, canonical(binding))
            else:
                return dict(status='NEXT_MONTH_READY', target_month=generated['target_month'],
                            completed_months=visited, account_writes=False, http_calls=0)
            child_path, child_hash = next_path.relative_to(root).as_posix(), digest
            child = load(child_path, child_hash)
        raise ValueError('ROLLING_CHAIN_DEPTH_LIMIT')

    if not execute:
        result = drive(); gate(); return result
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory/'running.lock'
    with lock.open('xb') as stream:
        stream.write(canonical(dict(pid=os.getpid(), config_sha256=config_sha256)))
        stream.flush(); os.fsync(stream.fileno())
    try:
        result = drive(); gate(); return result
    finally:
        lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path', required=True)
    parser.add_argument('--config-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result = dict(status='BLOCKED', reason=safe_reason(error), automatic_retry=False)
    print(json.dumps(result))
    return 1 if result['status'] in {'BLOCKED', 'MISSED_PREPARATION_WINDOW', 'WAITING_REVIEW'} else 0


if __name__ == '__main__':
    raise SystemExit(main())
