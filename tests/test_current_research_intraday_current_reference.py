from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
from threading import Event
import unittest
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from test_current_research_intraday_execution import NOW,payload,snapshot

RID='a'*24

class CurrentReferenceTests(unittest.TestCase):
    def test_latest_busy_failure_cannot_be_overwritten_by_slow_old_success(self):
        with tempfile.TemporaryDirectory() as root:
            entered,release=Event(),Event();calls=[];slow=[False]
            def fetch(ticker):
                calls.append(ticker)
                if slow[0]:entered.set();self.assertTrue(release.wait(5))
                return payload()
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=fetch,clock=lambda:NOW,journal=IntradayObservationJournal(root))
            service.preview(RID);self.assertEqual(service.current_reference(RID)['status'],'AVAILABLE')
            slow[0]=True
            with ThreadPoolExecutor(max_workers=1) as pool:
                old=pool.submit(service.preview,RID);self.assertTrue(entered.wait(5))
                pending=service.current_reference(RID);self.assertEqual(pending['status'],'PENDING');self.assertIsNone(pending['response'])
                latest=service.preview(RID);self.assertEqual(latest['stocks'][0]['reason'],'FETCH_IN_PROGRESS')
                failed=service.current_reference(RID);self.assertEqual(failed['status'],'UNAVAILABLE')
                release.set();self.assertEqual(old.result(10)['status'],'AVAILABLE')
            current=service.current_reference(RID)
            self.assertEqual(current,failed);self.assertIsNone(current['response'])
            self.assertEqual(current['attempt_token'],3);self.assertEqual(len(calls),2)
            self.assertEqual(current['current_receipt'],latest['observation_record'])
    def test_snapshot_failure_invalidates_before_fetch(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[];service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda ticker:(calls.append(ticker) or payload()),clock=lambda:NOW,journal=IntradayObservationJournal(root))
            service.preview(RID)
            def broken(_):raise ValueError('SNAPSHOT_SOURCE_CHANGED')
            service.snapshot_reader=broken
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_SOURCE_CHANGED'):service.preview(RID)
            current=service.current_reference(RID)
            self.assertEqual(current['status'],'UNAVAILABLE');self.assertEqual(current['reason'],'SNAPSHOT_SOURCE_CHANGED')
            self.assertIsNone(current['response']);self.assertIsNone(current['current_receipt']);self.assertEqual(len(calls),1)
    def test_missing_or_failed_receipt_never_authorizes_reference(self):
        class FailedJournal:
            def record(self,*args):raise OSError('DISK_FAILURE')
        for journal in (None,FailedJournal()):
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,journal=journal)
            result=service.preview(RID);self.assertEqual(result['status'],'AVAILABLE') # legacy HTTP contract unchanged
            current=service.current_reference(RID)
            self.assertEqual(current['status'],'UNAVAILABLE');self.assertEqual(current['reason'],'CURRENT_OBSERVATION_NOT_SAVED');self.assertIsNone(current['response'])
    def test_getter_deepcopy_expiry_and_no_extra_http_or_writes(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[NOW];calls=[];service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda ticker:(calls.append(ticker) or payload()),clock=lambda:clock[0],journal=IntradayObservationJournal(root))
            original=service.preview(RID);files={str(p):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            current=service.current_reference(RID);self.assertEqual(current['response'],original)
            current['response']['stocks'][0]['limit_price']='99999';current['current_receipt']['event_sha256']='changed'
            self.assertEqual(service.current_reference(RID)['response'],original)
            clock[0]+=timedelta(seconds=120)
            expired=service.current_reference(RID);self.assertEqual(expired['status'],'UNAVAILABLE');self.assertIsNone(expired['response'])
            self.assertEqual(len(calls),1);self.assertEqual(files,{str(p):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()})
    def test_restart_has_no_current_even_with_persisted_cap_and_journal(self):
        with tempfile.TemporaryDirectory() as root:
            journal=IntradayObservationJournal(Path(root)/'journal');caps=PersistentIntradayCapStore(Path(root)/'cap.sqlite3');calls=[]
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda ticker:(calls.append(ticker) or payload()),clock=lambda:NOW,journal=journal,cap_store=caps)
            first=service.preview(RID);self.assertEqual(service.current_reference(RID)['status'],'AVAILABLE')
            higher=payload();row=higher['chart']['result'][0];row['meta']['regularMarketPrice']+=10
            for k in ('open','high','low','close'):row['indicators']['quote'][0][k][0]+=10
            restarted=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda ticker:(calls.append(ticker) or higher),clock=lambda:NOW,journal=journal,cap_store=caps)
            current=restarted.current_reference(RID);self.assertEqual(current['status'],'NO_CURRENT_REFERENCE');self.assertIsNone(current['response']);self.assertEqual(len(calls),1)
            result=restarted.preview(RID);self.assertEqual(result['stocks'][0]['limit_price'],first['stocks'][0]['limit_price'])
            self.assertEqual(restarted.current_reference(RID)['status'],'AVAILABLE');self.assertNotEqual(service.process_boot_id,restarted.process_boot_id)

if __name__=='__main__':unittest.main()
