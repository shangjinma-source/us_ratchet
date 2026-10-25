from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_daily_dynamic_factory_v5 import run_dynamic_sources,FACTORY_SOURCES,resolve_saved_context
import test_strategy_daily_dynamic_factory_v4 as old_fixture
ROOT=Path(__file__).resolve().parents[1]

class MigrationFactoryTests(unittest.TestCase):
 def setup(self,folder):
  c,root,old_run,_=old_fixture.DynamicFactoryTests().setup(folder)
  first=old_run();self.assertEqual(first['status'],'DYNAMIC_DOMAIN_PACKET_SAVED')
  old_raw=(root/'dynamic-runs/2026-11-02/configuration.json').read_bytes();(root/'old-config.json').write_bytes(old_raw)
  old=json.loads(old_raw);config=deepcopy(old)
  config.update(runs_root='dynamic-runs-v5',official_time_policy='REAL_WAIT_CHANNEL_MAX_5S_ITEMS_AT_NETWORK_RECEIPT_V2',prior_configuration=dict(path='old-config.json',sha256=sha256(old_raw).hexdigest()),migration_session='2026-11-03')
  pins={r['path']:r['sha256'] for r in old['source_pins']}
  for name in FACTORY_SOURCES:
   body=(ROOT/name).read_bytes();path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body);pins[name]=sha256(body).hexdigest()
  config['source_pins']=[dict(path=k,sha256=v) for k,v in sorted(pins.items())]
  c.clock[0]=datetime.fromisoformat('2026-11-03T15:00:00+00:00');calls=[]
  calendar=json.loads((root/'dynamic-calendar.json').read_bytes())
  def fetch(ticker,*args):
   calls.append(ticker);dates=[x['date'] for x in calendar['sessions']];idx=dates.index(c.clock[0].date().isoformat());window=calendar['sessions'][idx-20:idx]
   raw=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeName='NMS'),events={},timestamp=[int(datetime.fromisoformat(x['open']).timestamp()) for x in window],indicators=dict(quote=[dict(close=[100]*20)],adjclose=[dict(adjclose=[100]*20)]))])))
   return dict(status=200,body=raw)
  def run():
   raw=canonical(config)
   return run_dynamic_sources(root=root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),account_reader=c.store.read,target_reader=lambda:c.target,execute=True,clock=lambda:c.clock[0],fetch_daily=fetch,fetch_official=lambda:dict(status=200,body=b'<rss><channel><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated</title><pubDate>Mon, 02 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'))
  return c,root,config,run,calls
 def test_explicit_old_parent_then_new_parent_no_copy(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=self.setup(folder);before=c.store.path.read_bytes();old=(root/'dynamic-runs/2026-11-02/terminal.json').read_bytes()
   result=run();self.assertEqual(result['status'],'DYNAMIC_DOMAIN_PACKET_SAVED',result);self.assertEqual(result['routes'],{'B':'ROLLING'})
   self.assertEqual(run()['status'],'EXISTING_DYNAMIC_PACKET_VERIFIED');self.assertEqual(calls,['BBB'])
   self.assertFalse((root/'dynamic-runs-v5/2026-11-02').exists())
   c.clock[0]=datetime.fromisoformat('2026-11-04T15:00:00+00:00')
   result=run();self.assertEqual(result['status'],'DYNAMIC_DOMAIN_PACKET_SAVED',result);self.assertEqual(result['routes'],{'B':'ROLLING'})
   self.assertEqual(calls,['BBB','BBB']);self.assertEqual(before,c.store.path.read_bytes());self.assertEqual(old,(root/'dynamic-runs/2026-11-02/terminal.json').read_bytes())
 def test_failed_or_missing_parent_no_fallback_and_changed_scope_rejected(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=self.setup(folder)
   path=root/'dynamic-runs/2026-11-02/terminal.json';terminal=json.loads(path.read_bytes());terminal['status']='NEEDS_RECOVERY';path.write_bytes(canonical(terminal))
   self.assertEqual(run()['status'],'WAIT_PREVIOUS_SESSION_EVIDENCE');self.assertEqual(calls,[])
   config['account_id']='other'
   with self.assertRaisesRegex(ValueError,'MIGRATION_SCOPE'):run()
   self.assertEqual(calls,[])
 def test_existing_failed_new_run_is_preserved_without_retry(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=self.setup(folder)
   directory=root/config['runs_root']/config['migration_session'];directory.mkdir(parents=True)
   raw=canonical(dict(status='NEEDS_RECOVERY',reason='fixture_failure'))
   (directory/'terminal.json').write_bytes(raw)
   self.assertEqual(run()['status'],'NEEDS_RECOVERY');self.assertEqual(calls,[])
   self.assertEqual((directory/'terminal.json').read_bytes(),raw)
 def test_old_configuration_hash_and_pin_change_rejected(self):
  with TemporaryDirectory() as folder:
   c,root,config,run,calls=self.setup(folder)
   (root/'old-config.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):run()
   self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
