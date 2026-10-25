"""Create the next market plan only after verified real release adoption.

Read-only by default. No SimulationStore, capture, account changes or scheduler
changes. Partial output requires inspection instead of automatic overwrite.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from core.strategy_account_ledger import require
from data.current_quantity_v2_current_cash_plan import canonical
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_profiled_ready_release import PROFILE_ADMISSION_SOURCES
from scripts.build_real_monthly_release_entry import build as build_entry
from scripts.build_monthly_successor_plan import build_next_plan
from scripts.run_real_monthly_market_preparation import bounded
from scripts.coordinate_monthly_simulation import safe_reason


def run(*, root, complete_path, complete_sha256, descriptor_path, descriptor_sha256,
        output_directory, snapshot_provider, validate_code, runtime_pins, execute=False, clock=lambda: datetime.now(timezone.utc)):
    from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
    root = Path(root).resolve()
    pins = {}

    def read(path, digest):
        target = bounded(root, path)
        require(target.is_file() and target.stat().st_size <= 32*1024*1024, 'SUCCESSOR_INPUT_UNAVAILABLE')
        raw = target.read_bytes()
        require(sha256(raw).hexdigest() == digest, 'SUCCESSOR_INPUT_CHANGED')
        relative = target.relative_to(root).as_posix()
        require(relative not in pins or pins[relative] == digest, 'SUCCESSOR_INPUT_PIN_CONFLICT')
        pins[relative] = digest
        return json.loads(raw)

    entry = build_entry(root=root, complete_path=complete_path, complete_sha256=complete_sha256,
                        descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256)
    complete = read(complete_path, complete_sha256)
    # build_entry has verified all bytes, including non-JSON evidence.
    pins.update(complete['output_hashes'])
    descriptor = read(descriptor_path, descriptor_sha256)
    require(ROLLING_SOURCE_PATHS <= set(descriptor['source_pins']), 'SUCCESSOR_DEPLOYMENT_SCOPE_REQUIRED')
    gate = bind_dynamic_source_gate(root=root, source_pins=descriptor['source_pins'])
    validate_code()
    for name in RUNTIME_PATHS | PROFILE_ADMISSION_SOURCES:
        entry['runtime_pins'][name] = runtime_pins[name]
    snapshot = snapshot_provider()
    require(snapshot['revision'] > 0, 'SUCCESSOR_REAL_ADOPTION_REQUIRED')
    # Adoption is a live prerequisite, not a fixed input of the pure plan.
    # Later adoption appends a registry, while this month's market and outputs
    # remain unchanged. Keep its pin outside the permanent input closure.
    stable_pins = dict(pins)
    registry = read(snapshot['registry_path'], snapshot['registry_sha256'])
    require(registry['schema']=='PROFILED_MONTHLY_RELEASES_V1' and
            dict(target_month=entry['target_month'],selector_profile=PROFILE_ID) in registry['profiles'],
            'SUCCESSOR_CURRENT_PROFILE_REQUIRED')
    reference=registry['original_registry']
    registry=read(reference['path'],reference['sha256'])
    pins = stable_pins
    require(registry['schema'] == 'REAL_STRATEGY_MONTHLY_RELEASES_V1'
            and [row for row in registry['entries'] if row.get('target_month') == entry['target_month']] == [entry],
            'SUCCESSOR_ACTIVE_MARKET_MISMATCH')
    coordinator_hash = complete['binding']['coordinator_sha256']
    candidates = [path for path, digest in complete['output_hashes'].items() if digest == coordinator_hash]
    require(len(candidates) == 1, 'SUCCESSOR_COORDINATOR_BINDING_AMBIGUOUS')
    config = read(candidates[0], coordinator_hash)
    require(Path(config['root']).resolve() == root, 'SUCCESSOR_COORDINATOR_ROOT_MISMATCH')
    def dependency(path, digest=None):
        relative = bounded(root, path).relative_to(root).as_posix()
        require(relative in complete['output_hashes'] and
                (digest is None or complete['output_hashes'][relative] == digest), 'SUCCESSOR_DEPENDENCY_NOT_PINNED')
        return read(relative, complete['output_hashes'][relative])
    settings = dependency(config['settings_path'], config['settings_sha256'])
    dependency(config['daily_config'], config['daily_sha256'])  # compatibility input only
    require(config['session'][:7] == entry['target_month'], 'SUCCESSOR_TARGET_MONTH_MISMATCH')
    receipt_path = bounded(root, Path(config['stage_directory'])/'prepare.complete.json').relative_to(root).as_posix()
    receipt = dependency(receipt_path)
    require(receipt['binding']['config_sha256'] == coordinator_hash and
            receipt['binding']['settings_sha256'] == config['settings_sha256'], 'SUCCESSOR_PREPARATION_BINDING_MISMATCH')
    manifest_path = bounded(root, Path(settings['preparation_output'])/'manifest.json').relative_to(root).as_posix()
    dependency(manifest_path)
    schedule_path = settings['schedule_path']
    schedule_hash = settings['fixed_source_hashes'][schedule_path]
    schedule = dependency(schedule_path, schedule_hash)
    schedule_pins = {**schedule['source_hashes'], schedule_path: schedule_hash}
    require(all(complete['output_hashes'].get(path) == digest for path, digest in schedule_pins.items()),
            'SUCCESSOR_CALENDAR_NOT_PINNED')
    destination = bounded(root, output_directory)
    output = destination.relative_to(root).as_posix()
    require(all(destination != bounded(root, path) and destination not in bounded(root, path).parents
                for path in pins), 'SUCCESSOR_OUTPUT_OVERLAPS_SOURCE')
    generated = build_next_plan(root=root, previous_manifest_path=manifest_path,
        previous_manifest_sha256=complete['output_hashes'][manifest_path], previous_completion_path=receipt_path,
        previous_completion_sha256=complete['output_hashes'][receipt_path], calendar_path=schedule_path,
        calendar_source_hashes=schedule_pins, output_directory=output, clock=clock,
        completed_target_month=entry['target_month'])
    artifacts = generated['artifacts']
    boundary = json.loads(artifacts[output+'/boundary.json'])
    settings_path = output+'/settings.json'
    config = dict(config, settings_path=settings_path, settings_sha256=sha256(artifacts[settings_path]).hexdigest(),
                  session=boundary['active_date'], daily_output=output+'/daily.json', stage_directory=output+'/stages')
    coordinator_path = output+'/coordinator.json'
    artifacts[coordinator_path] = canonical(config)
    result = dict(status='REAL_SUCCESSOR_MATERIALIZED', coordinator_path=coordinator_path,
        coordinator_sha256=sha256(artifacts[coordinator_path]).hexdigest(), target_month=generated['target_month'],
        account_writes=False, http_calls=0, search_calls=0, published=False)
    binding = dict(complete_path=complete_path, complete_sha256=complete_sha256,
                   descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256, output_directory=output)
    hashes = {path: sha256(raw).hexdigest() for path, raw in artifacts.items()}

    def recheck():
        gate(); validate_code()
        require(snapshot_provider() == snapshot, 'SUCCESSOR_ACTIVE_RELEASE_CHANGED')
        require(sha256(bounded(root, snapshot['registry_path']).read_bytes()).hexdigest() == snapshot['registry_sha256'],
                'SUCCESSOR_ACTIVE_REGISTRY_CHANGED')
        for path, digest in pins.items():
            require(sha256(bounded(root, path).read_bytes()).hexdigest() == digest, 'SUCCESSOR_INPUT_CHANGED')

    recheck()
    completion = dict(binding=binding, input_hashes=pins, output_hashes=hashes, result=result)
    if destination.exists():
        done = destination/'materialization.complete.json'
        require(done.is_file(), 'SUCCESSOR_PARTIAL_OUTPUT_NO_OVERWRITE')
        require(json.loads(done.read_bytes()) == completion, 'SUCCESSOR_COMPLETION_CHANGED')
        require(json.loads((destination/'materialization.started.json').read_bytes()) == binding,
                'SUCCESSOR_START_CHANGED')
        for path, digest in hashes.items():
            require(sha256(bounded(root, path).read_bytes()).hexdigest() == digest, 'SUCCESSOR_OUTPUT_CHANGED')
        recheck()
        return result
    if not execute:
        return dict(result, status='REAL_SUCCESSOR_PREFLIGHT')
    destination.mkdir(parents=True, exist_ok=False)
    def save(path, raw):
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    save(destination/'materialization.started.json', canonical(binding))
    for path, raw in artifacts.items():
        require(bounded(root, path).parent == destination, 'SUCCESSOR_ARTIFACT_OUTSIDE_DESTINATION')
        save(root/path, raw)
    recheck()
    save(destination/'materialization.complete.json', canonical(completion))
    return result

