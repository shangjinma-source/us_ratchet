from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from data.current_quantity_v2_pullback_cap_store import PullbackCapStore
from test_current_quantity_v2_pullback_sources import payload


def arguments(seconds=0, last=1356.8, day=15):
    document = payload()
    result = document['chart']['result'][0]
    shift = (day - 15) * 86400
    result['timestamp'] = [value + shift for value in result['timestamp']]
    meta = result['meta']
    meta['regularMarketPrice'] = last
    meta['regularMarketTime'] += shift + seconds
    for field in ('start', 'end'):
        meta['currentTradingPeriod']['regular'][field] += shift
    raw = json.dumps(document).encode()
    def time(value):
        return (datetime.fromisoformat(f'2026-10-{day}T{value}-04:00') +
                timedelta(seconds=seconds)).isoformat()
    return dict(raw=raw, expected_sha256=sha256(raw).hexdigest(),
        security_id='SNDK-ID', ticker='SNDK', session=f'2026-10-{day}',
        session_open=f'2026-10-{day}T09:30:00-04:00',
        session_close=f'2026-10-{day}T16:00:00-04:00',
        captured_at=time('09:32:15'), checked_at=time('09:32:16'), now=time('09:32:17'),
        rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120)


class CapStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'research.sqlite3'
        self.clock_value = '2026-10-15T09:32:30-04:00'
        self.store = self.new_store()

    def new_store(self, **changes):
        parameters = dict(clock=lambda: self.clock_value, max_history_rows=100, max_history_bytes=1000000)
        parameters.update(changes)
        return PullbackCapStore(self.path, **parameters)

    def count(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute('SELECT COUNT(*) FROM pullback_caps').fetchone()[0]

    def test_restart_replay_and_cash_independent_identity(self):
        first = self.store.candidate(**arguments())
        second = self.new_store().candidate(**arguments(1, 1450))
        self.assertEqual(first['candidate']['limit_price'], second['candidate']['limit_price'])
        self.assertEqual(second['cap_store_receipt']['prior_history_replayed'], 1)
        self.assertFalse(second['cap_store_receipt']['production_enabled'])
        for forbidden in ('cash', 'previous_cap'):
            with self.assertRaises(TypeError):
                self.store.candidate(**arguments(2), **{forbidden: 100})
        self.assertEqual(self.count(), 2)

    def test_session_and_policy_are_separate(self):
        self.store.candidate(**arguments())
        self.clock_value = '2026-10-16T09:32:30-04:00'
        next_day = self.store.candidate(**arguments(last=1450, day=16))
        self.assertEqual(next_day['cap_store_receipt']['ordinal'], 0)
        self.assertGreater(Fraction(next_day['candidate']['limit_price']), Fraction('1316.43'))
        self.clock_value = '2026-10-15T09:32:30-04:00'
        parameters = arguments(1)
        parameters['rebound_fraction'] = '1/4'
        self.assertEqual(self.store.candidate(**parameters)['cap_store_receipt']['ordinal'], 0)

    def test_old_input_and_invalid_bytes_leave_history_unchanged(self):
        self.store.candidate(**arguments(1))
        for seconds in (0, 1):
            with self.assertRaisesRegex(ValueError, 'CAP_INPUT_NOT_NEWER'):
                self.store.candidate(**arguments(seconds))
        parameters = arguments(2)
        parameters['raw'] = b'changed'
        with self.assertRaises(ValueError):
            self.store.candidate(**parameters)
        self.assertEqual(self.count(), 1)

    def test_tampered_result_rejected_even_with_recomputed_digest(self):
        from data.current_quantity_v2_pullback_entry import digest
        self.store.candidate(**arguments())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            parameters, result = connection.execute('SELECT parameters,result FROM pullback_caps').fetchone()
            changed = json.loads(result)
            changed['candidate']['limit_price'] = '1400'
            new_hash = digest(dict(ordinal=0, parameters=json.loads(parameters), result=changed, previous_hash=''))
            connection.execute('UPDATE pullback_caps SET result=?,record_hash=?',
                (json.dumps(changed, sort_keys=True, separators=(',', ':')), new_hash))
        with self.assertRaisesRegex(ValueError, 'CAP_HISTORY_REPLAY_MISMATCH'):
            self.store.candidate(**arguments(1))
        self.assertEqual(self.count(), 1)

    def test_concurrent_same_capture_commits_only_once(self):
        def submit():
            try:
                return self.store.candidate(**arguments())['cap_store_receipt']['ordinal']
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: submit(), range(2)))
        self.assertCountEqual(results, [0, 'CAP_INPUT_NOT_NEWER'])
        self.assertEqual(self.count(), 1)

    def test_stored_raw_corruption_rejected(self):
        self.store.candidate(**arguments())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE pullback_caps SET raw=?', (b'corrupted',))
        with self.assertRaisesRegex(ValueError, 'RAW_SHA256_MISMATCH'):
            self.store.candidate(**arguments(1))
        self.assertEqual(self.count(), 1)

    def test_missing_middle_history_rejected(self):
        for seconds in range(3):
            self.store.candidate(**arguments(seconds))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DELETE FROM pullback_caps WHERE ordinal=1')
        with self.assertRaisesRegex(ValueError, 'CAP_HISTORY_CHAIN_MISMATCH'):
            self.store.candidate(**arguments(3))
        self.assertEqual(self.count(), 2)

    def test_expiry_during_replay_rolls_back_insert(self):
        self.store.candidate(**arguments())
        times = iter(['2026-10-15T09:32:30-04:00', '2026-10-15T09:34:00-04:00'])
        store = self.new_store(clock=lambda: next(times))
        with self.assertRaisesRegex(ValueError, 'CAP_REFERENCE_EXPIRED_BEFORE_COMMIT'):
            store.candidate(**arguments(1))
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.store.candidate(**arguments(1))['cap_store_receipt']['ordinal'], 1)

    def test_server_clock_must_not_reverse_or_precede_request(self):
        times = iter(['2026-10-15T09:32:30-04:00', '2026-10-15T09:32:29-04:00'])
        with self.assertRaisesRegex(ValueError, 'SERVER_CLOCK_REVERSED'):
            self.new_store(clock=lambda: next(times)).candidate(**arguments())
        self.assertEqual(self.count(), 0)
        with self.assertRaisesRegex(ValueError, 'SERVER_CLOCK_BEFORE_REQUEST'):
            self.new_store(clock=lambda: '2026-10-15T09:32:16-04:00').candidate(**arguments())
        self.assertEqual(self.count(), 0)

    def test_row_budget_rejects_before_corrupt_history_replay(self):
        self.store.candidate(**arguments())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE pullback_caps SET raw=?', (b'corrupted',))
        with self.assertRaisesRegex(ValueError, 'CAP_HISTORY_BUDGET_EXCEEDED'):
            self.new_store(max_history_rows=1).candidate(**arguments(1))
        self.assertEqual(self.count(), 1)

    def test_byte_budget_current_and_prospective_history(self):
        with self.assertRaisesRegex(ValueError, 'CAP_HISTORY_BUDGET_EXCEEDED'):
            self.new_store(max_history_bytes=1).candidate(**arguments())
        self.assertEqual(self.count(), 0)
        self.store.candidate(**arguments())
        with closing(sqlite3.connect(self.path)) as connection:
            size = connection.execute('SELECT LENGTH(raw)+LENGTH(CAST(parameters AS BLOB))+'
                'LENGTH(CAST(result AS BLOB)) FROM pullback_caps').fetchone()[0]
        for budget in (size - 1, size + 1):
            with self.assertRaisesRegex(ValueError, 'CAP_HISTORY_BUDGET_EXCEEDED'):
                self.new_store(max_history_bytes=budget).candidate(**arguments(1))
        self.assertEqual(self.count(), 1)


if __name__ == '__main__':
    unittest.main()
