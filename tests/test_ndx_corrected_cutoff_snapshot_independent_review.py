import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_cutoff_snapshot_runner_research as runner
from test_ndx_corrected_cutoff_snapshot_research import snapshot_fixture


class Tests(unittest.TestCase):
    def test_completed_memory_cannot_be_erased_to_repeat_fit(self):
        snapshot=snapshot_fixture();runner.core.evaluate(snapshot,'a')
        runner.core.state(snapshot)['records'].pop('a')
        with patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=RuntimeError('count only')) as fit:
            with self.assertRaises(ValueError):runner.core.evaluate(snapshot,'a')
            fit.assert_not_called()

    def test_source_denominators_cannot_be_shortened(self):
        for field in ('sources','small_sources','additional'):
            snapshot=snapshot_fixture();s=runner.core.state(snapshot)
            if field=='additional':s[field]['unknown']='0'*64
            else:s[field].clear()
            with self.subTest(field=field),patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(ValueError):runner.core.evaluate(snapshot,'a')
                fit.assert_not_called()

    def test_restore_rejects_extra_whole_wrapper_metadata(self):
        original=snapshot_fixture();value=runner.core.evaluate(original,'a')
        value['unreviewed_scope_upgrade']=True
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'result.json';path.write_text(json.dumps(value));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            target=snapshot_fixture(reference=runner.core.state(original)['reference'])
            with patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                with self.assertRaises(ValueError):runner.core.restore(target,path,sha)
                fit.assert_not_called()

    def test_seed_presence_cannot_be_erased_to_repeat_fit(self):
        snapshot=snapshot_fixture();s=runner.core.state(snapshot)
        s['seed']={'path':'external_seed','sha256':'hard'};s['seed_value']={'job_id':'a'}
        s['seed_reference_digest']=runner.core.adapter.digest(s['seed'])
        s['seed_wrapper_digest']=runner.core.adapter.digest(s['seed_value'])
        s['seed']=None
        with patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=RuntimeError('count only')) as fit:
            with self.assertRaises(ValueError):runner.core.evaluate(snapshot,'a')
            fit.assert_not_called()

    def test_marker_precedes_fit_and_interruption_cannot_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=Path(folder)/'queue.json';output=Path(folder)/'tasks'
            original=runner.core.state(snapshot_fixture())['queue'];queue.write_text(json.dumps(original))
            sha=hashlib.sha256(queue.read_bytes()).hexdigest()
            def begin(**kwargs):
                return snapshot_fixture(reference={'path':str(queue),'sha256':sha})
            def interrupted(**kwargs):
                self.assertTrue((output/'a.started.json').exists())
                self.assertFalse((output/'a.json').exists())
                raise KeyboardInterrupt('synthetic interruption after durable marker')
            with patch.object(runner.core,'begin',side_effect=begin),patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights',side_effect=interrupted) as fit:
                with self.assertRaises(KeyboardInterrupt):runner.run(queue_path=queue,queue_sha256=sha,output=output,max_new_tasks=1)
                fit.assert_called_once()
            with patch.object(runner.core,'begin') as prepare:
                with self.assertRaises(ValueError):runner.run(queue_path=queue,queue_sha256=sha,output=output,max_new_tasks=1)
                prepare.assert_not_called()

    def test_zero_budget_never_calls_fitter(self):
        with tempfile.TemporaryDirectory() as folder:
            queue=Path(folder)/'queue.json';queue.write_text(json.dumps(runner.core.state(snapshot_fixture())['queue']))
            sha=hashlib.sha256(queue.read_bytes()).hexdigest()
            with patch.object(runner.core,'begin',side_effect=lambda **kwargs:snapshot_fixture()),patch.object(runner.core.adapter.archive,'load_contract',return_value={}),patch.object(runner.core.adapter.archive,'verify_expected_sources',return_value={}),patch.object(runner.core.adapter.fitter,'refit_dynamic_cutoff_weights') as fit:
                result=runner.run(queue_path=queue,queue_sha256=sha,output=Path(folder)/'tasks',max_new_tasks=0)
                self.assertEqual(result['new_fit_attempts'],0);fit.assert_not_called()


if __name__=='__main__':unittest.main()
