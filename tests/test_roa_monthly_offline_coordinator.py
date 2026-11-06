import json
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
import unittest
import test_roa_monthly_package_20261106 as package_fixture
from scripts.research.coordinate_roa_monthly_offline import coordinate

class CoordinatorTests(unittest.TestCase):
 def setUp(self):
  self.f=package_fixture.PackageTests();self.f.setUp();self.addCleanup(self.f.tearDown);self.root=self.f.root
  def save(name,value):
   p=self.root/name;p.write_text(json.dumps(value));return dict(path=name,sha256=sha256(p.read_bytes()).hexdigest())
  base=save('base.json',{});code=save('code.json',{})
  config=save('config.json',dict(schema='ROA_UNIFIED_PREPARATION_V34',base_v33=base,source_pins={code['path']:code['sha256']},roa=dict(monthly_selections={})))
  active=save('active.json',dict(schema='STRATEGY_SERVER_ACTIVE_V6',configuration_path=config['path'],configuration_sha256=config['sha256']))
  self.request=dict(active=active,decision_date='2026-10-30',package=self.f.request,output_directory='coordinator')
  self.selector=patch('scripts.research.prepare_roa_monthly_package.generate_month_selection',return_value=self.f.artifact);self.selector.start();self.addCleanup(self.selector.stop)
 def run_it(self):return coordinate(root=self.root,request=self.request,now=self.f.now)
 def test_chain_idempotence_and_tampering(self):
  before=(self.root/'active.json').read_bytes();first=self.run_it();self.assertFalse(first['reused']);second=self.run_it();self.assertTrue(second['reused']);self.assertEqual(first['registration'],second['registration']);self.assertEqual((self.root/'active.json').read_bytes(),before)
  registration=(self.root/first['registration']['path']).parent
  self.assertEqual((registration/'rollback_active.json').read_bytes(),before)
  next_active=json.loads((registration/'next_active.json').read_bytes())
  next_raw=(self.root/next_active['configuration_path']).read_bytes()
  self.assertEqual(sha256(next_raw).hexdigest(),next_active['configuration_sha256'])
  proposal=json.loads((self.root/first['registry_proposal']).read_bytes())
  self.assertEqual(json.loads(next_raw)['roa']['monthly_selections'],proposal)
  (self.root/first['registry_proposal']).write_text('{}')
  with self.assertRaisesRegex(ValueError,'PREPARED_ARTIFACT_CHANGED'):self.run_it()
 def test_wait_missing_and_busy(self):
  (self.root/'manifest.json').unlink()
  self.assertEqual(coordinate(root=self.root,request=self.request,now=datetime(2026,10,30,19,tzinfo=timezone.utc))['status'],'WAIT_COMPLETED_MONTH_END')
  self.assertEqual(self.run_it()['missing'],['manifest.json']);self.assertFalse((self.root/'coordinator').exists())
 def test_lock_no_concurrent_work(self):
  out=self.root/'coordinator';out.mkdir();(out/'running.lock').write_text('another')
  self.assertEqual(self.run_it()['status'],'BUSY_OR_NEEDS_LOCK_RECONCILIATION');self.assertEqual(list(out.iterdir()),[out/'running.lock'])
 def test_concurrent_entry_does_not_duplicate_generation(self):
  from scripts.research.prepare_roa_monthly_package import prepare
  observed=[]
  def reenter(**kw):
   observed.append(self.run_it()['status']);return prepare(**kw)
  with patch('scripts.research.coordinate_roa_monthly_offline.prepare_package',side_effect=reenter):self.run_it()
  self.assertEqual(observed,['BUSY_OR_NEEDS_LOCK_RECONCILIATION']);self.assertEqual(len(list((self.root/'coordinator').glob('attempt-*'))),1)
 def test_failed_attempt_retained_then_retry(self):
  with patch('scripts.research.coordinate_roa_monthly_offline.prepare_registration',side_effect=ValueError('temporary')):
   with self.assertRaisesRegex(ValueError,'temporary'):self.run_it()
  prior=list((self.root/'coordinator').glob('attempt-*/failure.json'));self.assertEqual(len(prior),1);raw=prior[0].read_bytes()
  result=self.run_it();self.assertEqual(result['status'],'PREPARED_REGISTRATION_NOT_ACTIVATED');self.assertEqual(prior[0].read_bytes(),raw);self.assertEqual(len(list((self.root/'coordinator').glob('attempt-*'))),2)
 def test_active_change_during_artifact_hash_rejected(self):
  original=Path.rglob
  def changed(path,*args,**kwargs):
   if path.name.startswith('attempt-'):(self.root/'active.json').write_text('{}')
   return original(path,*args,**kwargs)
  with patch.object(Path,'rglob',changed):
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.run_it()
  self.assertFalse((self.root/'coordinator/complete.json').exists())
 def test_active_change_blocks_publication(self):
  from scripts.research.prepare_roa_monthly_package import prepare
  def change(**kw):
   result=prepare(**kw);(self.root/'active.json').write_text('{}');return result
  with patch('scripts.research.coordinate_roa_monthly_offline.prepare_package',side_effect=change):
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):self.run_it()
  self.assertFalse((self.root/'coordinator/complete.json').exists());self.assertEqual(len(list((self.root/'coordinator').glob('attempt-*/failure.json'))),1)

if __name__=='__main__':unittest.main()
