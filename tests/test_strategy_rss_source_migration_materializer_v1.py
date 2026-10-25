"""RSS timing migration only; temporary materials, no network or activation."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
import test_strategy_source_migration_chain_materializer_v1 as prior
from data.strategy_source_migration_chain_materializer_v1 import materialize_source_migration_chain as old_materializer
from data.strategy_rss_source_migration_materializer_v1 import materialize_source_migration_chain,MIGRATION_SOURCES,PARENTS

class RssMigrationTests(unittest.TestCase):
 def setUp(self):
  self.fixture=prior.SourceMigrationTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.root=self.fixture.root;self.arguments=deepcopy(self.fixture.arguments)
  first=old_materializer(**dict(self.arguments,output_directory='before-rss'))
  self.arguments['server_reference']=first['server_reference']
  old_source=json.loads((self.root/self.arguments['new_source_reference']['path']).read_bytes())
  source=deepcopy(old_source);source.update(runs_root='rss-repaired-runs',official_time_policy='REAL_WAIT_CHANNEL_MAX_1S_ITEMS_AT_NETWORK_RECEIPT_V1')
  workspace=Path(__file__).resolve().parents[1]
  pins={r['path']:r['sha256'] for r in source['source_pins']}
  for name in MIGRATION_SOURCES:pins[name]=self.fixture.copy(workspace,name)['sha256']
  source['source_pins']=[dict(path=k,sha256=v) for k,v in sorted(pins.items())]
  self.arguments['new_source_reference']=self.put('rss-source.json',source)
  app=json.loads((self.root/self.arguments['application_reference']['path']).read_bytes())
  app['source_configuration']=self.arguments['new_source_reference']
  pins={r['path']:r['sha256'] for r in app['code_pins']}
  for name in MIGRATION_SOURCES:pins[name]=sha256((self.root/name).read_bytes()).hexdigest()
  app['code_pins']=[dict(path=k,sha256=v) for k,v in sorted(pins.items())]
  self.arguments['application_reference']=self.put('rss-app.json',app)
 def put(self,name,value):
  raw=canonical(value);(self.root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
 def test_only_daily_refs_change_preserving_v10_and_policy(self):
  result=materialize_source_migration_chain(**self.arguments)
  before=json.loads((self.root/'before-rss/daily.json').read_bytes());after=json.loads((self.root/'candidate/daily.json').read_bytes())
  for field in ('configuration_path','configuration_sha256','review_configuration_path','review_configuration_sha256'):
   before['evidence'].pop(field);after['evidence'].pop(field)
  self.assertEqual(before,after);self.assertEqual(result['valid_from'],'2026-10-21T13:30:00+00:00')
  old=self.arguments['server_reference'];new=result['server_reference']
  for parent in PARENTS.values():
   a=json.loads((self.root/old['path']).read_bytes());b=json.loads((self.root/new['path']).read_bytes());old=a.pop(parent);new=b.pop(parent);self.assertEqual(a,b)
  a=json.loads((self.root/old['path']).read_bytes());b=json.loads((self.root/new['path']).read_bytes());a.pop('daily_configuration');b.pop('daily_configuration');self.assertEqual(a,b)
  with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):materialize_source_migration_chain(**self.arguments)
 def test_scope_time_and_existing_capture_root_rejected(self):
  for mode in ('account','dates','policy','oldpin','existing-root'):
   args=deepcopy(self.arguments)
   if mode=='dates':
    doc=json.loads((self.root/args['application_reference']['path']).read_bytes());doc['valid_from']='2026-10-20T13:30:00+00:00';args['application_reference']=self.put('bad-app.json',doc)
   else:
    doc=json.loads((self.root/args['new_source_reference']['path']).read_bytes())
    if mode=='account':doc['account_id']='wrong'
    if mode=='policy':doc['official_time_policy']='IGNORE_FUTURE_TIMES'
    if mode=='oldpin':doc['source_pins'][0]['sha256']='0'*64
    if mode=='existing-root':(self.root/doc['runs_root']).mkdir()
    args['new_source_reference']=self.put('bad-source.json',doc)
   with self.subTest(mode=mode),self.assertRaises(ValueError):materialize_source_migration_chain(**args)
   self.assertFalse((self.root/'candidate').exists())
 def test_source_changes_before_publish_preserve_failed_material(self):
  calls=[]
  def gate():
   calls.append(1)
   if len(calls)==2:(self.root/self.arguments['new_source_reference']['path']).write_bytes(b'{}')
  with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):materialize_source_migration_chain(**dict(self.arguments,validate_sources=gate))
  self.assertFalse((self.root/'candidate').exists());self.assertEqual(len(list(self.root.glob('.candidate.preparing-*/failed.json'))),1)
if __name__=='__main__':unittest.main()
