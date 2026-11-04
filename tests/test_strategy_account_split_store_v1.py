from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore


class SplitStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'split.sqlite3'
        self.now = datetime.fromisoformat('2026-11-20T14:32:00+00:00')
        self.store = SplitStrategyAccountStore(self.path, clock=lambda: self.now)
        self.state = self.store.initialize('synthetic', operation_id='init')
        self.state, _ = self.store.append(dict(event_id='buy', kind='DIRECT_FILL',
            security_id='S', side='BUY', quantity=14, price='1000', fees='0',
            executed_at='2026-11-02T15:00:00Z'), expected_revision=self.state['revision'])
        self.split = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action',
            security_id='S', ratio=8, effective_at='2026-11-20T14:30:00Z',
            broker_confirmed_at='2026-11-20T14:31:00Z', old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)

    def test_restart_duplicate_and_old_reader_refuses(self):
        updated, effect = self.store.append(self.split, expected_revision=self.state['revision'])
        restarted = SplitStrategyAccountStore(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.read(), updated)
        self.assertEqual(restarted.append(self.split, expected_revision=self.state['revision']), (updated, effect))
        self.assertEqual(updated['shares']['S'], 112)
        with self.assertRaises(ValueError): StrategyAccountStore(self.path).read()

    def test_old_database_is_not_silently_upgraded(self):
        old_path = Path(self.directory.name)/'old.sqlite3'
        old = StrategyAccountStore(old_path)
        expected = old.initialize('old', operation_id='old-init')
        before = old_path.read_bytes()
        with self.assertRaises(ValueError): SplitStrategyAccountStore(old_path).read()
        self.assertEqual(old_path.read_bytes(), before)
        self.assertEqual(old.read(), expected)

    def test_future_confirmation_and_clock_rollback_leave_no_event(self):
        future = dict(self.split, broker_confirmed_at='2026-11-20T14:33:00Z')
        with self.assertRaisesRegex(ValueError, 'FUTURE_SPLIT_CONFIRMATION'):
            self.store.append(future, expected_revision=self.state['revision'])
        self.assertEqual(self.store.read(), self.state)
        self.now = datetime.fromisoformat('2026-11-20T14:31:00+00:00')
        with self.assertRaisesRegex(ValueError, 'SERVER_CLOCK_ROLLBACK'):
            self.store.append(self.split, expected_revision=self.state['revision'])
        self.assertEqual(self.store.read(), self.state)

    def test_insert_then_meta_failure_rolls_back_entire_transaction(self):
        # Inject a database failure after INSERT without changing schema/reducer.
        real_connect = self.store._connect
        class FailingConnection:
            def __init__(self, inner): self.inner = inner
            def __getattr__(self, name): return getattr(self.inner, name)
            def execute(self, sql, *args):
                if sql.startswith('UPDATE strategy_meta'): raise sqlite3.OperationalError('injected')
                return self.inner.execute(sql, *args)
        self.store._connect = lambda readonly: FailingConnection(real_connect(readonly))
        with self.assertRaisesRegex(sqlite3.OperationalError, 'injected'):
            self.store.append(self.split, expected_revision=self.state['revision'])
        self.store._connect = real_connect
        self.assertEqual(self.store.read(), self.state)
        updated, _ = self.store.append(self.split, expected_revision=self.state['revision'])
        self.assertEqual(updated['shares']['S'], 112)

    def test_concurrent_same_request_commits_once(self):
        def submit(_):
            return SplitStrategyAccountStore(self.path, clock=lambda: self.now).append(
                self.split, expected_revision=self.state['revision'])[0]
        with ThreadPoolExecutor(max_workers=2) as workers:
            states = list(workers.map(submit, range(2)))
        self.assertEqual(states[0], states[1])
        self.assertEqual(len(self.store.read()['events']), 2)
