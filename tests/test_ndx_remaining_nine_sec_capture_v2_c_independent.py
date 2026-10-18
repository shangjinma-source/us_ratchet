import copy
import hashlib
import importlib.util
import inspect
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path('E:/Git/us_ratchet')
SOURCE=ROOT/'scripts/ndx_remaining_nine_sec_capture_20261009_v2.py'
EXPECTED='e345b980a6a94669cb027da472fd19c69faf23789ecf66891c37bddf076208b7'
def digest(raw): return hashlib.sha256(raw).hexdigest()
assert digest(SOURCE.read_bytes())==EXPECTED
spec=importlib.util.spec_from_file_location('independent_capture_v2',SOURCE)
capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
DETAILS={}

def mismatch_child(sender,audit):
    import http.client
    with patch.object(http.client,'HTTPSConnection',side_effect=AssertionError('NETWORK CONSTRUCTOR FORBIDDEN')) as constructor:
        capture._http_worker(sender,'https://www.sec.gov/Archives/edgar/data/97210/x/primary.htm',100,'f'*64)
        audit.send(dict(constructor_calls=constructor.call_count,loaded_sha=capture.LOADED_SOURCE_SHA))
        audit.close()
        assert constructor.call_count==0

def slow_child(sender):
    sender.send(('metadata',{'http_status':200}))
    sender.send(('chunk',b'offline-partial'))
    time.sleep(10)

class IndependentReview(unittest.TestCase):
    def test_01_complete_roster_loaded_version_and_arming(self):
        raw=capture.PLAN.read_bytes();plan=json.loads(raw)
        jobs,sources,namespaces=capture._bound_inputs()
        expected=[]
        for row in plan['proposed_first_batch_primary_and_index_roster']:
            for role,key,limit in [('primary','primary_url',32_000_000),('index','attachment_listing_url_to_capture_once',2_000_000)]:
                expected.append(dict(ticker=row['ticker_context_only_not_sid'],cik=row['cik'],accession=row['declared_filing']['accessionNumber'],role=role,url=row[key],max_bytes=limit,declared_filing=row['declared_filing'],source_submission_reference=row['source_submission_reference']))
        self.assertEqual(jobs,expected);self.assertEqual(len(jobs),34)
        self.assertEqual(len(sources),21);self.assertEqual(len(namespaces),4)
        self.assertEqual(sources[str(SOURCE)],EXPECTED);self.assertEqual(capture.LOADED_SOURCE_SHA,EXPECTED)
        self.assertEqual(set(sources),set(plan['source_hashes'])|{str(capture.PLAN),str(SOURCE)})
        self.assertEqual(list(inspect.signature(capture.capture).parameters),['execute'])
        with patch.object(Path,'read_bytes',side_effect=AssertionError('DEFAULT SOURCE READ FORBIDDEN')),patch.object(capture,'_start_transport',side_effect=AssertionError('SPAWN FORBIDDEN')):
            for value in [False,None,0,1,'true',{},[]]:
                self.assertEqual(capture.capture(execute=value)['network_attempt_count'],0)
        DETAILS['roster']=dict(jobs=34,source_count=21,plan_source_count=19,namespaces=4,loaded_source_sha=EXPECTED,strict_arming_zero_read=True)

    def test_02_actual_windows_junction_ancestor_and_member(self):
        self.assertEqual(os.name,'nt','Actual Windows junction review requires Windows')
        with tempfile.TemporaryDirectory(prefix='capture_v2_c_junction_') as directory:
            base=Path(directory).absolute();target=base/'target';target.mkdir()
            sentinel=target/'sentinel';sentinel.write_bytes(b'unchanged fixture target')
            before=digest(sentinel.read_bytes());link=base/'junction'
            command=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True,timeout=5)
            self.assertEqual(command.returncode,0,command.stdout+command.stderr)
            try:
                self.assertTrue(link.is_junction());self.assertFalse(link.is_symlink())
                self.assertTrue(link.lstat().st_file_attributes & 1024)
                with patch.object(capture,'OUTPUT_ROOT',link/'capture'),patch.object(capture,'_bound_inputs',side_effect=AssertionError('BOUND INPUT MUST NOT RUN')) as bound,patch.object(capture,'_request_once',side_effect=AssertionError('HTTP FORBIDDEN')):
                    with self.assertRaisesRegex(ValueError,'reparse'):capture.capture(execute=True)
                    bound.assert_not_called()
                with self.assertRaisesRegex(ValueError,'reparse'):capture.inventory(base)
                with patch.object(Path,'read_bytes',side_effect=AssertionError('LINKED MEMBER READ FORBIDDEN')):
                    with self.assertRaisesRegex(ValueError,'reparse'):capture.safe_path(link/'sentinel')
                self.assertEqual(digest(sentinel.read_bytes()),before)
                self.assertEqual(sorted(p.name for p in target.iterdir()),['sentinel'])
                DETAILS['junction']=dict(actual_windows_junction=True,is_symlink=False,reparse_attribute=1024,ancestor_pre_bound_rejected=True,member_before_read_rejected=True,target_unchanged=True)
            finally:
                # Remove only the verified junction itself. Never recurse through it.
                self.assertEqual(link.parent,base);self.assertEqual(target.parent,base)
                self.assertTrue(link.is_junction());os.rmdir(link)
                self.assertTrue(target.is_dir());self.assertEqual(digest(sentinel.read_bytes()),before)

    def test_03_parent_drift_retains_attempt_and_stops_next(self):
        jobs,_,_=capture._bound_inputs();jobs=copy.deepcopy(jobs[:2])
        with tempfile.TemporaryDirectory(prefix='capture_v2_c_drift_') as directory:
            base=Path(directory);fixed=base/'fixed';fixed.mkdir();source=fixed/'one';source.write_bytes(b'fixed')
            output=base/'output';sources={str(source):digest(b'fixed'),str(SOURCE):EXPECTED};namespaces={str(fixed):['one']}
            drift=False;read=Path.read_bytes
            def read_view(path):
                if path==SOURCE and drift:return b'simulated current disk source revision'
                return read(path)
            def response(url,limit):
                nonlocal drift
                drift=True
                return dict(raw_bytes=b'<html>offline preserved</html>',response={'http_status':200},error=None,monotonic_elapsed_seconds=0,request_completed=True)
            with patch.object(capture,'OUTPUT_ROOT',output),patch.object(capture,'_bound_inputs',return_value=(jobs,sources,namespaces)),patch.object(capture,'_sec_headers',return_value={}),patch.object(capture,'_request_once',side_effect=response) as requests,patch.object(Path,'read_bytes',read_view):
                with self.assertRaisesRegex(ValueError,'Loaded capture source version drift'):capture.capture(execute=True)
                self.assertEqual(requests.call_count,1)
            failure=json.loads((output/'failure.json').read_bytes())
            self.assertEqual((failure['network_attempt_count'],failure['completed_receipt_count'],failure['failed_receipt_count'],failure['not_attempted_count']),(1,1,0,1))
            self.assertEqual(failure['not_attempted_jobs'],jobs[1:])
            self.assertTrue(failure['not_attempted_is_not_a_HTTP_missing_source_result'])
            self.assertFalse((output/'result.json').exists())
            with patch.object(capture,'OUTPUT_ROOT',output),patch.object(capture,'_bound_inputs',side_effect=AssertionError('RETRY IO FORBIDDEN')):
                with self.assertRaisesRegex(ValueError,'already exists'):capture.capture(execute=True)
            DETAILS['parent_drift']=dict(scope='Path.read_bytes simulated drift, original source disk unchanged',attempted=1,completed_receipts=1,failed_http_receipts=0,not_attempted=1,retry_before_io_rejected=True)

    def test_04_spawn_mismatch_and_deadline_inside_orchestration(self):
        context=multiprocessing.get_context('spawn')
        receiver,sender=context.Pipe(duplex=False);audit_recv,audit_send=context.Pipe(duplex=False)
        process=context.Process(target=mismatch_child,args=(sender,audit_send));process.start();sender.close();audit_send.close()
        try:
            self.assertTrue(receiver.poll(5));self.assertEqual(receiver.recv(),('error','ValueError'))
            self.assertTrue(audit_recv.poll(5));audit=audit_recv.recv()
            self.assertEqual(audit,dict(constructor_calls=0,loaded_sha=EXPECTED))
            process.join(5);self.assertFalse(process.is_alive());self.assertEqual(process.exitcode,0)
        finally:
            if process.is_alive():process.terminate();process.join(1)
            receiver.close();audit_recv.close()
        jobs,_,_=capture._bound_inputs();jobs=copy.deepcopy(jobs[:2]);processes=[]
        def start_transport(url,limit):
            receive,send=context.Pipe(duplex=False)
            child=context.Process(target=slow_child,args=(send,));processes.append(child)
            child.start();send.close();return child,receive
        with tempfile.TemporaryDirectory(prefix='capture_v2_c_deadline_') as directory:
            output=Path(directory)/'output'
            with patch.object(capture,'OUTPUT_ROOT',output),patch.object(capture,'_bound_inputs',return_value=(jobs,{str(SOURCE):EXPECTED},{})),patch.object(capture,'_sec_headers',return_value={}),patch.object(capture,'DEADLINE_SECONDS',.8),patch.object(capture,'_start_transport',side_effect=start_transport):
                begin=time.monotonic()
                with self.assertRaisesRegex(ValueError,'TOTAL_REQUEST_DEADLINE_EXCEEDED'):capture.capture(execute=True)
                elapsed=time.monotonic()-begin
            self.assertEqual(len(processes),1);self.assertFalse(processes[0].is_alive());self.assertIsNotNone(processes[0].exitcode)
            self.assertLess(elapsed,3)
            folder=output/jobs[0]['ticker']/jobs[0]['accession'].replace('-','')
            self.assertEqual((folder/'primary.raw.bin').read_bytes(),b'offline-partial')
            receipt=json.loads((folder/'primary.receipt.json').read_bytes());failure=json.loads((output/'failure.json').read_bytes())
            self.assertEqual(receipt['error'],'TOTAL_REQUEST_DEADLINE_EXCEEDED');self.assertFalse(receipt['response']['request_completed'])
            self.assertEqual((failure['network_attempt_count'],failure['failed_receipt_count'],failure['not_attempted_count']),(1,1,1))
            self.assertFalse(any(p.pid==processes[0].pid for p in multiprocessing.active_children()))
            DETAILS['spawn']=dict(mismatch_constructor_calls=0,mismatch_exitcode=process.exitcode,offline_slow_child_pid=processes[0].pid,deadline_seconds=.8,spawn_inside_request_timer=True,partial_raw_preserved=True,elapsed_with_cleanup=elapsed,child_alive=False,scope='short synthetic parent deadline mechanism; no real HTTP or full 25-second SEC request')

if __name__=='__main__':unittest.main()
