import gzip
import json
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_current79_new_asof_capture_20260919 as module


class Response:
    status = 200
    url = 'https://query1.finance.yahoo.com/mock'
    headers = {'Content-Encoding': 'gzip'}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return gzip.compress(b'{"chart":{"result":[],"error":null}}')


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = module.build_plan()

    def plan(self, output, count=10):
        return dict(self.real, tickers=self.real['tickers'][:count],
                    queue=self.real['queue'][:count], output_directory=str(output))

    def test_exact_hard_79_and_no_new22(self):
        self.assertEqual(len(set(self.real['tickers'])),79)
        self.assertFalse(self.real['new22_recaptured'])
        self.assertEqual(self.real['old_missing_receipts_not_backfilled'],['GOOGL','FTNT'])
        self.assertFalse(self.real['training_performed'])

    def test_eight_then_two_resume_and_durable_start_before_http(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary); plan=self.plan(output); seen=[]
            def opener(request,**kwargs):
                ticker=request.full_url.split('/chart/')[1].split('?')[0]
                started=json.loads((output/(ticker+'.started.json')).read_bytes())
                self.assertEqual(started['request_url'],request.full_url)
                seen.append(ticker)
                return Response()
            first=module.run_batch(plan,'p',output,opener=opener)
            self.assertEqual(len(seen),8)
            second=module.run_batch(plan,'p',output,first['path'],first['sha256'],opener)
            self.assertEqual(seen,plan['tickers'])
            self.assertEqual(second['attempted_count'],10)
            receipt=json.loads((output/(seen[0]+'.receipt.json')).read_bytes())
            self.assertIn('completed_training_excludes_dates_on_or_after',receipt)
            self.assertFalse(receipt['historical_identity_verified'])
            with self.assertRaisesRegex(ValueError,'complete'):
                module.run_batch(plan,'p',output,second['path'],second['sha256'],opener)
            (output/(seen[0]+'.response.bin')).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'Raw changed'):
                module.run_batch(plan,'p',output,second['path'],second['sha256'],opener)

    def test_unindexed_attempt_blocks_even_distant_ticker(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);plan=self.plan(output)
            module.previous.save(output/(plan['tickers'][-1]+'.started.json'),{})
            with self.assertRaisesRegex(ValueError,'Unindexed'):
                module.run_batch(plan,'p',output,opener=lambda *a,**k:self.fail('No HTTP'))

    def test_later_period2_and_duplicate_guard(self):
        url='https://query1.finance.yahoo.com/v8/finance/chart/A?period1=1640995200&period2=200&interval=1d&events=div,splits'
        self.assertEqual(module.check_request(url,'A',{'prior_max_request_period2':199},set()),200)
        for row,urls in [({'prior_max_request_period2':200},set()),({'prior_max_request_period2':None},{url})]:
            with self.assertRaisesRegex(ValueError,'strictly later'):
                module.check_request(url,'A',row,urls)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,'has not advanced'):
                module.capture_one({'ticker':'A','prior_max_request_period2':99999999999},Path(temporary),'p',set(),lambda *a,**k:self.fail('No HTTP'))
            self.assertEqual(list(Path(temporary).iterdir()),[])

    def test_network_failure_is_one_durable_attempt_not_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary);plan=self.plan(output,1);calls=[]
            def fail(*args,**kwargs):
                calls.append(1);raise TimeoutError()
            index=module.run_batch(plan,'p',output,opener=fail)
            receipt=json.loads((output/(plan['tickers'][0]+'.receipt.json')).read_bytes())
            self.assertEqual(receipt['error_type'],'TimeoutError')
            self.assertEqual(len(calls),1)
            with self.assertRaisesRegex(ValueError,'complete'):
                module.run_batch(plan,'p',output,index['path'],index['sha256'],fail)
            self.assertEqual(len(calls),1)


if __name__=='__main__': unittest.main()
