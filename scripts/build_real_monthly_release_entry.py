"""Read a pinned market completion into a candidate entry; no activation or writes."""
from copy import deepcopy
import json
from pathlib import Path

from core.strategy_account_ledger import require
from data.current_quantity_v2_difference_plan import stamp
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_monthly_training import compile_saved_training
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_account_monthly_release import RELEASE_PATHS
from scripts.prepare_real_monthly_release import _safe


def build(*, root, complete_path, complete_sha256, descriptor_path, descriptor_sha256):
    """The caller supplies approved hashes. Opening-time admission is left to prepare."""
    root = Path(root).resolve()
    reader = MonthlyFileConfiguration(root=root, path=complete_path,
                                     sha256_value=complete_sha256, clock=None)
    total = 0
    def read(path, digest):
        nonlocal total
        _safe(root, path)
        raw = reader._read(path, digest)
        total += len(raw)
        require(total <= 512 * 1024 * 1024, 'ENTRY_SOURCE_BYTES_LIMIT')
        return raw
    complete = json.loads(read(complete_path, complete_sha256))
    require(type(complete) is dict and set(complete) == {'binding', 'result', 'output_hashes', 'at'},
            'INVALID_MARKET_COMPLETION')
    hashes = complete['output_hashes']
    require(type(hashes) is dict and 0 < len(hashes) <= 10000, 'INVALID_MARKET_COMPLETION')
    for path, digest in hashes.items():
        read(path, digest)
    result = complete['result']
    require(result.get('status') == 'MARKET_PUBLICATION_READY_NOT_ACTIVATED'
            and result.get('account_writes') is False, 'COMPLETED_MARKET_REQUIRED')
    for path_key, hash_key in [('publication_path', 'publication_sha256'),
                               ('identity_manifest', 'identity_sha256')]:
        require(hashes.get(result[path_key]) == result[hash_key], 'MARKET_RESULT_BINDING_MISMATCH')
    destination = complete['binding']['output_directory']
    require(complete_path == destination + '/complete.json'
            and result['publication_path'] == destination + '/publication.json',
            'MARKET_COMPLETION_PATH_MISMATCH')
    publication = json.loads(read(result['publication_path'], result['publication_sha256']))
    require(publication.get('status') == 'PUBLISHED_CONDITIONAL_NOT_ACTIVATED'
            and publication.get('compiler_status') == 'READY_CONDITIONAL'
            and publication.get('account_writes') is False
            and publication.get('service_activated') is False
            and type(publication.get('search_calls')) is int and publication['search_calls'] == 0,
            'COMPLETED_PUBLICATION_REQUIRED')
    require(hashes.get(publication['config_path']) == publication['config_sha256'],
            'PUBLICATION_CONFIGURATION_NOT_PINNED')
    config = json.loads(read(publication['config_path'], publication['config_sha256']))
    rows = config.get('market_entries')
    require(type(rows) is list and len(rows) == 1, 'ONE_MARKET_ENTRY_REQUIRED')
    row = rows[0]
    calendar = json.loads(read(row['calendar_path'], row['source_hashes'][row['calendar_path']]))
    close, opening = stamp(calendar['decision_close_at']), stamp(calendar['active_open_at'])
    require(close <= stamp(publication['published_at']) <= stamp(complete['at']) < opening,
            'MARKET_COMPLETION_WINDOW_INVALID')
    # This is a routing probe only, never a claim that the actual market is open.
    probe = MonthlyFileConfiguration(root=root, path=publication['config_path'],
        sha256_value=publication['config_sha256'], clock=lambda: opening)
    supplied = probe.market_reader(None)
    package = supplied['source_package']
    for path, digest in package['source_hashes'].items():
        require(hashes.get(path) == digest, 'PUBLICATION_SOURCE_NOT_PINNED')
        read(path, digest)
    compiled = compile_saved_training(package, supplied['manifest_path'])
    require(compiled['status'] == 'READY_CONDITIONAL', 'MARKET_COMPILER_NOT_READY')
    manifest = json.loads(package['files'][supplied['manifest_path']])
    published_identities = json.loads(package['files'][supplied['identities_path']])['securities']
    identity_document = json.loads(read(result['identity_manifest'], result['identity_sha256']))
    identity = PinnedStrategyIdentity(root, result['identity_manifest'], result['identity_sha256'])
    for candidate in manifest['candidates']:
        sid = candidate['security_id']
        if sid not in compiled['input']['search_arguments']['prices']:
            continue
        verified = identity(candidate['ticker'])
        identities = [item for item in identity_document['candidates'] if item.get('ticker') == candidate['ticker']]
        require(verified['security_id'] == sid and len(identities) == 1
                and identities[0]['issuer_id'] == candidate['issuer_id']
                and published_identities.get(sid, {}).get('ticker') == candidate['ticker']
                and published_identities[sid]['issuer_id'] == candidate['issuer_id'],
                'MARKET_IDENTITY_BINDING_MISMATCH')
        for path, digest in verified['source_hashes'].items():
            require(hashes.get(path) == digest, 'IDENTITY_SOURCE_NOT_PINNED')
            read(path, digest)
    descriptor = json.loads(read(descriptor_path, descriptor_sha256))
    approved = descriptor.get('source_pins')
    require(type(approved) is dict and RELEASE_PATHS <= set(approved), 'APPROVED_RUNTIME_PINS_REQUIRED')
    pins = {path: approved[path] for path in sorted(RELEASE_PATHS)}
    for path, digest in pins.items():
        read(path, digest)
    return dict(target_month=calendar['target_month'], publication_path=result['publication_path'],
                publication_sha256=result['publication_sha256'], identity_manifest=result['identity_manifest'],
                identity_sha256=result['identity_sha256'], runtime_pins=deepcopy(pins))
