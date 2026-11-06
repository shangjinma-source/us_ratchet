import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_roa_monthly_registration as fixture
from scripts.research.prepare_roa_monthly_registration import prepare
from scripts.research.adopt_roa_monthly_registration import adopt

class AdoptionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  args,_,_,_=fixture.RegistrationTests().fixture(self.root);self.registration=prepare(**args);self.active=dict(path=args['active_path'],sha256=args['active_sha256'])
  for name in ('scripts.research.prepare_roa_monthly_publication','scripts.research.adopt_roa_monthly_registration'):
   p=patch(name+'.build_unified_server_preparation_v34',return_value={'validate_code':lambda:None});p.start();self.addCleanup(p.stop)
 def run_it(self,execute=False):return adopt(root=self.root,active=self.active,registration=self.registration,output_directory='adoption',execute=execute)
 def test_dryrun_and_exact_rollback(self):
  raw=(self.root/'active.json').read_bytes();r=self.run_it();self.assertEqual(r['status'],'DRY_RUN_VALIDATED_NOT_SWITCHED');self.assertEqual((self.root/'active.json').read_bytes(),raw);self.assertEqual((self.root/r['rollback']['path']).read_bytes(),raw)
 def test_switch_is_not_runtime_success(self):
  raw=(self.root/'active.json').read_bytes();r=self.run_it(True);self.assertEqual(r['status'],'ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED');self.assertFalse(r['service_restarted']);self.assertFalse(r['runtime_verified']);self.assertNotEqual((self.root/'active.json').read_bytes(),raw);self.assertEqual((self.root/r['rollback']['path']).read_bytes(),raw)
  with self.assertRaisesRegex(ValueError,'STALE_ACTIVE'):self.run_it(True)
 def test_busy_and_stale(self):
  lock=self.root/'active.json.roa-monthly.lock';lock.write_text('owned by another')
  with self.assertRaisesRegex(ValueError,'BUSY'):self.run_it(True)
  self.assertEqual(lock.read_text(),'owned by another');lock.unlink();(self.root/'active.json').write_text('{}')
  with self.assertRaisesRegex(ValueError,'STALE_ACTIVE'):self.run_it(True)
 def test_gate_active_race_prevents_replace(self):
  def changed(**kw):
   return {'validate_code':lambda:(self.root/'active.json').write_text('{"other":true}')}
  with patch('scripts.research.adopt_roa_monthly_registration.build_unified_server_preparation_v34',side_effect=changed):
   with self.assertRaises(ValueError):self.run_it(True)
  self.assertEqual(json.loads((self.root/'active.json').read_bytes()),{'other':True});self.assertTrue((self.root/'adoption/adoption-failure.json').exists())
 def test_replaced_lock_is_preserved_and_blocks_switch(self):
  before=(self.root/'active.json').read_bytes();lock=self.root/'active.json.roa-monthly.lock'
  def changed(**kw):
   return {'validate_code':lambda:lock.write_bytes(b'new owner lock')}
  with patch('scripts.research.adopt_roa_monthly_registration.build_unified_server_preparation_v34',side_effect=changed):
   with self.assertRaisesRegex(ValueError,'LOCK_OWNERSHIP_CHANGED'):self.run_it(True)
  self.assertEqual(lock.read_bytes(),b'new owner lock');self.assertEqual((self.root/'active.json').read_bytes(),before)
 def test_staged_bytes_changed_during_gate_never_replace(self):
  before=(self.root/'active.json').read_bytes()
  def changed(**kw):
   def gate():
    staged=list(self.root.glob('active.json.*.staged'));self.assertEqual(len(staged),1);staged[0].write_bytes(b'wrong bytes')
   return {'validate_code':gate}
  with patch('scripts.research.adopt_roa_monthly_registration.build_unified_server_preparation_v34',side_effect=changed):
   with self.assertRaisesRegex(ValueError,'STAGED_ACTIVE_CHANGED'):self.run_it(True)
  self.assertEqual((self.root/'active.json').read_bytes(),before);self.assertEqual(list(self.root.glob('*.staged')),[])
 def test_post_replace_receipt_failure_is_unknown_not_unchanged(self):
  before=(self.root/'active.json').read_bytes();original=Path.open
  def fail(path,*args,**kw):
   if path.name=='adoption.json':raise OSError('receipt failed')
   return original(path,*args,**kw)
  with patch.object(Path,'open',fail):
   with self.assertRaisesRegex(OSError,'receipt failed'):self.run_it(True)
  self.assertNotEqual((self.root/'active.json').read_bytes(),before)
  failure=json.loads((self.root/'adoption/adoption-failure.json').read_bytes());self.assertEqual(failure['status'],'FAILED_RECONCILE_ACTIVE_BEFORE_RETRY');self.assertNotEqual(failure['observed_active_sha256'],failure['expected_active_sha256'])

if __name__=='__main__':unittest.main()
