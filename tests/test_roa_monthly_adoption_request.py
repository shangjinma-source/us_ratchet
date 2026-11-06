import json
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.research.build_roa_monthly_adoption_request import build

class RequestTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  def save(name,value):
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));return dict(path=name,sha256=sha256(p.read_bytes()).hexdigest())
  self.save=save
  active=save('active.json',dict(configuration_path='config',configuration_sha256='config-hash'))
  manifest=save('capture/manifest.json',{});completion=save('capture/completion.json',{})
  hashes={r['path']:r['sha256'] for r in (manifest,completion)}
  save('capture/runner_receipt.json',dict(output_hashes=hashes))
  plan=save('plan.json',dict(calendar_path='calendar',calendar_source_hashes={}))
  registration=save('registration.json',{})
  self.publication=dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',month='2026-12',expected_active=active,registration=registration,source_hashes=hashes)
  save('publication/validated.json',self.publication)
  save('prepared.json',dict(exit_code=0,result={'status':'VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED'}))
  job=save('job.json',dict(active=active,capture=dict(output_directory='capture',plan=plan),package=dict(expected_month='2026-12',training_calendar={},session_calendar={})))
  self.descriptor=save('launcher.json',dict(request=job,python_path='python'))
  self.state=dict(status='PREPARED_PENDING_REVALIDATION',evidence='prepared.json',publication_directory='publication')
  self.runtime=dict(process={'pid':1},binding=dict(loaded_active_sha256=active['sha256'],loaded_configuration=dict(path='config',sha256='config-hash')),config=dict(active=True,strategy_epoch='epoch'))
 def run_it(self):
  with patch('scripts.research.build_roa_monthly_adoption_request.inspect',return_value=self.state),patch('scripts.research.build_roa_monthly_adoption_request.preview'):
   return build(root=self.root,descriptor_path=self.descriptor['path'],descriptor_sha256=self.descriptor['sha256'],observe=lambda root:self.runtime,read_task=lambda:'task-sha')
 def test_completed_sources_generate_request_without_adoption(self):
  r=self.run_it();self.assertEqual(r['request']['month'],'2026-12');self.assertEqual(r['request']['expected_process'],{'pid':1});self.assertFalse(r['task_changed'])
 def test_no_completion_waits(self):
  self.state={'status':'CONFIGURATION_VALID_NO_COMPLETION'}
  self.assertEqual(self.run_it()['status'],'WAIT_PREPARED_MONTH')
 def test_broken_preparation_is_not_normal_wait(self):
  self.state={'status':'INPUT_REVIEW_REQUIRED'}
  self.assertEqual(self.run_it()['status'],'PREPARATION_REVIEW_REQUIRED')
 def test_stale_loaded_release_rejected(self):
  self.runtime['binding']['loaded_active_sha256']='stale'
  with self.assertRaisesRegex(ValueError,'LOADED_CURRENT_RELEASE'):self.run_it()
 def test_wrong_month_rejected(self):
  self.publication['month']='2027-01';self.save('publication/validated.json',self.publication)
  with self.assertRaisesRegex(ValueError,'PUBLICATION_CONFLICT'):self.run_it()
 def test_changed_capture_rejected(self):
  self.save('capture/manifest.json',{'changed':True})
  with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):self.run_it()

if __name__=='__main__':unittest.main()
