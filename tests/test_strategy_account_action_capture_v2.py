import unittest,time,tempfile,json
from pathlib import Path
from threading import Barrier,Lock,Event
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
from data.strategy_account_action_capture_v2 import ConcurrentCaptureFilesV2,StrategyAccountActionCaptureV2

class ConcurrentActionFilesTests(unittest.TestCase):
    def test_unique_slow_writes_run_concurrently(self):
        barrier=Barrier(4);seen=[];lock=Lock()
        def write(name,raw):
            barrier.wait(timeout=3)
            time.sleep(.02)
            with lock:seen.append(name)
        store=ConcurrentCaptureFilesV2(write)
        with ThreadPoolExecutor(max_workers=4) as pool:
            paths=list(pool.map(lambda n:store.put(str(n).encode(),'.raw'),range(4)))
        self.assertEqual(len(seen),4);self.assertEqual(set(paths),set(store.files))

    def test_same_hash_single_owner_and_failure_propagation(self):
        for fail in (False,True):
            with self.subTest(fail=fail):
                count=[];ready=Event();release=Event()
                def write(name,raw):
                    count.append(name);ready.set();release.wait(3)
                    if fail:raise OSError('disk failure')
                store=ConcurrentCaptureFilesV2(write)
                with ThreadPoolExecutor(max_workers=4) as pool:
                    jobs=[pool.submit(store.put,b'same','.raw') for _ in range(4)]
                    self.assertTrue(ready.wait(2));release.set()
                    for job in jobs:
                        if fail:
                            with self.assertRaises(OSError):job.result(timeout=3)
                        else:job.result(timeout=3)
                self.assertEqual(len(count),1);self.assertEqual(len(store.files),0 if fail else 1)
                if fail:
                    with self.assertRaises(OSError):store.put(b'same','.raw')
                    self.assertEqual(len(count),1)

    def test_budget_reserves_inflight_bytes_and_dedup(self):
        ready=Event();release=Event()
        def write(name,raw):ready.set();release.wait(3)
        store=ConcurrentCaptureFilesV2(write,maximum_bytes=4)
        with ThreadPoolExecutor(max_workers=4) as pool:
            first=pool.submit(store.put,b'abcd','.raw');self.assertTrue(ready.wait(2))
            with self.assertRaisesRegex(ValueError,'TOO_LARGE'):store.put(b'x','.raw')
            duplicate=pool.submit(store.put,b'abcd','.raw');release.set()
            self.assertEqual(first.result(timeout=3),duplicate.result(timeout=3))
        self.assertEqual(store.total,4)

    def test_capture_preserves_receipts_and_failed_window(self):
        for expire in (False,True):
            with self.subTest(expire=expire),tempfile.TemporaryDirectory() as folder:
                clock=[datetime(2026,10,20,14,tzinfo=timezone.utc)]
                def fetch(ticker,*args):return {'status':200,'body':b'{}'}
                def rss():
                    if expire:clock[0]+=timedelta(seconds=120)
                    return {'status':200,'body':b'<rss/>'}
                capture=StrategyAccountActionCaptureV2(fetch=fetch,rss_fetch=rss,clock=lambda:clock[0])
                request=dict(account_id='a',state_revision='r',window_start=(clock[0]-timedelta(days=1)).isoformat(),observed_floor=clock[0].isoformat(),securities={str(i):{'ticker':'A'+str(i)} for i in range(8)},current_target_quantities={})
                path=Path(folder)/'capture'
                if expire:
                    with self.assertRaisesRegex(ValueError,'WINDOW_EXPIRED'):capture.capture(request,path)
                    self.assertTrue((path/'failed.json').exists());self.assertFalse((path/'complete.json').exists())
                else:
                    result=capture.capture(request,path)
                    self.assertEqual(len(result['documents']['action_receipts']),8)
                    self.assertEqual(len(list(path.glob('*.raw'))),1)
                    self.assertTrue((path/'complete.json').exists())
                    self.assertEqual(set(result['files']),set(result['source_hashes']))

if __name__=='__main__':unittest.main()
