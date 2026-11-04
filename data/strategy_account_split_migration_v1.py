"""Prepare a separate split-capable account snapshot; never activate or edit source."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import os
import sqlite3
import tempfile

from core.strategy_account_ledger import require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore, SCHEMA


def checked_path(value):
    path = Path(value).absolute()
    for item in (path, *path.parents):
        require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(),
                'MIGRATION_LINK_REFUSED')
    return path


def prepare_split_account(*, source_path, destination_path, expected_revision):
    source_path, destination_path = map(checked_path, (source_path, destination_path))
    require(source_path.resolve() != destination_path.resolve(), 'MIGRATION_SAME_PATH')
    require(not destination_path.exists(), 'MIGRATION_DESTINATION_EXISTS')
    source = StrategyAccountStore(source_path)
    # The existing parent must be explicit; do not create arbitrary directory trees.
    require(destination_path.parent.is_dir(), 'MIGRATION_DESTINATION_PARENT_MISSING')
    descriptor, temporary_name = tempfile.mkstemp(prefix='.split-prepare-', suffix='.sqlite3',
                                                   dir=destination_path.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with closing(source._connect(True)) as original:
            original.execute('BEGIN')
            try:
                snapshot, _ = source._read(original)
                require(snapshot['revision'] == expected_revision, 'STALE_MIGRATION_SOURCE')
                with closing(sqlite3.connect(temporary)) as copied:
                    original.backup(copied)
            finally:
                original.rollback()
        # Validate the untouched copy with the OLD reader before changing format.
        require(StrategyAccountStore(temporary).read() == snapshot, 'MIGRATION_COPY_MISMATCH')
        with closing(sqlite3.connect(temporary)) as copied:
            copied.execute('UPDATE strategy_meta SET schema=? WHERE singleton=1', (SCHEMA,))
            copied.commit()
        require(SplitStrategyAccountStore(temporary).read() == snapshot, 'MIGRATION_REPLAY_MISMATCH')
        require(source.read() == snapshot, 'MIGRATION_SOURCE_CHANGED')
        with temporary.open('r+b') as stream:
            os.fsync(stream.fileno())
        digest = sha256(temporary.read_bytes()).hexdigest()
        checked_path(destination_path)
        # Atomic publication; existing files, including a concurrent creator, win.
        os.link(temporary, destination_path)
        return dict(status='SPLIT_ACCOUNT_SNAPSHOT_PREPARED_NOT_ACTIVATED',
                    source_revision=snapshot['revision'], account_id=snapshot['account_id'],
                    destination_sha256=digest, event_count=len(snapshot['events']),
                    requires_activation_source_recheck=True, production_activated=False)
    finally:
        temporary.unlink(missing_ok=True)
