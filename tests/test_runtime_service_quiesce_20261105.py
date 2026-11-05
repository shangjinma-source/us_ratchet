"""A real app task and real worker must both exit; join returning is insufficient."""
import asyncio
from threading import Event,Thread
from types import SimpleNamespace
import unittest
from docs.candidates.runtime_request_drain_20261105 import RequestDrain,DrainMiddleware
from docs.candidates.runtime_service_quiesce_20261105 import ServiceQuiescer

class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_inflight_http_then_worker_timeout_then_actual_exit(self):
  entered=asyncio.Event();finish_http=asyncio.Event();worker_entered=Event();finish_worker=Event();stop=Event()
  def work():worker_entered.set();finish_worker.wait()
  worker=Thread(target=work,name='isolated-quiesce-test',daemon=True);worker.start()
  self.assertTrue(worker_entered.wait(1));self.addCleanup(lambda:(finish_worker.set(),worker.join(1)))
  owner=SimpleNamespace(worker=worker,stop_event=stop)
  gate=RequestDrain();quiescer=ServiceQuiescer(gate=gate,worker_owner=owner);responses=[]
  async def app(scope,receive,send):entered.set();await finish_http.wait()
  async def send(value):responses.append(value)
  middleware=DrainMiddleware(app,gate)
  request=asyncio.create_task(middleware({'type':'http'},None,send));await entered.wait()
  first=await asyncio.to_thread(quiescer.quiesce,timeout=0.02)
  self.assertEqual(first['stage'],'HTTP');self.assertFalse(first['http_drained']);self.assertFalse(stop.is_set())
  await middleware({'type':'http'},None,send);self.assertEqual(responses[-2]['status'],503)
  # Cancelling the client still does not finish the underlying application.
  request.cancel()
  with self.assertRaises(asyncio.CancelledError):await request
  self.assertFalse(gate.wait(0))
  finish_http.set();await asyncio.gather(*list(middleware._requests))
  self.assertTrue(gate.wait(0))
  worker.join(timeout=0);self.assertTrue(worker.is_alive())
  second=await asyncio.to_thread(quiescer.quiesce,timeout=0.02)
  self.assertEqual(second['stage'],'WORKER');self.assertTrue(second['http_drained']);self.assertFalse(second['worker_stopped']);self.assertFalse(second['may_switch'])
  self.assertTrue(stop.is_set());self.assertTrue(worker.is_alive());self.assertFalse(gate.enter())
  finish_worker.set();worker.join(timeout=1);self.assertFalse(worker.is_alive())
  final=await asyncio.to_thread(quiescer.quiesce,timeout=0.2)
  self.assertEqual(final['status'],'QUIESCED');self.assertTrue(final['worker_stopped']);self.assertFalse(final['may_switch']);self.assertFalse(gate.enter())
  gate.resume();self.assertTrue(gate.enter());gate.leave()
if __name__=='__main__':unittest.main()
