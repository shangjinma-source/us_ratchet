"""Default-off, isolated research archive for one saved frontier proposal.

Exact source bytes are checked against the original saved hashes, not certified
as authentic financial evidence. No runtime registration or account operations.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
from uuid import uuid4

from core.saved_monthly_frontier_proposal import build_frontier_proposal
from core.strategy_account_ledger import canonical, require
from data.strategy_daily_session_capture import reject_links


SCHEMA = 'ISOLATED_SAVED_FRONTIER_ARCHIVE_V1'
MAXIMUM_FILE_BYTES = 32 * 1024 * 1024
MAXIMUM_SOURCE_BYTES = 128 * 1024 * 1024
MAXIMUM_TOTAL_BYTES = 160 * 1024 * 1024
IMPLEMENTATION_PATHS = (
    'core/saved_monthly_frontier_proposal.py',
    'core/strategy_account_ledger.py',
    'data/strategy_daily_session_capture.py',
    'data/saved_frontier_policy_archive.py',
)


def _identifier(value):
    require(type(value) is str and re.fullmatch('[a-f0-9]{64}', value), 'ARCHIVE_ID_REQUIRED')
    return value


def _research_root(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'ISOLATED_RESEARCH_ROOT_REQUIRED')
    reject_links(path)
    allowed = Path(__file__).resolve().parents[1] / 'tmp'
    require(path.is_dir() and path.resolve().is_relative_to(allowed.resolve())
            and path.resolve() != allowed.resolve(), 'ISOLATED_RESEARCH_ROOT_REQUIRED')
    return path.resolve()


def _read(path, maximum=MAXIMUM_FILE_BYTES):
    reject_links(path)
    require(path.is_file(), 'ARCHIVE_FILE_MISSING')
    before = path.stat()
    require(before.st_size <= min(maximum, MAXIMUM_FILE_BYTES) and before.st_nlink == 1, 'ARCHIVE_FILE_BUDGET_OR_ALIAS')
    signature = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    with path.open('rb') as stream:
        require(signature(os.fstat(stream.fileno())) == signature(before), 'ARCHIVE_READ_RACE')
        raw = stream.read(min(maximum, MAXIMUM_FILE_BYTES) + 1)
        require(signature(os.fstat(stream.fileno())) == signature(before), 'ARCHIVE_READ_RACE')
    reject_links(path)
    require(len(raw) == before.st_size and signature(path.stat()) == signature(before), 'ARCHIVE_READ_RACE')
    return raw


def _document(raw):
    value = json.loads(raw)
    require(canonical(value) == raw, 'ARCHIVE_NONCANONICAL_DOCUMENT')
    return value


def _source_pins(target):
    payload = target['payload']
    maps = (payload['decision']['payload']['input_binding']['source_hashes'], payload['runtime_pins'])
    pins = {}
    aliases = set()
    for mapping in maps:
        require(type(mapping) is dict and bool(mapping), 'ARCHIVE_SOURCE_PINS_REQUIRED')
        for name, digest in mapping.items():
            require(type(name) is str and name and '\\' not in name and ':' not in name
                    and not PurePosixPath(name).is_absolute()
                    and all(part not in ('', '.', '..') for part in name.split('/')), 'ARCHIVE_SOURCE_NAME_INVALID')
            _identifier(digest)
            if name in pins:
                require(pins[name] == digest, 'ARCHIVE_SOURCE_PIN_CONFLICT')
            else:
                require(name.casefold() not in aliases, 'ARCHIVE_SOURCE_NAME_ALIAS')
                aliases.add(name.casefold())
                pins[name] = digest
    require(0 < len(pins) <= 2000, 'ARCHIVE_SOURCE_COUNT_BUDGET')
    return pins


def _expected_files(target, proposal, source_files):
    require(type(source_files) is dict, 'ARCHIVE_COMPLETE_SOURCE_DOMAIN_REQUIRED')
    source_files = source_files.copy()  # Immutable bytes, detached mutable lookup.
    original, proposed = deepcopy(target), deepcopy(proposal)
    require(proposed == build_frontier_proposal(target=original), 'ARCHIVE_PROPOSAL_CHANGED')
    pins = _source_pins(original)
    require(set(source_files) == set(pins), 'ARCHIVE_COMPLETE_SOURCE_DOMAIN_REQUIRED')
    require(all(type(raw) is bytes and len(raw) <= MAXIMUM_FILE_BYTES for raw in source_files.values()),
            'ARCHIVE_SOURCE_BYTES_REQUIRED')
    require(sum(map(len, source_files.values())) <= MAXIMUM_SOURCE_BYTES, 'ARCHIVE_SOURCE_BYTE_BUDGET')
    require(all(sha256(source_files[name]).hexdigest() == digest for name, digest in pins.items()),
            'ARCHIVE_SOURCE_BYTES_CHANGED')
    target_bytes, proposal_bytes = canonical(original), canonical(proposed)
    implementation = {}
    files = {'target.json': target_bytes, 'proposal.json': proposal_bytes}
    for name, digest in pins.items():
        files['sources/' + digest + '.bin'] = source_files[name]
    repository = Path(__file__).resolve().parents[1]
    for name in IMPLEMENTATION_PATHS:
        raw = _read(repository / name)
        digest = sha256(raw).hexdigest()
        implementation[name] = digest
        files['implementation/' + digest + '.bin'] = raw
    receipt = dict(schema=SCHEMA, target_id=original['target_id'], proposal_id=proposed['proposal_id'],
        target_sha256=sha256(target_bytes).hexdigest(), proposal_sha256=sha256(proposal_bytes).hexdigest(),
        source_sha256=pins, implementation_sha256=implementation,
        admission_scope='ISOLATED_RESEARCH_CONTENT_ONLY', source_bytes_verified=True,
        source_authenticity_verified=False, original_runtime_admitted=False, production_admitted=False,
        policy_execution_enabled=False, account_mutated=False, target_mutated=False)
    files['receipt.json'] = canonical(receipt)
    files['complete.json'] = canonical(dict(schema=SCHEMA + '_COMPLETE',
        receipt_sha256=sha256(files['receipt.json']).hexdigest(),
        file_sha256={name: sha256(raw).hexdigest() for name, raw in files.items()}))
    require(all(len(raw) <= MAXIMUM_FILE_BYTES for raw in files.values())
            and sum(map(len, files.values())) <= MAXIMUM_TOTAL_BYTES, 'ARCHIVE_TOTAL_BYTE_BUDGET')
    return files, receipt


def _verify_folder(folder, files):
    reject_links(folder)
    require(folder.is_dir(), 'ARCHIVE_NOT_COMPLETE')
    actual_files, actual_directories = set(), set()
    for path in folder.rglob('*'):
        reject_links(path)
        relative = path.relative_to(folder).as_posix()
        if path.is_dir():
            require(relative in {'sources', 'implementation'}, 'ARCHIVE_UNEXPECTED_DIRECTORY')
            actual_directories.add(relative)
        else:
            require(relative in files, 'ARCHIVE_UNEXPECTED_FILE')
            actual_files.add(relative)
    require(actual_files == set(files) and actual_directories == {'sources', 'implementation'},
            'ARCHIVE_LAYOUT_CHANGED_OR_INCOMPLETE')
    for name, raw in files.items():
        require(_read(folder / name) == raw, 'ARCHIVE_BYTES_CHANGED')


def _result(folder, receipt):
    return dict(status='ISOLATED_RESEARCH_ARCHIVED', archive_path=str(folder),
        target_id=receipt['target_id'], proposal_id=receipt['proposal_id'],
        receipt_sha256=sha256(canonical(receipt)).hexdigest(), source_count=len(receipt['source_sha256']),
        source_bytes_verified=True, source_authenticity_verified=False, original_runtime_admitted=False,
        production_admitted=False, policy_execution_enabled=False, account_mutated=False,
        target_mutated=False, new_searches=0, new_candidate_generation=0)


def read_saved_frontier_policy(*, research_root, target_id):
    """Read only a complete archive; no missing-source or older-target fallback."""
    root = _research_root(research_root)
    folder = root / _identifier(target_id)
    reject_links(folder)
    require(folder.is_dir(), 'ARCHIVE_NOT_COMPLETE')
    target = _document(_read(folder / 'target.json'))
    proposal = _document(_read(folder / 'proposal.json'))
    require(target.get('target_id') == target_id, 'ARCHIVE_TARGET_KEY_CHANGED')
    pins = _source_pins(target)
    source_files, total = {}, 0
    for name, digest in pins.items():
        raw = _read(folder / 'sources' / (digest + '.bin'), maximum=MAXIMUM_SOURCE_BYTES-total)
        total += len(raw)
        require(total <= MAXIMUM_SOURCE_BYTES, 'ARCHIVE_SOURCE_BYTE_BUDGET')
        source_files[name] = raw
    files, receipt = _expected_files(target, proposal, source_files)
    _verify_folder(folder, files)
    return dict(_result(folder, receipt), target=target, proposal=proposal, receipt=receipt)


def _write(path, raw):
    reject_links(path)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def archive_saved_frontier_policy(*, research_root, target, proposal, source_files, enabled=False):
    """Publish once per original target, exclusively inside an explicit tmp child.

    Concurrent writers fail busy rather than replace another writer. Failed
    staging directories remain diagnostic artifacts; readers never accept them.
    Atomic directory publication assumes the local filesystem's rename contract.
    """
    require(type(enabled) is bool, 'ARCHIVE_ENABLED_BOOLEAN_REQUIRED')
    if not enabled:
        return dict(status='ISOLATED_ARCHIVE_DISABLED', archive_created=False,
                    production_admitted=False, policy_execution_enabled=False, account_mutated=False,
                    target_mutated=False, new_searches=0, new_candidate_generation=0)
    root = _research_root(research_root)
    files, receipt = _expected_files(target, proposal, source_files)
    folder = root / _identifier(receipt['target_id'])
    lock = root / ('.lock-' + receipt['target_id'])
    reject_links(lock)
    token = uuid4().hex.encode()
    try:
        _write(lock, token)
    except FileExistsError as error:
        raise ValueError('ARCHIVE_TARGET_BUSY') from error
    try:
        reject_links(root)
        reject_links(folder)
        if folder.exists():
            _verify_folder(folder, files)
            return _result(folder, receipt)
        pending = root / ('.pending-' + uuid4().hex)
        pending.mkdir()
        (pending / 'sources').mkdir()
        (pending / 'implementation').mkdir()
        for name, raw in files.items():
            _write(pending / name, raw)
        _verify_folder(pending, files)
        reject_links(root)
        reject_links(folder)
        require(not folder.exists(), 'ARCHIVE_TARGET_CONFLICT')
        pending.rename(folder)
        _verify_folder(folder, files)
        return _result(folder, receipt)
    finally:
        # Only unlink this invocation's exact lock; never clean other artifacts.
        require(_read(lock) == token, 'ARCHIVE_LOCK_CHANGED')
        lock.unlink()
