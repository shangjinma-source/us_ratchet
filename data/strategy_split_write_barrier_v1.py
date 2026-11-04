"""Unmounted short-lived write barrier for existing split transition sources.

This blocks SQLite writers only while held. It does not activate anything or
retire old processes; callers still need verified bindings and a routing switch.
Never perform network/model work while holding this barrier.
"""
from contextlib import contextmanager, ExitStack, closing
from pathlib import Path
import os
import sqlite3
from core.strategy_account_ledger import require
from data.strategy_account_split_migration_v1 import checked_path


@contextmanager
def freeze_split_sources(*, paths, timeout=1.0):
    require(type(paths) is dict and set(paths) == {'account','target','risk'}, 'SPLIT_BARRIER_DOMAIN')
    require(type(timeout) in (int,float) and 0 <= timeout <= 5, 'SPLIT_BARRIER_TIMEOUT')
    files = {name:checked_path(value) for name,value in paths.items()}
    require(all(path.is_file() for path in files.values()), 'SPLIT_BARRIER_EXISTING_FILES_REQUIRED')
    identities = {name:(path.stat().st_dev,path.stat().st_ino) for name,path in files.items()}
    require(len(set(identities.values())) == 3, 'SPLIT_BARRIER_DATABASE_ALIAS')
    # Stable acquisition order across all cooperating transition attempts.
    ordered = sorted(files, key=lambda name:os.path.normcase(str(files[name])))
    with ExitStack() as stack:
        for name in ordered:
            path=files[name]
            for suffix in ('-wal','-shm','-journal'):
                checked_path(Path(str(path)+suffix))
            connection=stack.enter_context(closing(sqlite3.connect(
                path.as_uri()+'?mode=rw',uri=True,timeout=timeout,isolation_level=None)))
            stack.callback(connection.rollback)
            connection.execute('BEGIN IMMEDIATE')
            require((path.stat().st_dev,path.stat().st_ino)==identities[name], 'SPLIT_BARRIER_FILE_CHANGED')
        # Reserved locks allow normal readers; all three source writers are blocked.
        yield dict(files)
        for name,path in files.items():
            checked_path(path)
            require((path.stat().st_dev,path.stat().st_ino)==identities[name], 'SPLIT_BARRIER_FILE_CHANGED')
