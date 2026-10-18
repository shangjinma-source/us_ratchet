from copy import deepcopy
import json
import unittest
from scripts import ndx_may_cutoff_snapshot_independent_readback_20260919 as m


def fixture():
    queue=json.loads(m.QUEUE.read_bytes());context=json.loads(m.CONTEXT.read_bytes())
    candidate=next(c for c in queue['candidates'] if c['task']['weight_spec']=='equal_weight');job=candidate['task']['job_id'];selected=candidate['selected']
    index=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',queue=dict(path=str(m.QUEUE),sha256=m.QUEUE_SHA),seed=None,
        planned=104,completed=[dict(job_id=job)],status='PARTIAL',**dict.fromkeys(m.FLAGS,False),
        finalization=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1',planned=104,completed=1,status='PARTIAL',**dict.fromkeys(m.FLAGS,False)))
    returns=m.pure.decode(context['prepared_inputs']['returns']['payload']);names=[selected[s]['ticker'] for s in sorted(selected)]
    payload=dict(dates=[d[:10] for d in returns['index'][-126:]],tickers=names,
        returns=[[returns['column_values'][returns['columns'].index(t)][i] for t in names] for i in range(len(returns['index'])-126,len(returns['index']))])
    fit=dict.fromkeys(m.FIT_KEYS,None)
    fit.update(schema='ndx_dynamic_cutoff_refit_research_v2',weight_spec='equal_weight',cutoff='2023-04-28',fit_start=payload['dates'][0],fit_end=payload['dates'][-1],fit_row_count=126,fit_data_sha256=m.pure.digest(payload),
        targets={s:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=.25) for s,v in selected.items()},risk_chains_by_security={s:v['risk_chain'] for s,v in selected.items()},
        previous_target_weights={},surviving_anchor_mass=0.,anchor_by_security={s:0. for s in selected},effective_anchor_strength=0.,
        anchor_policy='SURVIVING_SECURITY_TARGET_MASS_RENORMALIZED_NEW_ENTRIES_ZERO_NO_OVERLAP_DISABLED',declared_parameters={k:v for k,v in queue['fit_parameters'].items() if k!='fit_days'},
        declared_constraint_checks=dict.fromkeys(m.CHECKS,True),declared_constraints_passed=True,
        source_hashes={str(m.ROOT/p):queue['historical_expected_source_hashes'][str(m.ROOT/p)] for p in m.NUMERICAL_FILES})
    for flag in ('checkpoint_weights_used','historical_task_evaluation_performed','order_generation_allowed','point_in_time_verified','promotion_allowed','source_authenticity_verified'):fit[flag]=False
    result=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',queue_sha256=m.pure.digest(queue),job_id=job,candidate=deepcopy(candidate),historical_cutoff='2023-04-28',
        diagnostic_policy='FIRST_DECISION_NO_PRIOR_TARGET_DIAGNOSTIC',effective_anchor_strength=0.,input_binding=queue['input_binding'],new_cutoff_fit_attempt_count=1,
        whole_lot_execution_performed=False,forward_oos_evaluation_performed=False,numerical_failure_is_economic_infeasibility=False,**dict.fromkeys(m.FLAGS,False),
        status='FITTED_FIVE_RISKS_PASSED',refit=fit,independently_recomputed_five_checks=dict.fromkeys(m.CHECKS,True))
    value=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1',queue=index['queue'],job_id=job,mode='ONE_NEW_HISTORICAL_CUTOFF_FIT',result=result,
        risk_projection_metadata_independently_recomputed=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    attempt=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=index['queue'],seed=None,job_id=job,mode=value['mode'],runner_source_hashes={str(m.RUNNER):m.LOADED[str(m.RUNNER)]},status='STARTED_NOT_COMPLETED')
    return queue,context,index,value,attempt


class Tests(unittest.TestCase):
    def test_real_may_matrix_synthetic_equal_weights_no_fitter(self):
        queue,context,index,value,attempt=fixture();candidates=m.validate_index(index,queue)
        result=m.validate_task(value,attempt,queue,index,candidates);details=m.pure.inspect_context(context,queue,result)
        self.assertEqual(details['fit_end'],'2023-04-28');self.assertEqual(details['fit_row_count'],126)
        self.assertTrue(all(details['decimal_risks']['checks'].values()))

    def test_seed_april_coordinate_missing_final_duplicate_reject(self):
        for defect in ('seed','april','final','duplicate','count_bool'):
            queue,context,index,value,attempt=fixture()
            if defect=='seed':index['seed']={'path':'not allowed','sha256':'0'*64}
            if defect=='april':index['queue']=dict(path=str(m.pure.QUEUE),sha256=m.pure.QUEUE_SHA)
            if defect=='final':index['finalization']=None
            if defect=='duplicate':index['completed']*=2
            if defect=='count_bool':index['finalization']['completed']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(index,queue)

    def test_success_requires_full_payload_and_exact_sources(self):
        for defect in ('none','checks','extra','source','mode'):
            queue,context,index,value,attempt=fixture();candidates=m.validate_index(index,queue)
            if defect=='none':value['result']['refit']=None
            if defect=='checks':value['result']['independently_recomputed_five_checks']['MAX_SINGLE_WEIGHT']=1
            if defect=='extra':value['promoted']=True
            if defect=='source':value['result']['refit']['source_hashes'].pop(next(iter(value['result']['refit']['source_hashes'])))
            if defect=='mode':value['mode']='EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(value,attempt,queue,index,candidates)

    def test_numerical_failure_retained_without_economic_claim(self):
        queue,context,index,value,attempt=fixture();r=value['result'];r.pop('independently_recomputed_five_checks')
        r.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',refit=None,error='synthetic solver failure',error_type='RuntimeError')
        saved=m.validate_task(value,attempt,queue,index,m.validate_index(index,queue))
        self.assertIsNone(saved['refit']);self.assertFalse(saved['numerical_failure_is_economic_infeasibility'])
        r['refit']={}
        with self.assertRaises(ValueError):m.validate_task(value,attempt,queue,index,m.validate_index(index,queue))


if __name__=='__main__':unittest.main()
