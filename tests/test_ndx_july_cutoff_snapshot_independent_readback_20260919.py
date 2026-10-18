import copy,json,unittest
from unittest.mock import patch
from scripts import ndx_july_cutoff_snapshot_independent_readback_20260919 as m
from test_ndx_may_cutoff_snapshot_independent_readback_20260919 import fixture as may_fixture

def fixture():
    queue,context,index,value,attempt=may_fixture()
    reference=dict(path=str(m.QUEUE),sha256='1'*64)
    index['queue']=reference;value['queue']=reference;attempt['queue']=reference
    queue['historical_cutoff']='2023-06-30';value['result']['historical_cutoff']='2023-06-30'
    value['result']['queue_sha256']=m.pure.digest(queue)
    return queue,index,value,attempt

def actual_fixture():
    queue=json.loads(m.QUEUE.read_bytes());context=json.loads(m.CONTEXT.read_bytes())
    candidate=next(c for c in queue['candidates'] if c['task']['weight_spec']=='equal_weight');job=candidate['task']['job_id'];selected=candidate['selected']
    index=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',queue=dict(path=str(m.QUEUE),sha256=m.QUEUE_SHA),seed=None,
        planned=122,completed=[dict(job_id=job)],status='PARTIAL',**dict.fromkeys(m.FLAGS,False),
        finalization=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1',planned=122,completed=1,status='PARTIAL',**dict.fromkeys(m.FLAGS,False)))
    returns=m.pure.decode(context['prepared_inputs']['returns']['payload']);names=[selected[s]['ticker'] for s in sorted(selected)]
    payload=dict(dates=[d[:10] for d in returns['index'][-126:]],tickers=names,
        returns=[[returns['column_values'][returns['columns'].index(t)][i] for t in names] for i in range(len(returns['index'])-126,len(returns['index']))])
    fit=dict.fromkeys(m.FIT_KEYS,None)
    fit.update(schema='ndx_dynamic_cutoff_refit_research_v2',weight_spec='equal_weight',cutoff='2023-06-30',fit_start=payload['dates'][0],fit_end=payload['dates'][-1],fit_row_count=126,fit_data_sha256=m.pure.digest(payload),
        targets={s:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for s,v in selected.items()},risk_chains_by_security={s:v['risk_chain'] for s,v in selected.items()},
        previous_target_weights={},surviving_anchor_mass=0.,anchor_by_security={s:0. for s in selected},effective_anchor_strength=0.,
        anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',declared_parameters={k:v for k,v in queue['fit_parameters'].items() if k!='fit_days'},
        declared_constraint_checks=dict.fromkeys(m.CHECKS,True),declared_constraints_passed=True,
        source_hashes={str(m.ROOT/p):queue['historical_expected_source_hashes'][str(m.ROOT/p)] for p in m.NUMERICAL_FILES})
    for flag in ('checkpoint_weights_used','historical_task_evaluation_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','source_authenticity_verified'):fit[flag]=False
    result=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',queue_sha256=m.pure.digest(queue),job_id=job,candidate=copy.deepcopy(candidate),historical_cutoff='2023-06-30',
        diagnostic_policy='FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC',effective_anchor_strength=0.,input_binding=queue['input_binding'],new_cutoff_fit_attempt_count=1,
        whole_lot_execution_performed=False,forward_oos_evaluation_performed=False,numerical_failure_is_economic_infeasibility=False,**dict.fromkeys(m.FLAGS,False),
        status='FITTED_FIVE_RISKS_PASSED',refit=fit,independently_recomputed_five_checks=dict.fromkeys(m.CHECKS,True))
    value=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1',queue=index['queue'],job_id=job,mode='ONE_NEW_HISTORICAL_CUTOFF_FIT',result=result,
        risk_projection_metadata_independently_recomputed=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    attempt=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=index['queue'],seed=None,job_id=job,mode=value['mode'],runner_source_hashes={str(m.RUNNER):m.LOADED[str(m.RUNNER)]},status='STARTED_NOT_COMPLETED')
    return queue,context,index,value,attempt


class JulyTests(unittest.TestCase):
    def test_actual_july_126_matrix_synthetic_equal_target_no_fit(self):
        q,c,i,v,a=actual_fixture()
        self.assertEqual(m.archive.drift.file_sha(m.QUEUE),m.QUEUE_SHA)
        self.assertEqual(m.archive.drift.file_sha(m.CONTEXT),m.CONTEXT_SHA)
        result=m.validate_task(v,a,q,i,m.validate_index(i,q))
        inspected=m.pure.inspect_context(c,q,result)
        self.assertEqual(inspected['fit_end'],'2023-06-30')
        self.assertEqual(inspected['fit_row_count'],126)
        self.assertEqual(q['candidate_count'],122)
        self.assertEqual(q['risk_liquidity_frontier_count'],121)
        self.assertEqual(q['user_preference_count'],1)
        self.assertEqual(q['candidates'][0]['task']['job_id'],'03b0380924dc110013f9bfd2cc5c6a884967bcde70da0edebd1c01b3dfea07c4')
    def test_private_binding_does_not_mutate_may(self):
        original=m.may.QUEUE
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            q,i,v,a=fixture();m.validate_task(v,a,q,i,m.validate_index(i,q))
        self.assertEqual(m.may.QUEUE,original);self.assertNotEqual(m.QUEUE,m.may.QUEUE)

    def test_no_seed_and_complete_ordered_denominator(self):
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            for defect in ('seed','wrong_queue','count','duplicate','unknown','incomplete_queue'):
                q,i,v,a=fixture()
                if defect=='seed':i['seed']={}
                if defect=='wrong_queue':i['queue']['path']=str(m.may.QUEUE)
                if defect=='count':i['finalization']['completed']=True
                if defect=='duplicate':i['completed']*=2
                if defect=='unknown':i['completed'][0]['job_id']='other'
                if defect=='incomplete_queue':q['candidates'].pop()
                with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(i,q)

    def test_success_none_and_risk_boolean_and_sources_rejected(self):
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            for defect in ('none','bool','sources','scope'):
                q,i,v,a=fixture();c=m.validate_index(i,q)
                if defect=='none':v['result']['refit']=None
                if defect=='bool':v['result']['independently_recomputed_five_checks']['MAX_SINGLE_WEIGHT']=1
                if defect=='sources':v['result']['refit']['source_hashes']={}
                if defect=='scope':v['result']['promotion_allowed']=True
                with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(v,a,q,i,c)

    def test_failure_not_economic_and_gap_end_verification(self):
        with patch.object(m,'PLANNED',104),patch.object(m,'QUEUE_SHA','1'*64):
            q,i,v,a=fixture();r=v['result'];r.pop('independently_recomputed_five_checks');r.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',refit=None,error='synthetic',error_type='RuntimeError')
            self.assertIsNone(m.validate_task(v,a,q,i,m.validate_index(i,q))['refit'])
        with self.assertRaises(ValueError):m.verify_gaps([dict(path=str(m.QUEUE),observed_current_sha256='0'*64)])

if __name__=='__main__':unittest.main()
