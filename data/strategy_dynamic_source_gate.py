"""Verify server-reviewed source pins before/after dynamic HTTP operations.

This read-only gate never creates approval pins, imports replacement sources or
activates deployment. Callers retain a private copy of their approved pin map.
"""
from hashlib import sha256
from pathlib import Path, PurePosixPath
import re

from core.strategy_account_ledger import require
from data.strategy_account_runtime import RUNTIME_PATHS


DYNAMIC_SOURCE_PATHS = frozenset(RUNTIME_PATHS | {
    'data/strategy_account_monthly_router.py',
    'data/strategy_account_runtime_archive.py',
    'data/strategy_account_monthly_release.py',
    'data/current_quantity_v2_monthly_composition.py',
    'api/strategy_dynamic_monthly_target.py',
    'api/strategy_account_charts.py',
    'api/strategy_account.py',
    'data/strategy_account_archived_holding_charts.py',
    'data/strategy_account_holding_charts.py',
    'data/strategy_monthly_target_charts.py',
    'data/strategy_dynamic_source_gate.py',
})
MAXIMUM_SOURCE_BYTES = 32 * 1024 * 1024


def bind_dynamic_source_gate(*, root, source_pins):
    """Freeze explicit approvals at composition time; recheck on every call."""
    require(type(source_pins) is dict, 'DYNAMIC_SOURCE_SCOPE_REQUIRED')
    pins = dict(source_pins)
    approved_root = Path(root).absolute()

    def validate():
        validate_dynamic_sources(root=approved_root, source_pins=pins)

    validate()
    return validate


def _executing_root():
    return Path(__file__).absolute().parents[1]


def _hash_file(path):
    for item in (path, *path.parents):
        require(not item.is_symlink() and not (item.exists() and
                getattr(item.lstat(), 'st_file_attributes', 0) & 0x400),
                'DYNAMIC_SOURCE_LINK_REFUSED')
    require(path.is_file(), 'DYNAMIC_SOURCE_MISSING')
    with path.open('rb') as stream:
        raw = stream.read(MAXIMUM_SOURCE_BYTES + 1)
    require(len(raw) <= MAXIMUM_SOURCE_BYTES, 'DYNAMIC_SOURCE_TOO_LARGE')
    return sha256(raw).hexdigest()


def validate_dynamic_sources(*, root, source_pins):
    """Check both data-root files and executing files against explicit approvals.

    The HTTP caller must pass this gate before and after operations; success is
    a bounded source check, not certification of the entire Python import graph.
    """
    require(type(source_pins) is dict and DYNAMIC_SOURCE_PATHS <= set(source_pins)
            and len(source_pins) <= 2000, 'DYNAMIC_SOURCE_SCOPE_REQUIRED')
    pins = dict(source_pins)
    for name, digest in pins.items():
        require(type(name) is str and '\\' not in name and ':' not in name
                and not PurePosixPath(name).is_absolute()
                and all(part not in ('', '.', '..') for part in name.split('/')),
                'DYNAMIC_SOURCE_PATH_INVALID')
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest),
                'DYNAMIC_SOURCE_HASH_REQUIRED')
    # Do not resolve away symlinks/junctions before checking the supplied path.
    data_root = Path(root).absolute()
    executing_root = _executing_root()
    for name, digest in pins.items():
        require(_hash_file(data_root/name) == digest, 'DYNAMIC_SOURCE_CHANGED')
        require(_hash_file(executing_root/name) == digest,
                'DYNAMIC_EXECUTING_SOURCE_CHANGED')
