from copy import deepcopy
from datetime import datetime,timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_session_capture import encoded
from data.strategy_daily_rolling_runner_v3 import run_rolling_sources,V3_SOURCES
import test_strategy_daily_rolling_parent_v3 as fixtures

class RollingRunnerTests(unittest.TestCase):
 def setUp(self):
  self.f=fixtures.RollingParentTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
  self.root=self.f.root;self.calls=[]
  from test_strategy_daily_continuity_normalizer import ROOT
  pins=[]
  for name in V3_SOURCES:
   raw=(ROOT/name).read_bytes();path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
   pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
  capture=self.f.put('rolling-capture.json',encoded(self.f.f.capture.configuration))
  self.config=dict(schema='SERVER_ROLLING_DAILY_SOURCE_V3',source_pins=pins,capture_configuration=capture,
   first_execution_date='2026-10-21',seed_receipt=self.f.f.parent,seed_source_paths=self.f.seed_paths,
   accepted_prior_configuration_sha256=[],runs_root='runs',account_id=self.f.f.accounts.read()['account_id'])
 def run_day(self,day,**overrides):
  row=next(r for r in self.f.sessions if r['date']==day);index=self.f.sessions.index(row)
  self.f.f.now=datetime.fromisoformat(row['open'])-timedelta(minutes=30)
  window=self.f.sessions[index-20:index]
  for item in window:self.f.prices.setdefault(item['date'],'1000')
  body=deepcopy(self.f.template);series=body['chart']['result'][0]
  series['timestamp']=[int(datetime.fromisoformat(r['close']).timestamp()) for r in window]
  values=[float(self.f.prices[r['date']]) for r in window]
  series['indicators']['quote'][0]['close']=values;series['indicators']['adjclose'][0]['adjclose']=values
  def daily(*args):self.calls.append('daily');return dict(status=200,body=canonical(body))
  def official():self.calls.append('official');return dict(status=200,body=self.f.f.capture.official)
  raw=canonical(self.config)
  args=dict(root=self.root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),execute=True,
   account_reader=self.f.f.accounts.read,target_reader=lambda:self.f.f.target,clock=lambda:self.f.f.now,
   fetch_daily=daily,fetch_official=official)
  args.update(overrides);return run_rolling_sources(**args)
 def test_two_real_pipeline_sessions_and_duplicate_zero_calls(self):
  before=self.f.f.accounts.path.read_bytes()
  self.assertEqual(self.run_day('2026-10-21')['status'],'DAILY_CONDITIONAL_PACKET_SAVED')
  self.assertEqual(self.run_day('2026-10-22')['status'],'DAILY_CONDITIONAL_PACKET_SAVED')
  self.assertEqual(self.calls,['daily','official','daily','official'])
  self.assertEqual(self.run_day('2026-10-22')['status'],'EXISTING_DAILY_PACKET_VERIFIED')
  self.assertEqual(len(self.calls),4);self.assertEqual(self.f.f.accounts.path.read_bytes(),before)
 def test_dry_run_missing_predecessor_and_domain_block_no_fetch(self):
  self.assertEqual(self.run_day('2026-10-21',execute=False)['status'],'DRY_RUN_NO_HTTP_NO_FILES')
  self.assertEqual(self.run_day('2026-10-22')['status'],'WAIT_PREVIOUS_SESSION_EVIDENCE')
  self.f.f.target['payload']['target_quantities']['new-sid']=1
  self.assertEqual(self.run_day('2026-10-21')['status'],'WAIT_SECURITY_DOMAIN_CONFIGURATION')
  self.assertEqual(self.calls,[])
 def test_failure_preserved_without_retry(self):
  def failed(*args):self.calls.append('failed');raise OSError('fixture transport failed')
  first=self.run_day('2026-10-21',fetch_daily=failed)
  self.assertEqual(first['status'],'NEEDS_RECOVERY')
  self.assertEqual(first['http_calls'],2)
  count=len(self.calls)
  self.assertEqual(self.run_day('2026-10-21')['status'],'NEEDS_RECOVERY')
  self.assertEqual(len(self.calls),count)
 def test_publication_pin_race_and_duplicate_future_terminal(self):
  original=Path.open
  def changed(path,*args,**kwargs):
   if path.name=='receipt.json' and 'runs' in path.parts and args and args[0]=='xb':
    (self.root/'data/strategy_daily_rolling_runner_v3.py').write_bytes(b'changed')
   return original(path,*args,**kwargs)
  with patch.object(Path,'open',changed):result=self.run_day('2026-10-21')
  self.assertEqual(result['status'],'NEEDS_RECOVERY')
  self.assertEqual(result['reason'],'SOURCE_HASH_CHANGED')
 def test_duplicate_future_terminal_is_not_verified(self):
  self.assertEqual(self.run_day('2026-10-21')['status'],'DAILY_CONDITIONAL_PACKET_SAVED')
  path=self.root/'runs/2026-10-21/terminal.json';terminal=json.loads(path.read_bytes())
  terminal['finished_at']='2099-01-01T00:00:00Z';path.write_bytes(canonical(terminal))
  with self.assertRaisesRegex(ValueError,'ROLLING_SAVED_TIME_CHANGED'):self.run_day('2026-10-21')

if __name__=='__main__':unittest.main()
