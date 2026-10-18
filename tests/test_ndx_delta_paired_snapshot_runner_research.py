from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_delta_paired_snapshot_research import fixture
from scripts import ndx_delta_paired_snapshot_runner_research as runner


def prepared(directory):
    args,parameters,parent=fixture(directory)
    path=Path(args['manifest_path']);manifest=json.loads(path.read_bytes())
    first=parent['dates'][0]['tasks'][0];second=dict(first,new_job_id='second')
    parent['dates'][0]['tasks'].append(second)
    parent_path=Path(manifest['parent_plan_path']);raw=json.dumps(parent,sort_keys=True).encode();parent_path.write_bytes(raw)
    parent_sha=hashlib.sha256(raw).hexdigest();manifest['parent_plan_sha256']=parent_sha
    manifest['source_hashes'][str(parent_path)]=parent_sha;manifest['tasks'].append(second);manifest['planned']=2
    result=runner.core.sealed.recover_paired_delta(**parameters)
    probe=dict(schema='ndx_delta_three_cell_paired_gap_probe_v2',selected=parent['probe'],plan_path=str(parent_path),plan_sha256=parent_sha,result=result)
    probe_path=Path(directory)/'probe.json';raw=json.dumps(probe).encode();probe_path.write_bytes(raw)
    manifest['completed_probe']=dict(path=str(probe_path),sha256=hashlib.sha256(raw).hexdigest(),new_job_id='synthetic')
    raw=json.dumps(manifest,sort_keys=True).encode();path.write_bytes(raw)
    return dict(manifest_path=path,manifest_sha256=hashlib.sha256(raw).hexdigest(),output=Path(directory)/'outputs'),manifest


class DeltaRunnerTests(unittest.TestCase):
    def test_zero_import_then_one_trace_then_external_resume_without_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            args,manifest=prepared(directory)
            with patch.object(runner,'load_manifest',return_value=manifest):
                with patch.object(runner.core.sealed.trace,'evaluate_with_window_trace') as traced:
                    imported=runner.run(**args,max_new_tasks=0);traced.assert_not_called()
                self.assertEqual((imported['completed'],imported['new_traces'],imported['status']),(1,0,'PARTIAL'))
                finished=runner.run(**args,max_new_tasks=1,resume_index=imported['path'],resume_index_sha256=imported['sha256'])
                self.assertEqual((finished['completed'],finished['new_traces'],finished['status']),(2,1,'COMPLETE'))
                with patch.object(runner.core.sealed.trace,'evaluate_with_window_trace') as traced:
                    resumed=runner.run(**args,max_new_tasks=1,resume_index=finished['path'],resume_index_sha256=finished['sha256']);traced.assert_not_called()
                self.assertEqual((resumed['completed'],resumed['new_traces']),(2,0))

    def test_unindexed_outputs_bad_external_sha_and_boolean_budget_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            args,manifest=prepared(directory)
            with patch.object(runner,'load_manifest',return_value=manifest):
                with self.assertRaises(ValueError):runner.run(**args,max_new_tasks=True)
                imported=runner.run(**args,max_new_tasks=0)
                with self.assertRaisesRegex(ValueError,'Unindexed imported'):runner.run(**args,max_new_tasks=0)
                with self.assertRaisesRegex(ValueError,'External artifact SHA'):
                    runner.run(**args,max_new_tasks=0,resume_index=imported['path'],resume_index_sha256='0'*64)

    def test_tampered_scalar_result_cannot_resume_even_with_new_checkpoint_and_index_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            args,manifest=prepared(directory)
            with patch.object(runner,'load_manifest',return_value=manifest):
                saved=runner.run(**args,max_new_tasks=0)
                index=json.loads(Path(saved['path']).read_bytes());entry=index['completed'][0]
                task_path=Path(entry['path']);task=json.loads(task_path.read_bytes())
                task['result']['result']['paired_return_p50_vs_incumbent']+=.1
                raw=json.dumps(task).encode();task_path.write_bytes(raw);entry['sha256']=hashlib.sha256(raw).hexdigest()
                index_path=Path(directory)/'modified_index.json';raw=json.dumps(index).encode();index_path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError,'Saved paired values'):
                    runner.run(**args,max_new_tasks=0,resume_index=index_path,resume_index_sha256=hashlib.sha256(raw).hexdigest())
