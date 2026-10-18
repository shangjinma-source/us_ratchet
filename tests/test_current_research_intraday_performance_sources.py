import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import test_current_research_intraday_performance as pure_tests
from test_current_research_intraday_execution import NOW
from data.current_research_intraday_performance_sources import review_saved_intraday_performance

class SourceTests(unittest.TestCase):
    def fixture(self, directory, filled=True):
        root=Path(directory);state=pure_tests.PerformanceTests().fixture(directory,filled=filled)
        close=NOW.replace(hour=16,minute=0,second=0);received=close+timedelta(minutes=1)
        channel=dict(meta=dict(symbol='SNDK',currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d'),timestamp=[int(NOW.timestamp())],indicators={'quote':[dict(open=[1400],high=[1420],low=[1390],close=[1412])]},events={})
        raw=json.dumps({'chart':{'error':None,'result':[channel]}}).encode()
        digest=lambda b:hashlib.sha256(b).hexdigest()
        receipt=json.dumps(dict(http_status=200,ticker='SNDK',raw_sha256=digest(raw),received_at_utc=received.isoformat())).encode()
        decoded=json.dumps(dict(ticker='SNDK',receipt_sha256=digest(receipt),decoded_sha256=digest(raw),raw_returned_events={})).encode()
        pins={};entry={}
        for suffix,key,content in [('.response.bin','raw_sha256',raw),('.receipt.json','receipt_sha256',receipt),('.decoded.json','decoded_sha256',decoded)]:
            name='SNDK'+suffix;(root/name).write_bytes(content);pins[name]=digest(content);entry[key]=digest(content)
        (root/'evidence.txt').write_text('Synthetic conditional unit/calendar evidence')
        calendar=dict(status='REVIEWED_OFFICIAL_SESSION_CALENDAR',source_references=['evidence.txt'],sessions={'2026-10-15':dict(timezone='America/New_York',open_at=NOW.replace(hour=9,minute=30,second=0).isoformat(),close_at=close.isoformat())})
        (root/'calendar.json').write_text(json.dumps(calendar))
        for name in ('calendar.json','evidence.txt'):pins[name]=digest((root/name).read_bytes())
        sources={'sndk':dict(ticker='SNDK',expected_security_type='EQUITY',entry=entry,relative_directory='.',reviewed_at=(received+timedelta(minutes=1)).isoformat(),continuity=dict(status='NO_UNPROCESSED_ACTIONS',from_date='2026-10-15',to_date='2026-10-15',price_basis='NOMINAL_PER_CURRENT_SHARE',source_references=['evidence.txt']))}
        return state,dict(root=root,sources=sources,source_hashes=pins,calendar_path='calendar.json',session_date='2026-10-15',now=close+timedelta(days=1))
    def test_real_bytes_close_not_intraday_freshness(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root);before=deepcopy(state)
            result=review_saved_intraday_performance(state,**args)
            self.assertEqual(result['status'],'COMPLETE');self.assertEqual(result['equity'],'20011')
            self.assertTrue(result['source_bytes_verified']);self.assertFalse(result['source_authenticated'])
            self.assertEqual(result['valuation_kind'],'COMPLETED_SESSION_CLOSE');self.assertEqual(state,before)
    def test_missing_evidence_tamper_identity_future_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root)
            for field,value in [('ticker','WRONG'),('reviewed_at','2099-01-01T00:00:00+00:00'),('continuity',{})]:
                changed=deepcopy(args);changed['sources']['sndk'][field]=value
                self.assertEqual(review_saved_intraday_performance(state,**changed)['status'],'INCOMPLETE')
            changed=deepcopy(args);changed['now']=NOW+timedelta(minutes=6)
            self.assertEqual(review_saved_intraday_performance(state,**changed)['status'],'INCOMPLETE')
            (Path(root)/'SNDK.response.bin').write_bytes(b'bad')
            result=review_saved_intraday_performance(state,**args)
            self.assertEqual(result['status'],'INCOMPLETE');self.assertIsNone(result['total_return'])
    def test_cash_only_needs_calendar_but_not_price_sources(self):
        with tempfile.TemporaryDirectory() as root:
            state,args=self.fixture(root,filled=False)
            args['sources']={}
            args['source_hashes']={k:v for k,v in args['source_hashes'].items() if k in ('calendar.json','evidence.txt')}
            result=review_saved_intraday_performance(state,**args)
            self.assertEqual(result['status'],'COMPLETE')
            self.assertEqual(result['equity'],'20000');self.assertIsNone(result['total_return'])
            self.assertEqual(result['valuation_session'],'2026-10-15')
            self.assertEqual(result['valuation_at'],'2026-10-15T20:00:00+00:00')
            changed=deepcopy(args);changed['now']=NOW
            self.assertEqual(review_saved_intraday_performance(state,**changed)['status'],'INCOMPLETE')
            changed=deepcopy(args);changed['session_date']='2099-01-01'
            self.assertEqual(review_saved_intraday_performance(state,**changed)['status'],'INCOMPLETE')
            changed=deepcopy(args);changed['calendar_path']='missing.json'
            self.assertEqual(review_saved_intraday_performance(state,**changed)['status'],'INCOMPLETE')
            (Path(root)/'calendar.json').write_text('{}')
            self.assertEqual(review_saved_intraday_performance(state,**args)['status'],'INCOMPLETE')

if __name__=='__main__':unittest.main()

