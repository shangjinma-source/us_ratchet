import unittest
from copy import deepcopy
from unittest.mock import patch
from types import SimpleNamespace
from scripts import ndx_cash_topup_neighbor_full_independent_readback_20261003 as m


def partition():
    queue=[];pos=0
    for i in range(324):
        n=532 if i==0 else (933 if i<=89 else 932)
        queue.append(dict(scenario_index=i//9,shard_index=i%9,global_shard_index=i,global_task_start=pos,global_task_stop=pos+n,shard=dict(start=0,stop=n),contract_reference=dict(path='contract',sha256='a'*64)));pos+=n
    # Window sizes in this fixture are only partition metadata, never prepared numerical candidates.
    queue[-1]['global_task_stop']=301657
    refs=[dict(path=str(m.BATCH/f'scenario-{d["scenario_index"]:02d}-shard-{d["shard_index"]:05d}'/'completion.json'),sha256='a'*64) for d in queue]
    ctx={'scenario_count':40};ch=m.digest(ctx)
    result=dict(schema='CASH_NEIGHBOR_SHARD_BATCH_RUN_V1',status='COMPLETE',context_sha256=ch,full_shard_count=324,full_task_count=301657,failure=None,partial_shard_recovery=None,remaining_shard_descriptors=[],accepted_task_count=301657,known_externally_completed_task_count=1,actual_new_undispatched_task_count=0,partition_includes_external_first_even_before_its_shard_is_referenced=True,whole_batch_status_is_partition_not_feasibility=True,remaining_scope_includes_unresolved_failed_shard=False,completed_shard_references=refs,outcome_counts=dict(FEASIBLE=100000,INFEASIBLE=201656,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=1,UNRESOLVED_DISPATCH=0,UNDISPATCHED=0))
    request=dict(context_sha256=ch,full_shard_count=324,full_task_count=301657,max_new_shards=None)
    return result,request,dict(context=ctx,context_sha256=ch),queue,ctx

class Tests(unittest.TestCase):
    def test_whole_partition_and_no_partial_pass(self):
        args=partition();self.assertEqual(m.validate_partition(*args),m.digest(args[-1]))
        for mode in ('bool','remaining','partial','duplicate','technical'):
            a=deepcopy(args)
            if mode=='bool':a[0]['outcome_counts']['UNDISPATCHED']=False
            elif mode=='remaining':a[0]['remaining_shard_descriptors']=[a[3][-1]]
            elif mode=='partial':a[0]['partial_shard_recovery']={}
            elif mode=='duplicate':a[0]['completed_shard_references'][1]=a[0]['completed_shard_references'][0]
            else:a[0]['failure']={'status':'EXCEPTION'}
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_partition(*a)
    def test_reused_audit_strict_context_and_outcome(self):
        d=dict(global_task_start=532,global_task_stop=534);ref=dict(path='r',sha256='a'*64)
        detail=dict(task_count=2,new_arithmetic_checked_count=2,task_results=[dict(task_id=str(i),outcome='FEASIBLE',new_arithmetic_checked=True) for i in range(2)],outcome_counts=dict(FEASIBLE=2,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=0))
        r=dict(schema='CASH_NEIGHBOR_FULL_AUDIT_SHARD_V1',status='PASS',reader_sha256=m.LOADED,global_shard_index=1,audit_context_sha256='a',result_reference=ref,descriptor=d,completion_reference=ref,detail=detail,**m.FLAGS)
        self.assertEqual(m.validate_reused(r,1,'a',ref,d,ref),detail)
        for key,value in [('global_shard_index',True),('audit_context_sha256','b'),('status','FAILED'),('evaluator_called',True)]:
            wrong=deepcopy(r);wrong[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate_reused(wrong,1,'a',ref,d,ref)
        wrong=deepcopy(r);wrong['detail']['task_results'][1]['task_id']='0'
        with self.assertRaises(ValueError):m.validate_reused(wrong,1,'a',ref,d,ref)
    def test_first_report_is_external_not_new_evaluation(self):
        helper=SimpleNamespace(FALSE=('fit_performed',),FIRST_ID='first');q=[{'x':1}];ref=dict(path='c',sha256='a'*64)
        r=dict(schema='CASH_NEIGHBOR_SHARD_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=m.HELPER_SHA,global_shard_index=0,descriptor=q[0],completion_reference=ref,all_completed_prefix_arithmetic_checked_in_this_report=True,existing_first_arithmetic_recomputed=False,fit_performed=False,task_count=532,new_arithmetic_checked_count=531,outcome_counts=dict(FEASIBLE=98,INFEASIBLE=433,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=1),task_results=[dict(task_id='first' if i==0 else str(i)) for i in range(532)])
        m.validate_first(r,q,ref,helper)
        r['new_arithmetic_checked_count']=532
        with self.assertRaises(ValueError):m.validate_first(r,q,ref,helper)
    def test_pending_blocks_before_file_reads_or_loading(self):
        with patch.object(m,'RESULT_PATH',None),patch.object(m,'fresh_helper',side_effect=AssertionError('No helper')):
            with self.assertRaisesRegex(ValueError,'pending'):m.run(result_reference={},execute=True)
    def test_aggregate_refuses_missing_or_duplicate_scope(self):
        with self.assertRaises(ValueError):m.aggregate({}, {})
        details={i:dict(task_count=1,new_arithmetic_checked_count=1,task_results=[dict(task_id='same')],outcome_counts=dict(FEASIBLE=1,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=0)) for i in range(324)}
        with self.assertRaisesRegex(ValueError,'repeated'):m.aggregate(details,{})
    def test_reused_prepared_order_and_exact_source_closure(self):
        contract={'original':True};h=m.digest(contract);prepared=dict(contract=contract,contract_sha256=h)
        tasks=[]
        for i in range(2):
            identity=dict(scenario_contract_sha256=h,buy_shares={'X':i});tasks.append(dict(identity=identity,task_id=m.digest(identity),scenario_candidate_ordinal=i))
        descriptor=dict(shard=dict(start=0),global_task_start=532,global_task_stop=534)
        ids=[t['task_id'] for t in tasks];sources={'fixed':'a'*64};jr=dict(path='journal',sha256='b'*64);sr=dict(path='start',sha256='c'*64)
        counts=dict(FEASIBLE=2,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0,EXTERNALLY_REFERENCED=0)
        report=dict(source_hashes=sources,journal_reference=jr,started_reference=sr,detail=dict(task_count=2,new_arithmetic_checked_count=2,task_results=[dict(task_id=x) for x in ids],outcome_counts=counts,record_count=6,journal_sha256=jr['sha256']))
        completion=dict(schema='CASH_NEIGHBOR_SHARD_COMPLETION_V1',status='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED',descriptor=descriptor,context_sha256='ctx',journal_reference=jr,started_reference=sr,task_count=2,outcome_counts=counts,new_evaluator_call_count=2,record_count=6)
        started=dict(schema='CASH_NEIGHBOR_SHARD_STARTED_V1',descriptor=descriptor,context_sha256='ctx',contract_sha256=h,ordered_task_ids=ids)
        args=dict(completion=completion,started=started,prepared=prepared,tasks=tasks,descriptor=descriptor,expected_sources=deepcopy(sources),execution_context_sha256='ctx')
        m.validate_reused_metadata(report,**args)
        for mode in ('empty','extra','reorder','journal'):
            wrong=deepcopy(report)
            if mode=='empty':wrong['source_hashes']={}
            elif mode=='extra':wrong['source_hashes']['invented']='d'*64
            elif mode=='reorder':wrong['detail']['task_results'].reverse()
            else:wrong['journal_reference']['sha256']='e'*64
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_reused_metadata(wrong,**args)
    def test_actual_schemaless_request_and_new_prefix_bound(self):
        flags=dict.fromkeys(('fit_performed','account_executed','orders_executed','point_in_time_verified','promotion_allowed','full_integer_domain_exhausted','economic_winner_selected','target_weights_changed','holdings_sold','runtime_binary_closure_verified','continuous_source_monitoring_claimed','automatic_retry_allowed'),False)
        request=dict(context_sha256='ctx',max_new_shards=3,full_shard_count=324,full_task_count=301657,**flags)
        result=dict(context_sha256='ctx',new_completed_shard_count=3,completed_shard_references=[{}, {}, {}, {}])
        m.validate_request_link(result,request,1)
        for mode in ('countbool','limit','schema','context'):
            r=deepcopy(result);q=deepcopy(request)
            if mode=='countbool':r['new_completed_shard_count']=True
            elif mode=='limit':q['max_new_shards']=2
            elif mode=='schema':q['schema']='fabricated'
            else:q['context_sha256']='wrong'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.validate_request_link(r,q,1)
if __name__=='__main__':unittest.main()
