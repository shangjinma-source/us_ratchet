from datetime import datetime, timedelta
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from data.strategy_halt_aware_pullback_cap_store_v1 import PullbackCapStore
from data.strategy_account_live_pullback_cap_store import PullbackCapStore as LegacyStore
from test_strategy_halt_aware_pullback_sources_v1 import fixture
import test_strategy_halt_aware_pullback_sources_v1 as source_tests


def args(data=None, second=17):
    raw=json.dumps(fixture() if data is None else data).encode()
    return dict(raw=raw, expected_sha256=sha256(raw).hexdigest(),security_id='SNDK-ID',ticker='SNDK',
        session='2026-10-15',session_open='2026-10-15T09:30:00-04:00',session_close='2026-10-15T16:00:00-04:00',
        captured_at=f'2026-10-15T09:36:{second-2:02}-04:00',checked_at=f'2026-10-15T09:36:{second-1:02}-04:00',
        now=f'2026-10-15T09:36:{second:02}-04:00',rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120)


class CapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.now='2026-10-15T09:36:17-04:00'
    def tearDown(self):self.tmp.cleanup()
    def store(self, legacy=None, clock=None):
        return PullbackCapStore(self.root/'new.db',clock=clock or (lambda:self.now),
            max_history_rows=100,max_history_bytes=1000000,legacy_path=legacy)
    def legacy(self):
        s=LegacyStore(self.root/'old.db',clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000000)
        data=fixture()
        r=data['chart']['result'][0];r['meta']['regularMarketPrice']=90
        for values in r['indicators']['quote'][0].values():values[:]=[80]*6
        result=s.candidate(**args(data))
        return result
    def test_legacy_ceiling_preserved_and_source_read_only(self):
        old=self.legacy();before=(self.root/'old.db').read_bytes();self.now='2026-10-15T09:36:20-04:00'
        s=self.store(self.root/'old.db');new=s.candidate(**args(second=20))
        self.assertEqual(new['candidate']['limit_price'],old['candidate']['limit_price'])
        self.assertEqual(new['frozen_proof']['legacy_record_hash'],old['cap_store_receipt']['record_hash'])
        self.assertEqual((self.root/'old.db').read_bytes(),before)
        self.now='2026-10-15T09:36:23-04:00'
        self.assertEqual(s.candidate(**args(second=23))['candidate']['limit_price'],old['candidate']['limit_price'])
    def test_halt_bytes_replay(self):
        f=source_tests.HaltSourceTests(); s=self.store()
        first=s.candidate(**args(f.null_data()),**f.evidence())
        self.now='2026-10-15T09:36:20-04:00'
        second=s.candidate(**args(f.null_data(),20),**f.evidence())
        self.assertEqual(second['cap_store_receipt']['prior_history_replayed'],1)
        self.assertTrue(first['frozen_proof']['parameters']['halt_raw_hex'])
    def test_modified_raw_fails(self):
        s=self.store();s.candidate(**args())
        with closing(sqlite3.connect(self.root/'new.db')) as c, c:c.execute('UPDATE pullback_caps SET raw=?',(b'{}',))
        self.now='2026-10-15T09:36:20-04:00'
        with self.assertRaisesRegex(ValueError,'RAW_SHA256_MISMATCH'):s.candidate(**args(second=20))
    def test_modified_legacy_fails(self):
        self.legacy()
        with closing(sqlite3.connect(self.root/'old.db')) as c, c:c.execute('UPDATE pullback_caps SET raw=?',(b'{}',))
        self.now='2026-10-15T09:36:20-04:00'
        with self.assertRaisesRegex(ValueError,'RAW_SHA256_MISMATCH'):self.store(self.root/'old.db').candidate(**args(second=20))
    def test_expired_before_commit_rolls_back(self):
        clocks=iter([self.now,'2026-10-15T09:40:00-04:00'])
        s=self.store(clock=lambda:next(clocks))
        with self.assertRaisesRegex(ValueError,'EXPIRED_BEFORE_COMMIT'):s.candidate(**args())
        with closing(sqlite3.connect(self.root/'new.db')) as c, c:self.assertEqual(c.execute('SELECT COUNT(*) FROM pullback_caps').fetchone()[0],0)
    def test_legacy_extension_after_migration_is_not_silent_reset(self):
        self.legacy(); self.now='2026-10-15T09:36:20-04:00'
        s=self.store(self.root/'old.db');s.candidate(**args(second=20))
        self.now='2026-10-15T09:36:23-04:00'
        old=LegacyStore(self.root/'old.db',clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000000)
        old.candidate(**args(second=23))
        self.now='2026-10-15T09:36:26-04:00'
        with self.assertRaisesRegex(ValueError,'LEGACY_SNAPSHOT_CHANGED'):s.candidate(**args(second=26))

    def test_halt_snapshot_tamper_rejected(self):
        f=source_tests.HaltSourceTests();s=self.store()
        s.candidate(**args(f.null_data()),**f.evidence())
        with closing(sqlite3.connect(self.root/'new.db')) as c, c:
            p=json.loads(c.execute('SELECT parameters FROM pullback_caps').fetchone()[0])
            p['halt_raw_hex']=b'changed'.hex()
            c.execute('UPDATE pullback_caps SET parameters=?',(json.dumps(p),))
        self.now='2026-10-15T09:36:20-04:00'
        with self.assertRaises(ValueError):s.candidate(**args(f.null_data(),20),**f.evidence())

    def test_budget_counts_encoded_halt_evidence(self):
        f=source_tests.HaltSourceTests()
        s=PullbackCapStore(self.root/'small.db',clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000)
        with self.assertRaisesRegex(ValueError,'CAP_HISTORY_BUDGET'):s.candidate(**args(f.null_data()),**f.evidence())
        with closing(sqlite3.connect(self.root/'small.db')) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM pullback_caps').fetchone()[0],0)

    def test_missing_legacy_is_not_empty_history(self):
        with self.assertRaisesRegex(ValueError,'LEGACY_STORE_MISSING'):self.store(self.root/'missing.db').candidate(**args())

if __name__=='__main__':unittest.main()
