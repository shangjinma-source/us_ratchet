"""Synthetic metadata/report bytes only; no saved task or raw reads."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_bulk_budgeted_status_summary_20261003 as m

def ref(name):return dict(path='synthetic/'+name,sha256=m.digest(name))
def fixture(mode='STOPPED'):
    refs={key:ref(key) for key in m.BOUND};combos=[];ids=[]
    for k in range(4,21):
        for rank in range(32):
            tasks=[]
            for spec in m.SPECS:
                identity=dict(holding_count=k,weight_spec=spec,unique=[k,rank,spec]);tid=m.digest(identity);ids.append(tid);tasks.append(dict(numerical_task_id=tid,numerical_identity=identity))
            combos.append(dict(k=k,tasks=tasks))
    oldrows=[]
    for i in range(504):
        identity=dict(holding_count=4+i//30%17,weight_spec=m.SPECS[i%3],old=i);tid=m.digest(identity)
        oldrows.append(dict(numerical_task_id=tid,status='EXTERNALLY_COMPLETED_NUMERICALLY_IDENTICAL_REBOUND',new_wrapper_call_attempt_count=0,old_completed_row=dict(status='FITTED_FIVE_RISKS_PASSED',full_task=dict(numerical_task_id=tid,numerical_identity=identity)),old_completed_row_reference=dict(ref('oldindex'),json_pointer=f'/rows/{i}')))
    flags=dict.fromkeys(m.FALSE,False)
    q=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_V1',status='PREPARED_NOT_ATTEMPTED',materialized=dict(materialized_task_count=1632,complete_saved_completed_task_count=504,selected_completed_intersection_count=0,new_unattempted_numerical_task_ids=ids,combinations=combos,full_plan_task_denominator=999999),**flags)
    envelopes={};rows=[]
    count=1632 if mode=='FINISHED' else 4
    for i in range(count):
        tid=ids[i];outcome=m.OUTCOMES[i%2];post=ref(tid+'/postcheck');ci=i//3;si=i%3
        report=dict(schema='BULK_BUDGETED_SINGLE_TASK_INDEPENDENT_READBACK_V1',status='PASSED',attempt_outcome=outcome,numerical_task_id=tid,postcheck_reference=post,started_reference=ref(tid+'/started'),raw_reference=ref(tid+'/raw'),task_reference=dict(refs['preparation'],json_pointer=f'/materialized/combinations/{ci}/tasks/{si}'),input_references=dict(preparation=refs['preparation']),materialized_task_denominator=1632,externally_completed_task_count=504,full_plan_task_denominator=999999,other_new_tasks_not_inferred=1631,independent_readback_performed=True,runner_called=False,fitter_called=False,optimization_repeated=False,risk_projection_metadata_independently_recomputed=False,optimizer_optimality_proved=False,runtime_binary_closure_verified=False,full_transitive_source_closure_reverified=False,source_hashes={},runtime={},**flags)
        report.pop('economic_comparison_performed');report['detail']={'status':'FITTED_FIVE_RISKS_PASSED' if outcome=='RISK_PASSED' else 'FITTED_FIVE_RISKS_FAILED'}
        blob=m.encoded(report);r=dict(path='synthetic/'+tid+'/independent_readback.json',sha256=m.sha(blob));envelopes[r['path']]=dict(reference=r,bytes=blob)
        row=dict(numerical_task_id=tid,independent_readback_reference=r,postcheck_reference=post)
        if i>=2:row.update(ordinal=i-2,attempt_outcome=outcome)
        rows.append(row)
    initial=dict(schema='BULK_BUDGETED_FIRST_TWO_COMPLETED_V1',rows=rows[:2],remaining_batch_request_count=1630,**flags)
    context=dict(first_two_reference=refs['initial'],planned_total_task_count=1632,prior_completed_task_count=2,ordered_task_ids_sha256=m.sha(__import__('json').dumps(ids,separators=(',',':')).encode()))
    failure=None if mode=='FINISHED' else dict(numerical_task_id=ids[4],dispatch_invoked=True,reason='DISPATCH_OR_READBACK_FAILURE',independent_readback_reference=None)
    batch=dict(schema='BULK_BUDGETED_BATCH_RESULT_V1',status='BUDGETED_QUEUE_FINISHED' if failure is None else 'STOPPED_WITH_EVIDENCE',initial_completed_rows=rows[:2],newly_readback_rows=rows[2:],new_outcome_counts={s:sum(r['attempt_outcome']==s for r in rows[2:]) for s in m.OUTCOMES},new_readback_count=count-2,planned_remaining_dispatch_count=1630,undispatched_task_ids=[] if failure is None else ids[5:],unresolved_dispatched_task_ids=[] if failure is None else [ids[4]],failure=failure,batch_context=context,**flags)
    return dict(preparation=q,rebinding=dict(schema='BULK_COMPLETED_TASK_REBINDING_V1',numerical_contracts_unchanged=True,rows=oldrows),initial=initial,batch=batch),refs,envelopes

class Tests(unittest.TestCase):
    def test_stopped_disjoint_counts_and_scope(self):
        d,r,e=fixture();saved=deepcopy(d);v=m.assemble_summary(d,r,e)
        self.assertEqual(v['new_state_counts'],dict(RISK_PASSED=2,RISK_FAILED=2,NUMERICAL_EXCEPTION=0,VALIDATION_FAILURE=0,UNDISPATCHED=1627,UNRESOLVED_DISPATCH=1))
        self.assertEqual(v['accepted_new_readback_count'],4);self.assertEqual(v['dispatch_invocation_count'],5);self.assertEqual(v['successful_reusable_evidence_count'],506)
        self.assertEqual(v['remaining_without_accepted_terminal_readback'],999999-508);self.assertEqual(d,saved)
        self.assertEqual(sum(sum(x.values()) for specs in v['per_cardinality_and_spec'].values() for x in specs.values()),2136)

    def test_finished_is_not_all_success_or_full_pool(self):
        d,r,e=fixture('FINISHED');v=m.assemble_summary(d,r,e)
        self.assertEqual(v['accepted_new_readback_count'],1632);self.assertEqual(v['successful_new_risk_pass_evidence_count'],816)
        self.assertFalse(v['all_plan_tasks_completed']);self.assertFalse(v['risk_checks_recomputed'])

    def test_duplicate_missing_or_false_counts_rejected(self):
        d,r,e=fixture()
        for mutate in (lambda x:x['batch']['undispatched_task_ids'].append(x['batch']['unresolved_dispatched_task_ids'][0]),lambda x:x['batch'].update(new_readback_count=False),lambda x:x['batch']['newly_readback_rows'][0].update(attempt_outcome='RISK_PASSED'),lambda x:x['rebinding']['rows'].__setitem__(1,deepcopy(x['rebinding']['rows'][0]))):
            bad=deepcopy(d);mutate(bad)
            if bad==d:continue
            with self.assertRaises(ValueError):m.assemble_summary(bad,r,e)
        bad=deepcopy(e);next(iter(bad.values()))['bytes']+=b' '
        with self.assertRaises(ValueError):m.assemble_summary(d,r,bad)

    def test_unaccepted_saved_report_never_success(self):
        d,r,e=fixture();failure=d['batch']['failure'];tid=failure['numerical_task_id'];source=m.loads(next(iter(e.values()))['bytes']);source.update(numerical_task_id=tid,task_reference=dict(r['preparation'],json_pointer='/materialized/combinations/1/tasks/1'))
        blob=m.encoded(source);rr=dict(path='synthetic/unaccepted.json',sha256=m.sha(blob));e[rr['path']]=dict(reference=rr,bytes=blob);failure['independent_readback_reference']=rr
        v=m.assemble_summary(d,r,e);self.assertEqual(v['saved_independent_report_count'],5);self.assertEqual(v['successful_reusable_evidence_count'],506)
        self.assertEqual(v['new_rows'][4]['state'],'UNRESOLVED_DISPATCH')

    def test_accepted_numerical_exception_is_terminal_not_success(self):
        d,r,e=fixture();row=d['batch']['newly_readback_rows'][-1];oldref=row['independent_readback_reference'];report=m.loads(e.pop(oldref['path'])['bytes']);report.update(attempt_outcome='NUMERICAL_EXCEPTION',detail={'status':'NUMERICAL_EXCEPTION_NO_RETURNED_FIT'})
        blob=m.encoded(report);rr=dict(oldref,sha256=m.sha(blob));e[rr['path']]=dict(reference=rr,bytes=blob);row.update(attempt_outcome='NUMERICAL_EXCEPTION',independent_readback_reference=rr)
        d['batch'].update(failure=dict(numerical_task_id=row['numerical_task_id'],reason='NUMERICAL_EXCEPTION',task_readback_saved=True),unresolved_dispatched_task_ids=[],undispatched_task_ids=d['batch']['unresolved_dispatched_task_ids']+d['batch']['undispatched_task_ids'],new_outcome_counts=dict(RISK_PASSED=1,RISK_FAILED=0,NUMERICAL_EXCEPTION=1,VALIDATION_FAILURE=0))
        value=m.assemble_summary(d,r,e);self.assertEqual(value['new_state_counts']['NUMERICAL_EXCEPTION'],1);self.assertEqual(value['dispatch_invocation_count'],4);self.assertEqual(value['successful_reusable_evidence_count'],506);self.assertFalse(value['numerical_exception_proves_economic_infeasibility'])

    def test_pending_pin_before_reads(self):
        bound=deepcopy(m.BOUND);bound['batch']=(bound['batch'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.load_inputs()
            read.assert_not_called()

if __name__=='__main__':unittest.main()
