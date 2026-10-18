import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_ndx_joint_weight_delta import plan as delta_plan,coordinate
from test_ndx_joint_weight_evaluation import fixture
from backtest import ndx_joint_weight_runner as runner

spec=importlib.util.spec_from_file_location('progress',Path(__file__).resolve().parents[1]/'scripts/ndx_joint_weight_progress.py')
progress=importlib.util.module_from_spec(spec);spec.loader.exec_module(progress)


class ProgressTests(unittest.TestCase):
    def test_partial_read_only_counts_pending_separately_and_retains_preference(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);batch_root=root/'batch';checkpoint_root=root/'checkpoints'
            first=delta_plan()['tasks']; other=coordinate();other['child_manifest_sha256']='b'*64
            second=delta_plan(scope=other)['tasks']
            plans=[dict(tasks=first,coordinate=coordinate(),child_sha256='a'*64),
                   dict(tasks=second,coordinate=other,child_sha256='b'*64)]
            plan=dict(plans=plans,planned=4,experiment_sha256='c'*64)
            cli_hash='d'*64
            destination=batch_root/runner._sha(dict(experiment_sha256='c'*64,cli_sha256=cli_hash))
            destination.mkdir(parents=True)
            prepared=fixture()[1]
            evidence=dict(experiment_sha256='c'*64,cli_sha256=cli_hash,loader_provenance={})
            runtime=dict(python=runner.platform.python_version(),numpy=runner.np.__version__,
                pandas=runner.pd.__version__,scipy=runner.scipy.__version__)
            capture=dict(schema='ndx_joint_weight_batch_capture_v1',experiment_sha256='c'*64,cli_sha256=cli_hash,
                tasks=first,prepared_inputs={k:runner._panel_context(v) for k,v in prepared.items()},
                source_evidence=runner._normalize(evidence),numerical_sources=runner._source_hashes(),runtime=runtime,panel_metadata={})
            capture['capture_sha256']=runner._sha(capture)
            runner._publish(destination/('a'*64+'.json'),capture)
            context=dict(schema='ndx_joint_weight_checkpoint_v1',tasks=first,
                prepared_inputs=capture['prepared_inputs'],source_evidence=capture['source_evidence'],
                numerical_sources=capture['numerical_sources'],runtime=runtime)
            digest=runner._sha(context);directory=checkpoint_root/digest;directory.mkdir(parents=True)
            runner._publish(directory/'context.json',context)
            result={f:0. for f in progress.RETURN_FIELDS+progress.DRAWDOWN_FIELDS}
            result.update(declared_constraints_passed=False,whole_lot_executable_all_windows=False)
            result['constraint_failure_reasons']='WHOLE_LOT_EXECUTABILITY_FAILED'
            result.update(tickers=first[0]['tickers'],weight_spec=first[0]['weight_spec'],holding_count=first[0]['holding_count'])
            checkpoint=dict(context_sha256=digest,task=first[0],status='EVALUATED',result=runner._normalize(result))
            checkpoint['checkpoint_sha256']=runner._sha(checkpoint)
            runner._publish(directory/(first[0]['job_id']+'.json'),checkpoint)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with patch.object(progress.batch,'BATCH_ROOT',batch_root),patch.object(runner,'CHECKPOINT_ROOT',checkpoint_root),patch.object(
                progress.batch,'prepare_joint_weight_history_inputs',side_effect=AssertionError('must not prepare')):
                report=progress.inspect_plan(plan,cli_hash=cli_hash)
            self.assertEqual((report['planned'],report['completed'],report['pending']),(4,1,3))
            self.assertEqual(report['fractional_joint_noninferior'],1)
            self.assertEqual(report['declared_and_eight_component_noninferior'],0)
            self.assertEqual([r['status'] for r in report['coordinates']],['PARTIAL','NOT_VISITED'])
            self.assertEqual(len(report['user_preference_tasks']),4)
            self.assertFalse(report['missing_results_are_economic_failures'])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(len(report['evaluated_results'][0]['fractional_metrics']),8)
            self.assertEqual(report['evaluated_results'][0]['constraint_failure_reasons'],'WHOLE_LOT_EXECUTABILITY_FAILED')
            checkpoint_path=directory/(first[0]['job_id']+'.json')
            original_checkpoint=checkpoint_path.read_bytes()
            polluted=dict(checkpoint)
            polluted['result']=runner._normalize(dict(result,declared_constraints_passed=1))
            polluted.pop('checkpoint_sha256')
            polluted['checkpoint_sha256']=runner._sha(polluted)
            checkpoint_path.write_bytes(runner._json_bytes(polluted))
            with patch.object(progress.batch,'BATCH_ROOT',batch_root),patch.object(runner,'CHECKPOINT_ROOT',checkpoint_root):
                with self.assertRaisesRegex(ValueError,'Invalid result boolean'):
                    progress.inspect_plan(plan,cli_hash=cli_hash)
            checkpoint_path.write_bytes(original_checkpoint)
            capture_path=destination/('a'*64+'.json')
            original_capture=capture_path.read_bytes()
            changed=dict(capture,cli_sha256='e'*64)
            changed.pop('capture_sha256')
            changed['capture_sha256']=runner._sha(changed)
            capture_path.write_bytes(runner._json_bytes(changed))
            with patch.object(progress.batch,'BATCH_ROOT',batch_root),patch.object(runner,'CHECKPOINT_ROOT',checkpoint_root):
                with self.assertRaisesRegex(ValueError,'Capture source/task/runtime binding'):
                    progress.inspect_plan(plan,cli_hash=cli_hash)
            capture_path.write_bytes(original_capture)
            (directory/(first[0]['job_id']+'.json')).write_text('{}')
            with patch.object(progress.batch,'BATCH_ROOT',batch_root),patch.object(runner,'CHECKPOINT_ROOT',checkpoint_root):
                with self.assertRaisesRegex(ValueError,'Checkpoint binding'):
                    progress.inspect_plan(plan,cli_hash=cli_hash)

    def test_snapshot_detects_concurrent_directory_growth(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);snapshot=progress.Snapshot();snapshot.directory(root)
            (root/'new.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Directory changed'):
                snapshot.verify()


if __name__=='__main__':
    unittest.main()
