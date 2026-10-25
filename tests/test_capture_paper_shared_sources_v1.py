from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
from scripts.capture_paper_shared_sources_v1 import capture,capture_files


class SharedCaptureTests(TestCase):
    def test_shared_capture_passes_existing_full_first_window_review(self):
        import test_strategy_prospective_paper_first_window_v1 as fixtures
        from data.strategy_prospective_paper_first_window_v1 import review_paper_first_window
        from core.strategy_account_ledger import canonical
        from hashlib import sha256
        from zoneinfo import ZoneInfo
        with TemporaryDirectory() as temp:
            context,config,original,_=fixtures.PaperFirstTests().case(temp)
            calendar=json.loads((Path(temp)/config['calendar']['path']).read_bytes())
            today=context.clock[0].astimezone(ZoneInfo('America/New_York')).date().isoformat()
            sessions=calendar['sessions'];index=[r['date'] for r in sessions].index(today)
            left=datetime.fromisoformat(sessions[index-20]['open'])-timedelta(days=1)
            request=dict(ticker='BBB',security_id='B',session=today,
                         requested_from=left.isoformat(),session_close=sessions[index]['close'])
            folder=Path(temp)/'shared'
            capture(requests=[request],output=folder,clock=lambda:context.clock[0],
                    daily_fetch=lambda *args:dict(status=200,body=original['daily.response.bin']),
                    official_fetch=lambda:dict(status=200,body=original['official.response.bin']))
            files=capture_files(folder,0);raw=canonical(config)
            result=review_paper_first_window(root=temp,configuration_bytes=raw,
                configuration_sha256=sha256(raw).hexdigest(),capture_files=files,clock=lambda:context.clock[0])
            self.assertIsNotNone(result['receipt'],result)
            # The review still rejects hash-consistent wrong securities.
            daily=json.loads(files['daily.response.bin']);daily['chart']['result'][0]['meta']['symbol']='WRONG'
            files['daily.response.bin']=canonical(daily)
            receipt=json.loads(files['daily.receipt.json']);receipt.update(
                raw_sha256=sha256(files['daily.response.bin']).hexdigest(),stored_bytes=len(files['daily.response.bin']))
            files['daily.receipt.json']=canonical(receipt)
            rejected=review_paper_first_window(root=temp,configuration_bytes=raw,
                configuration_sha256=sha256(raw).hexdigest(),capture_files=files,clock=lambda:context.clock[0])
            self.assertIsNone(rejected['receipt'])

    def test_two_securities_one_official_receipt_without_restamping(self):
        with TemporaryDirectory() as temp:
            now=datetime(2026,10,23,14,tzinfo=timezone.utc);calls=[]
            def clock():
                nonlocal now
                now+=timedelta(seconds=1);return now
            rows=[dict(security_id=t,ticker=t,session='2026-10-23',requested_from='2026-09-20T13:30:00+00:00',
                       session_close='2026-10-23T20:00:00+00:00') for t in ('A','B')]
            def daily(t,*args):
                calls.append(t);return dict(status=200,body=json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':t}}]}}).encode())
            def official():
                calls.append('official');return dict(status=200,body=b'<rss><channel><item><title>Example notice</title><pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>')
            folder=Path(temp)/'run';result=capture(requests=rows,output=folder,clock=clock,daily_fetch=daily,official_fetch=official)
            self.assertEqual(calls,['A','B','official']);self.assertEqual(result['network_calls'],3)
            a,b=capture_files(folder,0),capture_files(folder,1)
            self.assertEqual(a['official.receipt.json'],b['official.receipt.json'])
            self.assertGreater(json.loads(a['official.receipt.json'])['started_at'],json.loads(b['daily.receipt.json'])['received_at'])

    def test_html_failure_is_preserved_and_incomplete_batch_unreadable(self):
        with TemporaryDirectory() as temp:
            row=dict(security_id='A',ticker='A',session='2026-10-23',requested_from='2026-09-20T13:30:00+00:00',session_close='2026-10-23T20:00:00+00:00')
            folder=Path(temp)/'run'
            with self.assertRaises(Exception):
                capture(requests=[row],output=folder,clock=lambda:datetime(2026,10,23,14,tzinfo=timezone.utc),
                    daily_fetch=lambda *args:dict(status=200,body=b'{"chart":{"result":[{"meta":{"symbol":"A"}}]}}'),
                    official_fetch=lambda:dict(status=200,body=b'<html>blocked</html>'))
            self.assertTrue((folder/'failed.json').exists());self.assertFalse((folder/'complete.json').exists())
            self.assertEqual((folder/'official.response.bin').read_bytes(),b'<html>blocked</html>')
            with self.assertRaisesRegex(ValueError,'INCOMPLETE'):capture_files(folder,0)
