from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_execution import IntradayExecutionService
from test_current_research_intraday_execution import NOW, payload, snapshot


class ScopeEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        store = PersistentIntradayCapStore(root / 'caps.db')
        journal = IntradayObservationJournal(root / 'journal')
        service = IntradayExecutionService(snapshot_reader=snapshot, fetch=lambda _: payload(), clock=lambda: NOW, cap_store=store, journal=journal)
        first = service.preview('a' * 24)
        second = service.preview('a' * 24)
        self.assertEqual(second['status'], 'AVAILABLE')
        key = dict(research_id='a' * 24, security_id=snapshot('a' * 24)['selected_security']['security_id'], ticker='SNDK', session=second['stocks'][0]['session'], current_event_id=second['observation_record']['event_id'])
        return store, journal, key, first, second

    def test_original_closure_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); store, journal, key, first, second = self.fixture(root)
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            result = store.read_scope_evidence(journal, **key)
            self.assertEqual(len(result['event_hashes']), 2)
            self.assertEqual(result['current_receipt'], second['observation_record'])
            self.assertIn(first['observation_record']['event_id'], result['dependency_event_ids'])
            self.assertEqual(before, {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_missing_scope_current_and_database_no_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); store, journal, key, _, _ = self.fixture(root)
            for changes in ({'research_id': 'b' * 24}, {'current_event_id': 'f' * 32}, {'security_id': 'other'}):
                with self.assertRaises(ValueError): store.read_scope_evidence(journal, **dict(key, **changes))
            missing = root / 'missing' / 'caps.db'
            with self.assertRaisesRegex(ValueError, 'CAP_DATABASE_MISSING'):
                PersistentIntradayCapStore(missing).read_scope_evidence(journal, **key)
            self.assertFalse(missing.parent.exists())

    def test_changed_journal_cannot_self_hash_new_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); store, journal, key, _, second = self.fixture(root)
            path = journal.root / second['observation_record']['event_path']
            event = json.loads(path.read_bytes()); event['tampered'] = True
            replacement = json.dumps(event).encode(); path.write_bytes(replacement)
            # An independently recalculated digest is not the original outbox receipt.
            second['observation_record']['event_sha256'] = sha256(replacement).hexdigest()
            with self.assertRaisesRegex(ValueError, 'JOURNAL_ORIGINAL_(BYTES|SIZE)_MISMATCH'):
                store.read_scope_evidence(journal, **key)
            self.assertEqual(path.read_bytes(), replacement)


    def test_scope_row_changed_and_unrelated_sequence_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = PersistentIntradayCapStore(root / 'caps.db')
            journal = IntradayObservationJournal(root / 'journal')
            def enriched(identifier):
                value = snapshot(identifier)
                value['selected_security']['issuer_id'] = 'extra-valid-metadata'
                return value
            service = IntradayExecutionService(snapshot_reader=enriched, fetch=lambda _: payload(), clock=lambda: NOW, cap_store=store, journal=journal)
            first = service.preview('a' * 24)
            service.observation_sequence += 5  # Failed/non-cap observations need no outbox ancestry.
            second = service.preview('a' * 24)
            key = dict(research_id='a' * 24, security_id=snapshot('a' * 24)['selected_security']['security_id'], ticker='SNDK', session=second['stocks'][0]['session'], current_event_id=second['observation_record']['event_id'])
            self.assertEqual(len(store.read_scope_evidence(journal, **key)['event_hashes']), 2)
            with closing(sqlite3.connect(store.path)) as connection:
                connection.execute('UPDATE session_caps SET cents=cents-1')
                connection.commit()
            with self.assertRaisesRegex(ValueError, 'CURRENT_CAP_ROW_MISMATCH'):
                store.read_scope_evidence(journal, **key)

    def test_raw_tampering_same_size_is_not_repaired(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); store, journal, key, _, _ = self.fixture(root)
            source = next((journal.root / 'raw').glob('*.bin'))
            content = source.read_bytes(); replacement = b'X' + content[1:]
            source.write_bytes(replacement)
            with self.assertRaisesRegex(ValueError, 'JOURNAL_ORIGINAL_BYTES_MISMATCH'):
                store.read_scope_evidence(journal, **key)
            self.assertEqual(source.read_bytes(), replacement)

    def test_corrupt_original_package_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); store, journal, key, _, _ = self.fixture(root)
            with closing(sqlite3.connect(store.path)) as connection:
                connection.execute('UPDATE cap_outbox SET package=? WHERE event_id=?', (b'{}', key['current_event_id']))
                connection.commit()
            with self.assertRaisesRegex(ValueError, 'OUTBOX_HASH_MISMATCH'):
                store.read_scope_evidence(journal, **key)


if __name__ == '__main__': unittest.main()
