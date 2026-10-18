from copy import deepcopy
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_bulk_budgeted_status_summary_20261003 import m,fixture

class IndependentStatusSummaryReview(unittest.TestCase):
 def test_predispatch_stop_preserves_current_unattempted_and_counts(self):
  d,r,e=fixture();b=d['batch'];tid=b['unresolved_dispatched_task_ids'][0]
  b['undispatched_task_ids']=[tid]+b['undispatched_task_ids'];b['unresolved_dispatched_task_ids']=[];b['failure'].update(dispatch_invoked=False)
  v=m.assemble_summary(d,r,e)
  self.assertEqual(v['dispatch_invocation_count'],4);self.assertEqual(v['new_state_counts']['UNDISPATCHED'],1628);self.assertEqual(v['new_state_counts']['UNRESOLVED_DISPATCH'],0)
  self.assertEqual(v['remaining_without_accepted_terminal_readback'],999999-504-4);self.assertEqual(v['remaining_without_successful_risk_pass'],999999-504-2)
  self.assertEqual(len({x['numerical_task_id'] for x in v['new_rows']+v['old_external_rows']}),2136)
 def test_rehashed_outcome_lie_and_missing_report_fail_closed(self):
  d,r,e=fixture();row=d['batch']['newly_readback_rows'][-1];original=row['independent_readback_reference'];report=m.loads(e[original['path']]['bytes']);report['attempt_outcome']='RISK_PASSED'
  blob=m.encoded(report);newref=dict(original,sha256=m.sha(blob));row.update(independent_readback_reference=newref,attempt_outcome='RISK_PASSED');e[original['path']]={'reference':newref,'bytes':blob}
  with self.assertRaises(ValueError):m.assemble_summary(d,r,e)
  d,r,e=fixture();e.pop(next(iter(e)))
  with self.assertRaises(ValueError):m.assemble_summary(d,r,e)
 def test_validation_failure_with_passed_numeric_subresult_not_reusable(self):
  d,r,e=fixture();b=d['batch'];row=b['newly_readback_rows'][-1];ref=row['independent_readback_reference'];report=m.loads(e[ref['path']]['bytes']);report.update(attempt_outcome='VALIDATION_FAILURE',detail={'status':'FITTED_FIVE_RISKS_PASSED'})
  blob=m.encoded(report);newref=dict(ref,sha256=m.sha(blob));e[ref['path']]={'reference':newref,'bytes':blob};row.update(independent_readback_reference=newref,attempt_outcome='VALIDATION_FAILURE')
  b['failure']={'numerical_task_id':row['numerical_task_id'],'reason':'VALIDATION_FAILURE','task_readback_saved':True};b['undispatched_task_ids']=b['unresolved_dispatched_task_ids']+b['undispatched_task_ids'];b['unresolved_dispatched_task_ids']=[];b['new_outcome_counts']={'RISK_PASSED':1,'RISK_FAILED':0,'NUMERICAL_EXCEPTION':0,'VALIDATION_FAILURE':1}
  v=m.assemble_summary(d,r,e);self.assertEqual(v['new_state_counts']['VALIDATION_FAILURE'],1);self.assertEqual(v['successful_reusable_evidence_count'],506);self.assertFalse(v['new_rows'][3]['successful_reusable_evidence']);self.assertFalse(v['bounded_queue_all_readbacks_accepted'])
 def test_unknown_dispatch_cannot_be_dropped_and_no_overwrite(self):
  d,r,e=fixture();d['batch']['unresolved_dispatched_task_ids']=[]
  with self.assertRaises(ValueError):m.assemble_summary(d,r,e)
  with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)),patch.object(m,'load_inputs') as load:
   (Path(t)/'failure.json').write_text('{}')
   with self.assertRaises(ValueError):m.run()
   load.assert_not_called();self.assertEqual((Path(t)/'failure.json').read_text(),'{}')
if __name__=='__main__':unittest.main()
