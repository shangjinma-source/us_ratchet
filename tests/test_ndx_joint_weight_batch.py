import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from test_ndx_joint_weight_delta import fixture as candidates_fixture
from test_ndx_joint_weight_evaluation import fixture as inputs_fixture
from backtest.ndx_two_stage_joint_coverage import select_joint_coverage_security_sets

spec=importlib.util.spec_from_file_location('joint_batch',Path(__file__).resolve().parents[1]/'scripts/ndx_joint_weight_batch.py')
batch=importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)


class BatchTests(unittest.TestCase):
    def test_complete_plan_checks_real_selector_and_coverage_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def put(name,value):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                raw=value.encode() if isinstance(value,str) else json.dumps(value).encode()
                path.write_bytes(raw)
                return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
            frame=candidates_fixture()
            selected=select_joint_coverage_security_sets(frame,selection_date='2024-05-01',decision_data_end='2024-04-30')
            candidates=put('candidates.csv',frame.to_csv(index=False))
            old=put('old.csv',selected['legacy_control'].to_csv(index=False))
            child=put('batch/runs/run/jobs/strict/2024-05-01/k4/shard0000/manifest.json',dict(
                selection_date='2024-05-01',holding_count=4,universe_track='strict',training_end='2024-04-30',
                artifacts={'candidates':candidates,'second_stage_shortlist':old},
                search_audit={'first_stage_security_sets':17,'second_stage_security_sets':16}))
            original=put('original.json',{'rows':[dict(date='2024-05-01',k=4,candidate_rows=17,
                path=candidates['path'],sha256=candidates['sha256'],child_manifest_path=child['path'],child_manifest_sha256=child['sha256'])]})
            coverage=put('coverage.json',dict(base_original_screen_sha256=original['sha256'],additional_model_evaluations=2,
                rows=[dict(date='2024-05-01',k=4,audit=selected['audit'],
                    selected_sha256=batch._digest(selected['selected'].to_dict('records')),
                    added_sets_sha256=batch._digest(['AMAT;AVGO;CDNS;GOOG']),additional_model_evaluations=2)]))
            experiment=put('experiment.json',dict(schema=batch.SCHEMA,original_screen=original,coverage_report=coverage,
                evaluation_contract=inputs_fixture()[1]['contract'],training_lookback_days=504,
                minimum_price_rows_before_selection=252,allow_revised_return_data=True,per_frontier_limit=16,
                second_stage_weight_specs=list(batch.SUPPORTED_WEIGHT_SPECS)))
            with patch.object(batch,'prepare_joint_weight_history_inputs',side_effect=AssertionError('plan must not prepare')):
                plan=batch.build_plan(experiment['path'])
            self.assertEqual(plan['planned'],2)
            self.assertEqual(len(plan['plans']),1)
            Path(old['path']).write_text('corrupted')
            with self.assertRaisesRegex(ValueError,'Unrecoverable source'):
                batch.build_plan(experiment['path'])

    def test_budget_preserves_global_denominator_and_not_visited(self):
        plans=[dict(tasks=[{},{}],coordinate={'k':k},child_sha256=str(k)) for k in range(3)]
        plan=dict(plans=plans,planned=6,experiment={},experiment_sha256='a'*64)
        with patch.object(batch,'_captured_inputs',return_value=({},{})),patch.object(batch,'run_joint_weight_tasks',
            return_value=dict(attempted=1,completed=1,resumed=0,status='PARTIAL')) as runner:
            result=batch.execute_plan(plan,max_new_evaluations=1,destination=Path('.'),cli_hash='b'*64)
        self.assertEqual(result['planned'],6)
        self.assertEqual(result['attempted'],1)
        self.assertEqual([r['status'] for r in result['coordinates']],['PARTIAL','NOT_VISITED','NOT_VISITED'])
        self.assertEqual(runner.call_count,1)

    def test_first_failure_capture_resumes_without_repreparing_changed_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            prepared=inputs_fixture()[1]
            prepared['provenance']={'sources':[{'observed_sha256':'a'*64}]}
            coordinate=dict(child_path='unused',child_sha256='c'*64,tasks=[{'job_id':'one'}],coordinate={'k':4})
            experiment=dict(evaluation_contract=prepared['contract'],training_lookback_days=504,
                minimum_price_rows_before_selection=252,allow_revised_return_data=True)
            plan=dict(plans=[coordinate],planned=1,experiment=experiment,experiment_sha256='a'*64)
            with patch.object(batch,'prepare_joint_weight_history_inputs',return_value=prepared),patch.object(
                batch,'run_joint_weight_tasks',side_effect=RuntimeError('first evaluation failed')):
                with self.assertRaisesRegex(RuntimeError,'first evaluation failed'):
                    batch.execute_plan(plan,max_new_evaluations=1,destination=Path(folder),cli_hash='b'*64)
            with patch.object(batch,'prepare_joint_weight_history_inputs',side_effect=AssertionError('cache changed')),patch.object(
                batch,'run_joint_weight_tasks',return_value=dict(attempted=1,completed=1,resumed=0,status='COMPLETE')) as runner:
                result=batch.execute_plan(plan,max_new_evaluations=1,destination=Path(folder),cli_hash='b'*64)
            self.assertEqual(result['status'],'COMPLETE')
            recovered=runner.call_args.kwargs['prepared_inputs']
            for key in ('universe','returns','nominal_prices'):
                pd.testing.assert_frame_equal(recovered[key],prepared[key],check_exact=True)
            pd.testing.assert_series_equal(recovered['target_returns'],prepared['target_returns'],check_exact=True)
            self.assertEqual(runner.call_args.kwargs['source_evidence']['loader_provenance'],prepared['provenance'])
            capture_path = Path(folder) / ('c'*64 + '.json')
            original_capture = capture_path.read_bytes()
            captured = json.loads(original_capture)
            captured['source_evidence']['mapping']['loader_provenance']['mapping']['sources']['sequence_type'] = 'INVALID'
            captured.pop('capture_sha256')
            captured['capture_sha256'] = batch._sha(captured)
            capture_path.write_bytes(batch._json_bytes(captured))
            with self.assertRaisesRegex(ValueError, 'source evidence canonical'):
                batch._captured_inputs(Path(folder),coordinate,experiment,'a'*64,'b'*64)
            capture_path.write_bytes(original_capture)
            with patch.object(batch,'_source_hashes',return_value={'changed':'f'*64}):
                with self.assertRaisesRegex(ValueError,'numerical source/runtime differs'):
                    batch._captured_inputs(Path(folder),coordinate,experiment,'a'*64,'b'*64)


if __name__=='__main__':
    unittest.main()
