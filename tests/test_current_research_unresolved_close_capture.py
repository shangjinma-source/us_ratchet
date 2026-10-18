from datetime import datetime
from unittest.mock import patch
import json,unittest
from scripts.current_research_unresolved_close_capture import capture_unresolved_close
import test_current_research_close_capture as close_fixture

class UnresolvedTests(unittest.TestCase):
    def setUp(self):
        self.f=close_fixture.CloseCaptureTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.security=dict(ticker='AAA',security_type='EQUITY',security_id=None,identity_status='UNRESOLVED')
    def call(self,**kwargs):
        args=dict(root=self.f.root,output_directory='unresolved',session='2026-10-13',history_start_date='2025-10-10',session_close_at='2026-10-13T16:00:00-04:00',clock=lambda:self.f.now,fetch=self.f.fetch,capture=True);args.update(kwargs)
        return capture_unresolved_close(self.security,**args)
    def test_default_and_preclose_zero_http_zero_output(self):
        self.assertEqual(self.call(capture=False)['status'],'PREFLIGHT_ONLY')
        self.f.now=datetime.fromisoformat('2026-10-13T19:59:59+00:00')
        with self.assertRaisesRegex(ValueError,'SESSION_NOT_CLOSED'):self.call()
        self.assertFalse((self.f.root/'unresolved').exists());self.assertEqual(self.f.calls,[])
    def test_valid_raw_never_promotes_null_identity_and_no_retry(self):
        result=self.call();self.assertIsNone(result['security_id']);self.assertEqual(result['identity_status'],'UNRESOLVED')
        self.assertEqual(result['quote_validation'],'EXACT_SESSION_OHLC_VALIDATED_IDENTITY_UNRESOLVED',result)
        self.assertFalse(result['training_admitted']);self.assertFalse(result['security_identity_verified'])
        self.assertIn('period1=1760054400',self.f.calls[0])
        with self.assertRaisesRegex(ValueError,'NO_RETRY'):self.call()
        self.assertEqual(len(self.f.calls),1)
    def test_failures_save_evidence_and_never_admit(self):
        def failed(*a,**k):raise OSError('offline')
        self.assertEqual(self.call(fetch=failed)['status'],'TRANSPORT_FAILED')
        receipt=json.loads((self.f.root/'unresolved/AAA.receipt.json').read_bytes());self.assertEqual(receipt['error_type'],'OSError')
        with patch('scripts.current_research_unresolved_close_capture.MAX_BYTES',100):
            result=self.call(output_directory='oversize',fetch=lambda url,**kw:dict(raw=b'x'*101,http_status=200,final_url=url))
        self.assertEqual(result['status'],'BODY_LIMIT_FAILED');self.assertFalse(result['training_admitted'])
        result=self.call(output_directory='redirect',fetch=lambda url,**kw:dict(raw=b'redirect',http_status=302,final_url=url))
        self.assertEqual(result['status'],'HTTP_FAILED')
    def test_invalid_identity_paths_clock_and_fixed_transport_bounds(self):
        self.security['security_id']='made-up'
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'):self.call()
        self.security['security_id']=None
        with self.assertRaises(ValueError):self.call(output_directory='../escape')
        with self.assertRaises(ValueError):self.call(clock=lambda:datetime(2026,10,14))
        def fetch(url,**kwargs):
            self.assertEqual(kwargs,dict(timeout=15,max_bytes=8000000));return self.f.fetch(url,**kwargs)
        self.call(fetch=fetch)

if __name__=='__main__':unittest.main()
