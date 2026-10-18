from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from threading import Barrier, Lock

SPEC = importlib.util.spec_from_file_location('current_raw_capture', Path(__file__).resolve().parents[1] / 'scripts/ndx_current_raw_capture_20261013.py')
capture = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(capture)
CLOCK = datetime(2026, 10, 13, 4, 10, tzinfo=timezone.utc)


class Response(io.BytesIO):
    def __init__(self, raw, url, status=200):
        super().__init__(raw); self.status=status; self.url=url; self.headers={}


def payload(ticker):
    stamp = int(datetime(2026,10,12,13,30,tzinfo=timezone.utc).timestamp())
    return json.dumps({'chart': {'error': None, 'result': [{
        'meta': {'symbol': ticker, 'currency':'USD','exchangeTimezoneName':'America/New_York','dataGranularity':'1d'},
        'timestamp':[stamp], 'indicators':{'quote':[{'open':[10],'high':[12],'low':[9],'close':[11],'volume':[100]}]},
        'events':{'splits':{},'dividends':{}},
    }]}}).encode()


class CurrentRawCaptureTests(unittest.TestCase):
    def test_success_prior_day_target_continuation_and_default_no_http(self):
        with TemporaryDirectory() as directory:
            output=Path(directory)/'capture'; calls=[]
            def opener(request,**kwargs):
                ticker=request.full_url.split('/chart/')[1].split('?')[0]; calls.append(ticker)
                self.assertTrue((output/(ticker+'.started.json')).exists())
                return Response(payload(ticker),request.full_url)
            with patch.object(capture,'OUTPUT',output), patch.object(capture,'guard',return_value=['AAA','BBB']):
                check=capture.run(runner_sha='fixed',opener=opener,clock=lambda:CLOCK)
                self.assertEqual(check['network_requests'],0); self.assertFalse(output.exists())
                first=capture.run(runner_sha='fixed',execute=True,max_new=1,opener=opener,clock=lambda:CLOCK)
                decoded=json.loads((output/'AAA.decoded.json').read_text())
                self.assertEqual(decoded['status'],'RAW_TARGET_OHLCV_PRESENT_NOT_CALENDAR_CERTIFIED')
                self.assertEqual(decoded['target_date'],'2026-10-12')
                self.assertEqual(decoded['receipt_new_york_date'],'2026-10-13')
                self.assertFalse(decoded['close_time_certified'])
                self.assertFalse(decoded['prices_reconstructed'])
                second=capture.run(runner_sha='fixed',execute=True,max_new=1,index_sha=first['last_index_sha256'],opener=opener,clock=lambda:CLOCK)
                self.assertEqual(second['completed_attempts'],2); self.assertEqual(calls,['AAA','BBB'])
                self.assertEqual((output/'AAA.response.bin').read_bytes(),payload('AAA'))

    def test_failed_http_truncated_and_partial_bytes_are_saved_no_retry(self):
        for kind in ('http','truncated','partial','decode'):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                output=Path(directory)/'capture'; calls=[]
                def opener(request,**kwargs):
                    calls.append(request.full_url)
                    if kind=='http': raise HTTPError(request.full_url,429,'fake rate limit',{},io.BytesIO(b'failed body'))
                    if kind=='truncated': return Response(b'x'*101,request.full_url)
                    if kind=='decode': return Response(b'{"a":1,"a":2}',request.full_url)
                    response=Response(b'prefix',request.full_url)
                    oldread=response.read; first=[True]
                    def read(size):
                        if first[0]: first[0]=False; return oldread(size)
                        raise TimeoutError('fake interruption')
                    response.read=read; return response
                with patch.object(capture,'OUTPUT',output),patch.object(capture,'MAX_BYTES',100),patch.object(capture,'guard',return_value=['AAA']):
                    result=capture.run(runner_sha='fixed',execute=True,opener=opener,clock=lambda:CLOCK)
                    receipt=json.loads((output/'AAA.receipt.json').read_text())
                    self.assertEqual(receipt['status'], {'http':'HTTP_FAILED','truncated':'BODY_LIMIT_FAILED','partial':'TRANSPORT_FAILED','decode':'RAW_CAPTURED'}[kind])
                    self.assertTrue((output/'AAA.response.bin').exists())
                    self.assertEqual(receipt['raw_bytes'], len((output/'AAA.response.bin').read_bytes()))
                    if kind=='truncated': self.assertTrue(receipt['body_truncated']); self.assertEqual(receipt['raw_bytes'],101)
                    if kind=='partial': self.assertEqual((output/'AAA.response.bin').read_bytes(),b'prefix')
                    done=capture.run(runner_sha='fixed',execute=True,index_sha=result['last_index_sha256'],opener=opener,clock=lambda:CLOCK)
                    self.assertEqual(done['network_requests'],0);self.assertEqual(len(calls),1)

    def test_clock_gate_bounds_orphans_before_network_and_backward_clock_retains_raw(self):
        with TemporaryDirectory() as directory:
            output=Path(directory)/'capture'
            with patch.object(capture,'OUTPUT',output),patch.object(capture,'guard',return_value=['AAA']):
                def forbidden(*args,**kwargs): raise AssertionError('unexpected network')
                for clock in (datetime(2026,10,13,3,59,tzinfo=timezone.utc),datetime(2026,10,14,4,tzinfo=timezone.utc),datetime(2026,10,13,4)):
                    with self.assertRaises(ValueError): capture.run(runner_sha='fixed',execute=True,opener=forbidden,clock=lambda:clock)
                for options in ({'max_new':9},{'workers':5},{'max_new':True}):
                    with self.assertRaises(ValueError): capture.run(runner_sha='fixed',execute=True,opener=forbidden,**options)
                output.mkdir();(output/'AAA.started.json').write_text('{}')
                with self.assertRaises(ValueError): capture.run(runner_sha='fixed',execute=True,opener=forbidden,clock=lambda:CLOCK)
        with TemporaryDirectory() as directory:
            output=Path(directory)/'capture';times=iter([CLOCK,CLOCK,datetime(2026,10,13,4,9,tzinfo=timezone.utc)])
            with patch.object(capture,'OUTPUT',output),patch.object(capture,'guard',return_value=['AAA']):
                result=capture.run(runner_sha='fixed',execute=True,opener=lambda request,**kwargs:Response(payload('AAA'),request.full_url),clock=lambda:next(times))
                self.assertEqual(result['statuses'],['CLOCK_FAILED']);self.assertTrue((output/'AAA.response.bin').exists())

    def test_real_fixed_observation_queue_and_json_rejections(self):
        queue=capture.guard(hashlib.sha256(capture.SOURCE.read_bytes()).hexdigest())
        self.assertEqual(len(queue),104);self.assertIn('MRNA',queue);self.assertNotIn('WBD',queue)
        self.assertEqual(queue[-3:],['TSM','QQQ','SPY'])
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}'):
            with self.assertRaises(ValueError):capture.loads(raw)
        with self.assertRaises(ValueError): capture.guard('0'*64)

    def test_eight_attempts_four_workers_keep_queue_order(self):
        with TemporaryDirectory() as directory:
            output=Path(directory)/'capture'; barrier=Barrier(4); lock=Lock()
            state={'active':0,'peak':0,'calls':[]};queue=['AAA'+str(index) for index in range(8)]
            def opener(request,**kwargs):
                ticker=request.full_url.split('/chart/')[1].split('?')[0]
                with lock:
                    state['active']+=1;state['peak']=max(state['peak'],state['active']);state['calls'].append(ticker)
                barrier.wait(timeout=5)
                with lock:state['active']-=1
                return Response(payload(ticker),request.full_url)
            with patch.object(capture,'OUTPUT',output),patch.object(capture,'guard',return_value=queue):
                result=capture.run(runner_sha='fixed',execute=True,max_new=8,workers=4,opener=opener,clock=lambda:CLOCK)
                index=json.loads(Path(result['last_index']).read_text())
                self.assertEqual([row['ticker'] for row in index['entries']],queue)
                self.assertEqual(state['peak'],4)
                self.assertEqual(sorted(state['calls']),queue)


if __name__=='__main__':unittest.main()
