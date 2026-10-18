from copy import deepcopy
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_dated_economic_batch_independent_readback_20261003 as m


def partition_fixture():
    ids=sorted(m.INITIAL_IDS)+[format(i,'064x') for i in range(1629)]
    summary=dict(schema='DATED_BATCH_SAVED_READBACK_SUMMARY_V1',rows=[dict(numerical_task_id=t) for t in ids],full_new_cutoff_task_denominator=m.FULL,old_different_cutoff_completed_count_deducted=0)
    initial=dict(schema='DATED_INITIAL_ECONOMIC_COMPLETED_V1',rows=[dict(numerical_task_id=t) for t in ids[:3]])
    refs={k:dict(path=k,sha256='a'*64) for k in m.STAGES}
    batch=dict(schema='DATED_ECONOMIC_BATCH_RESULT_V1',initial_rows_preserved=deepcopy(initial['rows']),new_completed_rows=[dict(numerical_task_id=ids[3],stage_references=refs)],planned_remaining_count=1629,new_completed_count=1,unresolved_task_ids=[],undispatched_task_ids=ids[4:],status='STOPPED_WITH_EVIDENCE',failure=dict(numerical_task_id=ids[4],ordinal=1,task_stage_invoked=False,current_stage_invoked=False,stage_may_have_written_evidence=False,completed_stage_references={},stage=None,retry_allowed=False),**dict.fromkeys(('fit_performed','incumbent_executed','incumbent_continuous_recomputed','retry_allowed','economic_comparison_performed','promotion_allowed','point_in_time_verified','formal_benchmark_qualified','all_plan_tasks_completed'),False))
    ctxrefs={k:m.ref(k) for k in ('summary','summary_publication','summary_audit','initial')}
    batch['context']=dict(full_task_count=1632,full_new_cutoff_task_denominator=m.FULL,input_references=ctxrefs,source_hashes={r['path']:r['sha256'] for r in [*ctxrefs.values(),m.ref('driver')]},comparison_stage_not_implemented=True,disk_gate_is_resource_limit_not_task_domain=True,minimum_free_disk_bytes=5*1024**3)
    return summary,initial,batch


def task_fixture():
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in m.STAGES}
    other={k:dict(path=k+'.json',sha256='b'*64) for k in ('raw','account_started','inputs_publication','continuous_publication')}
    ident=dict(cutoff='2026-03-20',requested_previous_target_weights=None);tid=m.sha(m.enc(ident));task=dict(numerical_task_id=tid,numerical_identity=ident)
    summaryrow=dict(task_reference={'coordinate':'same'},saved_batch_row={'independent_readback_reference':{'fitted':'same'}})
    flags=dict(point_in_time_verified=False,promotion_allowed=False)
    inputs=dict(schema='DATED_ACCOUNT_INPUT_DOCUMENT_V1',inputs={'original_task':task},source_hashes={},task_reference=summaryrow['task_reference'],independent_readback_reference=summaryrow['saved_batch_row']['independent_readback_reference'],original_provenance_and_missing=[{}]*101,preserved_evidence_sidecars={str(i):{} for i in range(7)},account_executed=False,fit_performed=False,**flags)
    ia=dict(schema='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=refs['inputs'],publication_reference=other['inputs_publication'],**flags)
    post=dict(schema='DATED_ACCOUNT_POSTCHECK_V1',track='candidate',numerical_task_id=tid,raw_reference=other['raw'],started_reference=other['account_started'],status='ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING',error=None)
    state=dict(numerical_task_id=tid,track='candidate',inputs_reference=refs['inputs'],input_readback_reference=refs['input_readback'],source_hashes={},runtime={})
    raw=dict(schema='DATED_ACCOUNT_RAW_V1',status='ACCOUNT_RETURNED',engine_call_attempt_count=1,returned_account_count=1,started_reference=other['account_started'],source_hashes={},runtime={},account=dict(decisions=[{'status':'NO_PLAN'}],executions=[]),error=None)
    aa=dict(schema='DATED_ACCOUNT_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=tid,postcheck_reference=refs['account_postcheck'],raw_reference=other['raw'],inputs_reference=refs['inputs'],input_readback_reference=refs['input_readback'],attempt_outcome=post['status'],accounting_verified=True,accounting=dict(status='PASS',daily_rows=127,decision_status='NO_PLAN',execution_statuses=[]),**flags)
    c=dict(schema='SOURCE_BOUND_DATED_PER_TASK_CONTINUOUS_DIAGNOSTIC_V1',original_task_preserved=task,numerical_task_id=tid,candidate_core_call_count=1,control_core_call_count=0,input_references={'inputs':refs['inputs']},source_hashes={})
    ca=dict(schema='DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=tid,diagnostic_reference=refs['continuous'],publication_reference=other['continuous_publication'],inputs_reference=refs['inputs'],**flags)
    for role,obj in [('input_readback',ia),('account_readback',aa),('continuous_readback',ca)]:p,h=m.READERS[role];obj.update(reader_sha256=h,source_hashes={str(m.ROOT/p):h})
    docs=dict(inputs=inputs,input_readback=ia,account_postcheck=post,account_readback=aa,continuous=c,continuous_readback=ca,raw=raw,account_started=dict(schema='DATED_ACCOUNT_STARTED_V1',state=state),inputs_publication=dict(inputs_reference=refs['inputs'],source_hashes={},status='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED'),continuous_publication=dict(diagnostic_reference=refs['continuous'],source_hashes={}),_refs=other)
    return tid,refs,docs,summaryrow


class Tests(unittest.TestCase):
    def test_wrong_batch_context_even_when_rows_correct(self):
        for mutation in (
            lambda c:c.__setitem__('full_task_count',True),
            lambda c:c.__setitem__('full_new_cutoff_task_denominator',m.FULL-504),
            lambda c:c['input_references']['summary_audit'].__setitem__('sha256','0'*64),
            lambda c:c['source_hashes'].__setitem__(m.ref('driver')['path'],'0'*64),
            lambda c:c.__setitem__('comparison_stage_not_implemented',False),
        ):
            s,i,b=partition_fixture();mutation(b['context'])
            with self.assertRaises(ValueError):m.partition(s,i,b)

    def test_partition_all_denominators_and_unknown_dispatch(self):
        a=partition_fixture();m.partition(*a)
        s,i,b=deepcopy(a);tid=b['undispatched_task_ids'].pop(0);b['unresolved_task_ids']=[tid];b['failure'].update(task_stage_invoked=True,current_stage_invoked=False,stage_may_have_written_evidence=True,stage='account_postcheck',completed_stage_references={k:dict(path=k,sha256='a'*64) for k in sorted(m.STAGES[:2])})
        m.partition(s,i,b)
        b['failure']['task_stage_invoked']=False
        with self.assertRaises(ValueError):m.partition(s,i,b)
        for mutate in (lambda b:b.__setitem__('new_completed_count',True),lambda b:b['undispatched_task_ids'].pop(),lambda b:b['initial_rows_preserved'].pop()):
            s,i,b=deepcopy(a);mutate(b)
            with self.assertRaises(ValueError):m.partition(s,i,b)

    def test_preserve_no_plan_rejected_and_blocked(self):
        args=task_fixture();r=m.validate_task(*args);self.assertEqual(r['decision_status'],'NO_PLAN');self.assertEqual(r['execution_statuses'],[])
        tid,refs,d,s=task_fixture();d['raw']['account'].update(decisions=[{'status':'FROZEN'}],executions=[{'status':'REJECTED'}]);d['account_readback']['accounting'].update(decision_status='FROZEN',execution_statuses=['REJECTED'])
        self.assertEqual(m.validate_task(tid,refs,d,s)['execution_statuses'],['REJECTED'])
        outcome='NOT_EXECUTED_NONPOSITIVE_TARGET';d['raw'].update(account=None,status=outcome,engine_call_attempt_count=0,returned_account_count=0);d['account_postcheck']['status']=outcome;d['account_readback'].update(attempt_outcome=outcome,accounting_verified=False,accounting=None)
        r=m.validate_task(tid,refs,d,s);self.assertFalse(r['integer_account_available']);self.assertIsNone(r['decision_status'])
        d['raw']['returned_account_count']=False
        with self.assertRaises(ValueError):m.validate_task(tid,refs,d,s)

    def test_technical_failure_and_crosslinks_cannot_complete(self):
        for mutate in (lambda d:d['account_readback'].__setitem__('inputs_reference',{}),lambda d:d['continuous'].__setitem__('control_core_call_count',False),lambda d:d['input_readback'].__setitem__('publication_reference',{}),lambda d:d['account_readback'].__setitem__('reader_sha256','0'*64)):
            tid,r,d,s=task_fixture();mutate(d)
            with self.assertRaises(ValueError):m.validate_task(tid,r,d,s)
        tid,r,d,s=task_fixture();d['account_postcheck']['status']='VALIDATION_FAILURE_RECORDED';d['account_readback']['attempt_outcome']='VALIDATION_FAILURE_RECORDED'
        with self.assertRaises(ValueError):m.validate_task(tid,r,d,s)

    def test_pending_result_no_reads(self):
        with patch.object(m,'RESULT_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.readback(dict(path=str(m.RESULT_PATH),sha256='a'*64),execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
