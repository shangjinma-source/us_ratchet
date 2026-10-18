import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from data.current_research_saved_quote import read_saved_quote


class SavedQuoteTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.channel=dict(meta=dict(symbol='AAA',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d',regularMarketTime=1791921600,regularMarketPrice=10.25,currentTradingPeriod={}),timestamp=[1791898200,1791984600],indicators={'quote':[dict(open=[10,None],high=[11,None],low=[9,None],close=[10.25,None])]},events={'splits':{'event':dict(date=1791984600,numerator=2,denominator=1,splitRatio='2:1')}})
        self.received='2026-10-14T12:00:00+00:00';self.event_override=None
    def read(self, entry_changes=None):
        raw=gzip.compress(json.dumps({'chart':{'error':None,'result':[self.channel]}}).encode())
        digest=lambda b:hashlib.sha256(b).hexdigest()
        receipt=json.dumps(dict(http_status=200,ticker='AAA',raw_sha256=digest(raw),received_at_utc=self.received)).encode()
        observation=json.dumps(dict(ticker='AAA',receipt_sha256=digest(receipt),decoded_sha256=digest(gzip.decompress(raw)),raw_returned_events=self.channel['events'] if self.event_override is None else self.event_override)).encode()
        for suffix,content in [('.response.bin',raw),('.receipt.json',receipt),('.decoded.json',observation)]:
            (self.root/('AAA'+suffix)).write_bytes(content)
        entry=dict(raw_sha256=digest(raw),receipt_sha256=digest(receipt),decoded_sha256=digest(observation))
        entry.update(entry_changes or {})
        return read_saved_quote(root=self.root,ticker='AAA',expected_security_type='EQUITY',entry=entry,relative_directory='.',decision_date='2026-10-13',decision_session_close_at='2026-10-13T16:00:00-04:00')
    def test_exact_decision_not_next_intraday_and_future_events_labeled(self):
        r=self.read();self.assertEqual(r['ohlc']['close'],'10.25');self.assertEqual(r['later_provider_dates'],['2026-10-14'])
        self.assertTrue(r['event_details'][0]['after_decision']);self.assertFalse(r['no_unprocessed_actions_certified'])
        self.channel['meta']['regularMarketTime']=1791984600
        self.channel['meta']['regularMarketPrice']=999
        self.assertIsNone(self.read()['reference_quote'])
    def test_close_time_identity_ohlc_and_events_fail_closed(self):
        self.received='2026-10-13T19:59:59+00:00'
        with self.assertRaisesRegex(ValueError,'CAPTURE_BEFORE'):self.read()
        self.received='2026-10-13T20:00:00+00:00';self.assertEqual(self.read()['ohlc']['close'],'10.25')
        self.event_override={}
        with self.assertRaisesRegex(ValueError,'EVENTS_MISMATCH'):self.read()
        self.event_override=None;self.channel['indicators']['quote'][0]['high'][0]=9
        with self.assertRaisesRegex(ValueError,'OHLC_RANGE'):self.read()
    def test_each_file_pin_is_enforced(self):
        for key in ('raw_sha256','receipt_sha256','decoded_sha256'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):
                self.read({key:'0'*64})

    def test_missing_decision_and_wrong_identity(self):
        self.channel['meta']['symbol']='OTHER'
        with self.assertRaisesRegex(ValueError,'COORDINATE'):self.read()
        self.channel['meta']['symbol']='AAA';self.channel['timestamp'][0]=1791811800
        with self.assertRaisesRegex(ValueError,'DECISION_BAR'):self.read()

if __name__=='__main__':unittest.main()
