import asyncio
import unittest
from docs.candidates.runtime_request_drain_20261105 import RequestDrain, DrainMiddleware


class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_inflight_completes_new_requests_refused_and_resume_explicit(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls, messages = [], []
        async def app(scope, receive, send):
            calls.append(scope['type'])
            entered.set()
            await release.wait()
            await send(dict(type='http.response.start',status=200,headers=[]))
            await send(dict(type='http.response.body',body=b'ok'))
        async def send(message): messages.append(message)
        async def receive(): return dict(type='http.request',body=b'')
        gate = RequestDrain(); middleware = DrainMiddleware(app,gate)
        original = asyncio.create_task(middleware({'type':'http','method':'POST'},receive,send))
        await entered.wait()
        self.assertEqual(gate.begin(),1)
        self.assertFalse(gate.wait(0))
        with self.assertRaisesRegex(RuntimeError,'DRAIN_REQUESTS_STILL_ACTIVE'): gate.resume()
        await middleware({'type':'http','method':'POST'},receive,send)
        self.assertEqual(calls,['http'])
        self.assertEqual(messages[0]['status'],503)
        release.set(); await original
        self.assertTrue(gate.wait(0))
        await middleware({'type':'http','method':'GET'},receive,send)
        self.assertEqual(calls,['http'])
        gate.resume()
        await middleware({'type':'http','method':'POST'},receive,send)
        self.assertEqual(calls,['http','http'])

    async def test_exception_releases_count(self):
        gate = RequestDrain()
        async def broken(*args): raise ValueError('failure')
        with self.assertRaisesRegex(ValueError,'failure'):
            await DrainMiddleware(broken,gate)({'type':'http'},None,None)
        self.assertEqual(gate.begin(),0)
        self.assertTrue(gate.wait(0))

    async def test_cancelled_caller_does_not_mark_unfinished_write_drained(self):
        entered, release, committed = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def writing(scope, receive, send):
            entered.set()
            await release.wait()
            committed.set()
        gate = RequestDrain(); middleware = DrainMiddleware(writing, gate)
        caller = asyncio.create_task(middleware({'type':'http'}, None, None))
        await entered.wait()
        caller.cancel()
        with self.assertRaises(asyncio.CancelledError): await caller
        self.assertEqual(gate.begin(), 1)
        self.assertFalse(gate.wait(0))
        self.assertFalse(committed.is_set())
        pending = list(middleware._requests)
        self.assertEqual(len(pending), 1)
        release.set()
        await asyncio.gather(*pending)
        self.assertTrue(committed.is_set())
        self.assertTrue(gate.wait(0))
        self.assertFalse(middleware._requests)


if __name__ == '__main__': unittest.main()
