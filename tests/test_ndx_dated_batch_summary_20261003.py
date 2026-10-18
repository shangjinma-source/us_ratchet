from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/'scripts/ndx_dated_batch_summary_20261003.py'
s=importlib.util.spec_from_file_location('summary',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def fixture(stop=False):
    combos=[];ids=[];reports={};allrows=[]
    for k in range(4,21):
        for rank in range(32):
            tasks=[]
            for spec in m.SPECS:
                ident=dict(cutoff='2026-03-20',requested_previous_target_weights=None,holding_count=k,weight_spec=spec,rank=rank)
                tid=m.sha(m.encode(ident));tasks.append(dict(numerical_task_id=tid,numerical_identity=ident));ids.append(tid)
            combos.append(dict(tasks=tasks))
    count=5 if stop else 1632
    for i,tid in enumerate(ids[:count]):
        ref=dict(path=tid,sha256='a'*64);outcome=('RISK_PASSED','RISK_FAILED')[i%2] if i<4 else ('NUMERICAL_EXCEPTION' if stop else 'RISK_FAILED')
        row=dict(numerical_task_id=tid,postcheck_reference=ref,independent_readback_reference=ref)
        if i>=2:row.update(ordinal=i-2,attempt_outcome=outcome)
        allrows.append(row)
        reports[tid]=dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',status='PASSED',numerical_task_id=tid,attempt_outcome=outcome,postcheck_reference=ref,task_reference=dict(m.BOUND['preparation'],json_pointer=f'/materialized/combinations/{i//3}/tasks/{i%3}'),full_plan_task_denominator=m.FULL,materialized_task_denominator=1632,source_hashes={m.READER:m.READER_SHA},**dict.fromkeys(('runner_called','fitter_called','optimization_repeated','promotion_allowed','point_in_time_verified'),False))
    initial=dict(schema='DATED_INITIAL_COMPLETED_TASKS_V1',preparation_reference=m.BOUND['preparation'],rows=allrows[:2])
    rows=allrows[2:];batch=dict(schema='DATED_BATCH_RESULT_V1',initial_completed_rows=deepcopy(initial['rows']),newly_readback_rows=rows,new_readback_count=len(rows),planned_remaining_dispatch_count=1630,unresolved_dispatched_task_ids=[],undispatched_task_ids=ids[count:],failure=dict(numerical_task_id=ids[count-1],reason='NUMERICAL_EXCEPTION',task_readback_saved=True) if stop else None,status='STOPPED_WITH_EVIDENCE' if stop else 'BUDGETED_QUEUE_FINISHED',new_outcome_counts={o:sum(r['attempt_outcome']==o for r in rows) for o in m.OUTCOMES})
    return dict(preparation=dict(materialized=dict(materialized_task_count=1632,full_plan_task_denominator=m.FULL,combinations=combos)),initial=initial,batch=batch,reports_by_id=reports,references=deepcopy(m.BOUND))
class Tests(unittest.TestCase):
    def test_complete_not_all_pass_and_domain(self):
        out=m.assemble_summary(**fixture());self.assertEqual(out['accepted_independent_terminal_count'],1632);self.assertEqual(out['remaining_without_accepted_terminal_count'],m.FULL-1632);self.assertEqual(len(out['k_spec_coverage']),51);self.assertGreater(out['risk_failed_task_count'],0);self.assertFalse(out['all_plan_tasks_completed'])
    def test_stopped_and_unresolved(self):
        a=fixture(True);out=m.assemble_summary(**a);self.assertEqual(out['failed_terminal_task_count'],1);self.assertEqual(out['undispatched_count'],1627)
        a['batch']['unresolved_dispatched_task_ids']=[a['batch']['undispatched_task_ids'].pop(0)];a['batch']['failure']=dict(numerical_task_id=a['batch']['unresolved_dispatched_task_ids'][0],dispatch_invoked=True,reason='DISPATCH_OR_READBACK_FAILURE');out=m.assemble_summary(**a);self.assertEqual(out['attempted_task_count'],6)
    def test_tamper(self):
        for mutation in (lambda a:a['preparation']['materialized'].update(materialized_task_count=True),lambda a:next(iter(a['reports_by_id'].values())).update(point_in_time_verified=0),lambda a:a['batch']['undispatched_task_ids'].append('x'),lambda a:next(iter(a['reports_by_id'].values()))['task_reference'].update(json_pointer='/old/tasks/0')):
            a=fixture(True);mutation(a)
            with self.assertRaises(ValueError):m.assemble_summary(**a)
    def test_failclosed_no_execute_and_pins(self):
        with self.assertRaises(ValueError):m.run()
        for ref in m.BOUND.values():self.assertEqual(m.sha(Path(ref['path']).read_bytes()),ref['sha256'])
if __name__=='__main__':unittest.main()
