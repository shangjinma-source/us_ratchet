"""Derive a paper-only successor from a verified policy-bound market release.

No real-account adoption, HTTP, selection, trading or task changes.
The caller must obtain expected_binding and terminal_month from its fixed policy.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

from core.strategy_account_ledger import require
from data.current_quantity_v2_current_cash_plan import canonical
from scripts.build_real_monthly_release_entry import build as build_entry
from scripts.build_monthly_successor_plan import build_next_plan
from scripts.run_real_monthly_market_preparation import bounded
from data.strategy_paper_application_descriptor_v2 import stamp


def run(*, root, complete_path, complete_sha256, descriptor_path, descriptor_sha256,
        output_directory, expected_binding, terminal_month, execute=False,
        clock=lambda: datetime.now(timezone.utc)):
    root = Path(root).resolve()
    pins = {}
    now = stamp(clock())
    clock = lambda: now

    def read(path, digest):
        target = bounded(root, path)
        require(target.is_file() and target.stat().st_size <= 32*1024*1024, 'SUCCESSOR_INPUT_UNAVAILABLE')
        raw = target.read_bytes()
        require(sha256(raw).hexdigest() == digest, 'SUCCESSOR_INPUT_CHANGED')
        relative = target.relative_to(root).as_posix()
        require(relative not in pins or pins[relative] == digest, 'SUCCESSOR_INPUT_PIN_CONFLICT')
        pins[relative] = digest
        return json.loads(raw)

    complete = read(complete_path, complete_sha256)
    failure = bounded(root, complete_path).parent/'failed.json'
    require(not failure.exists(), 'PAPER_SUCCESSOR_FAILED_PRESERVED')
    require(complete['binding'] == expected_binding and stamp(complete['at']) <= now,
            'PAPER_SUCCESSOR_COMPLETION_BINDING')
    entry = build_entry(root=root, complete_path=complete_path, complete_sha256=complete_sha256,
                        descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256)
    pins.update(complete['output_hashes'])
    descriptor = read(descriptor_path, descriptor_sha256)
    for path, digest in descriptor['source_pins'].items():
        require(sha256(bounded(root, path).read_bytes()).hexdigest() == digest,
                'PAPER_SUCCESSOR_RUNTIME_CHANGED')
        require(path not in pins or pins[path] == digest, 'SUCCESSOR_INPUT_PIN_CONFLICT')
        pins[path] = digest
    require(isinstance(terminal_month, str) and len(terminal_month) == 7,
            'PAPER_SUCCESSOR_TERMINAL_MONTH')
    require(datetime.strptime(terminal_month, '%Y-%m').strftime('%Y-%m') == terminal_month,
            'PAPER_SUCCESSOR_TERMINAL_MONTH')
    require(entry['target_month'] < terminal_month, 'PAPER_SUCCESSOR_STUDY_FINISHED')
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
    require(entry['target_month'] < generated['target_month'] <= terminal_month,
            'PAPER_SUCCESSOR_OUTSIDE_STUDY')
    artifacts = generated['artifacts']
    boundary = json.loads(artifacts[output+'/boundary.json'])
    settings_path = output+'/settings.json'
    config = dict(config, settings_path=settings_path, settings_sha256=sha256(artifacts[settings_path]).hexdigest(),
                  session=boundary['active_date'], daily_output=output+'/daily.json', stage_directory=output+'/stages')
    coordinator_path = output+'/coordinator.json'
    artifacts[coordinator_path] = canonical(config)
    result = dict(status='PAPER_SUCCESSOR_MATERIALIZED', coordinator_path=coordinator_path,
        coordinator_sha256=sha256(artifacts[coordinator_path]).hexdigest(), target_month=generated['target_month'],
        account_writes=False, http_calls=0, search_calls=0, published=False)
    binding = dict(complete_path=complete_path, complete_sha256=complete_sha256,
                   descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256, output_directory=output,
                   expected_binding=expected_binding, terminal_month=terminal_month)
    hashes = {path: sha256(raw).hexdigest() for path, raw in artifacts.items()}

    def recheck():
        require(not failure.exists(), 'PAPER_SUCCESSOR_FAILED_PRESERVED')
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
        return dict(result, status='PAPER_SUCCESSOR_PREFLIGHT')
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

