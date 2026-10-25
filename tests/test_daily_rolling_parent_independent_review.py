from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
import json,unittest
from core.strategy_account_ledger import canonical
import test_strategy_daily_rolling_parent_v3 as fixtures

class IndependentRollingParent(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.RollingParentTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  row=next(r for r in self.f.sessions if r['date']=='2026-10-21');self.f.run_day(row)
  self.now=datetime.fromisoformat(next(r for r in self.f.sessions if r['date']=='2026-10-22')['open'])
  self.directory=self.f.root/'runs/2026-10-21';self.terminal=json.loads((self.directory/'terminal.json').read_bytes())
 def terminal_write(self,value):(self.directory/'terminal.json').write_bytes(canonical(value))
 def receipt_change(self,update):
  path=self.directory/'receipt.json';value=json.loads(path.read_bytes());value.update(update);raw=canonical(value);path.write_bytes(raw)
  terminal=deepcopy(self.terminal);terminal['receipt_reference']['sha256']=sha256(raw).hexdigest();self.terminal_write(terminal)
 def test_future_terminal_and_received_refused(self):
  t=deepcopy(self.terminal);t['finished_at']=(self.now+timedelta(seconds=1)).isoformat();self.terminal_write(t)
  with self.assertRaisesRegex(ValueError,'ROLLING_PARENT_FUTURE'):self.f.parent(self.now)
  self.terminal_write(self.terminal);self.receipt_change(dict(available_at=(self.now+timedelta(seconds=1)).isoformat()))
  with self.assertRaisesRegex(ValueError,'ROLLING_PARENT_FUTURE'):self.f.parent(self.now)
 def test_null_policy_cannot_promote(self):
  self.receipt_change(dict(release_sha256='f'*64))
  with self.assertRaisesRegex(ValueError,'ROLLING_POLICY_CHANGED'):self.f.parent(self.now)
 def test_content_addressed_path_cannot_escape(self):
  path=self.directory/'source-paths.json';manifest=json.loads(path.read_bytes());name=next(iter(manifest));manifest[name]['path']='../outside.bin'
  raw=canonical(manifest);path.write_bytes(raw);t=deepcopy(self.terminal);t['manifest_reference']['sha256']=sha256(raw).hexdigest();self.terminal_write(t)
  with self.assertRaisesRegex(ValueError,'ROLLING_SOURCE_PATH_CHANGED'):self.f.parent(self.now)
 def test_prior_session_identity_and_configuration_rejected(self):
  t=deepcopy(self.terminal);t['session']='2026-10-20';self.terminal_write(t)
  with self.assertRaisesRegex(ValueError,'ROLLING_PARENT_CONFIGURATION_CHANGED'):self.f.parent(self.now)
  t=deepcopy(self.terminal);t['configuration_sha256']='b'*64;self.terminal_write(t)
  with self.assertRaisesRegex(ValueError,'ROLLING_PARENT_CONFIGURATION_CHANGED'):self.f.parent(self.now)

 def test_oversized_metadata_rejected_before_json(self):
  with (self.directory/'terminal.json').open('wb') as stream:stream.truncate(1024*1024+1)
  with self.assertRaisesRegex(ValueError,'ROLLING_TERMINAL_READ_BUDGET'):self.f.parent(self.now)
 def test_semantically_equal_timezone_does_not_change_session(self):
  from datetime import timezone
  receipt=json.loads((self.directory/'receipt.json').read_bytes());session=receipt['execution_session']
  for key in ('open','close'):session[key]=datetime.fromisoformat(session[key]).astimezone(timezone.utc).isoformat()
  self.receipt_change(dict(execution_session=session))
  result=self.f.parent(self.now)
  self.assertEqual(result['provenance']['kind'],'PREVIOUS_SESSION_PACKET')
