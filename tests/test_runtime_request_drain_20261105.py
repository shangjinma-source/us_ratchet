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


if __name__ == '__main__': unittest.main()
