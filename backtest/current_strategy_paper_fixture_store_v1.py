"""Temporary-directory durable adapter for the fixture-only paper slice.

Reuses the isolated SimulationStore transaction/read-only patterns, but never its
old proposal or real-fill semantics. Pure replay and SQL commit are one unit;
there is no source fetching or partially prepared external operation to recover.
"""
from contextlib import contextmanager, closing
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import tempfile
import stat

from backtest.current_strategy_paper_slice_v1 import (
    create_book, transact, validate_application, digest, need, _apply)

TABLES = {
    'paper_fixture_header': ['id', 'application', 'application_hash', 'record_count', 'head_hash', 'revision'],
    'paper_fixture_events': ['ordinal', 'operation_id', 'request', 'outcome', 'revision', 'previous_hash', 'record_hash'],
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class PaperFixtureStore:
    def __init__(self, *, directory, application, timeout_seconds=2, fault=None):
        validate_application(application)
        raw = Path(directory).absolute()
        temp = Path(tempfile.gettempdir()).resolve()
        need(raw.is_dir() and raw.resolve().is_relative_to(temp) and raw.resolve() != temp,
             'PAPER_TEMP_DIRECTORY_REQUIRED')
        for path in [raw, *raw.parents]:
            need(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                 'PAPER_LINK_PATH_REJECTED')
            if path == temp:
                break
        need(type(timeout_seconds) in (int, float) and 0 < timeout_seconds <= 10,
             'PAPER_LOCK_TIMEOUT_BOUNDED')
        self.directory = raw.resolve()
        self.path = self.directory / 'current_strategy_paper_fixture.sqlite3'
        self.application = deepcopy(application)
        self.timeout = timeout_seconds
        self.fault = fault or (lambda phase: None)

    def _check_path(self):
        need(self.directory.is_dir() and self.directory.resolve() == self.directory,
             'PAPER_DIRECTORY_CHANGED')
        for path in [self.directory, *self.directory.parents]:
            info = path.lstat()
            need(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)()
                 and not (getattr(info, 'st_file_attributes', 0) & 0x400),
                 'PAPER_LINK_PATH_REJECTED')
            if path == Path(tempfile.gettempdir()).resolve():
                break
        identity = None
        for path in [self.path, *[Path(str(self.path)+suffix) for suffix in ('-journal','-wal','-shm')]]:
            need(not path.is_symlink() and not getattr(path, 'is_junction', lambda: False)(),
                 'PAPER_LINK_PATH_REJECTED')
            if path.exists():
                info = path.lstat()
                need(stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400),
                     'PAPER_LINK_PATH_REJECTED')
                need(info.st_nlink == 1, 'PAPER_HARDLINK_REJECTED')
                if path == self.path:
                    identity = (info.st_dev, info.st_ino)
        return identity

    def _check_identity(self, expected):
        actual = self._check_path()
        need(expected is not None and actual == expected, 'PAPER_DATABASE_PATH_CHANGED')

    @staticmethod
    def _schema(connection, create=False):
        objects = connection.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        need(set(objects) == {(name, 'table') for name in TABLES} or (create and not objects),
             'PAPER_WRONG_DATABASE')
        if not objects:
            connection.execute('CREATE TABLE paper_fixture_header (id INTEGER PRIMARY KEY CHECK(id=1), application TEXT NOT NULL, application_hash TEXT NOT NULL, record_count INTEGER NOT NULL, head_hash TEXT NOT NULL, revision TEXT NOT NULL)')
            connection.execute('CREATE TABLE paper_fixture_events (ordinal INTEGER PRIMARY KEY, operation_id TEXT UNIQUE NOT NULL, request TEXT NOT NULL, outcome TEXT NOT NULL, revision TEXT NOT NULL, previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL)')
        for name, expected in TABLES.items():
            need([row[1] for row in connection.execute('PRAGMA table_info('+name+')')] == expected,
                 'PAPER_SCHEMA_CHANGED')
        need(connection.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'PAPER_SQLITE_INTEGRITY')

    @contextmanager
    def _write(self, create=False):
        original_identity = self._check_path()
        need(create or self.path.is_file(), 'PAPER_DATABASE_MISSING')
        uri = self.path.as_uri() + ('?mode=rwc' if create else '?mode=rw')
        with closing(sqlite3.connect(uri, uri=True, timeout=self.timeout, isolation_level=None)) as connection:
            try:
                opened_identity = self._check_path()
                need(opened_identity is not None and (original_identity is None or
                     opened_identity == original_identity), 'PAPER_DATABASE_PATH_CHANGED')
                # Obtain reader exclusion before replay; a late reader cannot
                # defer this transaction's commit after its final validation.
                connection.execute('PRAGMA synchronous=FULL')
                connection.execute('BEGIN EXCLUSIVE')
                self._check_identity(opened_identity)
                self._schema(connection, create)
                self.fault('after_begin')
                yield connection
                self.fault('before_commit')
                self._check_identity(opened_identity)
                connection.commit()
                self._check_identity(opened_identity)
                self.fault('after_commit')
            except BaseException:
                connection.rollback()
                raise

    def _load(self, connection):
        headers = connection.execute('SELECT application,application_hash,record_count,head_hash,revision FROM paper_fixture_header').fetchall()
        need(len(headers) == 1, 'PAPER_HEADER_REQUIRED')
        raw, app_hash, count, head, revision = headers[0]
        application = json.loads(raw)
        need(raw == canonical(application) and digest(application) == app_hash and
             application == self.application, 'PAPER_APPLICATION_CHANGED')
        need(type(count) is int and 0 <= count <= 1000, 'PAPER_FIXTURE_RECORD_BUDGET')
        # A corruption must not silently truncate history or become a new book.
        size, actual_count = connection.execute('SELECT coalesce(sum(length(CAST(request AS BLOB))+length(CAST(outcome AS BLOB))),0),count(*) FROM paper_fixture_events').fetchone()
        need(actual_count == count, 'PAPER_RECORD_COUNT_MISMATCH')
        need(size + len(raw.encode()) <= 16*1024*1024, 'PAPER_FIXTURE_BYTE_BUDGET')
        book = create_book(application)
        previous = app_hash
        operation_ids = set()
        for ordinal, oid, request_raw, outcome_raw, result_revision, prior, record_hash in connection.execute(
                'SELECT ordinal,operation_id,request,outcome,revision,previous_hash,record_hash FROM paper_fixture_events ORDER BY ordinal'):
            request, outcome = json.loads(request_raw), json.loads(outcome_raw)
            need(ordinal == len(book['operations'])+1 and request['operation_id'] == oid and prior == previous
                 and request_raw == canonical(request) and outcome_raw == canonical(outcome), 'PAPER_EVENT_CHAIN_CHANGED')
            payload = dict(ordinal=ordinal, request=request, outcome=outcome,
                           revision=result_revision, previous_hash=prior)
            need(digest(payload) == record_hash, 'PAPER_RECORD_HASH_MISMATCH')
            # The prefix was replayed immediately above. Replaying it again for
            # every row makes a full read quadratic without adding verification.
            need(oid not in operation_ids, 'PAPER_DUPLICATE_STORED_OPERATION')
            operation_ids.add(oid)
            updated = _apply(book, request)
            need(len(updated['operations']) == ordinal and updated['revision'] == result_revision
                 and updated['operations'][-1]['outcome'] == outcome, 'PAPER_STORED_REPLAY_MISMATCH')
            book, previous = updated, record_hash
        need(previous == head and book['revision'] == revision, 'PAPER_HEAD_CHANGED')
        return book, previous

    def initialize(self):
        existed = self.path.exists()
        with self._write(create=True) as connection:
            if connection.execute('SELECT count(*) FROM paper_fixture_header').fetchone()[0] == 0:
                need(not existed, 'PAPER_EXISTING_HEADER_MISSING')
                need(connection.execute('SELECT count(*) FROM paper_fixture_events').fetchone()[0] == 0,
                     'PAPER_ORPHAN_EVENTS')
                state = create_book(self.application)
                app_hash = digest(self.application)
                connection.execute('INSERT INTO paper_fixture_header VALUES(1,?,?,?,?,?)',
                    (canonical(self.application), app_hash, 0, app_hash, state['revision']))
            result, _ = self._load(connection)
        return result

    def read(self):
        identity = self._check_path()
        need(self.path.is_file(), 'PAPER_DATABASE_MISSING')
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro', uri=True,
                                     timeout=self.timeout, isolation_level=None)) as connection:
            connection.execute('BEGIN')
            try:
                self._check_identity(identity)
                self._schema(connection)
                book, _ = self._load(connection)
                self._check_identity(identity)
                return book
            finally:
                connection.rollback()

    def apply(self, request):
        # Bound the serialized snapshot before copying/replaying or acquiring a
        # database lock. This bounds our snapshot, not the caller's input memory.
        chunks = []
        size = 0
        for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':'),
                                      allow_nan=False, ensure_ascii=True).iterencode(request):
            size += len(chunk)
            need(size <= 16*1024*1024, 'PAPER_REQUEST_BYTE_BUDGET')
            chunks.append(chunk)
        request = json.loads(''.join(chunks))
        with self._write() as connection:
            previous, head = self._load(connection)
            result = transact(previous, request)
            if result != previous:
                operation = result['operations'][-1]
                ordinal = len(result['operations'])
                payload = dict(ordinal=ordinal, request=request, outcome=operation['outcome'],
                               revision=result['revision'], previous_hash=head)
                record_hash = digest(payload)
                connection.execute('INSERT INTO paper_fixture_events VALUES(?,?,?,?,?,?,?)',
                    (ordinal, request['operation_id'], canonical(request), canonical(operation['outcome']),
                     result['revision'], head, record_hash))
                connection.execute('UPDATE paper_fixture_header SET record_count=?,head_hash=?,revision=? WHERE id=1',
                                   (ordinal, record_hash, result['revision']))
                self.fault('after_insert')
            checked, _ = self._load(connection)
            need(checked == result, 'PAPER_COMMIT_READBACK_MISMATCH')
        return result
