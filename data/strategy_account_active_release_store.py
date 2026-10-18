"""Durable pointer journal for caller-validated monthly release snapshots.

This primitive does not validate candidate contents, account revisions, clocks,
or admission. The caller must do those checks before adoption and again before
use. It never changes the actual account, monthly targets, or production router.
"""
from contextlib import closing
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from core.strategy_account_ledger import canonical, require
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources


class ActiveMonthlyReleaseStore:
    def __init__(self, *, root):
        self.root = Path(root).absolute()
        self.path = self.root/'data'/'strategy_account'/'active_monthly_releases.sqlite3'
        self._safe_storage()

    def _safe_storage(self):
        require(not any(item.is_symlink() or (item.exists() and
                    getattr(item.lstat(), 'st_file_attributes', 0) & 0x400)
                    for item in [self.path, *self.path.parents]), 'ACTIVE_RELEASE_LINK_REFUSED')

    @staticmethod
    def _validate(payload):
        fields = {'registry_path', 'registry_sha256', 'archive_path', 'archive_sha256',
                  'ready_path', 'ready_sha256', 'target_month', 'account_revision', 'adopted_at'}
        require(type(payload) is dict and set(payload) == fields, 'ACTIVE_RELEASE_FIELDS')
        for name in ('registry_path', 'archive_path', 'ready_path'):
            CurrentQuantityV2CurrentCashSources._path(payload[name])
            require(len(payload[name]) <= 1024, 'ACTIVE_RELEASE_PATH_LENGTH')
        for name in ('registry_sha256', 'archive_sha256', 'ready_sha256', 'account_revision'):
            require(type(payload[name]) is str and re.fullmatch('[a-f0-9]{64}', payload[name]),
                    'ACTIVE_RELEASE_HASH_REQUIRED')
        require(type(payload['target_month']) is str and
                re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', payload['target_month']),
                'ACTIVE_RELEASE_MONTH_REQUIRED')
        require(type(payload['adopted_at']) is str and len(payload['adopted_at']) <= 64,
                'ACTIVE_RELEASE_CLOCK_REQUIRED')
        require(datetime.fromisoformat(payload['adopted_at']).utcoffset() is not None,
                'ACTIVE_RELEASE_CLOCK_REQUIRED')

    def _initialize(self):
        self._safe_storage()
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._safe_storage()
        descriptor, name = tempfile.mkstemp(prefix='.active-release-', suffix='.sqlite3', dir=self.path.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as connection:
                connection.execute('CREATE TABLE releases(revision INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
                connection.commit()
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            try:
                os.link(temporary, self.path)
            except FileExistsError:
                pass
        finally:
            temporary.unlink(missing_ok=True)

    def _connect(self, write=False):
        self._safe_storage()
        if write:
            self._initialize()
        self._safe_storage()
        return sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),
                               uri=True, isolation_level=None, timeout=10)

    def _rows(self, connection):
        require({row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                == {'releases'}, 'ACTIVE_RELEASE_DATABASE_SCHEMA')
        require([(row[1],row[2],row[3],row[5]) for row in connection.execute('PRAGMA table_info(releases)')]
                == [('revision','INTEGER',0,1),('payload','TEXT',1,0)]
                and not connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone(),
                'ACTIVE_RELEASE_DATABASE_SCHEMA')
        count, size = connection.execute('SELECT COUNT(*), COALESCE(SUM(LENGTH(CAST(payload AS BLOB))),0) FROM releases').fetchone()
        require(count <= 1000 and size <= 8*1024*1024, 'ACTIVE_RELEASE_HISTORY_BUDGET')
        result = []
        receipts = set()
        for revision, raw in connection.execute('SELECT revision,payload FROM releases ORDER BY revision'):
            value = json.loads(raw)
            require(type(value) is dict and set(value) == {'revision','previous_revision','payload'}
                    and canonical(value).decode() == raw, 'ACTIVE_RELEASE_NONCANONICAL')
            require(type(value['revision']) is int and type(value['previous_revision']) is int
                    and value['revision'] == revision == len(result)+1
                    and value['previous_revision'] == len(result), 'ACTIVE_RELEASE_CHAIN')
            self._validate(value['payload'])
            receipt = value['payload']['ready_sha256']
            require(receipt not in receipts, 'ACTIVE_RELEASE_DUPLICATE_RECEIPT')
            receipts.add(receipt)
            result.append(value)
        return result

    def current(self):
        """Return the latest snapshot or None; an empty read creates no files."""
        self._safe_storage()
        if not self.path.exists():
            return None
        with closing(self._connect()) as connection:
            connection.execute('BEGIN')
            rows = self._rows(connection)
        return rows[-1] if rows else None

    def adopt(self, payload, *, expected_revision):
        """CAS append; exact receipt retries return their original record.

        Idempotence is evaluated before CAS. A historical retry does not move
        the pointer backwards; call current() to obtain the active snapshot.
        """
        payload = deepcopy(payload)
        self._validate(payload)
        require(type(expected_revision) is int and expected_revision >= 0, 'ACTIVE_RELEASE_EXPECTED_REVISION')
        with closing(self._connect(write=True)) as connection:
            try:
                connection.execute('BEGIN IMMEDIATE')
                rows = self._rows(connection)
                for old in rows:
                    if old['payload']['ready_sha256'] == payload['ready_sha256']:
                        require(old['payload'] == payload, 'ACTIVE_RELEASE_RECEIPT_CONFLICT')
                        connection.rollback()
                        return old
                require(expected_revision == len(rows), 'ACTIVE_RELEASE_STALE_REVISION')
                require(len(rows) < 1000, 'ACTIVE_RELEASE_HISTORY_BUDGET')
                value = dict(revision=len(rows)+1, previous_revision=len(rows), payload=payload)
                raw = canonical(value).decode()
                require(sum(len(canonical(row)) for row in rows)+len(raw.encode()) <= 8*1024*1024,
                        'ACTIVE_RELEASE_HISTORY_BUDGET')
                connection.execute('INSERT INTO releases VALUES (?,?)', (value['revision'], raw))
                connection.commit()
                return value
            except BaseException:
                connection.rollback()
                raise
