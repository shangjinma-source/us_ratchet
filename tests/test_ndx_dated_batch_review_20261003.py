"""Independent dispatch accounting tests, no task execution."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_dated_batch_20261003 as m
IDS=[format(i,'064x') for i in range(1,1633)]
class Review(unittest.TestCase):
    def test_before_dispatch_failure_keeps_current_undispatched(self):
        calls=[];guards=[]
        def guard():
            guards.append(1)
            if len(guards)==2:raise ValueError('pre-dispatch source drift')
        with tempfile.TemporaryDirectory() as folder:
            ref=m.execute_queue(IDS[:2],run_task=lambda t:calls.append(t),read_task=None,verify_sources=guard,output=Path(folder)/'batch',initial_rows=[])
            result=m.reference_load(ref)
            self.assertEqual(calls,[]);self.assertEqual(result['undispatched_task_ids'],IDS[:2]);self.assertEqual(result['unresolved_dispatched_task_ids'],[]);self.assertFalse(result['failure']['dispatch_invoked'])

    def test_saved_but_unaccepted_readback_not_counted_or_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);calls=[]
            def run(t):calls.append(t);return {'path':'post','sha256':'a'*64}
            def reader(t,p):return m.save(base/'bad.json',dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',numerical_task_id=t,status='PASSED',attempt_outcome='UNKNOWN'))
            result=m.reference_load(m.execute_queue(IDS[:3],run_task=run,read_task=reader,verify_sources=lambda:None,output=base/'batch',initial_rows=[]))
            self.assertEqual(calls,IDS[:1]);self.assertEqual(result['new_readback_count'],0);self.assertEqual(result['unresolved_dispatched_task_ids'],IDS[:1]);self.assertEqual(result['undispatched_task_ids'],IDS[1:3]);self.assertTrue(result['failure']['saved_readback_not_accepted'])

    def test_old_cutoff_report_and_nonprefix_never_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);tid=IDS[0]
            post=m.save(base/'post.json',dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',numerical_task_id=tid,status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK'))
            report=m.save(base/'read.json',dict(schema='BULK_BUDGETED_SINGLE_TASK_INDEPENDENT_READBACK_V1',numerical_task_id=tid,status='PASSED',attempt_outcome='RISK_PASSED',postcheck_reference=post))
            initial=dict(schema='DATED_INITIAL_COMPLETED_TASKS_V1',preparation_reference=m.PREPARATION_REFERENCE,rows=[dict(numerical_task_id=tid,postcheck_reference=post,independent_readback_reference=report)])
            with self.assertRaises(ValueError):m.validate_initial(initial,IDS)
            initial['rows'][0]['numerical_task_id']=IDS[1]
            with patch.object(m,'inspect_readback',side_effect=AssertionError('prefix gate first')):
                with self.assertRaises(ValueError):m.validate_initial(initial,IDS)

if __name__=='__main__':unittest.main()
