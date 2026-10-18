from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
from threading import Barrier
import unittest

from data.strategy_account_active_release_store import ActiveMonthlyReleaseStore


def snapshot(number=1):
    return dict(registry_path='tmp/candidate/registry.json', registry_sha256='a'*64,
                archive_path='tmp/candidate/archive.json', archive_sha256='b'*64,
                ready_path=f'tmp/candidate/{number}/ready.json', ready_sha256=f'{number:064x}',
                target_month='2026-11', account_revision='c'*64,
                adopted_at='2026-11-02T14:30:00+00:00')


class ActiveReleaseStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.store = ActiveMonthlyReleaseStore(root=self.root)

    def test_empty_read_and_restart_and_receipt_idempotence(self):
        self.assertIsNone(self.store.current())
        self.assertEqual(list(self.root.iterdir()), [])
        first = self.store.adopt(snapshot(), expected_revision=0)
        self.assertEqual(first['revision'], 1)
        restarted = ActiveMonthlyReleaseStore(root=self.root)
        self.assertEqual(restarted.current(), first)
        self.assertEqual(restarted.adopt(snapshot(), expected_revision=0), first)
        second = restarted.adopt(snapshot(2), expected_revision=1)
        self.assertEqual(second['previous_revision'], 1)
        self.assertEqual(restarted.adopt(snapshot(), expected_revision=0), first)
        self.assertEqual(restarted.current(), second)
        self.assertFalse((self.root/'data/strategy_account/real_strategy.sqlite3').exists())
        self.assertFalse((self.root/'data/strategy_account/monthly_targets.sqlite3').exists())

    def test_conflict_and_stale_cas_leave_existing_unchanged(self):
        original = self.store.adopt(snapshot(), expected_revision=0)
        changed = snapshot()
        changed['registry_sha256'] = 'd'*64
        with self.assertRaisesRegex(ValueError, 'RECEIPT_CONFLICT'):
            self.store.adopt(changed, expected_revision=1)
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.store.adopt(snapshot(2), expected_revision=0)
        self.assertEqual(self.store.current(), original)

    def test_two_instances_atomic_cas_including_concurrent_creation(self):
        barrier = Barrier(2)
        def attempt(number):
            store = ActiveMonthlyReleaseStore(root=self.root)
            barrier.wait()
            try:
                return store.adopt(snapshot(number), expected_revision=0)
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(attempt, [1, 2]))
        self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
        self.assertIn('ACTIVE_RELEASE_STALE_REVISION', outcomes)
        self.assertEqual(self.store.current()['revision'], 1)

    def test_strict_fields_paths_hashes_and_clock_before_any_write(self):
        invalid = []
        for field, value in [('registry_path','../escape'), ('archive_path','C:/escape'),
                             ('ready_path','tmp\\ready'), ('ready_sha256','bad'),
                             ('target_month','2026-13'), ('adopted_at','2026-11-02T14:30:00')]:
            payload = snapshot()
            payload[field] = value
            invalid.append(payload)
        payload = snapshot()
        payload['unexpected'] = True
        invalid.append(payload)
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.store.adopt(payload, expected_revision=0)
        with self.assertRaises(ValueError):
            self.store.adopt(snapshot(), expected_revision=True)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_corrupt_chain_fails_closed(self):
        self.store.adopt(snapshot(), expected_revision=0)
        with closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute('UPDATE releases SET revision=2')
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'ACTIVE_RELEASE_CHAIN'):
            self.store.current()
        with self.assertRaisesRegex(ValueError, 'ACTIVE_RELEASE_CHAIN'):
            self.store.adopt(snapshot(2), expected_revision=1)

    def test_mutable_inputs_and_outputs_do_not_change_saved_snapshot(self):
        payload = snapshot()
        expected = deepcopy(payload)
        result = self.store.adopt(payload, expected_revision=0)
        payload['target_month'] = '2027-01'
        result['payload']['target_month'] = '2027-02'
        self.assertEqual(self.store.current()['payload'], expected)

    def test_foreign_trigger_is_rejected_before_write(self):
        self.store.adopt(snapshot(), expected_revision=0)
        with closing(sqlite3.connect(self.store.path)) as connection:
            connection.execute('CREATE TRIGGER corrupt AFTER INSERT ON releases BEGIN DELETE FROM releases; END')
            connection.commit()
        with self.assertRaisesRegex(ValueError, 'ACTIVE_RELEASE_DATABASE_SCHEMA'):
            self.store.adopt(snapshot(2), expected_revision=1)
        with closing(sqlite3.connect(self.store.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM releases').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
