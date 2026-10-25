from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
import sqlite3
import subprocess
import sys
import unittest

from data.paper_dividend_journal_store_v1 import PaperDividendJournalStore
import test_paper_dividend_journal_v1 as fixtures


class DurableDividendTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'isolated-dividends.sqlite3'
        self.f = fixtures.DividendJournalTests(); self.f.setUp()
        self.store = PaperDividendJournalStore(self.path)
        self.store.initialize(self.f.f.book, **self.f.evidence)

    def post(self, store=None):
        return (store or self.store).post(self.f.request, clock=lambda:self.f.now, **self.f.evidence)

    def test_reopen_and_retry_returns_one_payment(self):
        before = deepcopy(self.f.f.book)
        posted = self.post()
        reopened = PaperDividendJournalStore(self.path)
        self.assertEqual(reopened.read(**self.f.evidence), posted)
        self.assertEqual(self.post(reopened), posted)
        self.assertEqual(reopened.initialize(self.f.f.book, **self.f.evidence), posted)
        self.assertEqual(len(posted['entries']), 1)
        self.assertEqual(posted['paid_net'], '23/10')
        self.assertEqual(self.f.f.book, before)

    def test_two_connections_same_payment_commit_once(self):
        barrier = Barrier(2)
        def worker():
            store = PaperDividendJournalStore(self.path); barrier.wait()
            return self.post(store)
        with ThreadPoolExecutor(max_workers=2) as pool:
            tasks = [pool.submit(worker) for _ in range(2)]
            results = [task.result(timeout=15) for task in tasks]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.read(**self.f.evidence)['entries']), 1)

    def test_exception_after_sql_update_rolls_back_then_retry_succeeds(self):
        before = self.store.read(**self.f.evidence)
        original = self.store._persist
        def fail(connection, journal):
            original(connection, journal)
            raise RuntimeError('isolated interruption before commit')
        with patch.object(self.store, '_persist', fail), self.assertRaises(RuntimeError): self.post()
        self.assertEqual(PaperDividendJournalStore(self.path).read(**self.f.evidence), before)
        self.assertEqual(self.post()['paid_net'], '23/10')

    def test_process_exit_before_commit_recovers_without_duplicate_payment(self):
        before = self.store.read(**self.f.evidence)
        script = '''
import os, sys
sys.path.insert(0, 'tests')
from data.paper_dividend_journal_store_v1 import PaperDividendJournalStore
from test_paper_dividend_journal_v1 import DividendJournalTests
f=DividendJournalTests(); f.setUp()
store=PaperDividendJournalStore(sys.argv[1])
original=store._persist
def crash(connection, journal):
    connection.execute('PRAGMA cache_size=1')
    original(connection, journal)
    # Temporary database only: force dirty pages to disk before abrupt exit,
    # so reopening genuinely exercises SQLite hot-journal rollback.
    connection.execute('UPDATE paper_dividend_journal SET body=zeroblob(1048576) WHERE slot=1')
    os._exit(17)
store._persist=crash
store.post(f.request, clock=lambda:f.now, **f.evidence)
'''
        child = subprocess.run([sys.executable, '-X', 'utf8', '-E', '-B', '-c', script, str(self.path)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=20)
        self.assertEqual(child.returncode, 17, child.stderr.decode('utf-8', errors='replace'))
        reopened = PaperDividendJournalStore(self.path)
        self.assertEqual(reopened.read(**self.f.evidence), before)
        self.assertEqual(self.post(reopened)['paid_net'], '23/10')
        self.assertEqual(len(reopened.read(**self.f.evidence)['entries']), 1)

    def test_foreign_database_and_changed_source_are_not_overwritten(self):
        foreign = Path(self.folder.name)/'foreign.sqlite3'
        with closing(sqlite3.connect(foreign)) as connection:
            connection.execute('CREATE TABLE account(value TEXT)'); connection.commit()
        before = foreign.read_bytes()
        with self.assertRaisesRegex(ValueError, 'FOREIGN_DATABASE'):
            PaperDividendJournalStore(foreign).initialize(self.f.f.book, **self.f.evidence)
        self.assertEqual(foreign.read_bytes(), before)
        self.post(); before = self.path.read_bytes()
        self.f.evidence['source_files'][self.f.request['review_sha256']] = {}
        with self.assertRaisesRegex(ValueError, 'SOURCE_CLOSURE'): self.post()
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == '__main__': unittest.main()
