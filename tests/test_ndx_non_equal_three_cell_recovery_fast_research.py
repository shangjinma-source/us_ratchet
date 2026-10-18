from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from scripts import ndx_non_equal_three_cell_recovery_fast_research as batch


class FastRecoveryTests(unittest.TestCase):
    def test_rehashed_forged_metrics_cannot_pass_resume(self):
        expected=dict(task={'job_id':'example'},context_sha256='bound',result={'corrected':{'metrics':{'return_p50':.1}}})
        value=deepcopy(expected);value['content_sha256']=batch.digest(value)
        batch.validate_resume_checkpoint(value,expected)
        value['result']['corrected']['metrics']['return_p50']=.2
        value.pop('content_sha256');value['content_sha256']=batch.digest(value)
        with self.assertRaises(ValueError):batch.validate_resume_checkpoint(value,expected)

    def test_changed_cells_and_outside_bucket_rejected(self):
        prepared={'errors':deepcopy(batch.ERRORS),'selected':[]}
        with self.assertRaises(ValueError):batch.recover_task(prepared,{})
        prepared['errors'][0]['new']+=.1
        with self.assertRaises(ValueError):batch.recover_task(prepared,{})

    def test_create_only_exact_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'artifact.json'
            sha=batch.publish(path,{'value':1})
            self.assertEqual(batch.publish(path,{'value':1}),sha)
            with self.assertRaises(ValueError):batch.publish(path,{'value':2})
