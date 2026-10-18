import json,unittest
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import test_capture_followup_evidence as fixture_module
from scripts import dispatch_followup_evidence as m
class BatchTests(unittest.TestCase):
 def save(self,root,identifier,hour,status='READY'):
  event=dict(status=status,event_id=identifier,decision_id='a'*64,observed_at=f'2026-10-15T{hour}:00:00+00:00',research_context=dict(research_id='a'*24,research_version=m.VERSION,available_cash_exact='20000'))
  p=root/'data/quantity_v2_observations/events/2026-10-15'/ (identifier+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(event));return p
 def test_real_preflight_zero_transport(self):
  with TemporaryDirectory() as folder:
   f=fixture_module.CaptureTests();args,clock,calls,_=f.fixture(folder);self.addCleanup(f.doCleanups)
   path=next((Path(folder)/'data/quantity_v2_observations/events').rglob('*.json'));event=json.loads(path.read_bytes());event['status']='READY';path.write_text(json.dumps(event))
   result=m.run(root=folder,clock=args['clock'])
   self.assertEqual(result['counts']['due'],1);self.assertEqual(result['events'][0]['status'],'DUE_READ_ONLY');self.assertEqual(calls,[])
   self.assertFalse((Path(folder)/'data/quantity_v2_followup').exists())
 def test_oldest_due_attempt_skip_and_limit_resume(self):
  with TemporaryDirectory() as folder:
   root=Path(folder)
   for identifier,hour in [('1'*32,'16'),('2'*32,'15'),('3'*32,'14')]:self.save(root,identifier,hour)
   self.save(root,'4'*32,'17',status='BLOCKED');bad=self.save(root,'5'*32,'18');bad.write_text('{')
   executed=[];completed=set()
   def executor(**kwargs):
    identifier=kwargs['event_id']
    if identifier=='1'*32:return dict(status='PRIOR_ATTEMPT_REQUIRES_REVIEW')
    if identifier in completed:return dict(status='ALREADY_COVERED')
    if not kwargs['execute']:return dict(status='PREFLIGHT_ONLY')
    executed.append(identifier);completed.add(identifier);return dict(status='FOLLOWUP_PUBLISHED')
   args=dict(root=root,max_scan=3,max_dispatch=1,clock=lambda:datetime(2026,10,16,tzinfo=timezone.utc),single_event=executor,execute=True)
   first=m.run(**args);self.assertEqual(executed,['3'*32]);self.assertTrue(first['repeat_current_page']);self.assertIsNone(first['next_scan_cursor']);self.assertEqual(first['counts']['prior_attempt_blocked'],1)
   second=m.run(**args);self.assertEqual(executed,['3'*32,'2'*32]);self.assertFalse(second['repeat_current_page']);self.assertEqual(second['next_scan_cursor'],'2026-10-15/'+'3'*32+'.json')
   last=m.run(**args,after=second['next_scan_cursor']);self.assertEqual(last['counts']['non_ready'],1);self.assertEqual(last['counts']['malformed'],1);self.assertEqual(last['status'],'BATCH_CHECK_COMPLETE')
 def test_invalid_limits_and_no_account_creation(self):
  with TemporaryDirectory() as folder:
   for values in [dict(max_scan=0),dict(max_dispatch=101),dict(after='../bad')]:
    with self.assertRaises(ValueError):m.run(root=folder,**values)
   self.assertEqual(m.run(root=folder)['counts']['scanned'],0);self.assertEqual(list(Path(folder).iterdir()),[])
if __name__=='__main__':unittest.main()
