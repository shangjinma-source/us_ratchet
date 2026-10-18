"""Injected fetch/clock only; all capture artifacts live in temporary roots."""
import gzip
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.current_research_close_capture import capture_saved_close
import test_current_research_saved_quote as quote_fixture


class CloseCaptureTests(unittest.TestCase):
    def setUp(self):
        self.f=quote_fixture.SavedQuoteTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.root=self.f.root
        (self.root/'evidence').write_bytes(b'explicit synthetic session source')
        digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        calendar=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',calendar=['2026-10-13'],sessions=[dict(date='2026-10-13',timezone='America/New_York',open_at='2026-10-13T09:30:00-04:00',close_at='2026-10-13T16:00:00-04:00')],source_hashes={'evidence':digest(self.root/'evidence')})
        (self.root/'calendar.json').write_text(json.dumps(calendar))
        self.manifest=dict(schema='SAVED_CLOSE_CAPTURE_MANIFEST_V1',session='2026-10-13',history_start_date='2026-10-01',calendar_path='calendar.json',calendar_source_hashes=dict(calendar['source_hashes'],**{'calendar.json':digest(self.root/'calendar.json')}),output_directory='capture',securities=[dict(ticker='AAA',security_type='EQUITY',security_id='declared:A')])
        self.now=datetime.fromisoformat('2026-10-13T20:01:00+00:00');self.calls=[]
    def save(self):
        raw=json.dumps(self.manifest).encode();(self.root/'manifest.json').write_bytes(raw);return hashlib.sha256(raw).hexdigest()
    def fetch(self,url,**kwargs):
        self.calls.append(url)
        raw=json.dumps({'chart':{'error':None,'result':[self.f.channel]}}).encode()
        # Non-binary-exact dividend amount must stay a JSON number through decoded observation.
        raw=raw.replace(b'"events": {',b'"events": {"dividends":{"d":{"date":1791898200,"amount":0.123456789012345678901}},')
        return dict(raw=gzip.compress(raw),http_status=200,final_url=url,response_headers={})
    def run_capture(self,**changes):
        args=dict(root=self.root,capture=True,clock=lambda:self.now,fetch=self.fetch);args.update(changes)
        return capture_saved_close('manifest.json',self.save(),**args)
    def test_preclose_and_dry_run_zero_http_zero_output(self):
        self.now=datetime.fromisoformat('2026-10-13T19:59:59+00:00')
        result=self.run_capture(capture=False)
        self.assertFalse(result['ready_after_close']);self.assertEqual(self.calls,[]);self.assertFalse((self.root/'capture').exists())
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_CLOSED'):self.run_capture()
        self.assertEqual(self.calls,[]);self.assertFalse((self.root/'capture').exists())
    def test_gzip_decimal_events_two_hash_layers_and_no_retry(self):
        result=self.run_capture();entry=result['entries'][0]
        self.assertEqual(entry['status'],'SAVED_EXACT_SESSION_READER_VALIDATED_NOT_ADMITTED',entry)
        self.assertEqual(entry['quote_observation']['ohlc']['close'],'10.25')
        self.assertEqual(entry['quote_observation']['raw_returned_events']['dividends']['d']['amount'],'0.123456789012345678901')
        decoded=(self.root/'capture/AAA.decoded.json').read_bytes();observation=json.loads(decoded)
        self.assertEqual(hashlib.sha256(decoded).hexdigest(),entry['decoded_sha256'])
        self.assertNotEqual(entry['decoded_sha256'],observation['decoded_sha256'])
        self.assertFalse(result['registration_performed'])
        with self.assertRaisesRegex(ValueError,'NO_RETRY'):self.run_capture()
        self.assertEqual(len(self.calls),1)
    def test_transport_failure_and_oversize_preserved_without_admission(self):
        def fail(*args,**kwargs):raise OSError('offline')
        result=self.run_capture(fetch=fail)
        self.assertEqual(result['entries'][0]['status'],'TRANSPORT_FAILED')
        self.assertFalse((self.root/'capture/AAA.response.bin').exists())
        self.manifest['output_directory']='large'
        with patch('scripts.current_research_close_capture.MAX_BYTES',100):
            result=self.run_capture(fetch=lambda url,**kw:dict(raw=b'x'*101,http_status=200,final_url=url))
        self.assertEqual(result['entries'][0]['status'],'BODY_LIMIT_FAILED')
        self.assertEqual((self.root/'large/AAA.response.bin').stat().st_size,101)
    def test_scope_calendar_and_type_fail_before_network(self):
        self.manifest['securities']*=6
        with self.assertRaisesRegex(ValueError,'SCOPE'):self.run_capture()
        self.assertEqual(self.calls,[])
        self.manifest['securities']=self.manifest['securities'][:1]
        (self.root/'evidence').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'CALENDAR_SOURCE_CHANGED'):self.run_capture()
        self.assertEqual(self.calls,[])
    def test_ticker_paths_rejected_and_capture_timestamp_precedes_disk(self):
        for ticker in ('A\\B','A/B','../A'):
            self.manifest['securities'][0]['ticker']=ticker
            with self.assertRaisesRegex(ValueError,'TICKER'):self.run_capture()
        self.assertEqual(self.calls,[])
        self.manifest['securities'][0]['ticker']='AAA'
        from scripts.current_research_close_capture import _write_raw
        original=self.now
        def disk(path,raw):
            from datetime import timedelta
            self.now=original+timedelta(seconds=20)
            return _write_raw(path,raw)
        with patch('scripts.current_research_close_capture._write_raw',side_effect=disk):
            self.run_capture()
        receipt=json.loads((self.root/'capture/AAA.receipt.json').read_bytes())
        self.assertEqual(receipt['received_at_utc'],original.isoformat())

    def test_etf_no_fake_sid_and_wrong_provider_identity_rejected(self):
        self.manifest['securities'][0].update(ticker='QQQ',security_type='ETF',security_id=None)
        result=self.run_capture()
        self.assertEqual(result['entries'][0]['status'],'READER_VALIDATION_FAILED')
        self.assertEqual(len(self.calls),1)

if __name__=='__main__':unittest.main()
