from contextlib import closing
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from test_current_research_intraday_execution import NOW,payload,snapshot

RID='a'*24

class OutboxTests(unittest.TestCase):
    def fixture(self,root,clock=None,fetch=payload):
        store=PersistentIntradayCapStore(Path(root)/'caps.db');journal=IntradayObservationJournal(Path(root)/'journal')
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:fetch(),clock=lambda:(clock or [NOW])[0],journal=journal,cap_store=store)
        return service,store,journal
    def package(self,store):
        with closing(sqlite3.connect(store.path)) as c:
            rows=c.execute('SELECT package,published FROM cap_outbox ORDER BY rowid').fetchall()
        return [(json.loads(raw),flag) for raw,flag in rows]
    def test_failed_publication_restart_recovers_exact_bytes_then_new_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            with patch.object(journal,'publish_prepared',side_effect=OSError('disk unavailable')):
                failed=service.preview(RID)
            self.assertEqual(failed['status'],'UNAVAILABLE');self.assertIsNone(failed['stocks'][0]['limit_price'])
            package,flag=self.package(store)[0];self.assertEqual(flag,0)
            original=deepcopy(package)
            restarted,_,_=self.fixture(root)
            response=restarted.preview(RID);self.assertEqual(response['status'],'AVAILABLE',response)
            receipt=package['receipt'];event=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
            self.assertEqual(event['delivery_status'],'NOT_ATTESTED');self.assertEqual(event['purpose'],'OBSERVED_BEFORE_DELIVERY')
            self.assertEqual(response['stocks'][0]['cap_origin_event_id'],event['event_id'])
            self.assertEqual(self.package(store)[0],(original,1))
    def test_recovery_never_falls_back_when_new_fetch_fails(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            with patch.object(journal,'publish_prepared',side_effect=OSError('disk')):service.preview(RID)
            restarted,_,_=self.fixture(root,fetch=lambda:(_ for _ in ()).throw(OSError('network failed')))
            result=restarted.preview(RID)
            self.assertEqual(result['status'],'UNAVAILABLE');self.assertNotIn('fresh_cash_reference',result['stocks'][0])
            package,published=self.package(store)[0];self.assertEqual(published,1)
            self.assertTrue((journal.root/package['receipt']['event_path']).exists())
    def test_partial_publish_and_repeated_exact_package(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root);write=journal._write
            def fail_event(path,raw):
                if path.startswith('events/'):raise OSError('event failed after raw')
                write(path,raw)
            with patch.object(journal,'_write',side_effect=fail_event):service.preview(RID)
            self.assertTrue(list((journal.root/'raw').glob('*.bin')))
            package,_=self.package(store)[0]
            first=journal.publish_prepared(package);second=journal.publish_prepared(package);self.assertEqual(first,second)
            bad=deepcopy(package);bad['files'][0]['path']='../escape'
            with self.assertRaisesRegex(ValueError,'PATH'):journal.publish_prepared(bad)
            bad=deepcopy(package);bad['files'][0]['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'HASH'):journal.publish_prepared(bad)
    def test_slow_publication_keeps_observation_time_but_withholds_price(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[NOW];service,store,journal=self.fixture(root,clock);publish=journal.publish_prepared
            def slow(package):
                result=publish(package);clock[0]+=timedelta(seconds=121);return result
            with patch.object(journal,'publish_prepared',side_effect=slow):result=service.preview(RID)
            self.assertEqual(result['status'],'UNAVAILABLE');self.assertIsNone(result['stocks'][0]['limit_price'])
            self.assertEqual(result['observation_record']['status'],'SAVED')
            package,_=self.package(store)[0];r=package['receipt'];event=journal.read_event(r['event_path'],expected_sha256=r['event_sha256'])
            self.assertEqual(event['response']['stocks'][0]['checked_at'],NOW.isoformat())
            self.assertEqual(event['delivery_status'],'NOT_ATTESTED')
    def test_transaction_failure_rolls_back_cap_and_outbox(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            class BadCommit(sqlite3.Connection):
                def commit(self):raise sqlite3.OperationalError('commit failed')
            connect=sqlite3.connect
            with patch('data.current_research_intraday_cap_store.sqlite3.connect',side_effect=lambda *a,**kw:connect(*a,**kw,factory=BadCommit)):
                response=service.preview(RID)
            self.assertEqual(response['status'],'UNAVAILABLE')
            with closing(connect(store.path)) as c:
                self.assertEqual(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),[])
            self.assertEqual(service.preview(RID)['status'],'AVAILABLE')
    def test_publish_mark_failure_republishes_identical_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            connect=sqlite3.connect
            class BadMark(sqlite3.Connection):
                def execute(self,sql,*args):
                    if sql.startswith('UPDATE cap_outbox SET published=1'):
                        raise sqlite3.OperationalError('mark failed')
                    return super().execute(sql,*args)
            with patch('data.current_research_intraday_cap_store.sqlite3.connect',side_effect=lambda *a,**kw:connect(*a,**kw,factory=BadMark)):
                response=service.preview(RID)
            self.assertEqual(response['status'],'UNAVAILABLE')
            package,published=self.package(store)[0];self.assertEqual(published,0)
            path=journal.root/package['receipt']['event_path'];original=path.read_bytes()
            self.assertEqual(service.preview(RID)['status'],'AVAILABLE')
            self.assertEqual(path.read_bytes(),original);self.assertEqual(self.package(store)[0][1],1)

    def test_published_origin_modified_event_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            result=service.preview(RID);self.assertEqual(result['status'],'AVAILABLE')
            package,published=self.package(store)[0];self.assertEqual(published,1)
            path=journal.root/package['receipt']['event_path']
            event=json.loads(path.read_bytes());event['delivery_status']='TAMPERED'
            path.write_text(json.dumps(event),encoding='utf-8')
            with patch.object(service,'fetch',side_effect=AssertionError('must not fetch')) as fetch:
                rejected=service.preview(RID)
            self.assertEqual(fetch.call_count,0)
            self.assertEqual(rejected['status'],'UNAVAILABLE')
            self.assertEqual(rejected['stocks'][0]['reason'],'EVENT_HASH_MISMATCH')
            with closing(sqlite3.connect(store.path)) as c:
                self.assertEqual(c.execute('SELECT cents FROM session_caps').fetchone()[0],141212)

    def test_valid_integer_cap_drift_rejected_before_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            self.assertEqual(service.preview(RID)['status'],'AVAILABLE')
            with closing(sqlite3.connect(store.path)) as c:
                c.execute('UPDATE session_caps SET cents=999999');c.commit()
            with patch.object(service,'fetch',side_effect=AssertionError('must not fetch')) as fetch:
                result=service.preview(RID)
            self.assertEqual(fetch.call_count,0);self.assertEqual(result['status'],'UNAVAILABLE')
            self.assertEqual(result['stocks'][0]['reason'],'ROW_ORIGIN_CAP_MISMATCH')
            with closing(sqlite3.connect(store.path)) as c:
                self.assertEqual(c.execute('SELECT cents FROM session_caps').fetchone()[0],999999)

    def test_legacy_missing_origin_fail_closed_without_reset(self):
        with tempfile.TemporaryDirectory() as root:
            service,store,journal=self.fixture(root)
            store.lower(research_id=RID,security_id='sndk',ticker='SNDK',session='2026-10-15',observed_cap='100',event_id='b'*32)
            result=service.preview(RID);self.assertEqual(result['status'],'UNAVAILABLE')
            with closing(sqlite3.connect(store.path)) as c:self.assertEqual(c.execute('SELECT cents FROM session_caps').fetchone()[0],10000)

if __name__=='__main__':unittest.main()
