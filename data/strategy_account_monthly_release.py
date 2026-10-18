"""Read an explicitly pinned monthly publication into real-account runtime inputs.

No activation, account IO, fetching or optimization. Publication receipts are
reviewed deployment inputs, not cryptographic proof of independent review.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_account_ledger import require, replay
from data.current_quantity_v2_difference_plan import stamp
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_runtime import RUNTIME_PATHS


RELEASE_PATHS = RUNTIME_PATHS | {
    'data/strategy_account_monthly_release.py',
    'data/current_quantity_v2_monthly_composition.py',
}


def validate_account_identity_coverage(root, configuration, state):
    """Check carried positions/orders against new identities without pool membership.

    Input is the complete replayable ledger, never a frontend account summary.
    PinnedStrategyIdentity performs bounded, hash-verified local evidence reads.
    """
    require(replay(state['account_id'], [event['payload'] for event in state['events']]) == state,
            'ACCOUNT_REPLAY_MISMATCH')
    needed = {sid for sid, quantity in state['shares'].items() if quantity > 0}
    needed.update(order['security_id'] for order in state['orders'].values()
                  if order['status'] == 'OPEN' and order['remaining_quantity'] > 0)
    require(len(needed) <= 250, 'TOTAL_SECURITY_DOMAIN_TOO_LARGE')
    tickers = {}
    for event in state['events']:
        evidence = event['payload'].get('identity_evidence')
        if evidence and evidence['security_id'] in needed:
            sid = evidence['security_id']
            require(sid not in tickers or tickers[sid] == evidence['ticker'],
                    'RECORDED_TICKER_CONFLICT')
            tickers[sid] = evidence['ticker']
    require(set(tickers) == needed, 'HELD_OR_PENDING_IDENTITY_MISSING')
    require(len(set(tickers.values())) == len(tickers), 'DUPLICATE_TICKER_MAPPING')
    identity = PinnedStrategyIdentity(root, configuration['identity_manifest'],
                                      configuration['identity_sha256'])
    verified = {}
    for sid, ticker in sorted(tickers.items()):
        evidence = identity(ticker)
        require(evidence['security_id'] == sid and evidence['ticker'] == ticker,
                'IDENTITY_MAPPING_CHANGED')
        verified[sid] = evidence
    return dict(account_id=state['account_id'], account_revision=state['revision'],
                identities=verified)


def resolve_monthly_runtime(*, root, registry_path, registry_sha256, clock=None,
                            account_state=None):
    """Resolve only the current New York month from a server-owned registry."""
    root = Path(root).resolve()
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    require(isinstance(now, datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    month = now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
    reader = MonthlyFileConfiguration(root=root, path=registry_path,
                                      sha256_value=registry_sha256, clock=lambda: now)

    def read(path, digest, limit=32*1024*1024):
        # The underlying reader enforces relative paths, bounds and byte hashes.
        target = root/path
        require(not any(p.is_symlink() for p in [target, *target.parents]), 'RELEASE_SYMLINK_REFUSED')
        return reader._read(path, digest, limit)

    registry = json.loads(read(registry_path, registry_sha256, 1024*1024))
    require(type(registry) is dict and set(registry) == {'schema', 'entries'}
            and registry['schema'] == 'REAL_STRATEGY_MONTHLY_RELEASES_V1'
            and type(registry['entries']) is list and len(registry['entries']) <= 100,
            'INVALID_REAL_MONTHLY_REGISTRY')
    fields = {'target_month', 'publication_path', 'publication_sha256',
              'identity_manifest', 'identity_sha256', 'runtime_pins'}
    entries = registry['entries']
    import re
    require(all(type(row) is dict and set(row) == fields
                and type(row['target_month']) is str
                and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', row['target_month']) for row in entries),
            'INVALID_REAL_MONTHLY_REGISTRY')
    require(len({row['target_month'] for row in entries}) == len(entries), 'DUPLICATE_RELEASE_MONTH')
    matching = [row for row in entries if row['target_month'] == month]
    require(len(matching) == 1, 'CURRENT_MONTH_RELEASE_REQUIRED')
    row = matching[0]
    receipt = json.loads(read(row['publication_path'], row['publication_sha256'], 1024*1024))
    require(type(receipt) is dict
            and receipt.get('status') == 'PUBLISHED_CONDITIONAL_NOT_ACTIVATED'
            and receipt.get('compiler_status') == 'READY_CONDITIONAL'
            and receipt.get('account_writes') is False and receipt.get('service_activated') is False
            and type(receipt.get('search_calls')) is int and receipt['search_calls'] == 0,
            'COMPLETED_PUBLICATION_REQUIRED')
    published = stamp(receipt['published_at'])
    require(published <= now, 'FUTURE_PUBLICATION_REFUSED')
    read(receipt['config_path'], receipt['config_sha256'], 1024*1024)
    published_reader = MonthlyFileConfiguration(root=root, path=receipt['config_path'],
        sha256_value=receipt['config_sha256'], clock=lambda: now)
    supplied = published_reader.market_reader(None)
    package = supplied['source_package']
    for path, digest in package['source_hashes'].items():
        read(path, digest)
    compiled = compile_saved_training(package, supplied['manifest_path'])
    manifest = json.loads(package['files'][supplied['manifest_path']])
    calendar = json.loads(package['files'][supplied['calendar_path']])
    close, opening = stamp(calendar['decision_close_at']), stamp(calendar['active_open_at'])
    require(calendar['target_month'] == month == calendar['active_date'][:7]
            and calendar['decision_date'] == manifest['decision_date']
            == close.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            and opening.astimezone(ZoneInfo('America/New_York')).date().isoformat() == calendar['active_date']
            and calendar['decision_date'][:7] < month
            and close <= published <= now and close < opening <= now,
            'RELEASE_DECISION_BOUNDARY_INVALID')
    identity_raw = read(row['identity_manifest'], row['identity_sha256'])
    identity_doc = json.loads(identity_raw)
    identity = PinnedStrategyIdentity(root, row['identity_manifest'], row['identity_sha256'])
    published_identities = json.loads(package['files'][supplied['identities_path']])['securities']
    for candidate in manifest['candidates']:
        sid = candidate.get('security_id')
        if sid not in compiled['input']['search_arguments']['prices']:
            continue
        verified = identity(candidate['ticker'])
        for path, digest in verified['source_hashes'].items():
            read(path, digest)
        rows = [item for item in identity_doc['candidates'] if item.get('ticker') == candidate['ticker']]
        require(verified['security_id'] == sid and len(rows) == 1
                and rows[0].get('issuer_id') == candidate['issuer_id']
                and published_identities.get(sid, {}).get('ticker') == candidate['ticker']
                and published_identities[sid].get('issuer_id') == candidate['issuer_id'],
                'RELEASE_IDENTITY_BINDING_MISMATCH')
    pins = row['runtime_pins']
    require(type(pins) is dict and RELEASE_PATHS <= set(pins), 'RELEASE_RUNTIME_PINS_REQUIRED')
    executing_root = Path(__file__).resolve().parents[1]
    from hashlib import sha256
    for path, digest in pins.items():
        read(path, digest)
        if path in RELEASE_PATHS:
            require(sha256((executing_root/path).read_bytes()).hexdigest() == digest,
                    'EXECUTING_COMPOSITION_SOURCE_CHANGED')
    configuration = dict(schema='REAL_STRATEGY_RUNTIME_V1', target_month=month,
        training_manifest=supplied['manifest_path'],
        training_sha256=package['source_hashes'][supplied['manifest_path']],
        training_closed_at=calendar['decision_close_at'], identity_manifest=row['identity_manifest'],
        identity_sha256=row['identity_sha256'], runtime_pins=deepcopy(pins))

    if account_state is not None:
        validate_account_identity_coverage(root, configuration, account_state)
    return configuration
