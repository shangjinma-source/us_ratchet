"""Read-only lookup of an archived runtime configuration bound to a saved target.

This is not current-month publication selection or runtime admission. A caller
must still build/validate the returned runtime before execution.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re

from core.strategy_account_ledger import canonical, require
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_runtime_archive import _configuration as original_configuration


def _document(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'ARCHIVE_DUPLICATE_JSON_FIELD')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('ARCHIVE_INVALID_JSON')))


def _digest(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value), 'ARCHIVE_HASH_REQUIRED')


def _configuration(value):
    if value.get('schema')=='REAL_STRATEGY_RUNTIME_V1':return original_configuration(value)
    fields = {'schema', 'target_month', 'training_manifest', 'training_sha256',
              'training_closed_at', 'identity_manifest', 'identity_sha256', 'runtime_pins','selector_profile'}
    require(type(value) is dict and set(value) == fields
            and value['schema'] == 'REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1' and value['selector_profile']==PROFILE_ID, 'ARCHIVE_CONFIGURATION_FIELDS')
    require(type(value['target_month']) is str
            and re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value['target_month']), 'ARCHIVE_MONTH_REQUIRED')
    for name in ('training_manifest', 'identity_manifest'):
        CurrentQuantityV2CurrentCashSources._path(value[name])
    for name in ('training_sha256', 'identity_sha256'):
        _digest(value[name])
    require(type(value['training_closed_at']) is str, 'ARCHIVE_TRAINING_CLOCK_REQUIRED')
    closed = datetime.fromisoformat(value['training_closed_at'])
    require(closed.utcoffset() is not None, 'ARCHIVE_TRAINING_CLOCK_REQUIRED')
    pins = value['runtime_pins']
    require(type(pins) is dict and RUNTIME_PATHS <= set(pins) and len(pins) <= 2000,
            'ARCHIVE_RUNTIME_PINS_REQUIRED')
    for path, digest in pins.items():
        CurrentQuantityV2CurrentCashSources._path(path)
        _digest(digest)
    return value


def _archive_configurations(*, root, archive_path, archive_sha256):
    root = Path(root).resolve()
    reader = MonthlyFileConfiguration(root=root, path=archive_path,
                                      sha256_value=archive_sha256, clock=None)
    def read(path, digest):
        CurrentQuantityV2CurrentCashSources._path(path)
        location = root/path
        require(not any(item.is_symlink() or (item.exists() and
                    getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)
                    for item in [location, *location.parents]), 'ARCHIVE_LINK_REFUSED')
        return _document(reader._read(path, digest, 1024*1024))
    archive = read(archive_path, archive_sha256)
    require(type(archive) is dict and set(archive) == {'schema', 'entries'}
            and archive['schema'] == 'PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1'
            and type(archive['entries']) is list and len(archive['entries']) <= 100,
            'INVALID_RUNTIME_ARCHIVE')
    configurations = []
    for entry in archive['entries']:
        require(type(entry) is dict and set(entry) == {'configuration_path', 'configuration_sha256'},
                'INVALID_RUNTIME_ARCHIVE_ENTRY')
        configurations.append(_configuration(read(entry['configuration_path'], entry['configuration_sha256'])))
    return configurations


def require_archived_configuration(*, root, archive_path, archive_sha256, configuration):
    """Admit a selected publication only when its exact configuration is archived."""
    _configuration(configuration)
    matches = [value for value in _archive_configurations(root=root, archive_path=archive_path,
        archive_sha256=archive_sha256) if value == configuration]
    require(len(matches) == 1, 'RELEASE_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE')
    return deepcopy(matches[0])


def configuration_for_target(*, root, archive_path, archive_sha256, target):
    """Match exactly one approved archived configuration; never use newest month."""
    require(type(target) is dict and type(target.get('payload')) is dict, 'ARCHIVE_TARGET_REQUIRED')
    payload = target['payload']
    require(payload.get('schema') == 'REAL_STRATEGY_MONTHLY_TARGET_V1'
            and sha256(canonical(payload)).hexdigest() == target.get('target_id'), 'TARGET_HASH_MISMATCH')
    decision = payload['decision']
    require(sha256(canonical(decision['payload'])).hexdigest() == decision['decision_id'],
            'TARGET_DECISION_MISMATCH')
    binding = decision['payload']['input_binding']
    require(sha256(canonical(binding)).hexdigest() == decision['payload']['input_id'],
            'TARGET_INPUT_MISMATCH')
    manifest = binding['documents']['training_manifest']
    training_hash = binding['source_hashes'][manifest]
    CurrentQuantityV2CurrentCashSources._path(manifest)
    _digest(training_hash)
    matches = []
    for configuration in _archive_configurations(root=root, archive_path=archive_path,
                                                  archive_sha256=archive_sha256):
        if (configuration.get('selector_profile') == binding.get('selector_profile')
                and configuration['target_month'] == payload['target_month']
                and configuration['training_manifest'] == manifest
                and configuration['training_sha256'] == training_hash
                and binding['source_hashes'].get(configuration['identity_manifest'])
                    == configuration['identity_sha256']
                and configuration['runtime_pins'] == payload['runtime_pins']):
            matches.append(configuration)
    require(len(matches) == 1, 'TARGET_RUNTIME_ARCHIVE_NOT_UNIQUE_OR_UNAVAILABLE')
    return deepcopy(matches[0])
