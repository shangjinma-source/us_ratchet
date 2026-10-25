from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from data.saved_frontier_current_migration_v1 import bind_unchanged_current_proposal
from data.saved_frontier_monthly_view_v1 import SavedFrontierMonthlyView, SavedFrontierProposalStore
from test_saved_monthly_frontier_proposal import native_fixture


class CurrentMigrationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = SavedFrontierProposalStore(Path(temporary.name)/'proposals.sqlite3')
        self.target = native_fixture(tie=True)
        self.state = dict(account_id=self.target['payload']['account_id'], revision='current-revision')
        case = self

        class Monthly:
            accounts = type('Accounts', (), {'read': lambda self: deepcopy(case.state)})()
            def current(self): return deepcopy(case.target)
            def snapshot_operation(self): return nullcontext()
            def validate_current_target_pins(self): pass

        self.view = SavedFrontierMonthlyView(monthly=Monthly(), proposals=self.store,
                                             validate_sources=lambda: None)

    def migrate(self, **overrides):
        arguments = dict(monthly_view=self.view, expected_target_id=self.target['target_id'],
                         expected_revision=self.state['revision'])
        return bind_unchanged_current_proposal(**dict(arguments, **overrides))

    def test_unchanged_basket_registration_is_idempotent(self):
        before = deepcopy(self.target)
        first = self.migrate()
        self.assertEqual(first, self.migrate())
        self.assertEqual(before, self.target)
        self.assertFalse(first['allocation_changed'])
        self.assertFalse(first['release_activated'])

    def test_improved_basket_requires_normal_selection_not_migration(self):
        self.target = native_fixture()
        with self.assertRaisesRegex(ValueError, 'FRONTIER_MIDMONTH_ALLOCATION_CHANGE_REFUSED'):
            self.migrate()
        self.assertFalse(self.store.path.exists())

    def test_stale_snapshots_do_not_write(self):
        for arguments in ({'expected_revision': 'stale'}, {'expected_target_id': 'stale'}):
            with self.assertRaisesRegex(ValueError, 'STALE_'):
                self.migrate(**arguments)
        self.assertFalse(self.store.path.exists())


if __name__ == '__main__':
    unittest.main()
