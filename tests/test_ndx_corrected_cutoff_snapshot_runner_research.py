import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_cutoff_snapshot_runner_research as m
from test_ndx_corrected_cutoff_snapshot_research import snapshot_fixture


class Tests(unittest.TestCase):
    def test_zero_budget_then_one_then_resume_without_refitting(self):
        with tempfile.TemporaryDirectory() as folder:
            queue_path=Path(folder)/'queue.json';s=m.core.state(snapshot_fixture());queue_path.write_text(json.dumps(s['queue']))
            sha=hashlib.sha256(queue_path.read_bytes()).hexdigest();out=Path(folder)/'tasks';ref=dict(path=str(queue_path),sha256=sha)
            def begin(**kwargs):
                return snapshot_fixture(reference=ref)
            with patch.object(m.core,'begin',side_effect=begin),patch.object(m.core.adapter.archive,'load_contract',return_value={}),patch.object(m.core.adapter.archive,'verify_expected_sources',return_value={'test_partition':True}):
                zero=m.run(queue_path=queue_path,queue_sha256=sha,output=out,max_new_tasks=0)
                self.assertEqual(zero['completed'],0)
                one=m.run(queue_path=queue_path,queue_sha256=sha,output=out,max_new_tasks=1,resume_index=zero['path'],resume_index_sha256=zero['sha256'])
                self.assertEqual(one['completed'],1)
                with patch.object(m.core.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=AssertionError('Never restore by refitting')):
                    resumed=m.run(queue_path=queue_path,queue_sha256=sha,output=out,max_new_tasks=0,resume_index=one['path'],resume_index_sha256=one['sha256'])
                self.assertEqual(resumed['completed'],1);self.assertEqual(resumed['new_fit_attempts'],0)

    def test_any_remote_orphan_rejects_before_snapshot_or_fit(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=Path(folder)/'queue.json';queue.write_text(json.dumps(dict(candidate_count=2,candidates=[dict(task=dict(job_id=j)) for j in ('a','b')])));sha=hashlib.sha256(queue.read_bytes()).hexdigest()
            out=Path(folder)/'tasks';out.mkdir();(out/'b.started.json').write_text('{}')
            with patch.object(m.core,'begin') as begin:
                with self.assertRaises(ValueError):m.run(queue_path=queue,queue_sha256=sha,output=out,max_new_tasks=1)
                begin.assert_not_called()

    def test_budget_and_unindexed_extra_result_reject(self):
        for count in (-1,101,True):
            with self.assertRaises(ValueError):m.run(queue_path='missing',queue_sha256='x',output='none',max_new_tasks=count)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);(out/'unindexed.json').write_text('{}')
            with self.assertRaises(ValueError):m.reconcile(out,[])


if __name__=='__main__':unittest.main()
