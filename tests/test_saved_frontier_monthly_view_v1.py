from contextlib import closing, nullcontext
from copy import deepcopy
from pathlib import Path
import sqlite3
import os
import tempfile
import unittest

from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from test_saved_monthly_frontier_proposal import native_fixture


class MonthlyViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = native_fixture(held=True)
        self.store = SavedFrontierProposalStore(Path(self.directory.name) / 'proposals.sqlite3')
        target = self.target

        class Monthly:
            def snapshot_operation(self):
                return nullcontext()

            def current(self):
                return deepcopy(target)

            def generate(self, **request):
                return deepcopy(target)

        self.view = SavedFrontierMonthlyView(monthly=Monthly(), proposals=self.store,
                                             validate_sources=lambda: None)

    def test_missing_binding_fails_closed_then_retry_recovers(self):
        with self.assertRaisesRegex(ValueError, 'FRONTIER_PROPOSAL_REQUIRED'):
            self.view.current()
        self.assertFalse(self.store.path.exists())
        generated = self.view.generate(event_id='retry')
        self.assertEqual(generated, self.view.current())
        self.assertEqual(generated, self.view.generate(event_id='retry'))
        self.assertEqual(generated['payload'], self.target['payload'])
        self.assertEqual(generated['target_id'], self.target['target_id'])

    def test_changed_persisted_binding_rejected_on_read_and_retry(self):
        self.view.generate()
        with closing(sqlite3.connect(self.store.path)) as connection, connection:
            connection.execute('UPDATE frontier_proposals SET document=?', (b'{}',))
        for operation in (self.view.current, self.view.generate):
            with self.assertRaisesRegex(ValueError, 'FRONTIER_PROPOSAL_CHANGED'):
                operation()

    def test_stale_proposal_rejected(self):
        view = self.view.generate()
        with self.assertRaisesRegex(ValueError, 'STALE_FRONTIER_PROPOSAL'):
            self.view.require_proposal(target_id=view['target_id'], expected_proposal_id='0' * 64)
        proposal = self.view.require_proposal(target_id=view['target_id'],
                                             expected_proposal_id=view['proposal_id'])
        self.assertEqual(proposal, view['frontier_proposal'])

    def test_missing_parent_is_not_created(self):
        store = SavedFrontierProposalStore(Path(self.directory.name) / 'missing' / 'db.sqlite3')
        with self.assertRaisesRegex(ValueError, 'FRONTIER_PROPOSAL_REQUIRED'):
            store.read(self.target)
        with self.assertRaisesRegex(ValueError, 'FRONTIER_STORAGE_PARENT_REQUIRED'):
            store.bind(self.target)
        self.assertFalse(store.path.parent.exists())

    def test_hard_link_refused(self):
        self.store.bind(self.target)
        alias = self.store.path.with_name('alias.sqlite3')
        os.link(self.store.path, alias)
        for operation in (self.store.read, self.store.bind):
            with self.assertRaisesRegex(ValueError, 'FRONTIER_STORAGE_ALIAS_FORBIDDEN'):
                operation(self.target)

    def test_read_preserves_database_bytes(self):
        self.store.bind(self.target)
        before = self.store.path.read_bytes()
        self.store.read(self.target)
        self.assertEqual(before, self.store.path.read_bytes())
        self.assertEqual([self.store.path], list(self.store.path.parent.iterdir()))


if __name__ == '__main__':
    unittest.main()
