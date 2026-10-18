import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_ndx_base_window_snapshot_research import fixture
from scripts import ndx_base_window_snapshot_runner_research as runner


def prepared(directory):
    args,_,_=fixture(directory)
    path=Path(args['manifest_path']);manifest=json.loads(path.read_bytes())
    manifest['source_hashes'][str(runner.SELF)]=runner.LOADED
    raw=json.dumps(manifest,sort_keys=True).encode();path.write_bytes(raw)
    return dict(manifest_path=path,manifest_sha256=hashlib.sha256(raw).hexdigest(),output=Path(directory)/'outputs')


class RunnerTests(unittest.TestCase):
    def test_later_probe_provenance_loaded_before_earlier_computed_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            args=prepared(directory);path=Path(args['manifest_path']);manifest=json.loads(path.read_bytes())
            late=dict(manifest['tasks'][0],new_job_id='later-probe');manifest['tasks'].append(late)
            raw=json.dumps(manifest,sort_keys=True).encode();path.write_bytes(raw);args['manifest_sha256']=hashlib.sha256(raw).hexdigest()
            snapshot=runner.core.begin_snapshot(manifest_path=path,manifest_sha256=args['manifest_sha256'])
            value=runner.core.evaluate_task(snapshot,'later-probe');state=runner.core._state(snapshot)
            probe=dict(schema='ndx_base_window_delta_probe_v1',selected=dict(new_job_id='later-probe',parent_task=late['task']),
                result=value['result'],numerical_input_digests=value['numerical_input_digests'])
            # A source-bound legacy-style result has no dependency on its new import manifest.
            probe['result']['source_hashes'].pop(str(path.resolve()))
            probe_path=Path(directory)/'late_probe.json';probe_raw=json.dumps(probe,sort_keys=True).encode();probe_path.write_bytes(probe_raw)
            imported=dict(path=str(probe_path),sha256=hashlib.sha256(probe_raw).hexdigest())
            completed=runner.run(**args,max_new_tasks=1,probes=[imported])
            resumed=runner.run(**args,max_new_tasks=0,resume_index=completed['path'],resume_index_sha256=completed['sha256'])
            self.assertEqual((resumed['completed'],resumed['new_tasks'],resumed['status']),(2,0,'COMPLETE'))

    def test_explicit_zero_then_one_and_external_resume_no_recompute(self):
        with tempfile.TemporaryDirectory() as directory:
            args=prepared(directory)
            empty=runner.run(**args,max_new_tasks=0)
            self.assertEqual((empty['completed'],empty['new_tasks'],empty['status']),(0,0,'PARTIAL'))
            one=runner.run(**args,max_new_tasks=1,resume_index=empty['path'],resume_index_sha256=empty['sha256'])
            self.assertEqual((one['completed'],one['new_tasks'],one['status']),(1,1,'COMPLETE'))
            again=runner.run(**args,max_new_tasks=1,resume_index=one['path'],resume_index_sha256=one['sha256'])
            self.assertEqual((again['completed'],again['new_tasks'],again['status']),(1,0,'COMPLETE'))

    def test_external_index_tamper_and_unindexed_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args=prepared(directory);one=runner.run(**args,max_new_tasks=1)
            with self.assertRaisesRegex(ValueError,'Unindexed task'):
                runner.run(**args,max_new_tasks=1)
            Path(one['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'External artifact SHA'):
                runner.run(**args,max_new_tasks=0,resume_index=one['path'],resume_index_sha256=one['sha256'])

    def test_boolean_budget_and_missing_runner_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args=prepared(directory)
            with self.assertRaises(ValueError):runner.run(**args,max_new_tasks=True)
            path=Path(args['manifest_path']);value=json.loads(path.read_bytes());value['source_hashes'].pop(str(runner.SELF))
            raw=json.dumps(value).encode();path.write_bytes(raw);args['manifest_sha256']=hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError,'Runner source missing'):runner.run(**args,max_new_tasks=0)
