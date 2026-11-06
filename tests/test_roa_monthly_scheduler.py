import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts.run_local_roa_monthly_preparation import run,source_closure
ROOT=Path(__file__).resolve().parents[1]
class SchedulerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  def save(name,v):
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v));return dict(path=name,sha256=sha256(p.read_bytes()).hexdigest())
  self.save=save;self.active=save('active.json',{});request=save('request.json',dict(active=self.active))
  code=save('code.py',{});self.descriptor=save('descriptor.json',dict(schema='ROA_MONTHLY_PREPARATION_LAUNCHER_V1',root=str(self.root),python_path='python',request=request,source_pins={'code.py':code['sha256']},log_directory='logs'))
  p=patch('scripts.run_local_roa_monthly_preparation.source_closure',return_value=['code.py']);p.start();self.addCleanup(p.stop)
 def go(self,execute=False):return run(root=self.root,descriptor_path=self.descriptor['path'],descriptor_sha256=self.descriptor['sha256'],execute=execute)
 def test_preview_no_logs_or_pipeline(self):
  with patch('scripts.research.run_roa_monthly_pipeline.run') as pipeline:
   self.assertEqual(self.go()['status'],'PREVIEW_VALIDATED_NO_CAPTURE');pipeline.assert_not_called()
  self.assertFalse((self.root/'logs').exists())
 def test_success_stops_full_pipeline_and_active_change_rejects(self):
  with patch('scripts.research.run_roa_monthly_pipeline.run',return_value=dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',publication_directory='publication')) as pipeline:
   self.go(True);second=self.go(True);self.assertEqual(pipeline.call_count,1);self.assertEqual(second['formal_gate_calls'],0)
  (self.root/'active.json').write_text('{"new":true}')
  with self.assertRaisesRegex(ValueError,'ACTIVE_CHANGED_REBUILD_REVIEWED_REQUEST'):self.go(True)
 def test_failure_not_automatically_retried(self):
  with patch('scripts.research.run_roa_monthly_pipeline.run',return_value=dict(status='FAILED_NOT_ACTIVATED',stage='capture')) as pipeline:
   self.assertEqual(self.go(True)['exit_code'],1);self.assertEqual(self.go(True)['status'],'BLOCKED_REVIEW_REQUIRED_NO_AUTOMATIC_RETRY');self.assertEqual(pipeline.call_count,1)
 def test_pin_request_and_lock(self):
  (self.root/'logs').mkdir();lock=self.root/'logs/running.lock';lock.write_text('other')
  self.assertEqual(self.go(True)['exit_code'],2);self.assertEqual(lock.read_text(),'other')
  (self.root/'code.py').write_text('changed')
  with self.assertRaisesRegex(ValueError,'CODE_SOURCE_CHANGED'):self.go()
 def test_closure_covers_real_pipeline_and_formal_builder(self):
  names=source_closure(ROOT)
  for p in ('scripts/research/run_roa_monthly_capture.py','scripts/research/prepare_roa_monthly_publication.py','data/strategy_unified_server_preparation_v34.py','data/roa_monthly_selection.py','scripts/install_local_roa_monthly_preparation.ps1'):
   self.assertIn(p,names)
if __name__=='__main__':unittest.main()
