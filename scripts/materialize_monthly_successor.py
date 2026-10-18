"""Create-only next coordinator registry from a fully completed prior pipeline.

Default preflight is read-only. Does not capture, search, publish a market route,
access accounts, or change automations. A registry here is a plan, not execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_difference_plan import require
from scripts.build_monthly_successor_plan import build_next_plan


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def calendar_source(root, source, expected):
    require(not Path(source).is_absolute() and '..' not in Path(source).parts,
            'SUCCESSOR_CALENDAR_PATH_INVALID')
    target = root/source
    require(target.resolve().is_relative_to(root) and not target.is_symlink() and target.is_file()
            and target.stat().st_size <= 32*1024*1024, 'SUCCESSOR_INPUT_UNAVAILABLE')
    require(digest(target.read_bytes()) == expected, 'SUCCESSOR_CALENDAR_SOURCE_CHANGED')
    return target


def run(*, previous_coordinator, previous_sha256, output_directory, execute=False,
        clock=lambda: datetime.now(timezone.utc)):
    previous_path = Path(previous_coordinator).resolve()
    raw = previous_path.read_bytes()
    require(digest(raw) == previous_sha256, 'SUCCESSOR_COORDINATOR_CHANGED')
    config = json.loads(raw); root = Path(config['root']).resolve()
    require(previous_path.is_relative_to(root), 'SUCCESSOR_COORDINATOR_OUTSIDE_ROOT')
    pins = {str(previous_path):previous_sha256}

    def bounded(path):
        path = Path(path)
        path = path if path.is_absolute() else root/path
        require('..' not in path.parts and path.resolve().is_relative_to(root)
                and not path.is_symlink() and path.is_file() and path.stat().st_size <= 32*1024*1024,
                'SUCCESSOR_INPUT_UNAVAILABLE')
        return path

    def checked(path, expected):
        path = bounded(path)
        raw = path.read_bytes(); require(digest(raw) == expected, 'SUCCESSOR_INPUT_CHANGED')
        pins[str(path.resolve())] = expected
        return json.loads(raw)

    settings = checked(config['settings_path'], config['settings_sha256'])
    checked(config['daily_config'], config['daily_sha256'])
    receipts = {}
    for stage in ('prepare', 'publish', 'bind'):
        path = root/config['stage_directory']/(stage+'.complete.json')
        require(path.is_file(), 'SUCCESSOR_PREVIOUS_MONTH_INCOMPLETE')
        receipt = checked(path, digest(path.read_bytes()))
        binding = receipt['binding']
        require(binding['config_sha256'] == previous_sha256 and binding['settings_sha256'] == config['settings_sha256'],
                'SUCCESSOR_STAGE_BINDING_CHANGED')
        start = path.with_name(stage+'.started.json')
        require(start.is_file() and json.loads(start.read_bytes())['binding'] == binding, 'SUCCESSOR_STAGE_START_MISMATCH')
        checked(start, digest(start.read_bytes()))
        require(not path.with_name(stage+'.failed.json').exists() or receipt.get('recovered_after_failure') is True,
                'SUCCESSOR_UNRECOVERED_STAGE')
        require(receipt['output_hashes'], 'SUCCESSOR_STAGE_OUTPUTS_MISSING')
        for output, sha in receipt['output_hashes'].items(): checked(output, sha)
        receipts[stage] = receipt
    require(receipts['prepare']['result']['status'] == 'READY_CONDITIONAL'
            and receipts['publish']['result']['status'] == 'PUBLISHED_CONDITIONAL_NOT_ACTIVATED'
            and receipts['bind']['result']['status'] == 'VALIDATED_MONTHLY_RUNTIME_RELEASE_PUBLISHED',
            'SUCCESSOR_PREVIOUS_MONTH_INCOMPLETE')
    bound = receipts['bind']['result']; published = receipts['publish']['result']
    require(bound['monthly_sha256'] == published['config_sha256']
            and bound['session'] == config['session'], 'SUCCESSOR_RELEASE_BINDING_MISMATCH')
    release = checked(bound['monthly_release'], receipts['bind']['output_hashes'][str(Path(bound['monthly_release']).resolve())])
    require(release['schema'] == 'LOCAL_MONTHLY_RUNTIME_RELEASE_V1'
            and release['target_month'] == config['session'][:7]
            and release['config_sha256'] == bound['config_sha256']
            and Path(release['config_path']).resolve() == Path(bound['config_path']).resolve()
            and release['base_sha256'] == config['daily_sha256'], 'SUCCESSOR_RELEASE_BINDING_MISMATCH')
    manifest_path = (Path(settings['preparation_output'])/'manifest.json').as_posix()
    manifest_hash = receipts['prepare']['output_hashes'][str((root/manifest_path).resolve())]
    manifest = checked(manifest_path, manifest_hash)
    for source, sha in manifest['source_hashes'].items():
        target = root/source
        require(not Path(source).is_absolute() and '..' not in Path(source).parts
                and target.resolve().is_relative_to(root) and not target.is_symlink()
                and target.is_file() and digest(target.read_bytes()) == sha, 'SUCCESSOR_INPUT_CHANGED')
        pins[str(target.resolve())] = sha
    receipt_path = (Path(config['stage_directory'])/'prepare.complete.json').as_posix()
    schedule_path = settings['schedule_path']
    schedule = checked(schedule_path, settings['fixed_source_hashes'][schedule_path])
    schedule_pins = {schedule_path:settings['fixed_source_hashes'][schedule_path], **schedule['source_hashes']}
    for source, sha in schedule_pins.items():
        target = calendar_source(root, source, sha)
        pins[str(target.resolve())] = sha
    output = Path(output_directory)
    require(not output.is_absolute() and '..' not in output.parts and output.as_posix() not in ('', '.'), 'SUCCESSOR_OUTPUT_INVALID')
    destination = root/output
    require(destination.resolve().is_relative_to(root), 'SUCCESSOR_OUTPUT_INVALID')
    binding = dict(previous_sha256=previous_sha256, previous_coordinator=str(previous_path), output_directory=output.as_posix())
    complete_path = destination/'materialization.complete.json'
    if complete_path.exists():
        complete = json.loads(bounded(complete_path).read_bytes())
        require(complete['binding'] == binding, 'SUCCESSOR_MATERIALIZATION_INPUT_CHANGED')
        require(complete['input_hashes'] == pins, 'SUCCESSOR_INPUT_CLOSURE_CHANGED')
        started = json.loads(bounded(destination/'materialization.started.json').read_bytes())
        require(started == dict(binding=binding, input_hashes=pins), 'SUCCESSOR_MATERIALIZATION_START_CHANGED')
        expected_outputs = {str((destination/name).resolve()) for name in
                            ('capture_plan.json','boundary.json','settings.json','coordinator.json','registry.json')}
        require(set(complete['output_hashes']) == expected_outputs, 'SUCCESSOR_OUTPUT_CLOSURE_CHANGED')
        for path, sha in complete['input_hashes'].items():
            require(digest(bounded(path).read_bytes()) == sha, 'SUCCESSOR_INPUT_CHANGED')
        for path, sha in complete['output_hashes'].items():
            require(digest(bounded(path).read_bytes()) == sha, 'SUCCESSOR_OUTPUT_CHANGED')
        return complete['result']
    require(not destination.exists(), 'SUCCESSOR_PARTIAL_OUTPUT_NO_OVERWRITE')
    generated = build_next_plan(root=root, previous_manifest_path=manifest_path, previous_manifest_sha256=manifest_hash,
        previous_completion_path=receipt_path, previous_completion_sha256=pins[str((root/receipt_path).resolve())],
        calendar_path=schedule_path, calendar_source_hashes=schedule_pins, output_directory=output.as_posix(),
        clock=clock, completed_target_month=config['session'][:7])
    artifacts = generated['artifacts']; boundary = json.loads(artifacts[(output/'boundary.json').as_posix()])
    settings_path = (output/'settings.json').as_posix()
    next_config = dict(config, settings_path=settings_path, settings_sha256=digest(artifacts[settings_path]),
        session=boundary['active_date'], daily_output=(output/'daily.json').as_posix(),
        stage_directory=(output/'stages').as_posix())
    next_path = (output/'coordinator.json').as_posix(); artifacts[next_path] = canonical(next_config)
    result = dict(status='SUCCESSOR_COORDINATOR_MATERIALIZED' if execute else 'SUCCESSOR_COORDINATOR_PREFLIGHT',
        coordinator_path=str((root/next_path).resolve()), coordinator_sha256=digest(artifacts[next_path]),
        target_month=generated['target_month'], session=boundary['active_date'],
        account_writes=False, http_calls=0, search_calls=0, market_route_published=False)
    registry = dict(schema='LOCAL_MONTHLY_COORDINATOR_PLAN_V1', **{k:result[k] for k in
        ('coordinator_path','coordinator_sha256','target_month','session')}, previous_coordinator_sha256=previous_sha256)
    artifacts[(output/'registry.json').as_posix()] = canonical(registry)
    if not execute: return result
    # Revalidate every previously read input immediately before create-only writing.
    for path, sha in pins.items(): require(digest(Path(path).read_bytes()) == sha, 'SUCCESSOR_INPUT_CHANGED')
    destination.mkdir(parents=True, exist_ok=False)
    def save(path, raw):
        with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    save(destination/'materialization.started.json', canonical(dict(binding=binding, input_hashes=pins)))
    for path, raw in artifacts.items(): save(root/path, raw)
    hashes = {str((root/path).resolve()):digest(raw) for path, raw in artifacts.items()}
    save(complete_path, canonical(dict(binding=binding,input_hashes=pins,output_hashes=hashes,result=result)))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('previous-coordinator','previous-sha256','output-directory'): parser.add_argument('--'+field, required=True)
    parser.add_argument('--execute', action='store_true')
    try: result = run(**vars(parser.parse_args()))
    except Exception as error:
        print(json.dumps(dict(status='BLOCKED', reason=str(error) if isinstance(error, ValueError) else type(error).__name__)))
        return 2
    print(json.dumps(result)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
