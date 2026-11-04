import unittest
from threading import RLock,Thread,Event
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from scripts.research.snapshot_timing_probe_20261105 import instrument_router


class SnapshotTiming(unittest.TestCase):
    def router(self,provider=None):
        router=object.__new__(RollingMonthlyRuntimeRouter)
        router.lock=RLock();router._active_snapshot=None;router._loading_snapshot=False
        snapshot=dict(registry_path='registry.json',registry_sha256='a'*64,
                      archive_path='archive.json',archive_sha256='b'*64,revision=1)
        for key,value in snapshot.items():
            if key!='revision':setattr(router,key,value)
        router._snapshot_provider=provider or (lambda:snapshot)
        return router

    def test_nested_scope_one_provider_and_original_values(self):
        router=self.router();original_lock=router.lock;original_provider=router._snapshot_provider
        events=[];restore=instrument_router(router,events)
        with router.snapshot_operation() as first:
            with router.snapshot_operation() as second:self.assertIs(first,second)
        self.assertEqual(len([e for e in events if e['kind']=='provider']),1)
        self.assertEqual(sorted(e['depth'] for e in events if e['kind']=='lock'),[1,2])
        self.assertIsNone(router._active_snapshot)
        restore()
        self.assertIs(router.lock,original_lock);self.assertIs(router._snapshot_provider,original_provider)

    def test_competing_thread_wait_separate_from_provider(self):
        router=self.router();events=[];restore=instrument_router(router,events)
        attempted=Event();done=Event()
        def worker():
            self.assertFalse(router.lock.acquire(blocking=False))
            attempted.set()
            with router.snapshot_operation():pass
            done.set()
        with router.snapshot_operation():
            thread=Thread(target=worker);thread.start();self.assertTrue(attempted.wait(1))
            self.assertFalse(done.wait(.04))
        thread.join(1);self.assertFalse(thread.is_alive())
        waits=[e['wait_seconds'] for e in events if e['kind']=='lock']
        self.assertGreater(max(waits),.02)
        self.assertEqual(len({e['thread_id'] for e in events}),2)
        self.assertEqual(len([e for e in events if e['kind']=='provider']),2)
        failed=[e for e in events if e['kind']=='lock' and not e['acquired']]
        self.assertEqual(len(failed),1);self.assertNotIn('held_seconds',failed[0])
        restore()

    def test_provider_exception_releases_and_recovers(self):
        router=self.router();original=router._snapshot_provider;calls=[]
        def fail_once():
            calls.append(1)
            if len(calls)==1:raise ValueError('FIXTURE')
            return original()
        router._snapshot_provider=fail_once;events=[];restore=instrument_router(router,events)
        with self.assertRaisesRegex(ValueError,'FIXTURE'):
            with router.snapshot_operation():pass
        with router.snapshot_operation():pass
        self.assertEqual([e['status'] for e in events if e['kind']=='provider'],['FAILED','COMPLETE'])
        self.assertEqual(router.lock.depth,0);self.assertFalse(router._loading_snapshot)
        restore()

if __name__=='__main__':unittest.main()
