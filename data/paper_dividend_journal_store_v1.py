"""Atomic storage for the separate isolated dividend journal; no live wiring."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3

from core.strategy_account_ledger import canonical, require
from backtest.paper_dividend_journal_v1 import create, replay, append


class PaperDividendJournalStore:
    def __init__(self, path):
        self.path = Path(path).absolute()
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)),
                'DIVIDEND_STORE_LINK_PATH')

    @contextmanager
    def _write(self, *, create_file=False):
        mode = 'rwc' if create_file else 'rw'
        connection = sqlite3.connect(self.path.as_uri() + '?mode=' + mode, uri=True,
                                     timeout=10, isolation_level=None)
        try:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            require(names <= {'paper_dividend_journal'}, 'DIVIDEND_STORE_FOREIGN_DATABASE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _load(connection, evidence):
        row = connection.execute('SELECT body FROM paper_dividend_journal WHERE slot=1').fetchone()
        require(row is not None, 'DIVIDEND_STORE_NOT_INITIALIZED')
        return replay(json.loads(row[0]), **evidence)

    @staticmethod
    def _persist(connection, journal):
        connection.execute('UPDATE paper_dividend_journal SET body=? WHERE slot=1', (canonical(journal),))

    def initialize(self, book, **evidence):
        opening = create(book)
        with self._write(create_file=True) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS paper_dividend_journal '
                               '(slot INTEGER PRIMARY KEY CHECK(slot=1), body BLOB NOT NULL)')
            found = connection.execute('SELECT body FROM paper_dividend_journal WHERE slot=1').fetchone()
            if found is not None:
                current = self._load(connection, evidence)
                require(current['identity'] == opening['identity'], 'DIVIDEND_STORE_IDENTITY_CONFLICT')
                return current
            # Validate the parent book through the same authority as postings.
            from backtest.current_strategy_prospective_paper_book_v1 import replay as replay_book
            replay_book(book, authority=evidence['authority'], admitted_decisions=evidence['admitted_decisions'],
                        admitted_settlements=evidence['admitted_settlements'])
            connection.execute('INSERT INTO paper_dividend_journal(slot,body) VALUES(1,?)', (canonical(opening),))
            return opening

    def read(self, **evidence):
        # SQLite must be able to roll back a hot journal after process death.
        # rw opens only an existing isolated DB; no application writes occur here.
        connection = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=10)
        try:
            return self._load(connection, evidence)
        finally:
            connection.close()

    def post(self, request, *, clock=None, **evidence):
        with self._write() as connection:
            before = self._load(connection, evidence)
            after = append(before, request, clock=clock, **evidence)
            if after != before:
                self._persist(connection, after)
            return after
