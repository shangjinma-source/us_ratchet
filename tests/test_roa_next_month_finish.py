import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts.research.finish_roa_next_month import finish_next

class NextTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.current='old';self.calls=0;self.fail_after_write=False
 def draft(self,**kw):
  p=self.root/kw['output_directory'];p.mkdir()
  result=dict(target_month='2027-01',launcher=dict(path='launcher.json',sha256='launcher'),source_hashes={})
  (p/'draft.json').write_text(json.dumps(result));return result
 def invoke(self,*a,**kw):
  self.calls+=1;p=self.root/'tmp/follow/task-binding';p.mkdir()
  (p/'success.json').write_text(json.dumps(dict(Status='ACTION_REBOUND_NO_TASK_STARTED',ConfigSha256='launcher',BeforeSha256='old',AfterSha256='new',NonActionFieldsUnchanged=True)))
  self.current='new'
  if self.fail_after_write:raise TimeoutError()
 def run_it(self):
  with patch('scripts.research.finish_roa_next_month.draft',side_effect=self.draft),patch('scripts.research.finish_roa_next_month.preview_launcher'):
   return finish_next(root=self.root,request={'scope':'fixture'},output_directory='tmp/follow',python_path='python',expected_task_sha256='old',read_task=lambda:self.current,invoke=self.invoke)
 def test_reentry_uses_receipt_not_second_update(self):
  self.assertEqual(self.run_it()['status'],'NEXT_MONTH_TASK_BOUND');self.run_it();self.assertEqual(self.calls,1)
 def test_lost_acknowledgment_after_update(self):
  self.fail_after_write=True
  with self.assertRaises(TimeoutError):self.run_it()
  self.run_it();self.assertEqual(self.calls,1)
 def test_later_task_not_overwritten(self):
  self.run_it();self.current='later'
  with self.assertRaisesRegex(ValueError,'NOT_VERIFIED'):self.run_it()
  self.assertEqual(self.calls,1)
 def test_partial_update_never_repeated(self):
  def uncertain(*a,**kw):
   self.calls+=1;(self.root/'tmp/follow/task-binding').mkdir();raise TimeoutError()
  self.invoke=uncertain
  with self.assertRaises(TimeoutError):self.run_it()
  with self.assertRaisesRegex(ValueError,'UNCERTAIN'):self.run_it()
  self.assertEqual(self.calls,1)
 def test_stale_task_refused_before_write(self):
  self.current='later'
  with self.assertRaisesRegex(ValueError,'CHANGED_BEFORE'):self.run_it()
  self.assertEqual(self.calls,0)

if __name__=='__main__':unittest.main()
