"""Isolated migration candidate; no activation, account reads or network."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import unittest
from core.strategy_account_ledger import canonical
from data.strategy_future_policy_chain_materializer_v1 import materialize_future_policy_chain,PARENTS
from data.strategy_source_migration_chain_materializer_v1 import materialize_source_migration_chain,FACTORY_SOURCES,MIGRATION_SOURCES
from test_future_policy_chain_materializer_v1 import FuturePolicyChainTest

class SourceMigrationTests(FuturePolicyChainTest):
 def setUp(self):
  super().setUp()
  original=materialize_future_policy_chain(**dict(self.arguments,output_directory='old-future'))
  self.arguments['server_reference']=original['server_reference']
  source_ref=json.loads((self.root/'old-future/daily.json').read_bytes())['evidence']
  source=json.loads((self.root/source_ref['configuration_path']).read_bytes())
  self.old_source=deepcopy(source)
  source.update(runs_root='new-daily-runs',first_window_review_version='CLOSED_AT_ORIGINAL_RECEIPT_V2')
  pins={r['path']:r['sha256'] for r in source['source_pins']}
  # Existing source transport pins also need their actual immutable bytes.
  workspace=Path(__file__).resolve().parents[1]
  for name in set(pins)|FACTORY_SOURCES|MIGRATION_SOURCES:
   ref=self.copy(workspace,name);pins[name]=ref['sha256']
  source['source_pins']=[dict(path=k,sha256=v) for k,v in sorted(pins.items())]
  self.arguments['new_source_reference']=self.put('new-source.json',source)
  application=json.loads((self.root/self.arguments['application_reference']['path']).read_bytes())
  application['source_configuration']=self.arguments['new_source_reference']
  pins={r['path']:r['sha256'] for r in application['code_pins']}
  for name in FACTORY_SOURCES|MIGRATION_SOURCES:pins[name]=sha256((self.root/name).read_bytes()).hexdigest()
  application['code_pins']=[dict(path=k,sha256=v) for k,v in sorted(pins.items())]
  self.arguments['application_reference']=self.put('new-application.json',application)
 def put(self,name,value):
  raw=canonical(value);(self.root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
 def test_only_source_refs_change(self):
  result=materialize_source_migration_chain(**self.arguments)
  before=json.loads((self.root/'old-future/daily.json').read_bytes());after=json.loads((self.root/'candidate/daily.json').read_bytes())
  for key in ('configuration_path','configuration_sha256','review_configuration_path','review_configuration_sha256'):
   before['evidence'].pop(key);after['evidence'].pop(key)
  self.assertEqual(before,after);self.assertEqual(result['valid_from'],'2026-10-21T13:30:00+00:00')
  old=self.arguments['server_reference'];new=result['server_reference']
  for parent in PARENTS.values():
   a=json.loads((self.root/old['path']).read_bytes());b=json.loads((self.root/new['path']).read_bytes());old=a.pop(parent);new=b.pop(parent);self.assertEqual(a,b)
  a=json.loads((self.root/old['path']).read_bytes());b=json.loads((self.root/new['path']).read_bytes());a.pop('daily_configuration');b.pop('daily_configuration');self.assertEqual(a,b)
  with self.assertRaisesRegex(ValueError,'OUTPUT_EXISTS'):materialize_source_migration_chain(**self.arguments)
 def test_changed_account_time_or_old_pin_rejected(self):
  for kind in ('account','time','pin'):
   args=deepcopy(self.arguments)
   if kind=='time':
    app=json.loads((self.root/args['application_reference']['path']).read_bytes());app['valid_from']='2026-10-20T13:30:00+00:00';args['application_reference']=self.put('bad-app.json',app)
   else:
    source=json.loads((self.root/args['new_source_reference']['path']).read_bytes())
    if kind=='account':source['account_id']='another-account'
    else:source['source_pins'][0]['sha256']='0'*64
    args['new_source_reference']=self.put('bad-source.json',source)
   with self.subTest(kind=kind),self.assertRaises(ValueError):materialize_source_migration_chain(**args)
   self.assertFalse((self.root/'candidate').exists())
 def test_binding_and_final_drift_fail_closed(self):
  calls=[]
  def gate():
   calls.append(1)
   if len(calls)==2:(self.root/self.arguments['new_source_reference']['path']).write_bytes(b'{}')
  with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):materialize_source_migration_chain(**dict(self.arguments,validate_sources=gate))
  self.assertFalse((self.root/'candidate').exists());self.assertEqual(len(list(self.root.glob('.candidate.preparing-*/failed.json'))),1)
 # Parent structural test assumes v1 arguments and is intentionally superseded above.
 test_only_daily_and_parent_refs_change=None
if __name__=='__main__':unittest.main()
