from copy import deepcopy
from datetime import timedelta,datetime
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import data.current_research_intraday_journal_reference as adapter
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_journal_reference import read_journal_execution_reference
from test_current_research_intraday_execution import NOW,payload,snapshot

RID='a'*24

def fixture(directory, pending=False, cross_boot=False):
    root=Path(directory);clock=[NOW];journal=IntradayObservationJournal(root/'journal');cap=PersistentIntradayCapStore(root/'caps.db');responses=[]
    p=payload()
    if pending:p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+7
    service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:deepcopy(p),clock=lambda:clock[0],journal=journal,cap_store=cap)
    responses.append(service.preview(RID))
    if pending:
        clock[0]+=timedelta(seconds=8);p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+15
        responses.append(service.preview(RID))
    if cross_boot:
        p=payload();p['chart']['result'][0]['meta']['regularMarketPrice']+=100
        for key in ('open','high','low','close'):p['chart']['result'][0]['indicators']['quote'][0][key][0]+=100
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:deepcopy(p),clock=lambda:clock[0],journal=journal,cap_store=cap)
        responses.append(service.preview(RID))
    authority=service.current_reference(RID)
    event_hashes={r['observation_record']['event_path']:r['observation_record']['event_sha256'] for r in responses}
    binding=dict(account_id='synthetic-account',target_month='2026-10',research_id=RID,security_id='sndk',ticker='SNDK',session='2026-10-15')
    args=dict(root=journal.root,binding=binding,current_reference=authority,event_hashes=event_hashes,now=clock[0])
    return dict(root=journal.root,binding=binding,current_reference=authority,event_hashes=event_hashes,now=clock[0],args=args,
                reference=read_journal_execution_reference(**args),service=service,clock=clock)


class JournalReferenceTests(unittest.TestCase):
    def test_cross_boot_original_cap_and_sell_same_raw(self):
        with tempfile.TemporaryDirectory() as root:
            f=fixture(root,cross_boot=True);r=f['reference']
            self.assertEqual(Fraction(r['buy_limit']),Fraction('1412.12'))
            self.assertEqual(Fraction(r['sell_limit']),Fraction('1512.35'))
            self.assertEqual(r['scope_id'],'synthetic-account:2026-10');self.assertFalse(r['latest_tip_authenticated'])
            self.assertNotIn('receipt_paths',r);self.assertEqual(r,read_journal_execution_reference(**dict(f['args'],now=f['now']+timedelta(seconds=1))))
            files={p:(f['root']/p).read_bytes() for p in r['source_hashes']}
            self.assertEqual(r,read_journal_execution_reference(**dict(f['args'],root='',frozen_files=files)))
    def test_pending_capture_matures_without_rewriting_capture(self):
        with tempfile.TemporaryDirectory() as root:
            f=fixture(root,pending=True);r=f['reference']
            self.assertLess(datetime.fromisoformat(r['captured_at']),datetime.fromisoformat(r['last_at']));self.assertLess(datetime.fromisoformat(r['last_at']),datetime.fromisoformat(r['checked_at']))
            self.assertEqual(r['captured_at'],NOW.isoformat());self.assertEqual(r['checked_at'],(NOW+timedelta(seconds=8)).isoformat())
            self.assertEqual(read_journal_execution_reference(**dict(f['args'],current_reference_reader=f['service'].current_reference)),r)
    def test_missing_dependency_tamper_mapping_and_expiry_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            f=fixture(root,cross_boot=True)
            bad=deepcopy(f['args']);bad['event_hashes']={bad['current_reference']['current_receipt']['event_path']:bad['current_reference']['current_receipt']['event_sha256']}
            with self.assertRaisesRegex(ValueError,'DEPENDENCY'):read_journal_execution_reference(**bad)
            for key,value in [('security_id','wrong'),('ticker','OTHER'),('target_month','2026-11')]:
                bad=deepcopy(f['args']);bad['binding'][key]=value
                with self.assertRaises(ValueError):read_journal_execution_reference(**bad)
            with self.assertRaises(ValueError):read_journal_execution_reference(**dict(f['args'],now=f['now']+timedelta(seconds=121)))
            path=next(p for p in f['reference']['source_hashes'] if p.startswith('raw/'));(f['root']/path).write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'HASH'):read_journal_execution_reference(**f['args'])
    def test_bounded_events_unique_bytes_live_and_frozen(self):
        with tempfile.TemporaryDirectory() as root:
            f=fixture(root,cross_boot=True)
            files={p:(f['root']/p).read_bytes() for p in f['reference']['source_hashes']}
            total=sum(map(len,files.values()))
            with patch.object(adapter,'MAX_EVENTS',1):
                with self.assertRaises(ValueError):read_journal_execution_reference(**f['args'])
            with patch.object(adapter,'MAX_TOTAL_BYTES',total):
                self.assertEqual(read_journal_execution_reference(**f['args']),f['reference'])
                self.assertEqual(read_journal_execution_reference(**dict(f['args'],frozen_files=files)),f['reference'])
            with patch.object(adapter,'MAX_TOTAL_BYTES',total-1):
                with self.assertRaises(ValueError):read_journal_execution_reference(**f['args'])
                with self.assertRaises(ValueError):read_journal_execution_reference(**dict(f['args'],frozen_files=files))
            with patch.object(adapter,'MAX_TOTAL_BYTES',0),patch.object(Path,'read_bytes',side_effect=AssertionError('must reject before read')):
                with self.assertRaisesRegex(ValueError,'BUDGET'):read_journal_execution_reference(**f['args'])

    def test_no_current_failed_attempt_and_authority_changes_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            f=fixture(root)
            for status in ('PENDING','UNAVAILABLE','NO_CURRENT_REFERENCE'):
                a=deepcopy(f['args']);a['current_reference']['status']=status
                with self.assertRaisesRegex(ValueError,'NO_AVAILABLE'):read_journal_execution_reference(**a)
            calls=[]
            def changed(rid):
                calls.append(rid);a=deepcopy(f['current_reference'])
                if len(calls)>1:a['status']='PENDING'
                return a
            with self.assertRaisesRegex(ValueError,'AUTHORITY_CHANGED'):read_journal_execution_reference(**dict(f['args'],current_reference_reader=changed))
            f['service'].fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
            f['service'].preview(RID)
            with self.assertRaisesRegex(ValueError,'NO_AVAILABLE'):read_journal_execution_reference(**dict(f['args'],current_reference=f['service'].current_reference(RID)))

if __name__=='__main__':unittest.main()
