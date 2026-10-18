from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_cutoff_snapshot_independent_readback_v2_20260919 as m
from test_ndx_cutoff_snapshot_independent_readback_20260919 import fixture


class Tests(unittest.TestCase):
    def nonseed(self):
        queue,seed,index,value,attempt=fixture()
        candidate=next(c for c in queue['candidates'] if c['task']['job_id']!=seed['job_id'])
        job=candidate['task']['job_id'];mode='ONE_NEW_HISTORICAL_CUTOFF_FIT'
        value.pop('seed');value.pop('original_single_fit_wrapper');value.update(job_id=job,mode=mode)
        value['result'].update(job_id=job,candidate=deepcopy(candidate),refit=None)
        attempt.update(job_id=job,mode=mode)
        return value,attempt,dict(queue=queue,index=index,candidates=m.previous.validate_index(index,queue),seed=seed)

    def test_previously_accepted_success_without_fit_now_rejected(self):
        value,attempt,kwargs=self.nonseed()
        self.assertIsNone(m.previous.validate_task(value,attempt,**kwargs)['refit'])
        with self.assertRaises(ValueError):m.validate_task(value,attempt,**kwargs)

    def test_failure_dict_and_missing_seed_reject(self):
        value,attempt,kwargs=self.nonseed();result=value['result']
        result.update(status='FIT_ERROR_NOT_ECONOMIC_INFEASIBILITY',error='synthetic',error_type='ValueError',refit={})
        result.pop('independently_recomputed_five_checks')
        with self.assertRaises(ValueError):m.validate_task(value,attempt,**kwargs)
        queue,seed,index,_,_=fixture();index['completed']=[];index['finalization']['completed']=0
        m.previous.validate_index(index,queue)
        with self.assertRaises(ValueError):m.validate_index(index,queue)

    def test_private_binding_uses_strict_validator_without_global_patch(self):
        old=m.previous.validate_task
        def probe(index_path,index_sha256):
            value,attempt,kwargs=index_path
            return validate_task(value,attempt,**kwargs)
        with patch.object(m.previous,'build',probe):
            with self.assertRaisesRegex(ValueError,'Successful status requires'):
                m.build(self.nonseed(),'unused')
        self.assertIs(m.previous.validate_task,old)
        queue,seed,index,value,attempt=fixture()
        self.assertEqual(m.validate_task(value,attempt,queue=queue,index=index,candidates=m.validate_index(index,queue),seed=seed)['job_id'],m.SEED_JOB)


if __name__=='__main__':unittest.main()
