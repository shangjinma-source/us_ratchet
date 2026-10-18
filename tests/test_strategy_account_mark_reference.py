from datetime import datetime, timezone, timedelta
import json
import unittest
from data.strategy_account_mark_reference import decode_current_mark


class MarkReferenceTests(unittest.TestCase):
    def test_selection_900_is_not_execution_120(self):
        now,data=self.fixture()
        meta=data['chart']['result'][0]['meta']
        meta['regularMarketTime']=int(now.timestamp())-123
        raw=json.dumps(data).encode()
        result=decode_current_mark(raw,ticker='ROST',now=now,captured_at=now,maximum_age_seconds=900)
        self.assertFalse(result['executable_limit'])
        with self.assertRaisesRegex(ValueError,'LAST_QUOTE_STALE'):
            decode_current_mark(raw,ticker='ROST',now=now,captured_at=now)
        meta['regularMarketTime']=int(now.timestamp())-901
        with self.assertRaisesRegex(ValueError,'LAST_QUOTE_STALE'):
            decode_current_mark(json.dumps(data).encode(),ticker='ROST',now=now,captured_at=now,maximum_age_seconds=900)
        meta['regularMarketTime']=int(now.timestamp())+1
        with self.assertRaisesRegex(ValueError,'LAST_QUOTE_FUTURE'):
            decode_current_mark(json.dumps(data).encode(),ticker='ROST',now=now,captured_at=now,maximum_age_seconds=900)
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_MARK_AGE_POLICY'):
            decode_current_mark(raw,ticker='ROST',now=now,captured_at=now,maximum_age_seconds=901)

    def fixture(self):
        now=datetime(2026,10,16,14,52,20,tzinfo=timezone.utc)
        opening=int(now.replace(hour=13,minute=30,second=0).timestamp())
        meta=dict(symbol='ROST',currency='USD',instrumentType='EQUITY',
            exchangeTimezoneName='America/New_York',dataGranularity='1m',
            regularMarketPrice=150,regularMarketTime=int(now.timestamp())-24,
            currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400)))
        return now,dict(chart=dict(error=None,result=[dict(meta=meta)]))

    def test_fresh_valuation_does_not_claim_a_minute_limit(self):
        now,data=self.fixture()
        result=decode_current_mark(json.dumps(data).encode(),ticker='ROST',now=now,captured_at=now)
        self.assertEqual(result['last_price'],'150')
        self.assertFalse(result['executable_limit'])
        self.assertNotIn('minute_low',result)

    def test_original_capture_preserved_subsecond_wait_does_not_authorize_future(self):
        now,data=self.fixture();data['chart']['result'][0]['meta']['regularMarketTime']=int(now.timestamp())
        captured=now-timedelta(seconds=.8)
        raw=json.dumps(data).encode()
        with self.assertRaisesRegex(ValueError,'LAST_QUOTE_FUTURE'):
            decode_current_mark(raw,ticker='ROST',now=captured,captured_at=captured)
        self.assertEqual(decode_current_mark(raw,ticker='ROST',now=now,captured_at=captured)['last_at'],now.isoformat())
        with self.assertRaisesRegex(ValueError,'QUOTE_CLOCK_SKEW_EXCEEDED'):
            decode_current_mark(raw,ticker='ROST',now=now,captured_at=now-timedelta(seconds=2))

    def test_stale_foreign_nonfinite_and_duplicate_rejected(self):
        for mode in ('stale','foreign','nonfinite','duplicate'):
            with self.subTest(mode=mode):
                now,data=self.fixture();meta=data['chart']['result'][0]['meta']
                if mode=='stale':meta['regularMarketTime']=int(now.timestamp())-120
                if mode=='foreign':meta['instrumentType']='ETF'
                if mode=='nonfinite':meta['regularMarketPrice']=float('nan')
                raw=json.dumps(data)
                if mode=='duplicate':raw=raw.replace('"symbol": "ROST"','"symbol": "OTHER", "symbol": "ROST"')
                with self.assertRaises(ValueError):decode_current_mark(raw.encode(),ticker='ROST',now=now,captured_at=now)


if __name__=='__main__':unittest.main()
