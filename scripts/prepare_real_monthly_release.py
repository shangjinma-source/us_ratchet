"""Prepare a create-only monthly candidate package; never activate a service."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import os

from core.strategy_account_ledger import canonical, require
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.strategy_account_runtime_archive import _document, _archive_configurations
from data.strategy_account_monthly_release import resolve_monthly_runtime


def _safe(root, relative):
    CurrentQuantityV2CurrentCashSources._path(relative)
    path = root/relative
    for item in (path, *path.parents):
        require(not item.is_symlink() and not (item.exists() and
                getattr(item.lstat(), 'st_file_attributes', 0) & 0x400), 'PREPARE_LINK_REFUSED')
    return path


def _read(root, path, digest):
    import re
    require(type(digest) is str and re.fullmatch('[a-f0-9]{64}',digest), 'PREPARE_HASH_REQUIRED')
    with _safe(root,path).open('rb') as stream:
        raw = stream.read(1024*1024+1)
    require(len(raw)<=1024*1024 and sha256(raw).hexdigest()==digest, 'PREPARE_SOURCE_CHANGED')
    return _document(raw)


def prepare(*, root, registry_path, registry_sha256, archive_path, archive_sha256,
            new_entry, output_directory, account_state=None, clock=None):
    """Consume explicit approvals. Clock injection is for deterministic tests.

    Production callers use the real UTC clock; no command-line date override is
    supplied. Source/runtime approvals are preserved, never generated here.
    """
    root = Path(root).absolute()
    output = _safe(root, output_directory)
    require(output.parent.is_dir() and not output.exists(), 'PREPARE_OUTPUT_CONFLICT')
    now = (clock or (lambda:datetime.now(timezone.utc)))()
    require(isinstance(now,datetime) and now.utcoffset() is not None, 'AWARE_SERVER_CLOCK_REQUIRED')
    account_state = deepcopy(account_state)
    registry = _read(root,registry_path,registry_sha256)
    archive = _read(root,archive_path,archive_sha256)
    require(type(registry) is dict and set(registry)=={'schema','entries'}
            and registry['schema']=='REAL_STRATEGY_MONTHLY_RELEASES_V1'
            and type(registry['entries']) is list, 'INVALID_REAL_MONTHLY_REGISTRY')
    old_configs = _archive_configurations(root=root,archive_path=archive_path,archive_sha256=archive_sha256)
    entry = deepcopy(new_entry)
    require(type(entry) is dict and type(entry.get('target_month')) is str, 'INVALID_RELEASE_ENTRY')
    same = [row for row in registry['entries'] if row.get('target_month')==entry['target_month']]
    require(not same or (len(same)==1 and same[0]==entry), 'PREPARE_MONTH_CONFLICT')
    if not same:
        registry['entries'].append(entry)
    # Resolver performs complete current-month, opening-time, source and identity
    # validation. The temporary candidate is inside root for its path contract.
    with TemporaryDirectory(prefix='prepare-monthly-',dir=root) as directory:
        stage = Path(directory)
        candidate = stage/'registry.json'
        raw = canonical(registry)
        candidate.write_bytes(raw)
        config = resolve_monthly_runtime(root=root,registry_path=candidate.relative_to(root).as_posix(),
            registry_sha256=sha256(raw).hexdigest(),clock=lambda:now,account_state=deepcopy(account_state))
        require(config['target_month']==entry['target_month'], 'PREPARE_NOT_CURRENT_RELEASE')
        matching = [value for value in old_configs if value==config]
        require(len(matching)<=1, 'PREPARE_DUPLICATE_CONFIGURATION')
        config_raw = canonical(config)
        if not matching:
            archive['entries'].append(dict(configuration_path=(Path(output_directory)/'runtime.json').as_posix(),
                configuration_sha256=sha256(config_raw).hexdigest()))
        require(len(archive['entries'])<=100, 'PREPARE_ARCHIVE_BUDGET')
        package = stage/'package'
        package.mkdir()
        documents = {'registry.json':raw,'runtime.json':config_raw,'archive.json':canonical(archive)}
        receipt = dict(status='PREPARED_NOT_ACTIVATED',target_month=config['target_month'],
            prepared_at=now.isoformat(),source_registry_sha256=registry_sha256,
            source_archive_sha256=archive_sha256,account_writes=False,service_activated=False,
            account_id=account_state['account_id'] if account_state is not None else None,
            account_revision=account_state['revision'] if account_state is not None else None,
            account_identity_coverage_checked=account_state is not None,
            candidate_only=True,
            limitations=['Publication validation and optional real-account identity coverage only.',
                'Simulation account reviews are not real-account reviews.',
                'No real-account corporate-action review is performed by this bridge.',
                'Source pins are inherited from explicit approvals, not generated as trust.',
                'No live account lock: activation must recheck the account revision and identity coverage.',
                'Current holding/order unit changes and execution remain subject to runtime checks.',
                'This candidate does not activate a deployment descriptor.'],
            files={name:sha256(value).hexdigest() for name,value in documents.items()})
        for name,value in {**documents,'receipt.json':canonical(receipt)}.items():
            with (package/name).open('xb') as stream:
                stream.write(value);stream.flush();os.fsync(stream.fileno())
        # Recheck old evidence and destination immediately before publication.
        _read(root,registry_path,registry_sha256)
        _read(root,archive_path,archive_sha256)
        _safe(root,output_directory)
        require(not output.exists(), 'PREPARE_OUTPUT_CONFLICT')
        # Windows rename refuses an existing destination; no replacement API.
        require(os.name=='nt', 'PREPARE_ATOMIC_PUBLICATION_PLATFORM_REQUIRED')
        os.rename(package,output)
    return receipt
