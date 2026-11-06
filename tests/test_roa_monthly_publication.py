import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
import test_roa_monthly_registration as fixture
from scripts.research.prepare_roa_monthly_registration import prepare
from scripts.research.prepare_roa_monthly_publication import prepare_publication

class PublicationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  args,self.save,self.config,_=fixture.RegistrationTests().fixture(self.root)
  self.registration=prepare(**args)
  self.active=dict(path=args['active_path'],sha256=args['active_sha256'])
  self.calls=[]
  def builder(**kw):
   self.calls.append(kw['configuration_path']);return {'validate_code':lambda:self.calls.append('validate')}
  self.patch=patch('scripts.research.prepare_roa_monthly_publication.build_unified_server_preparation_v34',side_effect=builder);self.patch.start();self.addCleanup(self.patch.stop)
 def run_it(self):return prepare_publication(root=self.root,active=self.active,registration=self.registration,output_directory='publication')
 def rewrite(self,mutator):
  preparation=json.loads((self.root/self.registration['path']).read_bytes());cpath=preparation['configuration']['path'];config=json.loads((self.root/cpath).read_bytes());mutator(config)
  preparation['configuration']=self.save(cpath,config);self.registration=self.save(self.registration['path'],preparation)
 def test_exact_append_and_two_formal_gates(self):
  before=(self.root/'active.json').read_bytes();r=self.run_it()
  self.assertEqual(r['status'],'VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED');self.assertEqual(self.calls,['config.json','validate','release/deploy-v34.json','validate','validate','validate'])
  self.assertEqual((self.root/r['rollback']['path']).read_bytes(),before);self.assertEqual((self.root/'active.json').read_bytes(),before)
 def test_contract_epoch_account_and_other_changes_reject(self):
  for key in ('contract_hashes','strategy_epoch','account_id','execution_admission'):
   with self.subTest(key=key):
    original=(self.root/'release/deploy-v34.json').read_bytes();prep=(self.root/self.registration['path']).read_bytes();reference=self.registration
    self.rewrite(lambda c:c['roa'].__setitem__(key,'changed'))
    with self.assertRaisesRegex(ValueError,'NON_MONTHLY'):self.run_it()
    (self.root/'release/deploy-v34.json').write_bytes(original);(self.root/reference['path']).write_bytes(prep);self.registration=reference
  self.assertEqual(self.calls,[])
 def test_extra_month_reject(self):
  self.rewrite(lambda c:c['roa']['monthly_selections'].__setitem__('2027-01',{}))
  with self.assertRaisesRegex(ValueError,'APPEND_ONLY'):self.run_it()
 def test_active_race_inside_real_gate_boundary(self):
  def changed(**kw):
   return {'validate_code':lambda:(self.root/'active.json').write_text('{}')}
  with patch('scripts.research.prepare_roa_monthly_publication.build_unified_server_preparation_v34',side_effect=changed):
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_GATE'):self.run_it()
  self.assertFalse((self.root/'publication').exists())
 def test_code_changed_after_builder_before_receipt_rejected(self):
  original=Path.open
  def changed(path,*args,**kwargs):
   if path.name=='next_active.json':(self.root/'code.json').write_text('{"changed":true}')
   return original(path,*args,**kwargs)
  with patch.object(Path,'open',changed):
   with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED_DURING_GATE:code.json'):self.run_it()
  self.assertFalse((self.root/'publication/validated.json').exists())
 def test_configuration_and_source_pins_in_receipt(self):
  result=self.run_it()
  self.assertIn('base.json',result['configuration_closure'])
  self.assertEqual(result['source_hashes']['code.json'],self.config['source_pins']['code.json'])
  self.assertIn('Rerun the complete formal V34',result['activation_requirement'])
  self.assertFalse(result['filesystem_read_only'])
 def test_gate_failure_never_approves(self):
  with patch('scripts.research.prepare_roa_monthly_publication.build_unified_server_preparation_v34',side_effect=ValueError('formal gate failure')):
   with self.assertRaisesRegex(ValueError,'formal gate failure'):self.run_it()
  self.assertFalse((self.root/'publication').exists())

if __name__=='__main__':unittest.main()
