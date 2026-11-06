import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from scripts.research.finish_roa_monthly_windows import WindowsAdapter
from api.roa_runtime_binding import build_runtime_binding_router

class AdapterTests(unittest.TestCase):
 def test_binding_captured_not_request_disk(self):
  config={'roa':{'monthly_selections':{'2026-12':{'path':'m','sha256':'artifact'}}}}
  router=build_runtime_binding_router(active_sha256='loaded',configuration_path='c',configuration_sha256='hash',configuration=config)
  config['roa']['monthly_selections'].clear()
  response=router.routes[0].endpoint()
  self.assertEqual(json.loads(response.body)['loaded_monthly_selections']['2026-12']['sha256'],'artifact')
 def fixture(self, missing=False):
  identity=dict(pid=123,creation_date='date',command_line='python -m api.server --port 8010')
  def get(path):
   if path.endswith('runtime-binding'):
    if missing: raise ValueError('404')
    return dict(loaded_active_sha256='a'*64,loaded_monthly_selections={'2026-12':{'sha256':'artifact'}})
   if path.endswith('/config'):return dict(active=True,strategy_epoch='epoch')
   return dict(execution_session='2026-12-01',strategy_epoch='epoch')
  adapter=WindowsAdapter('.',identity,'2026-12','artifact',powershell=lambda command:json.dumps(identity),get_json=get)
  adapter.listener=lambda:dict(identity)
  return adapter
 def test_missing_binding_refuses(self):
  with self.assertRaisesRegex(ValueError,'NOT_IMPLEMENTED'):self.fixture(True).inspect()
 def test_exact_loaded_evidence(self):
  observed=self.fixture().inspect();self.assertTrue(observed['healthy']);self.assertEqual(observed['active_sha256'],'a'*64)
 def test_process_identity_race_blocks_restart(self):
  adapter=self.fixture()
  with self.assertRaisesRegex(ValueError,'PROCESS_IDENTITY'):adapter.restart(expected_process_identity={'pid':123},expected_active_sha256='hash')
 def test_http_owner_change_rejected(self):
  adapter=self.fixture(); calls=[adapter.expected_process,dict(adapter.expected_process,pid=999)]
  adapter.listener=lambda:calls.pop(0)
  with self.assertRaisesRegex(ValueError,'HTTP_PROCESS_CHANGED'):adapter.inspect()
 def test_new_pid_initializing_and_resume(self):
  with TemporaryDirectory() as folder:
   adapter=self.fixture(); adapter.state_path=Path(folder)/'state.json'
   record=dict(old_process=adapter.expected_process,restart_started_at=0)
   adapter.save_state(record)
   new=dict(adapter.expected_process,pid=456,creation_date='newdate')
   adapter.discover_started=lambda state:dict(new)
   adapter.lookup_process=lambda pid:dict(new) if pid==456 else None
   adapter.listener=lambda:None
   self.assertEqual(adapter.inspect()['state'],'LIVE_INITIALIZING')
   self.assertEqual(json.loads(adapter.state_path.read_bytes())['new_process'],new)
   adapter.discover_started=lambda state:self.fail('must reuse persisted identity')
   self.assertEqual(adapter.inspect()['process_identity'],new)
 def test_live_unhealthy_not_absent(self):
  adapter=self.fixture();adapter.get_json=lambda path: (_ for _ in ()).throw(TimeoutError())
  self.assertEqual(adapter.inspect()['state'],'LIVE_INITIALIZING')

if __name__=='__main__':unittest.main()
