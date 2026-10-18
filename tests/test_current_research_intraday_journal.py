import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_execution import IntradayExecutionService
from test_current_research_intraday_execution import NOW,payload,snapshot

class JournalTests(unittest.TestCase):
    def test_atomic_idempotence_concurrency_and_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=IntradayObservationJournal(directory)
            event=dict(event_id='a'*32,request_started_at=NOW.isoformat(),response={'status':'UNAVAILABLE'})
            captures=[dict(role='FETCHED',captured_at=NOW.isoformat(),payload=b'{"original": 1}')]
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:journal.record(event,captures),range(8)))
            self.assertTrue(all(r==results[0] for r in results))
            result=results[0];saved=journal.read_event(result['event_path'],expected_sha256=result['event_sha256'])
            self.assertEqual(saved['captures'][0]['encoding'],'ORIGINAL_HTTP_RESPONSE_BYTES')
            with self.assertRaisesRegex(ValueError,'CONFLICT'):journal.record(dict(event,response={}),captures)
            self.assertEqual(len(list(Path(directory).glob('raw/*'))),1)
            (Path(directory)/saved['captures'][0]['path']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'RAW_HASH'):journal.read_event(result['event_path'],expected_sha256=result['event_sha256'])

    def test_service_pending_keeps_both_capture_times_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=IntradayObservationJournal(directory);clock=[NOW];p=payload()
            p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+7
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:deepcopy(p),clock=lambda:clock[0],journal=journal)
            first=service.preview('a'*24)
            self.assertEqual(first['stocks'][0]['reason'],'LAST_QUOTE_FUTURE')
            self.assertEqual(first['observation_record']['status'],'SAVED')
            clock[0]+=timedelta(seconds=10);p['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())+7
            second=service.preview('a'*24);receipt=second['observation_record']
            saved=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
            self.assertNotIn('observation_record',saved['response'])
            self.assertEqual([c['role'] for c in saved['captures']],['FETCHED','USED'])
            self.assertEqual(saved['captures'][1]['captured_at'],NOW.isoformat())
            self.assertEqual(saved['captures'][0]['captured_at'],clock[0].isoformat())
            self.assertTrue(all(c['encoding']=='SYNTHETIC_NORMALIZED_JSON' for c in saved['captures']))
            service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
            failed=service.preview('a'*24);receipt=failed['observation_record']
            event=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
            self.assertEqual(event['captures'],[]);self.assertEqual(event['response']['stocks'][0]['reason'],'offline')

    def test_verified_response_survives_repeated_future_ticks(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=IntradayObservationJournal(directory);clock=[NOW]
            def fetch(_):
                p=payload();p['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())+7
                return json.dumps(p).encode('utf-8')
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=fetch,clock=lambda:clock[0],journal=journal)
            self.assertEqual(service.preview('a'*24)['status'],'UNAVAILABLE')
            clock[0]=NOW+timedelta(seconds=10)
            self.assertEqual(service.preview('a'*24)['status'],'AVAILABLE')
            clock[0]=NOW+timedelta(seconds=11)
            result=service.preview('a'*24);row=result['stocks'][0]
            self.assertEqual(row['quote_response_origin'],'VERIFIED_RESPONSE_STILL_FRESH')
            self.assertEqual(row['quote_response_age_seconds'],11)
            receipt=result['observation_record'];event=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
            used=event['captures'][1]
            self.assertEqual(used['role'],'USED');self.assertEqual(used['captured_at'],NOW.isoformat())
            raw=json.loads((Path(directory)/used['path']).read_bytes())
            self.assertEqual(raw['chart']['result'][0]['meta']['regularMarketTime'],int(NOW.timestamp())+7)
            self.assertEqual(used['encoding'],'ORIGINAL_HTTP_RESPONSE_BYTES')
            original_fetch=service.fetch
            service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
            self.assertEqual(service.preview('a'*24)['stocks'][0]['reason'],'offline')
            bad=payload();bad['chart']['result'][0]['meta']['currency']='HKD'
            service.fetch=lambda _:bad
            self.assertEqual(service.preview('a'*24)['stocks'][0]['reason'],'QUOTE_IDENTITY_CURRENCY_MISMATCH')
            # New response has a current full minute but a future tick; old evidence expired.
            clock[0]=NOW+timedelta(seconds=131)
            def newer(_):
                p=payload();r=p['chart']['result'][0]
                r['meta']['regularMarketTime']=int(clock[0].timestamp())+7
                r['timestamp'][0]+=120
                return p
            service.fetch=newer
            expired=service.preview('a'*24)
            self.assertEqual(expired['status'],'UNAVAILABLE')
            self.assertIsNone(expired['stocks'][0]['limit_price'])
            self.assertNotIn('fresh_cash_reference',expired['stocks'][0])

    def test_sequence_and_prior_cap_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=IntradayObservationJournal(directory)
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,journal=journal)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results=list(pool.map(lambda _:service.preview('a'*24),range(6)))
            ordered=sorted(results,key=lambda r:r['observation_sequence'])
            self.assertEqual([r['observation_sequence'] for r in ordered],list(range(1,7)))
            first=ordered[0]['observation_record']['event_id']
            self.assertIsNone(ordered[0]['stocks'][0]['prior_cap_event_id'])
            for response in ordered[1:]:
                self.assertEqual(response['stocks'][0]['prior_cap_event_id'],first)
                self.assertEqual(response['stocks'][0]['cap_origin_event_id'],first)

    def test_write_symlink_rejected(self):
        for branch in ('raw','events'):
            with tempfile.TemporaryDirectory() as directory,tempfile.TemporaryDirectory() as outside:
                root=Path(directory)
                try:(root/branch).symlink_to(outside,target_is_directory=True)
                except OSError as error:self.skipTest(str(error))
                journal=IntradayObservationJournal(root)
                event=dict(event_id='b'*32,request_started_at=NOW.isoformat(),response={})
                captures=[dict(payload=b'raw')] if branch=='raw' else []
                with self.assertRaisesRegex(ValueError,'WRITE_PATH'):journal.record(event,captures)
                self.assertFalse(list(Path(outside).rglob('*.json')))
                self.assertFalse(list(Path(outside).rglob('*.bin')))

    def test_journal_failure_keeps_quote_without_saved_claim(self):
        class Broken:
            def record(self,*args):raise OSError('disk unavailable')
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,journal=Broken())
        response=service.preview('a'*24)
        self.assertEqual(response['status'],'AVAILABLE')
        self.assertEqual(response['stocks'][0]['limit_price'],'1412.12')
        self.assertEqual(response['observation_record']['status'],'FAILED')
        self.assertNotIn('event_sha256',response['observation_record'])

if __name__=='__main__':unittest.main()
