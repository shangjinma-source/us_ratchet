import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_joint_weight_progress_v3 as progress
from backtest import ndx_joint_weight_runner as old_runner
from test_ndx_joint_weight_runner import prepared


class ProgressV3Tests(unittest.TestCase):
    def test_v3_scope_partial_counts_and_wrong_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tasks, inputs = prepared()
            child = tasks[0]['child_manifest_sha256']
            coordinate = {key: tasks[0][key] for key in ('source_batch', 'universe_track', 'selection_date',
                          'decision_data_end', 'holding_count', 'child_manifest_sha256')}
            plan = dict(plans=[dict(tasks=tasks, coordinate=coordinate, child_sha256=child)],
                        planned=2, experiment_sha256='a' * 64)
            dependencies = progress.batch.dependency_hashes()
            bundle = dict(manifest_sha256='f' * 64, frozen={})
            namespace = progress.batch.namespace_hash(plan['experiment_sha256'], bundle['manifest_sha256'], dependencies)
            destination = root / 'batch' / namespace
            destination.mkdir(parents=True)
            versioned = dict(plan=plan, frozen_bundle=bundle, dependencies=dependencies,
                             namespace_sha256=namespace, capture_destination=destination)
            runtime = dict(python=old_runner.platform.python_version(), numpy=old_runner.np.__version__,
                           pandas=old_runner.pd.__version__, scipy=old_runner.scipy.__version__)
            evidence = dict(experiment_sha256=plan['experiment_sha256'],
                            cli_sha256=dependencies['scripts/ndx_joint_weight_batch_v3.py'],
                            loader_provenance=dict(frozen_input_manifest_sha256=bundle['manifest_sha256'],
                                v3_batch_dependency_sources=dependencies, old_results_reused=False))
            capture = dict(schema='ndx_joint_weight_batch_capture_v1', experiment_sha256=plan['experiment_sha256'],
                           cli_sha256=evidence['cli_sha256'], tasks=tasks,
                           prepared_inputs={k: old_runner._panel_context(v) for k, v in inputs.items()},
                           source_evidence=old_runner._normalize(evidence),
                           numerical_sources=progress.runner.source_hashes(), runtime=runtime, panel_metadata={})
            capture['capture_sha256'] = old_runner._sha(capture)
            old_runner._publish(destination / (child + '.json'), capture)
            context = dict(schema='ndx_joint_weight_checkpoint_v1', tasks=tasks,
                           prepared_inputs=capture['prepared_inputs'], source_evidence=capture['source_evidence'],
                           numerical_sources=capture['numerical_sources'], runtime=runtime)
            digest = old_runner._sha(context)
            directory = root / 'v3_runs' / digest
            directory.mkdir(parents=True)
            old_runner._publish(directory / 'context.json', context)
            result = {f: 0. for f in progress.original.RETURN_FIELDS + progress.original.DRAWDOWN_FIELDS}
            result.update(tickers=tasks[0]['tickers'], weight_spec=tasks[0]['weight_spec'], holding_count=tasks[0]['holding_count'],
                          declared_constraints_passed=False, whole_lot_executable_all_windows=False,
                          constraint_failure_reasons='TEST_NEGATIVE')
            checkpoint = dict(context_sha256=digest, task=tasks[0], status='EVALUATED', result=old_runner._normalize(result))
            checkpoint['checkpoint_sha256'] = old_runner._sha(checkpoint)
            old_runner._publish(directory / (tasks[0]['job_id'] + '.json'), checkpoint)
            original_globals = progress.original.inspect_plan.__globals__['runner']
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(progress.batch, 'BATCH_ROOT', root / 'batch'), patch.object(progress.runner, 'CHECKPOINT_ROOT', root / 'v3_runs'):
                report = progress.inspect_versioned_plan(versioned)
                self.assertEqual((report['planned'], report['completed'], report['pending']), (2, 1, 1))
                self.assertFalse(report['old_results_reused'])
                self.assertIs(progress.original.inspect_plan.__globals__['runner'], original_globals)
                self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
                # Only a v1 location exists: no v3 completion can be inferred.
                with patch.object(progress.runner, 'CHECKPOINT_ROOT', root / 'empty_v3'):
                    self.assertEqual(progress.inspect_versioned_plan(versioned)['completed'], 0)
                path = destination / (child + '.json')
                changed = json.loads(path.read_bytes())
                changed['source_evidence']['mapping']['loader_provenance']['mapping']['frozen_input_manifest_sha256'] = 'b' * 64
                changed.pop('capture_sha256')
                changed['capture_sha256'] = old_runner._sha(changed)
                path.write_bytes(old_runner._json_bytes(changed))
                with self.assertRaisesRegex(ValueError, 'provenance binding'):
                    progress.inspect_versioned_plan(versioned)


if __name__ == '__main__':
    unittest.main()


