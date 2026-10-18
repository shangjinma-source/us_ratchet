import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_review import review_intraday_session
from test_current_research_intraday_execution import NOW, payload, snapshot

class PersistentReviewTests(unittest.TestCase):
    def fixture(self, root):
        journal = Path(root)/'journal'
        store = Path(root)/'cap.sqlite3'
        responses=[]
        for i in range(2):
            data=payload();row=data['chart']['result'][0]
            row['meta']['regularMarketPrice'] += i*10
            for key in ('open','high','low','close'):
                row['indicators']['quote'][0][key][0] += i*10
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _, d=data:d,
                clock=lambda i=i:NOW+timedelta(seconds=i),journal=IntradayObservationJournal(journal),
                cap_store=PersistentIntradayCapStore(store))
            # Force reverse lexicographic boot order to exercise damage propagation.
            service.process_boot_id=('f' if i==0 else 'a')*32
            responses.append(service.preview('a'*24))
        return journal,responses

    def test_real_restart_journal_chain(self):
        with tempfile.TemporaryDirectory() as root:
            journal,rows=self.fixture(root)
            self.assertEqual(rows[0]['stocks'][0]['limit_price'],rows[1]['stocks'][0]['limit_price'])
            result=review_intraday_session(journal,'2026-10-15')
            self.assertEqual(result['status'],'REVIEWED_LOCAL_OBSERVATIONS',result)

    def test_other_boot_lower_cap_between_same_boot_requests(self):
        with tempfile.TemporaryDirectory() as root:
            journal=Path(root)/'journal';store=Path(root)/'cap.sqlite3'
            clock=[NOW];data=[payload()]
            services=[IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:data[0],
                clock=lambda:clock[0],journal=IntradayObservationJournal(journal),
                cap_store=PersistentIntradayCapStore(store)) for _ in range(2)]
            services[0].preview('a'*24)
            clock[0]+=timedelta(seconds=1)
            row=data[0]['chart']['result'][0];row['meta']['regularMarketPrice']-=10
            for key in ('open','high','low','close'):row['indicators']['quote'][0][key][0]-=10
            services[1].preview('a'*24)
            clock[0]+=timedelta(seconds=1);services[0].preview('a'*24)
            report=review_intraday_session(journal,'2026-10-15')
            self.assertEqual(report['status'],'REVIEWED_LOCAL_OBSERVATIONS',report)

    def test_damaged_cross_boot_root_propagates_through_same_boot_decreases(self):
        with tempfile.TemporaryDirectory() as root:
            journal=Path(root)/'journal';store=Path(root)/'cap.sqlite3'
            clock=[NOW];data=[payload()]
            def service(boot):
                value=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:data[0],
                    clock=lambda:clock[0],journal=IntradayObservationJournal(journal),
                    cap_store=PersistentIntradayCapStore(store))
                value.process_boot_id=boot*32;return value
            first=service('f').preview('a'*24);later=service('a')
            for i in range(3):
                clock[0]+=timedelta(seconds=1)
                if i:
                    row=data[0]['chart']['result'][0];row['meta']['regularMarketPrice']-=10
                    for key in ('open','high','low','close'):row['indicators']['quote'][0][key][0]-=10
                later.preview('a'*24)
            path=journal/first['observation_record']['event_path'];event=json.loads(path.read_bytes())
            event['response']['stocks'][0]['cap_origin_event_id']='e'*32
            path.write_text(json.dumps(event),encoding='utf8')
            report=review_intraday_session(journal,'2026-10-15')
            rows=[r for r in report['records'] if r['process_boot_id']=='a'*32]
            self.assertEqual(len(rows),3)
            self.assertTrue(all('SOURCE_CAP_EVENT_INVALID' in str(r['issues']) for r in rows),rows)

    def test_legacy_mode_and_security_mismatch_rejected(self):
        for field,value in [('cap_persistence','PROCESS_MEMORY_ONLY_RESET_ON_RESTART'),('security_id','wrong')]:
            with tempfile.TemporaryDirectory() as root:
                journal,rows=self.fixture(root)
                path=journal/rows[1]['observation_record']['event_path']
                event=json.loads(path.read_bytes())
                if field=='security_id':event['research_binding']['selected_security']['security_id']=value
                else:event['response']['stocks'][0][field]=value
                path.write_text(json.dumps(event),encoding='utf8')
                report=review_intraday_session(journal,'2026-10-15')
                self.assertIn('CAP_EVENT_SCOPE_MISMATCH',str(report))

    def test_damaged_later_sorted_source_propagates(self):
        with tempfile.TemporaryDirectory() as root:
            journal,rows=self.fixture(root)
            path=journal/rows[0]['observation_record']['event_path']
            event=json.loads(path.read_bytes());event['response']['stocks'][0]['cap_origin_event_id']='e'*32
            path.write_text(json.dumps(event),encoding='utf8')
            report=review_intraday_session(journal,'2026-10-15')
            target=next(r for r in report['records'] if r['process_boot_id']=='a'*32)
            self.assertIn('SOURCE_CAP_EVENT_INVALID',str(target['issues']))

if __name__=='__main__': unittest.main()
