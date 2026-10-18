import unittest,tempfile
from pathlib import Path
from unittest.mock import Mock
from test_bulk_budgeted_batch_20261003 import module as m

class IndependentBatchReview(unittest.TestCase):
 def test_guard_before_dispatch_keeps_current_in_undispatched(self):
  with tempfile.TemporaryDirectory() as t:
   runner=Mock();reader=Mock();guard=Mock(side_effect=[None,ValueError('source changed before dispatch')])
   ref=m.execute_queue(['a','b'],run_task=runner,read_task=reader,verify_sources=guard,output=Path(t)/'batch',initial_rows=[])
   d=m.reference_load(ref);runner.assert_not_called();reader.assert_not_called()
   self.assertEqual(d['undispatched_task_ids'],['a','b']);self.assertFalse(d['failure']['dispatch_invoked']);self.assertEqual(d['unresolved_dispatched_task_ids'],[])
 def test_guard_after_saved_readback_preserves_unknown_dispatch(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);saved=m.save(p/'readback.json',{'status':'PASSED','attempt_outcome':'RISK_PASSED','numerical_task_id':'a'})
   runner=Mock(return_value={'path':'saved-post','sha256':'a'*64});reader=Mock(return_value=saved)
   ref=m.execute_queue(['a','b'],run_task=runner,read_task=reader,verify_sources=Mock(side_effect=[None,None,ValueError('postread source drift')]),output=p/'batch',initial_rows=[])
   d=m.reference_load(ref);self.assertEqual(d['new_readback_count'],0);self.assertEqual(d['failure']['independent_readback_reference'],saved);self.assertTrue(d['failure']['saved_readback_not_accepted']);self.assertEqual(d['unresolved_dispatched_task_ids'],['a']);self.assertEqual(d['undispatched_task_ids'],['b']);self.assertEqual(runner.call_count,1)
 def test_risk_failed_is_continuable_validation_failure_is_terminal(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);calls=[]
   def run(task):calls.append(task);return {'path':'post-'+task,'sha256':'a'*64}
   def read(task,ref):return m.save(p/(task+'.json'),{'status':'PASSED','numerical_task_id':task,'attempt_outcome':{'a':'RISK_FAILED','b':'VALIDATION_FAILURE'}[task]})
   d=m.reference_load(m.execute_queue(['a','b','c'],run_task=run,read_task=read,verify_sources=lambda:None,output=p/'batch',initial_rows=[]))
   self.assertEqual(calls,['a','b']);self.assertEqual(d['undispatched_task_ids'],['c']);self.assertEqual(d['unresolved_dispatched_task_ids'],[]);self.assertEqual(d['new_outcome_counts']['RISK_FAILED'],1);self.assertEqual(d['new_outcome_counts']['VALIDATION_FAILURE'],1)
 def test_tampered_readback_id_stops_without_retry_and_reopen_rejects(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);wrong=m.save(p/'wrong.json',{'status':'PASSED','numerical_task_id':'different','attempt_outcome':'RISK_PASSED'});run=Mock(return_value={'path':'post','sha256':'a'*64})
   args=dict(run_task=run,read_task=lambda task,ref:wrong,verify_sources=lambda:None,output=p/'batch',initial_rows=[])
   d=m.reference_load(m.execute_queue(['a','b'],**args));self.assertEqual(d['new_readback_count'],0);self.assertEqual(d['unresolved_dispatched_task_ids'],['a'])
   with self.assertRaises(ValueError):m.execute_queue(['a','b'],**args)
   self.assertEqual(run.call_count,1)
if __name__=='__main__':unittest.main()
