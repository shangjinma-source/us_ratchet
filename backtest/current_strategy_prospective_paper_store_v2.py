"""Registered paper-only persistence; no registration, fetching or task changes.

Admission loaders belong to the server and must recover independently reviewed
historical evidence. Database request bytes never grant themselves authority.
"""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone, time
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import sqlite3
import stat

from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import require, stamp
from backtest.current_strategy_prospective_paper_book_v2 import (
    _context, _initial, _apply, create_book, transact, digest)

SOURCE = 'backtest/current_strategy_prospective_paper_store_v2.py'
TABLES = {'prospective_header': ['id', 'initial', 'initial_hash', 'count', 'head', 'revision'],
          'prospective_events': ['ordinal', 'operation_id', 'operation', 'previous_hash', 'record_hash']}
MAX_BYTES = 128 * 1024 * 1024


class ProspectivePaperStore:
    def __init__(self, *, root, authority, admission_loader, target_reader,
                 clock=None, timeout_seconds=2, fault=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.authority = deepcopy(authority)
        app = _context(self.authority, self.clock())
        require(SOURCE in app['code_sha256'], 'PROSPECTIVE_STORE_CODE_REQUIRED')
        require(callable(admission_loader) and callable(target_reader), 'PROSPECTIVE_SERVER_LOADERS_REQUIRED')
        require(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 10,
                'PROSPECTIVE_LOCK_TIMEOUT')
        self.root = Path(root).absolute()
        require(self.root.is_dir(), 'PROSPECTIVE_ROOT_REQUIRED')
        self.path = self.root / app['storage']['ledger']
        self.admission_loader = admission_loader
        self.target_reader = target_reader
        self.timeout = timeout_seconds
        self.fault = fault or (lambda phase: None)
        self._paths()

    def _paths(self):
        require(self.path.is_relative_to(self.root), 'PROSPECTIVE_PATH_ESCAPE')
        for item in [self.path.parent, *self.path.parent.parents]:
            if item.exists() or item.is_symlink():
                info = item.lstat()
                require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)()
                        and not (getattr(info, 'st_file_attributes', 0) & 0x400), 'PROSPECTIVE_LINK_PATH')
        identity = None
        for item in [self.path, *[Path(str(self.path)+suffix) for suffix in ('-journal', '-wal', '-shm')]]:
            require(not item.is_symlink(), 'PROSPECTIVE_LINK_PATH')
            if item.exists():
                info = item.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                        not (getattr(info, 'st_file_attributes', 0) & 0x400), 'PROSPECTIVE_LINK_PATH')
                if item == self.path:
                    identity = info.st_dev, info.st_ino
        return identity

    def _identity(self, expected):
        require(expected is not None and self._paths() == expected, 'PROSPECTIVE_DATABASE_REPLACED')

    @staticmethod
    def _schema(connection, create=False):
        objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        require(set(objects) == {(name, 'table') for name in TABLES} or (create and not objects),
                'PROSPECTIVE_WRONG_DATABASE')
        if not objects:
            connection.execute('CREATE TABLE prospective_header(id INTEGER PRIMARY KEY CHECK(id=1), initial TEXT NOT NULL, initial_hash TEXT NOT NULL, count INTEGER NOT NULL, head TEXT NOT NULL, revision TEXT NOT NULL)')
            connection.execute('CREATE TABLE prospective_events(ordinal INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, operation TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)')
        for name, columns in TABLES.items():
            require([row[1] for row in connection.execute('PRAGMA table_info('+name+')')] == columns,
                    'PROSPECTIVE_SCHEMA_CHANGED')
        require(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'PROSPECTIVE_DATABASE_INTEGRITY')

    @contextmanager
    def _write(self, create=False):
        prior = self._paths()
        require(create or self.path.is_file(), 'PROSPECTIVE_DATABASE_MISSING')
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._paths()
        with closing(sqlite3.connect(self.path.as_uri()+('?mode=rwc' if create else '?mode=rw'),
                                     uri=True, timeout=self.timeout, isolation_level=None)) as connection:
            try:
                identity = self._paths()
                require(prior is None or prior == identity, 'PROSPECTIVE_DATABASE_REPLACED')
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN EXCLUSIVE')
                self._identity(identity)
                self._schema(connection, create)
                self.fault('after_begin')
                yield connection, identity
                connection.commit()
                self.fault('after_commit')
            except BaseException:
                connection.rollback()
                raise

    def _admissions(self):
        result = self.admission_loader()
        require(type(result) is dict and set(result) == {'decisions', 'settlements'},
                'PROSPECTIVE_ADMISSION_LOADER')
        return deepcopy(result)

    def _operation_clock(self):
        previous = None
        def sample():
            nonlocal previous
            current = stamp(self.clock())
            require(previous is None or current >= previous, 'PROSPECTIVE_CLOCK_ROLLBACK')
            previous = current
            return current
        return sample

    def _load(self, connection, admissions):
        rows = connection.execute('SELECT initial,initial_hash,count,head,revision FROM prospective_header').fetchall()
        require(len(rows) == 1, 'PROSPECTIVE_HEADER_REQUIRED')
        raw, initial_hash, count, head, revision = rows[0]
        size, actual = connection.execute('SELECT coalesce(sum(length(CAST(operation AS BLOB))),0),count(*) FROM prospective_events').fetchone()
        require(type(count) is int and 0 <= count <= 10000 and count == actual and
                size+len(raw.encode()) <= MAX_BYTES, 'PROSPECTIVE_STORAGE_BUDGET_OR_COUNT')
        initial = json.loads(raw)
        require(canonical(initial).decode() == raw and digest(initial) == initial_hash,
                'PROSPECTIVE_INITIAL_HASH')
        book = _initial(self.authority, initial['initialized_at'])
        require(book == initial, 'PROSPECTIVE_INITIAL_BINDING')
        previous = initial_hash
        for ordinal, oid, encoded, prior, hashed in connection.execute(
                'SELECT ordinal,operation_id,operation,previous_hash,record_hash FROM prospective_events ORDER BY ordinal'):
            operation = json.loads(encoded)
            require(canonical(operation).decode() == encoded and ordinal == len(book['operations'])+1 and
                    operation['request']['operation_id'] == oid and prior == previous and
                    digest(dict(ordinal=ordinal, operation=operation, previous_hash=prior)) == hashed,
                    'PROSPECTIVE_EVENT_CHAIN')
            _apply(book, deepcopy(operation['request']), self.authority, admissions['decisions'], admissions['settlements'])
            require(book['operations'][-1] == operation, 'PROSPECTIVE_EVENT_REPLAY')
            previous = hashed
        require(head == previous and revision == book['revision'], 'PROSPECTIVE_HEAD_CHANGED')
        return book, head

    def initialize(self):
        existed = self.path.exists()
        with self._write(create=True) as (connection, identity):
            clock = self._operation_clock()
            rows = connection.execute('SELECT count(*) FROM prospective_header').fetchone()[0]
            fresh = rows == 0
            if fresh:
                require(not existed, 'PROSPECTIVE_PARTIAL_DATABASE_REQUIRES_RECOVERY')
                book = create_book(authority=self.authority, clock=clock)
                hashed = digest(book)
                connection.execute('INSERT INTO prospective_header VALUES(1,?,?,?,?,?)',
                                   (canonical(book).decode(), hashed, 0, hashed, book['revision']))
            result, _ = self._load(connection, self._admissions())
            self.fault('before_commit')
            self._identity(identity)
            if fresh:
                app = _context(self.authority, clock())
                now = clock()
                first = app['plan']['first_session']
                require(stamp(result['initialized_at']) <= now < stamp(first['decision_until']),
                        'PROSPECTIVE_INITIALIZATION_MISSED')
        return result

    def read(self):
        identity = self._paths()
        require(self.path.is_file(), 'PROSPECTIVE_DATABASE_MISSING')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True,
                                     timeout=self.timeout, isolation_level=None)) as connection:
            connection.execute('BEGIN')
            try:
                self._identity(identity)
                self._schema(connection)
                result, _ = self._load(connection, self._admissions())
                self._identity(identity)
                return result
            finally:
                connection.rollback()

    def apply(self, request):
        # Bound the serialized snapshot before joining it or taking a DB lock.
        # This does not bound memory already allocated by the caller.
        chunks = []
        size = 0
        encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'),
                                   ensure_ascii=False, allow_nan=False)
        for chunk in encoder.iterencode(request):
            size += len(chunk.encode('utf-8'))
            require(size <= MAX_BYTES, 'PROSPECTIVE_REQUEST_BUDGET')
            chunks.append(chunk)
        request = json.loads(''.join(chunks))
        with self._write() as (connection, identity):
            clock = self._operation_clock()
            admissions = self._admissions()
            before, head = self._load(connection, admissions)
            target = self.target_reader() if request['kind'] == 'ACCEPT' else None
            result = transact(before, request, authority=self.authority,
                admitted_decisions=admissions['decisions'], admitted_settlements=admissions['settlements'],
                current_target_id=target, clock=clock)
            changed = result != before
            if changed:
                operation = result['operations'][-1]
                ordinal = len(result['operations'])
                hashed = digest(dict(ordinal=ordinal, operation=operation, previous_hash=head))
                connection.execute('INSERT INTO prospective_events VALUES(?,?,?,?,?)',
                    (ordinal, request['operation_id'], canonical(operation).decode(), head, hashed))
                connection.execute('UPDATE prospective_header SET count=?,head=?,revision=? WHERE id=1',
                                   (ordinal, hashed, result['revision']))
                self.fault('after_insert')
            checked, _ = self._load(connection, self._admissions())
            require(checked == result, 'PROSPECTIVE_COMMIT_READBACK')
            self.fault('before_commit')
            self._identity(identity)
            if changed:
                _context(self.authority, clock())
                if request['kind'] == 'ACCEPT':
                    require(self.target_reader() == target, 'PROSPECTIVE_CURRENT_TARGET_CHANGED')
                now = clock()
                require(now >= stamp(result['last_available_at']), 'PROSPECTIVE_CLOCK_ROLLBACK')
                if request['kind'] == 'ACCEPT':
                    decision = json.loads(request['decision_bytes'])
                    local = now.astimezone(ZoneInfo('America/New_York'))
                    require(local.date().isoformat() == decision['session_date'] and
                            time(10) <= local.time() < time(10, 1) and now < stamp(decision['valid_until']),
                            'PROSPECTIVE_COMMIT_ACCEPT_DEADLINE')
        return result
