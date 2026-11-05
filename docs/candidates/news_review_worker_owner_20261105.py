"""Candidate lifecycle owner for actual asynchronous investment-review threads.

Install once before exposing a fresh service. Closing is irreversible; it does
not cancel models, stop other services, or authorize a production switch.
"""
import math
import time
from threading import Event, RLock, Thread, current_thread
from types import FunctionType
from data.news_investment_service_v1 import NewsInvestmentService


class ReviewWorkerOwner:
    def __init__(self, service):
        if not isinstance(service, NewsInvestmentService) or 'start' in service.__dict__:
            raise ValueError('REVIEW_OWNER_FRESH_SERVICE_REQUIRED')
        self.service = service
        self.closed = Event()
        self.lock = RLock()
        self.workers = []
        original = NewsInvestmentService.start
        start = FunctionType(original.__code__, dict(original.__globals__, Thread=self._thread),
                             original.__name__, original.__defaults__, original.__closure__)
        start.__kwdefaults__ = original.__kwdefaults__
        self._start = start.__get__(service, type(service))
        service.start = self.start

    def _thread(self, *args, **kwargs):
        worker = Thread(*args, **kwargs)
        self.workers.append(worker)
        return worker

    def start(self, binding, *, event_pending=None):
        with self.lock:
            if self.closed.is_set():
                raise ValueError('REVIEW_SERVICE_CLOSING')
            # Registration and actual Thread.start finish before closing can
            # inspect the collection. No lock is held during model execution.
            return self._start(binding, event_pending=event_pending)

    def close_and_wait(self, *, timeout):
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 <= timeout <= 60:
            raise ValueError('REVIEW_DRAIN_TIMEOUT_INVALID')
        deadline = time.monotonic() + timeout
        self.closed.set()
        if not self.lock.acquire(timeout=max(0, deadline-time.monotonic())):
            return dict(status='REVIEW_DRAIN_TIMEOUT', stage='START', may_switch=False)
        try:
            workers = tuple(self.workers)
        finally:
            self.lock.release()
        for worker in workers:
            if worker is current_thread():
                raise RuntimeError('REVIEW_CANNOT_JOIN_SELF')
            if worker.is_alive():
                worker.join(max(0, deadline-time.monotonic()))
        alive = sum(worker.is_alive() for worker in workers)
        return dict(status='REVIEW_DRAIN_TIMEOUT' if alive else 'REVIEWS_DRAINED',
                    stage='WORKERS', alive=alive, may_switch=False)
