"""Account-free, bounded monthly market preparation; no account writes or activation."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
from scripts.coordinate_monthly_simulation import run as coordinate, read, save, now, safe_reason
from scripts.monthly_experimental_domain_capture import default_fetch
from scripts.build_monthly_successor_plan import prepare
from scripts.current_research_official_alert_capture import capture_official_alerts, fetch_official_feed
from scripts.publish_monthly_market_configuration import publish
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_current_cash_sources import MANIFEST
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS


def bounded(root, value):
    path = Path(value)
    candidate = path if path.is_absolute() else root / path
    require(candidate.resolve().is_relative_to(root) and candidate.resolve() != root, 'PATH_OUTSIDE_ROOT')
    for node in (candidate, *candidate.parents):
        require(not node.is_symlink() and not (hasattr(node, 'is_junction') and node.is_junction()), 'LINK_PATH_FORBIDDEN')
        if node == root:
            break
    return candidate


def run(*, coordinator_config, coordinator_sha256, bootstrap_config, bootstrap_sha256,
        policy_path, policy_sha256, output_directory, execute=False, clock=now,
        fetch=default_fetch, rss_fetch=fetch_official_feed):
    config = json.loads(read(coordinator_config, coordinator_sha256))
    root = Path(config['root']).resolve()
    dependencies = {}
    def source(path, digest):
        path = bounded(root, path)
        raw = read(path, digest)
        dependencies[path.relative_to(root).as_posix()] = digest
        return raw
    source(coordinator_config, coordinator_sha256)
    settings = json.loads(source(config['settings_path'], config['settings_sha256']))
    source(config['daily_config'], config['daily_sha256'])
    initial = json.loads(source(bootstrap_config, bootstrap_sha256))
    descriptor = json.loads(source(initial['descriptor']['path'], initial['descriptor']['sha256']))
    pins = dict(descriptor['source_hashes'])
    require(0 < len(pins) <= 2000, 'SOURCE_PIN_LIMIT')
    VerifiedSnapshotBundleService(SimpleNamespace(root=root), source_withdrawals=SOURCE_WITHDRAWALS).require_source_hashes_admitted(pins)
    total = 0
    for path, digest in pins.items():
        total += len(source(path, digest))
        require(total <= 128 * 1024 * 1024, 'IDENTITY_SOURCE_BYTES_LIMIT')
    identity = initial.get('identity_manifest_path', MANIFEST)
    require(identity in pins, 'PINNED_MANIFEST_REQUIRED')
    source(policy_path, policy_sha256)
    policy_path = bounded(root, policy_path).relative_to(root).as_posix()
    for path, digest in settings['fixed_source_hashes'].items():
        source(path, digest)
    source(settings['plan_path'], settings['plan_sha256'])
    source(settings['previous_manifest_path'], settings['previous_manifest_sha256'])
    calendar = json.loads(source(settings['calendar_path'], settings['fixed_source_hashes'][settings['calendar_path']]))
    closing, opening = stamp(calendar['decision_close_at']), stamp(calendar['active_open_at'])
    require(closing < opening, 'INVALID_PREPARATION_WINDOW')
    destination = bounded(root, output_directory)
    output_directory = destination.relative_to(root).as_posix()
    for existing in (settings['preparation_output'], settings['publish_output'], config['stage_directory'], str(Path(settings['capture_index_path']).parent)):
        other = bounded(root, existing)
        require(destination != other and destination not in other.parents and other not in destination.parents, 'OUTPUT_DIRECTORIES_OVERLAP')
    binding = dict(coordinator_sha256=coordinator_sha256, bootstrap_sha256=bootstrap_sha256,
                   policy_path=policy_path, policy_sha256=policy_sha256, output_directory=output_directory)
    def check_dependencies():
        for path, digest in dependencies.items():
            read(bounded(root, path), digest)
    def window_clock():
        value = stamp(clock())
        require(closing <= value < opening, 'MARKET_PREPARATION_WINDOW_ELAPSED')
        return value
    # A complete result can be read after opening; no recomputation or fetch is allowed.
    if destination.exists():
        complete = destination / 'complete.json'
        require(complete.is_file(), 'PARTIAL_OR_FAILED_MARKET_PREPARATION_NO_RETRY')
        receipt = json.loads(read(complete))
        require(receipt['binding'] == binding, 'MARKET_PREPARATION_INPUT_CHANGED')
        for path, digest in receipt['output_hashes'].items():
            read(bounded(root, path), digest)
        check_dependencies()
        return receipt['result']
    preflight = coordinate(config_path=coordinator_config, config_sha256=coordinator_sha256, clock=clock)
    if not execute:
        return dict(status='PREFLIGHT_ONLY', preparation=preflight, ready_after_close=closing <= stamp(clock()) < opening,
                    account_writes=False, http_calls=0)
    if stamp(clock()) < closing:
        return dict(status='WAITING_SESSION_CLOSE', account_writes=False, http_calls=0)
    window_clock()
    destination.mkdir(parents=True, exist_ok=False)
    save(destination / 'started.json', dict(binding=binding, at=window_clock().isoformat(), automatic_retry=False))
    try:
        prepared = coordinate(config_path=coordinator_config, config_sha256=coordinator_sha256,
                              execute=True, clock=window_clock, fetch=fetch)
        require(prepared['status'] == 'WAITING_REVIEW', 'MARKET_TRAINING_NOT_PREPARED')
        preparation = {k:settings[k] for k in ('previous_manifest_path','previous_manifest_sha256','capture_index_path','plan_path','plan_sha256')}
        preparation['capture_index_sha256'] = sha256(read(bounded(root, settings['capture_index_path']))).hexdigest()
        source(settings['capture_index_path'], preparation['capture_index_sha256'])
        feed = output_directory + '/official-feed'
        captured = capture_official_alerts(feed, root=root, capture=True, fetch=rss_fetch, clock=window_clock)
        require(captured['status'] != 'UNAVAILABLE', 'OFFICIAL_FEED_UNAVAILABLE')
        for name in ('response.bin', 'receipt.json'):
            path = feed + '/' + name
            pins[path] = sha256(read(bounded(root, path))).hexdigest()
        pins[policy_path] = policy_sha256
        inputs = dict(schema='MONTHLY_MARKET_REVIEW_INPUTS_V1', source_hashes=pins,
                      feed_path=feed+'/response.bin', feed_receipt_path=feed+'/receipt.json',
                      policy_path=policy_path, identity_manifest_path=identity)
        from scripts.build_monthly_market_review_request import construct
        market_settings = dict(settings, publish_output=output_directory+'/publication')
        arguments = dict(preparation, root=root, clock=window_clock, plan_validator=prepare)
        reviewed = construct(preparation_arguments=arguments, settings=market_settings,
                             inputs=inputs, output_prefix=output_directory+'/review')
        for path, body in reviewed['artifacts'].items():
            target = bounded(root, path)
            require(target.is_relative_to(destination), 'REVIEW_OUTPUT_OUTSIDE_DESTINATION')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(body)
        save(destination/'inputs.json', inputs)
        if reviewed['request'] is None:
            result = dict(status='WAITING_REVIEW', reason=reviewed['reason'], account_writes=False, automatic_retry=False)
        else:
            save(destination/'request.json', reviewed['request'])
            request = dict(reviewed['request'], preparation_arguments=arguments)
            window_clock()
            publication = publish(**request)
            window_clock()
            save(destination/'publication.json', publication)
            path = output_directory+'/publication.json'
            result = dict(status='MARKET_PUBLICATION_READY_NOT_ACTIVATED', publication_path=path,
                          publication_sha256=sha256(read(root/path)).hexdigest(),
                          identity_manifest=identity, identity_sha256=pins[identity], account_writes=False)
        check_dependencies()
        window_clock()
        prepared_manifest = json.loads(read(bounded(root, settings['preparation_output'])/'manifest.json'))
        for path, digest in prepared_manifest['source_hashes'].items():
            source(path, digest)
        hashes = dict(dependencies)
        for path in destination.rglob('*'):
            if path.is_file():
                hashes[path.relative_to(root).as_posix()] = sha256(read(bounded(root, path))).hexdigest()
        # Capture/prepare receipts and outputs are dependencies too, including reused stages.
        for name in ('capture', 'prepare'):
            receipt_path = bounded(root, config['stage_directory'])/(name+'.complete.json')
            receipt = json.loads(read(receipt_path))
            hashes[receipt_path.relative_to(root).as_posix()] = sha256(read(receipt_path)).hexdigest()
            for path, digest in receipt['output_hashes'].items():
                relative = bounded(root, path).relative_to(root).as_posix()
                read(root/relative, digest)
                hashes[relative] = digest
        save(destination/'complete.json', dict(binding=binding, result=result, output_hashes=hashes, at=window_clock().isoformat()))
        return result
    except BaseException as error:
        save(destination/'failed.json', dict(binding=binding, reason=safe_reason(error), automatic_retry=False))
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('coordinator-config','coordinator-sha256','bootstrap-config','bootstrap-sha256','policy-path','policy-sha256','output-directory'):
        parser.add_argument('--'+field, required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception as error:
        result = dict(status='BLOCKED', reason=safe_reason(error), account_writes=False, automatic_retry=False)
    print(json.dumps(result))
    return 2 if result['status']=='BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
