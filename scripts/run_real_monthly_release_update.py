"""Review and adopt a completed market package; no account or target writes."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os

from core.strategy_account_ledger import canonical, require
from data.strategy_account_release_activation import MonthlyReleaseActivation, SNAPSHOT_FIELDS
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from scripts.prepare_real_monthly_release import _read, _safe
from scripts.review_prepare_real_monthly_release import run as review
from scripts.build_real_monthly_release_entry import build


def run(*, root, complete_path, complete_sha256, descriptor_path, descriptor_sha256,
        output_directory, execute=False, clock=None, market_capture=None, action_capture=None):
    from api.strategy_rolling_composition import ROLLING_SOURCE_PATHS
    root = Path(root).absolute()
    clock = clock or (lambda: datetime.now(timezone.utc))
    entry = build(root=root, complete_path=complete_path, complete_sha256=complete_sha256,
                  descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256)
    descriptor = _read(root, descriptor_path, descriptor_sha256)
    require(ROLLING_SOURCE_PATHS <= set(descriptor['source_pins']), 'ROLLING_DEPLOYMENT_SCOPE_REQUIRED')
    gate = bind_dynamic_source_gate(root=root, source_pins=descriptor['source_pins'])
    activation = MonthlyReleaseActivation(root=root,
        initial_snapshot={key: descriptor[key] for key in SNAPSHOT_FIELDS}, validate_code=gate, clock=clock)
    snapshot = activation.snapshot()
    now = clock()
    require(isinstance(now, datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    publication = _read(root, entry['publication_path'], entry['publication_sha256'])
    market_config = _read(root, publication['config_path'], publication['config_sha256'])
    market = next(row for row in market_config['market_entries'] if row['target_month'] == entry['target_month'])
    calendar = _read(root, market['calendar_path'], market['source_hashes'][market['calendar_path']])
    opening = datetime.fromisoformat(calendar['active_open_at'])
    require(opening.utcoffset() is not None, 'UPDATE_OPENING_TIME_REQUIRED')
    output = _safe(root, output_directory)
    require(output.parent.is_dir(), 'UPDATE_PARENT_REQUIRED')
    binding = dict(complete_path=complete_path, complete_sha256=complete_sha256,
                   descriptor_path=descriptor_path, descriptor_sha256=descriptor_sha256,
                   output_directory=output_directory)
    ready_path = (Path(output_directory)/'review/ready.json').as_posix()
    # Saved attempts are reconciled, never silently recreated after interruption.
    started = None
    if output.exists():
        require((output/'started.json').is_file(), 'UPDATE_PARTIAL_REQUIRES_REVIEW')
        raw = (output/'started.json').read_bytes()
        started = _read(root, output_directory+'/started.json', sha256(raw).hexdigest())
        require(started['binding'] == binding, 'UPDATE_INPUT_CHANGED')
        require(not (output/'failed.json').exists() and _safe(root, ready_path).is_file(),
                'UPDATE_PARTIAL_REQUIRES_REVIEW')
    if not execute:
        return dict(status='PREFLIGHT_ONLY', target_month=entry['target_month'],
                    release_revision=snapshot['revision'], ready_receipt_exists=started is not None,
                    ready_after_open=now >= opening, account_writes=False, target_created=False, http_calls=0)
    if started is None:
        if now < opening:
            return dict(status='WAITING_MARKET_OPEN', account_writes=False, http_calls=0)
        require(now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m') == entry['target_month'],
                'UPDATE_NOT_CURRENT_MONTH')
        output.mkdir(exist_ok=False)
        def save(name, value):
            with (output/name).open('xb') as stream:
                stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        save('started.json', dict(binding=binding, snapshot=snapshot, started_at=now.isoformat()))
        try:
            review(root=root, **{key:snapshot[key] for key in SNAPSHOT_FIELDS}, new_entry=entry,
                   output_directory=(Path(output_directory)/'review').as_posix(), clock=clock,
                   market_capture=market_capture, action_capture=action_capture)
            gate()
        except Exception:
            save('failed.json', dict(status='BLOCKED', reason='UPDATE_REVIEW_FAILED', automatic_retry=False))
            raise
    else:
        snapshot = started['snapshot']
    # Activation validates the receipt, account revision and old history again.
    # An interrupted successful adoption is safe to reconcile via its exact receipt.
    raw = _safe(root, ready_path).read_bytes()
    ready = _read(root, ready_path, sha256(raw).hexdigest())
    registry_binding = ready['files']['registry']
    registry = _read(root, registry_binding['path'], registry_binding['sha256'])
    require([row for row in registry['entries'] if row['target_month'] == entry['target_month']] == [entry],
            'UPDATE_READY_ENTRY_MISMATCH')
    result = activation.adopt(receipt_path=ready_path, receipt_sha256=sha256(raw).hexdigest(),
                              expected_release_revision=snapshot['revision'])
    gate()
    return dict(status='MONTHLY_DATA_RELEASE_ADOPTED', target_month=result['payload']['target_month'],
                release_revision=result['revision'], account_writes=False, target_created=False,
                orders_created=False)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'complete-path', 'complete-sha256', 'descriptor-path', 'descriptor-sha256', 'output-directory'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--execute', action='store_true')
    try:
        result = run(**vars(parser.parse_args(argv)))
    except Exception:
        result = dict(status='BLOCKED', reason='MONTHLY_UPDATE_REJECTED',
                      reconcile_release_before_retry=True, account_writes=False, orders_created=False)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result['status'] == 'BLOCKED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
