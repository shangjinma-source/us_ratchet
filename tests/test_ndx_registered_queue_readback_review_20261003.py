from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_registered_scoring_queue_independent_readback_20261003 as m
import test_ndx_registered_scoring_queue_independent_readback_20261003 as author


class IndependentReview(unittest.TestCase):
    def request(self):
        ids = [m.TASK_ID] + [f'{i:064x}' for i in range(1,9792)]
        queue = dict(logical_jobs=[dict(job_id=i) for i in ids], executable_logical_ordinals=list(range(9792)), shards=[dict(job_ids=ids[i:i+32]) for i in range(0,9792,32)])
        common = dict(context_references={}, context_sha256='a'*64, **m.FALSE)
        start = dict(schema='REGISTERED_SCORING_REQUEST_STARTED_V1', completed_references=[], max_new_shards=0, started_at_utc='2026-10-03T00:00:00+00:00', **common)
        result = dict(schema='REGISTERED_SCORING_REQUEST_RESULT_V1', status='ENGINEERING_BUDGET_STOP', initial_completed_references=[], new_shard_references=[], completed_shard_references=[], unresolved_shard_index=None, unresolved_shard_reference=None, current_shard_terminal_tasks=[], unresolved_task_ids=[], undispatched_new_task_ids=ids[1:], known_external_first_job_count=1, known_external_first_job_id=m.TASK_ID, logical_job_count=19584, source_blocked_job_count=9792, executable_job_count=9792, new_numerical_job_denominator=9791, completed_new_job_count=0, whole_queue_completed=False, error=None, **common)
        return result,start,queue

    def test_stop_requires_actual_stop_evidence_not_status_relabel(self):
        r,s,q=self.request()
        good=m.inspect_request(r,s,q,[])
        self.assertEqual(good['undispatched_count'],9791)
        for error in (None, {}, {'type':'ValueError','message':False,'traceback':'x'}):
            bad=deepcopy(r);bad.update(status='STOPPED',error=error)
            with self.subTest(error=error),self.assertRaises(ValueError):m.inspect_request(bad,s,q,[])
        r.update(status='STOPPED',unresolved_shard_index=0,unresolved_task_ids=[x['job_id'] for x in q['logical_jobs'][1:32]],undispatched_new_task_ids=[x['job_id'] for x in q['logical_jobs'][32:]],error={'type':'OSError','message':'original write failure','traceback':'original'})
        out=m.inspect_request(r,s,q,[])
        self.assertEqual(out['unresolved_count'],31)
        self.assertTrue(out['unresolved_without_result_metadata_only'])
        r['undispatched_new_task_ids'].append(m.TASK_ID)
        with self.assertRaises(ValueError):m.inspect_request(r,s,q,[])

    def test_context_closure_and_shard_recovery_cannot_be_resigned(self):
        kw,args,check,d,refs,start,result=author.shard_fixture()
        for attack in ('claim','descriptor','runtime_count','false'):
            bad=deepcopy(result)
            if attack=='claim':bad['recovery']['tasks'][0]['status']='EXTERNALLY_REFERENCED'
            elif attack=='descriptor':bad['descriptor']['job_ids']=['f'*64]
            elif attack=='runtime_count':bad['registered_executable_job_count']=9792.0
            else:bad['point_in_time_verified']=0
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inspect_shard_metadata(bad,start,d,kw['context_sha256'],refs,check,kw['journal_bytes'])

    def test_consumed_bytes_and_failure_marker_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'result.json';p.write_bytes(b'anchored')
            r=m.ref(p,m.sha(b'anchored'))
            (p.parent/'failure.json').write_bytes(b'original failed attempt')
            with self.assertRaises(ValueError):m.take(r,{})
            with patch.object(m.Path,'read_bytes',side_effect=[b'anchored',b'changed']) as read:
                self.assertEqual(m.take_attempt(r,{}),b'anchored')
                self.assertEqual(read.call_count,1)
            p.write_bytes(b'changed')
            with self.assertRaises(ValueError):m.take_attempt(r,{})


if __name__=='__main__':unittest.main()
