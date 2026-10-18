from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_base_three_cell_window_delta_research as runner


class BaseDeltaRunnerTests(unittest.TestCase):
    def test_interrupted_staging_never_publishes_partial_target(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);target=folder/'artifact.json'
            abandoned=folder/'.publishing-old-process.tmp';abandoned.write_bytes(b'partial')
            with patch.object(runner.os,'link',side_effect=OSError('interrupted before atomic publication')):
                with self.assertRaises(OSError):runner.publish(target,{'complete':True})
            self.assertFalse(target.exists())
            self.assertEqual(list(folder.glob('.publishing-*.tmp')),[abandoned])
            published=runner.publish(target,{'complete':True})
            self.assertEqual(runner.read(target,published['sha256']),{'complete':True})
            self.assertEqual(abandoned.read_bytes(),b'partial')

    def test_immutable_index_and_external_sha_reject_modified_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            task={'new_job_id':'new','task':{'job_id':'old'}}
            day={'tasks':[task]};context={'path':'context','sha256':'expected'}
            value=dict(schema='ndx_base_window_delta_checkpoint_v1',new_job_id='new',original=task,
                context=context,status='EVALUATED_ORIGINAL_BASE_WINDOW_DELTA',promotion_allowed=False,
                result={'value':.1})
            path=Path(directory)/'task.json';entry=runner.publish(path,value)
            self.assertEqual(runner.validate_resume_entry(entry,day,context),'new')
            value['result']['value']=.2
            with self.assertRaises(ValueError):runner.publish(path,value)
            path.write_text('{}')
            with self.assertRaises(ValueError):runner.validate_resume_entry(entry,day,context)

    def test_unknown_task_rejected_before_numerical_work(self):
        with self.assertRaises(ValueError):runner.execute_task({'day':{'tasks':[]}}, {'new_job_id':'unexpected'})

    def test_explicit_budget_required_before_preparation(self):
        for value in (None,0,-1,True):
            with self.assertRaises(ValueError):runner.run_date({},'2023-04-03',plan_path='unused',plan_sha256='unused',max_new_tasks=value)
