from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_selected_delta_drift_snapshot_research as fixtures
from scripts import ndx_selected_delta_drift_budget_runner_research as runner
core=runner.core


class BudgetRunnerTests(unittest.TestCase):
    def test_bounded_continuation_reuses_seed_then_exactly_one_remaining_fit(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory)
            path,sha,manifest,params,_,_=fixtures.SelectedSnapshotTests().setup_fixture(folder,stack)
            stack.enter_context(patch.object(runner,'load_verified_manifest',return_value=manifest))
            stack.enter_context(patch.object(runner,'RUN_SOURCES',{}))
            with patch.object(core.selected.trace,'evaluate_with_window_trace',wraps=core.selected.trace.evaluate_with_window_trace) as traced:
                first=runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=0)
                self.assertEqual(traced.call_count,0)
                second=runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=2,
                    resume_index=first['path'],resume_index_sha256=first['sha256'])
                self.assertEqual((traced.call_count,second['completed'],second['new_evaluations']),(1,2,1))
                final=core.read(second['path'],second['sha256'])['finalization']
                self.assertEqual(final['additional_provenance_hashes'][first['path']],first['sha256'])
                self.assertFalse(final['historical_full_source_closure_verified'])

    def test_budget_and_hard_manifest_reject_before_io(self):
        for budget in (-1,True,1001,1.0):
            with self.assertRaisesRegex(ValueError,'budget'):
                runner.run(manifest_path='unused',manifest_sha256='unused',output='unused',max_new_tasks=budget)
        with self.assertRaisesRegex(ValueError,'Hard actually tested'):
            runner.load_verified_manifest(runner.MANIFEST,'0'*64)

    def test_new_runner_source_drift_prevents_successful_finalization(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory)
            path,sha,manifest,params,_,_=fixtures.SelectedSnapshotTests().setup_fixture(folder,stack)
            source=folder/'batch_source.py';source.write_text('original')
            stack.enter_context(patch.object(runner,'load_verified_manifest',return_value=manifest))
            stack.enter_context(patch.object(runner,'RUN_SOURCES',{str(source):core.drift.file_sha(source)}))
            original=core.evaluate
            def mutate(*args):
                value=original(*args);source.write_text('changed');return value
            with patch.object(core,'evaluate',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'External provenance changed'):
                    runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=2)


if __name__=='__main__':unittest.main()
