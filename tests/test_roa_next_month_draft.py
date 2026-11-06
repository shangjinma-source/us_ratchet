import json
import unittest
from pathlib import Path
from hashlib import sha256
from tempfile import TemporaryDirectory
from unittest.mock import patch
from scripts.research.draft_roa_next_month import draft

class DraftTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  def save(name,obj):
   raw=json.dumps(obj).encode();(self.root/name).write_bytes(raw);return dict(path=name,sha256=sha256(raw).hexdigest())
  self.save=save
  active=save('active.json',{});manifest=save('manifest.json',{});completion=save('completion.json',{})
  adoption=save('adoption.json',dict(status='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED',active_sha256=active['sha256']))
  scope=dict(month='2026-12',active_sha256=active['sha256'],adoption_sha256=adoption['sha256'])
  hashes={r['path']:r['sha256'] for r in (manifest,completion)}
  self.request=dict(active=active,adoption=adoption,manifest=manifest,completion=completion,
   runtime_success=save('success.json',dict(status='MONTH_RUNTIME_VERIFIED',scope=scope,account_and_ledger_unchanged=True)),
   publication=save('publication.json',dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',month='2026-12',next_active={'sha256':active['sha256']},source_hashes=hashes)),
   capture_receipt=save('capture.json',dict(output_hashes=hashes)),training_calendar=save('training.json',{'sessions':[{'date':'2026-12-31'}]}),
   session_calendar=save('session.json',{}),calendar_path='session.json',calendar_source_hashes={})
  self.request['calendar_source_hashes']={'session.json':self.request['session_calendar']['sha256']}
 def build(self,**kwargs):
  self.assertEqual(kwargs['completed_target_month'],'2026-12')
  return dict(target_month='2027-01',artifacts={'next/capture_plan.json':b'{}','next/boundary.json':json.dumps({'training_dates':['2026-12-31']}).encode()})
 def run_it(self):
  with patch('scripts.research.draft_roa_next_month.build_next_plan',side_effect=self.build),patch('scripts.research.draft_roa_next_month.make_descriptor',return_value={'schema':'test'}):
   return draft(root=self.root,request=self.request,output_directory='next',python_path='unused')
 def test_draft_no_install(self):
  self.assertEqual(self.run_it()['target_month'],'2027-01')
  self.assertEqual(json.loads((self.root/'next/request.json').read_text())['package']['expected_month'],'2027-01')
 def test_no_overwrite(self):
  self.run_it()
  with self.assertRaisesRegex(ValueError,'ALREADY_EXISTS'):self.run_it()
 def test_no_calendar_no_output(self):
  self.build=lambda **kwargs: (_ for _ in ()).throw(ValueError('SUCCESSOR_NEXT_MONTH_BOUNDARY_UNAVAILABLE'))
  with self.assertRaisesRegex(ValueError,'BOUNDARY_UNAVAILABLE'):self.run_it()
  self.assertFalse((self.root/'next').exists())
 def test_stale_active_refused(self):
  (self.root/'active.json').write_text('later')
  with self.assertRaisesRegex(ValueError,'INPUT_CHANGED'):self.run_it()
 def test_not_adopted_refused(self):
  self.request['runtime_success']=self.save('bad.json',dict(status='DRY_RUN'))
  with self.assertRaisesRegex(ValueError,'COMPLETED_ADOPTION'):self.run_it()

 def test_real_successor_builder_preserves_training_and_month_boundary(self):
  from test_build_monthly_successor_plan import fixture
  from scripts.build_monthly_successor_plan import prepare
  with TemporaryDirectory() as directory:
   root,args,schedule,_,save=fixture(directory)
   def reference(name,value):
    return dict(path=name,sha256=save(name,value))
   active=reference('active.json',{})
   adoption=reference('adoption.json',dict(status='ACTIVE_POINTER_SWITCHED_RESTART_VALIDATION_REQUIRED',active_sha256=active['sha256']))
   manifest=dict(path=args['previous_manifest_path'],sha256=args['previous_manifest_sha256'])
   completion=dict(path=args['previous_completion_path'],sha256=args['previous_completion_sha256'])
   hashes={ref['path']:ref['sha256'] for ref in (manifest,completion)}
   prior=json.loads((root/manifest['path']).read_bytes())
   days=sorted(set(prior['training_dates'])|set(schedule['calendar']))
   request=dict(active=active,adoption=adoption,manifest=manifest,completion=completion,
    runtime_success=reference('runtime-success.json',dict(status='MONTH_RUNTIME_VERIFIED',scope=dict(month='2026-11',active_sha256=active['sha256'],adoption_sha256=adoption['sha256']),account_and_ledger_unchanged=True)),
    publication=reference('publication.json',dict(status='VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED',month='2026-11',next_active={'sha256':active['sha256']},source_hashes=hashes)),
    capture_receipt=reference('capture-receipt.json',dict(output_hashes=hashes)),
    training_calendar=reference('training-calendar.json',dict(sessions=[dict(date=day) for day in days])),
    session_calendar=dict(path=args['calendar_path'],sha256=args['calendar_source_hashes'][args['calendar_path']]),
    calendar_path=args['calendar_path'],calendar_source_hashes=args['calendar_source_hashes'])
   # Only launcher source discovery is substituted: calendar lineage, boundary,
   # capture plan generation and validation below use their real implementations.
   with patch('scripts.research.draft_roa_next_month.make_descriptor',return_value={'schema':'ISOLATED_LAUNCHER_NOT_INSTALLED'}):
    result=draft(root=root,request=request,output_directory='next-month',python_path='unused',clock=args['clock'])
   self.assertEqual(result['target_month'],'2026-12')
   name='next-month/capture_plan.json'
   plan,checked=prepare(name,sha256((root/name).read_bytes()).hexdigest(),root=root,clock=args['clock'])
   self.assertEqual(plan['session'],'2026-11-30')
   boundary=json.loads((root/'next-month/boundary.json').read_bytes())
   self.assertEqual(len(boundary['training_dates']),253)
   self.assertFalse(checked['ready_after_close'])
   self.assertFalse(result['capture_executed'])
   self.assertFalse(result['task_changed'])

if __name__=='__main__':unittest.main()
