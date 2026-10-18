import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_frontier_single_refit_archive_research as m


class Tests(unittest.TestCase):
    def test_changed_started_marker_rejected_before_result_publication(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m.adapter,'verify'):
            args=self.setup_queue(folder);target=Path(folder)/'result.json'
            def corrupt(**kwargs):
                Path(str(target)+'.started.json').write_text('{}')
                return {'status':'FITTED_FIVE_RISKS_PASSED'}
            with patch.object(m.adapter,'run_one',side_effect=corrupt):
                with self.assertRaises(ValueError):m.run(**args,execute=True,output=target)
            self.assertFalse(target.exists());self.assertTrue(Path(str(target)+'.started.json').exists())

    def setup_queue(self,folder):
        queue=dict(schema='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_QUEUE_V1',fit_performed=False,
            candidates=[dict(task=dict(job_id='one'))],candidate_count=1,historical_cutoff='2023-03-31')
        path=Path(folder)/'queue.json';path.write_text(json.dumps(queue),encoding='utf8')
        return dict(queue_path=path,queue_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),job_id='one')

    def test_default_no_fit_and_exact_one_explicit_execution(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m.adapter,'verify'),patch.object(m.adapter,'run_one',return_value={'status':'FITTED_FIVE_RISKS_FAILED'}) as fit:
            args=self.setup_queue(folder);target=Path(folder)/'result.json'
            self.assertFalse(m.run(**args)['fit_performed']);fit.assert_not_called()
            saved=m.run(**args,execute=True,output=target)
            self.assertEqual(saved['fit_attempts'],1);self.assertEqual(fit.call_count,1)
            body=json.loads(target.read_bytes());self.assertEqual(body['queue']['sha256'],args['queue_sha256'])
            with self.assertRaises(FileExistsError):m.run(**args,execute=True,output=target)
            self.assertEqual(fit.call_count,1)

    def test_failed_attempt_cannot_auto_refit_and_source_changed_rejects(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(m.adapter,'verify'),patch.object(m.adapter,'run_one',side_effect=RuntimeError('interrupted')) as fit:
            args=self.setup_queue(folder);target=Path(folder)/'result.json'
            with self.assertRaises(RuntimeError):m.run(**args,execute=True,output=target)
            self.assertFalse(target.exists());self.assertTrue(Path(str(target)+'.started.json').exists())
            with self.assertRaises(FileExistsError):m.run(**args,execute=True,output=target)
            self.assertEqual(fit.call_count,1)
            args['queue_path'].write_text('{}')
            with self.assertRaises(ValueError):m.run(**args)

    def test_atomic_failure_no_partial_official_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.json'
            with patch.object(m.os,'link',side_effect=OSError('before link')):
                with self.assertRaises(OSError):m.publish(path,{'x':1})
            self.assertFalse(path.exists());self.assertEqual(list(Path(folder).iterdir()),[])


if __name__=='__main__':unittest.main()
