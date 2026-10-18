import copy
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path('E:/Git/us_ratchet')
SOURCE=ROOT/'scripts/ndx_remaining_nine_sec_capture_20261009_v1.py'
spec=importlib.util.spec_from_file_location('fixed_sec_capture',SOURCE)
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)

def offline_slow(sender):
    sender.send(('metadata',{'http_status':200}))
    sender.send(('chunk',b'partial'))
    time.sleep(5)

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.output=self.root/'new_capture'
        self.original=self.root/'original';self.original.mkdir();self.file=self.original/'source.json';self.file.write_bytes(b'fixed source')
        self.sources={str(self.file):hashlib.sha256(b'fixed source').hexdigest()};self.namespaces={str(self.original):['source.json']}
        self.jobs=[dict(ticker='TER',cik='0000097210',accession='0001193125-26-059002',role=role,
                        url='https://www.sec.gov/Archives/edgar/data/97210/000119312526059002/'+name,
                        max_bytes=100,declared_filing={'form':'10-K'},source_submission_reference={'path':str(self.file),'sha256':self.sources[str(self.file)]})
                   for role,name in [('primary','ter-20251231.htm'),('index','index.json')]]
    def armed(self):
        stack=__import__('contextlib').ExitStack()
        stack.enter_context(patch.object(capture,'OUTPUT_ROOT',self.output))
        stack.enter_context(patch.object(capture,'_bound_inputs',return_value=(copy.deepcopy(self.jobs),self.sources,self.namespaces)))
        stack.enter_context(patch.object(capture,'_sec_headers',return_value={'User-Agent':'offline fixture not a real request'}))
        return stack
    def success(self,url,limit):
        raw=b'<html>complete original</html>' if url.endswith('.htm') else b'{"directory":{"item":[]}}'
        return dict(raw_bytes=raw,response={'http_status':200,'requested_url':url,'final_url':url},error=None,monotonic_elapsed_seconds=0,request_completed=True)
    def test_default_and_nonbool_and_fixed_roster(self):
        with patch.object(capture,'_bound_inputs',side_effect=AssertionError('Source IO')):
            for value in [False,None,1,'true',0]:self.assertEqual(capture.capture(execute=value)['network_attempt_count'],0)
        jobs,sources,namespaces=capture._bound_inputs()
        self.assertEqual(len(jobs),34);self.assertEqual(len({j['url'] for j in jobs}),34)
        self.assertEqual({j['role'] for j in jobs},{'primary','index'})
        self.assertTrue(all(j['url'].startswith('https://www.sec.gov/Archives/edgar/data/') for j in jobs))
    def test_success_exact_bytes_and_duplicate_early_refusal(self):
        with self.armed(),patch.object(capture,'_request_once',side_effect=self.success) as request:
            result=capture.capture(execute=True);self.assertEqual(result['network_attempt_count'],2)
            folder=self.output/'TER'/'000119312526059002'
            self.assertEqual((folder/'primary.raw.bin').read_bytes(),b'<html>complete original</html>')
            self.assertEqual(json.loads((folder/'primary.receipt.json').read_bytes())['source_available_at_utc'],None)
            with patch.object(capture,'_bound_inputs',side_effect=AssertionError('Must refuse before reads')):
                with self.assertRaises(ValueError):capture.capture(execute=True)
            self.assertEqual(request.call_count,2)
    def test_failed_responses_preserve_raw_stop_and_count_notattempted(self):
        for error,status,raw in [('HTTP_STATUS_NOT_200',403,b'denied original'),('REDIRECT_NOT_FOLLOWED',302,b'redirect original'),
                                 ('RESPONSE_BYTE_BOUND_EXCEEDED',200,b'x'*101),('TOTAL_REQUEST_DEADLINE_EXCEEDED',200,b'partial')]:
            with self.subTest(error=error):
                self.output=self.root/error
                response=dict(raw_bytes=raw,response={'http_status':status},error=error,monotonic_elapsed_seconds=25,request_completed=False)
                with self.armed(),patch.object(capture,'_request_once',return_value=response) as request:
                    with self.assertRaises(ValueError):capture.capture(execute=True)
                    self.assertEqual(request.call_count,1)
                    folder=self.output/'TER'/'000119312526059002'
                    self.assertEqual((folder/'primary.raw.bin').read_bytes(),raw)
                    failure=json.loads((self.output/'failure.json').read_bytes())
                    self.assertEqual((failure['network_attempt_count'],failure['failed_receipt_count'],failure['not_attempted_count']),(1,1,1))
                    self.assertTrue(failure['not_attempted_is_not_a_HTTP_missing_source_result'])
                    with self.assertRaises(ValueError):capture.capture(execute=True)
    def test_source_and_directory_drift_fail_preserve(self):
        for mode in ('source','input_namespace','output_directory','own_started'):
            with self.subTest(mode=mode):
                self.output=self.root/mode
                def drift(url,limit):
                    if mode=='source':self.file.write_bytes(b'drift')
                    elif mode=='input_namespace':(self.original/'extra.json').write_bytes(b'extra')
                    elif mode=='output_directory':(self.output/'unregistered_empty').mkdir()
                    else:(self.output/'started.json').write_bytes(b'drift')
                    return self.success(url,limit)
                with self.armed(),patch.object(capture,'_request_once',side_effect=drift) as request:
                    with self.assertRaises(ValueError):capture.capture(execute=True)
                    self.assertEqual(request.call_count,1);self.assertTrue((self.output/'failure.json').is_file())
                self.file.write_bytes(b'fixed source')
                extra=self.original/'extra.json'
                if extra.exists():extra.unlink()
    def test_existing_namespace_refused_before_any_read_or_request(self):
        self.output.mkdir()
        with self.armed(),patch.object(capture,'_bound_inputs',side_effect=AssertionError('Source IO')),patch.object(capture,'_request_once',side_effect=AssertionError('HTTP')):
            with self.assertRaises(ValueError):capture.capture(execute=True)
    def test_real_slow_child_total_deadline_killed_partial_preserved(self):
        context=multiprocessing.get_context('spawn');receiver,sender=context.Pipe(duplex=False)
        process=context.Process(target=offline_slow,args=(sender,));process.start();sender.close()
        # Spawn time is outside network timing only in this offline transport fixture.
        deadline=time.monotonic()+5
        while not receiver.poll(.05):self.assertLess(time.monotonic(),deadline)
        with patch.object(capture,'_start_transport',return_value=(process,receiver)),patch.object(capture,'DEADLINE_SECONDS',.15):
            start=time.monotonic();result=capture._request_once(self.jobs[0]['url'],100)
        self.assertEqual(result['error'],'TOTAL_REQUEST_DEADLINE_EXCEEDED')
        self.assertEqual(result['raw_bytes'],b'partial');self.assertFalse(process.is_alive());self.assertLess(time.monotonic()-start,2)
    def test_worker_does_not_follow_redirect_and_parent_bounds_chunk(self):
        class Sender:
            def __init__(self):self.values=[]
            def send(self,value):self.values.append(value)
            def close(self):pass
        class Response:
            status=302
            def getheader(self,key):return 'https://evil.invalid/' if key=='Location' else None
            def read1(self,count):return b''
        class Connection:
            requests=[]
            def __init__(self,*args,**kwargs):pass
            def request(self,*args,**kwargs):self.requests.append(args)
            def getresponse(self):return Response()
            def close(self):pass
        import http.client
        sender=Sender()
        with patch.object(http.client,'HTTPSConnection',Connection),patch.object(capture,'_sec_headers',return_value={}):
            capture._http_worker(sender,self.jobs[0]['url'],100)
        self.assertEqual(len(Connection.requests),1);self.assertEqual(sender.values[0][1]['http_status'],302)
        self.assertEqual(sender.values[-1][0],'complete')

    def test_parent_transport_oversize_and_partial_exception(self):
        class Process:
            alive=True
            def is_alive(self):return self.alive
            def terminate(self):self.alive=False
            def join(self,timeout):pass
            def kill(self):self.alive=False
        class Receiver:
            def __init__(self,messages):self.messages=iter(messages)
            def poll(self,remaining):return True
            def recv(self):return next(self.messages)
            def close(self):pass
        for messages,error,raw in [
            ([('metadata',{'http_status':200}),('chunk',b'123456789')],'RESPONSE_BYTE_BOUND_EXCEEDED',b'123456789'),
            ([('metadata',{'http_status':200}),('chunk',b'part'),('error','TimeoutError')],'NETWORK_TimeoutError',b'part'),
            ([('metadata',{'http_status':403}),('chunk',b'denied'),('complete',None)],'HTTP_STATUS_NOT_200',b'denied'),
            ([('metadata',{'http_status':302}),('chunk',b'moved'),('complete',None)],'REDIRECT_NOT_FOLLOWED',b'moved')]:
            with self.subTest(error=error):
                process=Process();receiver=Receiver(messages)
                with patch.object(capture,'_start_transport',return_value=(process,receiver)):
                    result=capture._request_once(self.jobs[0]['url'],8)
                self.assertEqual(result['error'],error);self.assertEqual(result['raw_bytes'],raw);self.assertFalse(process.is_alive())

if __name__=='__main__':unittest.main()
