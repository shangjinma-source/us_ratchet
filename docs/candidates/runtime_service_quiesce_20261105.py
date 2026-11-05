"""Unmounted owner-only quiescence; neither process switching nor worker restart.

Call from a supervisor thread while holding exclusive service lifecycle ownership
(no concurrent start_worker). The stop Event and Thread are the pipeline's actual
objects. A returned join is not proof of termination: is_alive is authoritative.
"""
import math
import time
from threading import Event,Thread,current_thread,Lock


class ServiceQuiescer:
    def __init__(self,*,gate,worker_owner):
        self.gate,self.owner=gate,worker_owner
        self._lock=Lock()

    def quiesce(self,*,timeout):
        """One total monotonic budget; failure leaves HTTP admission closed.

        Do not call on the ASGI loop. Scheduled financial tasks and other
        processes are outside this explicit single-service scope.
        """
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<=timeout<=60:
            raise ValueError('QUIESCE_TIMEOUT_INVALID')
        if not self._lock.acquire(blocking=False):raise RuntimeError('QUIESCE_ALREADY_RUNNING')
        deadline=time.monotonic()+timeout
        try:
            self.gate.begin()
            if not self.gate.wait(max(0,deadline-time.monotonic())):
                return dict(status='QUIESCE_TIMEOUT',stage='HTTP',http_drained=False,worker_stopped=False,gate_closed=True,may_switch=False)
            worker=self.owner.worker;stop=self.owner.stop_event
            if not isinstance(stop,Event) or (worker is not None and not isinstance(worker,Thread)):
                raise TypeError('QUIESCE_WORKER_INTERFACE_INVALID')
            if worker is current_thread():raise RuntimeError('QUIESCE_CANNOT_JOIN_SELF')
            # Equivalent stop signal, but avoid stop_worker's unrelated fixed
            # two-second timeout exceeding the caller's remaining total budget.
            stop.set()
            if worker is not None and worker.is_alive():worker.join(timeout=max(0,deadline-time.monotonic()))
            if self.owner.worker is not worker or self.owner.stop_event is not stop or not stop.is_set():
                raise RuntimeError('QUIESCE_WORKER_GENERATION_CHANGED')
            alive=worker is not None and worker.is_alive()
            if alive:
                return dict(status='QUIESCE_TIMEOUT',stage='WORKER',http_drained=True,worker_stopped=False,gate_closed=True,may_switch=False)
            return dict(status='QUIESCED',stage='COMPLETE',http_drained=True,worker_stopped=True,gate_closed=True,may_switch=False,
                        scope='THIS_HTTP_GATE_AND_ONE_REGISTERED_WORKER_ONLY')
        finally:
            self._lock.release()
