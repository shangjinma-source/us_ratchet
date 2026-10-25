from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import canonical
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_daily_dynamic_factory_v1 import run_dynamic_sources
from scripts.run_daily_dynamic_source_v1 import main,CLI_SOURCES
import test_strategy_daily_dynamic_factory_v1 as fixtures

ROOT=Path(__file__).resolve().parents[1]

class DynamicCliTests(unittest.TestCase):
 def setup(self,folder):
  c,root,unused,calls=fixtures.DynamicFactoryTests().setup(folder)
  payload=dict(c.target['payload'],previous_target_id=None,request=dict(event_id='cli-fixture-target'))
  target_path=root/'cli-target.sqlite3';targets=StrategyMonthlyTargetStore(target_path);targets.append(payload)
  pins=[]
  for name in CLI_SOURCES:
   body=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
   pins.append(dict(path=name,sha256=sha256(body).hexdigest()))
  config=dict(schema='SERVER_DYNAMIC_DAILY_SOURCE_V1',source_pins=pins,
   calendar=dict(path='dynamic-calendar.json',sha256=sha256((root/'dynamic-calendar.json').read_bytes()).hexdigest()),
   identity=c.identity_reference,runs_root='cli-runs',first_execution_date='2026-11-02',
   target_evidence_root='capture',account_id=c.store.read()['account_id'],
   account_database=c.store.path.relative_to(root).as_posix(),target_database='cli-target.sqlite3')
  raw=canonical(config);(root/'cli-config.json').write_bytes(raw)
  args=['--root',str(root),'--config-path','cli-config.json','--config-sha256',sha256(raw).hexdigest()]
  return c,root,args,target_path
 def invoke(self,c,args):
  def isolated_clock(**kwargs):
   # Only the test substitutes time. CLI exposes no clock/date argument.
   return run_dynamic_sources(**kwargs,clock=lambda:c.clock[0],
    fetch_daily=lambda *args:(_ for _ in ()).throw(AssertionError('HTTP forbidden')),
    fetch_official=lambda:(_ for _ in ()).throw(AssertionError('HTTP forbidden')))
  output=StringIO()
  with patch('scripts.run_daily_dynamic_source_v1.run_dynamic_sources',isolated_clock),redirect_stdout(output):
   code=main(args)
  return code,json.loads(output.getvalue())
 def test_default_is_dry_run_real_sqlite_reads_leave_bytes_unchanged(self):
  with TemporaryDirectory() as folder:
   c,root,args,target=self.setup(folder);before=(c.store.path.read_bytes(),target.read_bytes())
   code,result=self.invoke(c,args)
   self.assertEqual(code,0);self.assertEqual(result['status'],'DRY_RUN_NO_HTTP_NO_FILES',result)
   self.assertEqual(result['http_calls'],0);self.assertFalse((root/'cli-runs').exists())
   self.assertEqual((c.store.path.read_bytes(),target.read_bytes()),before)
 def test_hash_failure_prevents_factory_and_date_override_is_not_supported(self):
  with TemporaryDirectory() as folder:
   c,root,args,target=self.setup(folder)
   with patch('scripts.run_daily_dynamic_source_v1.run_dynamic_sources',side_effect=AssertionError('must not run')):
    output=StringIO()
    with redirect_stdout(output):code=main(args[:-1]+['0'*64])
   self.assertEqual(code,2);self.assertEqual(json.loads(output.getvalue())['reason'],'DYNAMIC_CLI_CONFIGURATION_HASH')
   with self.assertRaises(SystemExit) as raised:main(args+['--date','2026-11-02'])
   self.assertEqual(raised.exception.code,2)
 def test_existing_failed_session_never_retried_or_overwritten(self):
  with TemporaryDirectory() as folder:
   c,root,args,target=self.setup(folder)
   path=root/'cli-runs/2026-11-02';path.mkdir(parents=True)
   original=canonical(dict(status='NEEDS_RECOVERY',reason='preserved-fixture-failure'))
   (path/'terminal.json').write_bytes(original)
   code,result=self.invoke(c,args+['--execute'])
   self.assertEqual(code,2);self.assertEqual(result['status'],'NEEDS_RECOVERY')
   self.assertEqual(result['http_calls'],0);self.assertEqual((path/'terminal.json').read_bytes(),original)
 def test_missing_database_is_not_initialized(self):
  with TemporaryDirectory() as folder:
   c,root,args,target=self.setup(folder);target.unlink()
   code,result=self.invoke(c,args)
   self.assertEqual(code,2);self.assertEqual(result['reason'],'DYNAMIC_CLI_DATABASE_REQUIRED')
   self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
