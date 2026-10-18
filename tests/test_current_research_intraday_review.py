import json
import tempfile
import unittest
from pathlib import Path
from datetime import timedelta
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_review import review_intraday_session
from test_current_research_intraday_execution import NOW,payload,snapshot

class ReviewTests(unittest.TestCase):
    def service(self,root):
        return IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:NOW,journal=IntradayObservationJournal(root))
    def test_saved_success_failure_and_raw_replay(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);service.preview('a'*24);service.preview('a'*24)
            service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
            service.preview('a'*24)
            result=review_intraday_session(root,'2026-10-15')
            self.assertEqual(result['status'],'REVIEWED_LOCAL_OBSERVATIONS',result)
            self.assertEqual(result['event_count'],3)
            self.assertTrue(result['records'][0]['observations'][0]['raw_replay_verified'])
            self.assertEqual(result['records'][2]['observations'][0]['reason'],'offline')
    def test_hash_corruption_and_missing_cap_predecessor(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);first=service.preview('a'*24);service.preview('a'*24)
            (Path(root)/first['observation_record']['event_path']).unlink()
            result=review_intraday_session(root,'2026-10-15')
            self.assertEqual(result['status'],'INCOMPLETE')
            self.assertIn('MISSING_CAP_EVENT',str(result['records'][0]['issues']))
            next((Path(root)/'raw').glob('*.bin')).write_bytes(b'corrupt')
            result=review_intraday_session(root,'2026-10-15')
            self.assertIn('RAW_HASH_MISMATCH',str(result))
    def test_rewritten_event_cap_and_cash_fail_even_self_hashed(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);result=service.preview('a'*24)
            path=Path(root)/result['observation_record']['event_path'];event=json.loads(path.read_bytes())
            event['response']['stocks'][0]['fresh_cash_reference']['quantity']=999
            path.write_text(json.dumps(event),encoding='utf-8')
            report=review_intraday_session(root,'2026-10-15')
            self.assertIn('FRESH_QUANTITY_MISMATCH',str(report))
    def test_prior_receipt_mismatch_and_cross_boot_origin(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);first=service.preview('a'*24);second=service.preview('a'*24)
            receipt=second['observation_record'];path=Path(root)/receipt['event_path']
            event=json.loads(path.read_bytes());event['process_boot_id']='c'*32
            event['response']['process_boot_id']='c'*32
            path.write_text(json.dumps(event),encoding='utf-8')
            report=review_intraday_session(root,'2026-10-15',expected_event_hashes={receipt['event_path']:receipt['event_sha256']})
            self.assertIn('EXPECTED_EVENT_HASH_MISMATCH',str(report))
            report=review_intraday_session(root,'2026-10-15')
            self.assertIn('CAP_EVENT_SCOPE_MISMATCH',str(report))

    def test_missing_expected_and_invalid_sequence_do_not_crash(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);first=service.preview('a'*24);second=service.preview('a'*24)
            report=review_intraday_session(root,'2026-10-15',expected_event_hashes={'events/2026-10-15/missing.json':'0'*64})
            self.assertEqual(report['status'],'INCOMPLETE');self.assertEqual(len(report['missing_receipts']),1)
            path=Path(root)/first['observation_record']['event_path'];event=json.loads(path.read_bytes())
            event['observation_sequence']='bad';path.write_text(json.dumps(event),encoding='utf-8')
            report=review_intraday_session(root,'2026-10-15')
            self.assertIn('INVALID_SEQUENCE',str(report))
            self.assertEqual(report['status'],'INCOMPLETE')
    def test_damaged_cap_source_and_cross_day_prefix_note(self):
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);first=service.preview('a'*24);second=service.preview('a'*24)
            path=Path(root)/first['observation_record']['event_path'];event=json.loads(path.read_bytes())
            event['response']['stocks'][0]['fresh_cash_reference']['quantity']=999
            path.write_text(json.dumps(event),encoding='utf-8')
            report=review_intraday_session(root,'2026-10-15')
            self.assertIn('SOURCE_CAP_EVENT_INVALID',str(report))
        with tempfile.TemporaryDirectory() as root:
            service=self.service(root);service.observation_sequence=7;service.preview('a'*24)
            report=review_intraday_session(root,'2026-10-15')
            self.assertEqual(report['status'],'REVIEWED_LOCAL_OBSERVATIONS')
            self.assertEqual(report['coverage_notes'][0]['first_sequence'],8)

    def test_pending_uses_original_capture_not_review_clock(self):
        with tempfile.TemporaryDirectory() as root:
            clock=[NOW];p=payload();p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+7
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:json.dumps(p).encode(),clock=lambda:clock[0],journal=IntradayObservationJournal(root))
            service.preview('a'*24);clock[0]+=timedelta(seconds=10)
            p['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())+7
            service.preview('a'*24)
            report=review_intraday_session(root,'2026-10-15')
            self.assertEqual(report['status'],'REVIEWED_LOCAL_OBSERVATIONS',report)
            self.assertEqual(report['records'][1]['observations'][0]['quote_response_age_seconds'],10)

if __name__=='__main__':unittest.main()
