from copy import deepcopy
import json
import unittest
from scripts import ndx_cutoff_snapshot_independent_readback_20260919 as m


def fixture():
    queue=json.loads(m.pure.QUEUE.read_bytes());seed=json.loads(m.pure.EXECUTION.read_bytes());job=seed['job_id']
    index=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_COMPLETION_INDEX_V1',queue=dict(path=str(m.pure.QUEUE),sha256=m.pure.QUEUE_SHA),
        seed=dict(path=str(m.pure.EXECUTION),sha256=m.pure.EXECUTION_SHA),planned=queue['candidate_count'],completed=[dict(job_id=job)],status='PARTIAL',
        finalization=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_FINALIZATION_V1',planned=queue['candidate_count'],completed=1,status='PARTIAL',**dict.fromkeys(m.FLAGS,False)),**dict.fromkeys(m.FLAGS,False))
    result={k:deepcopy(v) for k,v in seed['result'].items() if k not in ('historical_expected_source_hashes','archive_resolution','historical_loader_gap_observations')}
    result.update(schema='CORRECTED_CUTOFF_SNAPSHOT_NUMERICAL_RESULT_V1',input_binding=queue['input_binding'])
    mode='EXTERNAL_SINGLE_FIT_IMPORTED_WITHOUT_REFIT'
    value=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_TASK_V1',queue=index['queue'],job_id=job,mode=mode,result=result,seed=index['seed'],original_single_fit_wrapper=seed,
        risk_projection_metadata_independently_recomputed=False,historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False)
    attempt=dict(schema='CORRECTED_CUTOFF_SNAPSHOT_ATTEMPT_V1',queue=index['queue'],seed=index['seed'],job_id=job,mode=mode,
        runner_source_hashes={str(m.RUNNER):m.LOADED[str(m.RUNNER)]},status='STARTED_NOT_COMPLETED')
    return queue,seed,index,value,attempt


class Tests(unittest.TestCase):
    def test_real_seed_exact_typed_decimal_without_fitter(self):
        queue,seed,index,value,attempt=fixture();candidates=m.validate_index(index,queue)
        result=m.validate_task(value,attempt,queue=queue,index=index,candidates=candidates,seed=seed)
        context=json.loads(m.pure.CONTEXT.read_bytes());details=m.pure.inspect_context(context,queue,result)
        self.assertEqual(details['fit_row_count'],126);self.assertTrue(all(details['decimal_risks']['checks'].values()))

    def test_seed_refit_mode_and_whole_wrapper_tampering_reject(self):
        for defect in ('mode','extra','nested','attempt','job'):
            queue,seed,index,value,attempt=fixture();candidates=m.validate_index(index,queue)
            if defect=='mode':value['mode']='ONE_NEW_HISTORICAL_CUTOFF_FIT'
            if defect=='extra':value['identity_upgraded']=True
            if defect=='nested':value['original_single_fit_wrapper']=deepcopy(seed);value['original_single_fit_wrapper']['fit_performed']=False
            if defect=='attempt':attempt['job_id']='wrong'
            if defect=='job':value['result']['job_id']='wrong'
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_task(value,attempt,queue=queue,index=index,candidates=candidates,seed=seed)

    def test_duplicate_complete_bool_and_missing_finalization_reject(self):
        for defect in ('duplicate','complete','bool','final'):
            queue,seed,index,value,attempt=fixture()
            if defect=='duplicate':index['completed']*=2
            if defect=='complete':index['status']='COMPLETE'
            if defect=='bool':index['finalization']['completed']=True
            if defect=='final':index['finalization']=None
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(index,queue)


if __name__=='__main__':unittest.main()
