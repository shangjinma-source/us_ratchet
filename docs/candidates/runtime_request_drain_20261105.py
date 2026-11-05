"""Local lifecycle-controlled HTTP draining, without a public control endpoint.

Only a server owner can call begin/resume. A drained gate is not evidence that
background workers, scheduled tasks or another process have stopped writing.
"""
from threading import Condition
import asyncio


class RequestDrain:
    def __init__(self):
        self._condition = Condition()
        self._draining = False
        self._active = 0

    def enter(self):
        with self._condition:
            if self._draining:
                return False
            self._active += 1
            return True

    def leave(self):
        with self._condition:
            if self._active <= 0:
                raise RuntimeError('DRAIN_REQUEST_COUNT_INVALID')
            self._active -= 1
            self._condition.notify_all()

    def begin(self):
        with self._condition:
            self._draining = True
            return self._active

    def wait(self, timeout):
        """Blocking supervisor operation; never call on the ASGI event loop."""
        if not isinstance(timeout, (int, float)) or not 0 <= timeout <= 60:
            raise ValueError('DRAIN_TIMEOUT_INVALID')
        with self._condition:
            if not self._draining:
                raise RuntimeError('DRAIN_NOT_STARTED')
            return self._condition.wait_for(lambda: self._active == 0, timeout=timeout)

    def resume(self):
        with self._condition:
            if self._active:
                raise RuntimeError('DRAIN_REQUESTS_STILL_ACTIVE')
            self._draining = False


class DrainMiddleware:
    def __init__(self, app, gate):
        self.app, self.gate = app, gate
        self._requests = set()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        if not self.gate.enter():
            body = b'{"status":"SERVICE_DRAINING","retryable":true}'
            await send(dict(type='http.response.start', status=503, headers=[
                (b'content-type', b'application/json'), (b'cache-control', b'no-store'),
                (b'retry-after', b'5'), (b'content-length', str(len(body)).encode())]))
            await send(dict(type='http.response.body', body=body))
            return
        # A cancelled HTTP caller does not prove that an account write stopped.
        # Keep ownership/counting until the actual application task terminates.
        try:
            task = asyncio.create_task(self.app(scope, receive, send))
        except BaseException:
            self.gate.leave()
            raise
        self._requests.add(task)
        def completed(request):
            self._requests.discard(request)
            self.gate.leave()
            if not request.cancelled():
                request.exception()  # Observe failures after the caller disconnected.
        task.add_done_callback(completed)
        await asyncio.shield(task)
