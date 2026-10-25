from contextlib import closing
from datetime import datetime,timedelta
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json,sqlite3,tempfile,time,unittest
from threading import Event, Thread
from data.strategy_halt_aware_pullback_cap_store_v2 import PullbackCapStore,read_blob
from data.strategy_account_live_pullback_cap_store import PullbackCapStore as LegacyStore
from test_strategy_halt_aware_pullback_cap_store_v1 import args
import test_strategy_halt_aware_pullback_sources_v1 as sources


class DeduplicatedCapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.now=args()['now']
    def tearDown(self):self.temp.cleanup()
    def store(self,**extra):
        return PullbackCapStore(self.root/'new.db',clock=lambda:self.now,max_history_rows=1000,
                                max_history_bytes=8*1024*1024,**extra)
    def table_count(self,name):
        with closing(sqlite3.connect(self.root/'new.db')) as c:return c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
    def test_100_large_source_refreshes_remain_bounded(self):
        helper=sources.HaltSourceTests();evidence=helper.evidence()
        evidence['halt_raw']+=b'<!--'+b'x'*600000+b'-->'
        evidence['halt_receipt'].update(bytes=len(evidence['halt_raw']),raw_sha256=sha256(evidence['halt_raw']).hexdigest())
        store=self.store();begin=time.perf_counter();durations=[];limits=[]
        base=datetime.fromisoformat(args()['now'])
        for i in range(100):
            request=args(helper.null_data());now=base+timedelta(seconds=i/5)
            self.now=now.isoformat();request.update(now=self.now,captured_at=(now-timedelta(seconds=2)).isoformat(),checked_at=(now-timedelta(seconds=1)).isoformat())
            evidence['halt_receipt'].update(started_at=(now-timedelta(seconds=4)).isoformat(),received_at=(now-timedelta(seconds=3)).isoformat())
            started=time.perf_counter();result=store.candidate(**request,**evidence);durations.append(time.perf_counter()-started)
            limits.append(Fraction(result['candidate']['limit_price']))
        elapsed=time.perf_counter()-begin
        self.assertEqual(self.table_count('halt_cap_records_v2'),100)
        self.assertEqual(self.table_count('cap_evidence_blobs'),3)
        self.assertLess(result['cap_store_receipt']['budget']['total_bytes'],3*1024*1024)
        self.assertTrue(all(b<=a for a,b in zip(limits,limits[1:])))
        self.assertLess(max(durations),5,'Each refresh must stay materially below 120s quote freshness')
        report=dict(refreshes=100,source_bytes=len(evidence['halt_raw']),elapsed_seconds=elapsed,
                    maximum_refresh_seconds=max(durations),last_refresh_seconds=durations[-1],
                    budget=result['cap_store_receipt']['budget'],blob_count=3,cap_never_raised=True)
        Path('tmp/halt_cap_v2_stress_20261023.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def test_missing_blob_not_recreated(self):
        store=self.store();store.candidate(**args())
        with closing(sqlite3.connect(self.root/'new.db')) as c,c:c.execute('DELETE FROM cap_evidence_blobs')
        self.now=args(second=20)['now']
        with self.assertRaisesRegex(ValueError,'CAP_BLOB_MISSING'):store.candidate(**args(second=20))
        self.assertEqual(self.table_count('cap_evidence_blobs'),0)
        self.assertEqual(self.table_count('halt_cap_records_v2'),1)
    def test_tampered_blob_fails(self):
        store=self.store();store.candidate(**args())
        with closing(sqlite3.connect(self.root/'new.db')) as c,c:c.execute("UPDATE cap_evidence_blobs SET payload=?",(b'tampered',))
        self.now=args(second=20)['now']
        with self.assertRaisesRegex(ValueError,'CAP_BLOB_CHANGED'):store.candidate(**args(second=20))
    def test_expiry_rolls_back_blobs_and_record(self):
        ticks=iter([self.now,'2026-10-15T09:40:00-04:00'])
        store=PullbackCapStore(self.root/'new.db',clock=lambda:next(ticks),max_history_rows=100,max_history_bytes=1000000)
        with self.assertRaisesRegex(ValueError,'EXPIRED_BEFORE_COMMIT'):store.candidate(**args())
        self.assertEqual(self.table_count('cap_evidence_blobs'),0);self.assertEqual(self.table_count('halt_cap_records_v2'),0)
    def test_legacy_ceiling_and_readonly_migration(self):
        oldpath=self.root/'legacy.db';old=LegacyStore(oldpath,clock=lambda:self.now,max_history_rows=100,max_history_bytes=1000000)
        data=sources.fixture();r=data['chart']['result'][0];r['meta']['regularMarketPrice']=90
        for values in r['indicators']['quote'][0].values():values[:]=[80]*6
        cap=old.candidate(**args(data));before=oldpath.read_bytes()
        self.now=args(second=20)['now'];store=self.store(legacy_path=oldpath)
        result=store.candidate(**args(second=20))
        self.assertEqual(result['candidate']['limit_price'],cap['candidate']['limit_price'])
        self.assertEqual(result['frozen_proof']['legacy_record_hash'],cap['cap_store_receipt']['record_hash'])
        self.assertEqual(before,oldpath.read_bytes())
    def test_reader_lock_wait_past_expiry_rolls_back(self):
        called=Event();errors=[]
        store=self.store()
        def clock():
            called.set()
            return self.now
        store.clock=clock
        with closing(sqlite3.connect(self.root/'new.db')) as reader:
            reader.execute('BEGIN')
            reader.execute('SELECT COUNT(*) FROM halt_cap_records_v2').fetchone()
            def run():
                try:store.candidate(**args())
                except Exception as error:errors.append(error)
            worker=Thread(target=run);worker.start()
            self.assertTrue(called.wait(2));time.sleep(.15)
            self.assertTrue(worker.is_alive())
            self.now='2026-10-15T09:40:00-04:00'
            reader.rollback();worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors),1)
        self.assertIn('EXPIRED_BEFORE_COMMIT',str(errors[0]))
        self.assertEqual(self.table_count('cap_evidence_blobs'),0)
        self.assertEqual(self.table_count('halt_cap_records_v2'),0)

    def test_budget_rolls_back(self):
        store=PullbackCapStore(self.root/'new.db',clock=lambda:self.now,max_history_rows=100,max_history_bytes=100)
        with self.assertRaisesRegex(ValueError,'CAP_HISTORY_BUDGET'):store.candidate(**args())
        self.assertEqual(self.table_count('cap_evidence_blobs'),0)
    def test_metadata_reference_size_tamper(self):
        store=self.store();store.candidate(**args())
        with closing(sqlite3.connect(self.root/'new.db')) as c,c:
            parameters=json.loads(c.execute('SELECT parameters FROM halt_cap_records_v2').fetchone()[0]);parameters['raw_blob']['bytes']+=1
            c.execute('UPDATE halt_cap_records_v2 SET parameters=?',(json.dumps(parameters),))
        self.now=args(second=20)['now']
        with self.assertRaisesRegex(ValueError,'CAP_BLOB_CHANGED'):store.candidate(**args(second=20))

if __name__=='__main__':unittest.main()
