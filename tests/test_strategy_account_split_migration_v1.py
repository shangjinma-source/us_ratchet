from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest

from core.strategy_account_store import StrategyAccountStore
from core.strategy_account_split_store_v1 import SplitStrategyAccountStore
from data.strategy_account_split_migration_v1 import prepare_split_account


class SplitMigrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name)/'old.sqlite3'
        self.destination = Path(self.directory.name)/'new.sqlite3'
        self.store = StrategyAccountStore(self.source, clock=lambda: datetime.fromisoformat('2026-11-04T06:00:00+00:00'))
        self.state = self.store.initialize('synthetic', operation_id='initial')
        self.state, _ = self.store.append(dict(event_id='cash', kind='CASH_CONFIRM',
            amount='500', cash_basis='TOTAL_UNINVESTED'), expected_revision=self.state['revision'])

    def prepare(self, revision=None):
        return prepare_split_account(source_path=self.source, destination_path=self.destination,
                                     expected_revision=revision or self.state['revision'])

    def test_preserves_state_receipts_and_source_bytes(self):
        before = self.source.read_bytes()
        result = self.prepare()
        self.assertFalse(result['production_activated'])
        self.assertTrue(result['requires_activation_source_recheck'])
        self.assertEqual(SplitStrategyAccountStore(self.destination).read(), self.state)
        with closing(sqlite3.connect(self.source)) as old, closing(sqlite3.connect(self.destination)) as new:
            self.assertEqual(old.execute('SELECT * FROM strategy_events').fetchall(),
                             new.execute('SELECT * FROM strategy_events').fetchall())
        self.assertEqual(before, self.source.read_bytes())

    def test_stale_revision_and_existing_destination(self):
        with self.assertRaisesRegex(ValueError, 'STALE_MIGRATION_SOURCE'): self.prepare('stale')
        self.assertFalse(self.destination.exists())
        self.destination.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'DESTINATION_EXISTS'): self.prepare()
        self.assertEqual(self.destination.read_bytes(), b'preserve')
        self.assertEqual(list(self.source.parent.glob('.split-prepare-*')), [])

    def test_replay_failure_cleans_unpublished_copy(self):
        with patch.object(SplitStrategyAccountStore, 'read', side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError, 'injected'): self.prepare()
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.store.read(), self.state)
        self.assertEqual(list(self.source.parent.glob('.split-prepare-*')), [])

    def test_source_change_during_preparation_refuses_publication(self):
        real_read = SplitStrategyAccountStore.read
        def change_then_read(store):
            self.store.append(dict(event_id='cash-later', kind='CASH_CONFIRM', amount='400',
                cash_basis='TOTAL_UNINVESTED'), expected_revision=self.state['revision'])
            return real_read(store)
        with patch.object(SplitStrategyAccountStore, 'read', change_then_read):
            with self.assertRaisesRegex(ValueError, 'MIGRATION_SOURCE_CHANGED'): self.prepare()
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.store.read()['available_cash'], '400')

    def test_same_path_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SAME_PATH'):
            prepare_split_account(source_path=self.source, destination_path=self.source,
                                  expected_revision=self.state['revision'])
