"""Isolated instrumentation; never installed into the running server."""
from threading import get_ident, local
from time import monotonic


class TimedRLock:
    def __init__(self, lock, events):
        self.lock=lock
        self.events=events
        self.thread=local()

    @property
    def depth(self):
        return len(getattr(self.thread,'stack',[]))

    def acquire(self,*args,**kwargs):
        started=monotonic()
        acquired=self.lock.acquire(*args,**kwargs)
        finished=monotonic()
        record=dict(kind='lock',thread_id=get_ident(),depth=self.depth+1,
                    wait_seconds=finished-started,acquired=acquired,acquired_monotonic=finished)
        if acquired:
            if not hasattr(self.thread,'stack'):self.thread.stack=[]
            self.thread.stack.append(record)
        else:self.events.append(record)
        return acquired

    def release(self):
        finished=monotonic()
        self.lock.release()  # Preserve ownership/error behavior before altering instrumentation.
        record=self.thread.stack.pop()
        self.events.append(dict(record,held_seconds=finished-record['acquired_monotonic']))

    def __enter__(self):
        return self.acquire()

    def __exit__(self,*args):
        self.release()


def instrument_router(router,events):
    original_lock=router.lock
    original_provider=router._snapshot_provider
    proxy=TimedRLock(original_lock,events)
    def provider(*args,**kwargs):
        started=monotonic();status='FAILED'
        try:
            result=original_provider(*args,**kwargs);status='COMPLETE';return result
        finally:
            events.append(dict(kind='provider',thread_id=get_ident(),depth=proxy.depth,
                               seconds=monotonic()-started,status=status))
    router.lock=proxy
    router._snapshot_provider=provider
    def restore():
        if proxy.depth:raise ValueError('CANNOT_RESTORE_ACTIVE_SCOPE')
        router.lock=original_lock
        router._snapshot_provider=original_provider
    return restore
