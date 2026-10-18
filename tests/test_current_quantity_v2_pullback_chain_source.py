from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
from data.current_quantity_v2_pullback_chain_source import DATABASE, read_pullback_chain_sources
from test_current_quantity_v2_pullback_cap_store import arguments


class ChainSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / DATABASE
        self.database.parent.mkdir(parents=True)

    def event(self, seconds=0):
        store = PullbackCapStore(self.database, clock=lambda: '2026-10-15T09:32:30-04:00', max_history_rows=100, max_history_bytes=1000000)
        args = arguments(seconds, 1356.8 + seconds)
        result = store.candidate(**args)
        pullback = dict(result['candidate'], cap_record_hash=result['cap_store_receipt']['record_hash'],
            prior_cap=result['frozen_proof']['prior_cap'], status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED')
        return json.dumps(dict(schema='V2_GENERATED_PREVIEW_OBSERVATION_V1',
            rows=[dict(security_id='SNDK-ID', ticker='SNDK', limit_price=pullback['limit_price'],
                       reference=dict(pullback=pullback))],
            captures=[dict(role='ORIGINAL_QUOTE', security_id='SNDK-ID', ticker='SNDK',
                           sha256=sha256(args['raw']).hexdigest())])).encode()

    def read(self, *events):
        return read_pullback_chain_sources(repository_root=self.root, event_raws=list(events))

    def test_missing_database_never_created(self):
        event = self.event()
        self.database.unlink()
        result = self.read(event)
        self.assertFalse(self.database.exists())
        self.assertFalse(result['local_prefix_replayed'])
        self.assertEqual(result['unavailable'][0]['reason'], 'PULLBACK_DATABASE_UNAVAILABLE')

    def test_real_replay_immutable_prefix_and_batch_dedup(self):
        first, second = self.event(), self.event(1)
        before = self.database.read_bytes()
        result = self.read(first, second, second)
        self.assertEqual(len(result['files']), 2)
        self.assertFalse(result['unavailable'])
        self.assertEqual(before, self.database.read_bytes())
        for path, raw in result['files'].items():
            self.assertEqual(sha256(raw).hexdigest(), result['source_hashes'][path])
        self.event(2)
        self.assertEqual(result, self.read(first, second))
        self.assertFalse(result['external_authentication'])
        self.assertFalse(result['database_writes'])

    def test_tamper_and_missing_prefix_refused(self):
        self.event()
        second = self.event(1)
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('DELETE FROM pullback_caps WHERE ordinal=0')
        self.assertFalse(self.read(second)['record_paths'])

    def test_wrong_quote_and_malformed_event_are_not_exported(self):
        event = json.loads(self.event())
        event['captures'][0]['sha256'] = '0' * 64
        self.assertFalse(self.read(json.dumps(event).encode())['files'])
        event['rows'].append(dict(reference=dict(pullback={})))
        result = self.read(json.dumps(event).encode())
        self.assertFalse(result['files'])
        self.assertEqual(result['unavailable'][0]['reason'], 'INVALID_EVENT_CHAIN_BINDING')

    def test_bounded_prefix_and_input(self):
        first = self.event()
        second = self.event(1)
        with patch('data.current_quantity_v2_pullback_chain_source.MAX_ROWS', 1):
            self.assertFalse(self.read(second)['files'])
            self.assertTrue(self.read(first)['files'])
        with patch('data.current_quantity_v2_pullback_chain_source.MAX_PREFIX_BYTES', 1):
            self.assertFalse(self.read(first)['files'])
        with self.assertRaisesRegex(ValueError, 'EVENT_BATCH_LIMIT'):
            self.read(*([first] * 51))


if __name__ == '__main__':
    unittest.main()


