from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_selected_delta_drift_snapshot_research as fixtures
from backtest import ndx_selected_archive_snapshot_research as core
from scripts import ndx_selected_archive_snapshot_runner_research as runner


class ArchiveSnapshotTests(unittest.TestCase):
    def fixture(self,folder,stack):
        old=core.old
        path,sha,legacy,params,probe,probe_sha=fixtures.SelectedSnapshotTests().setup_fixture(folder,stack)
        original=folder/'mutable.csv';original.write_bytes(b'exact historical bytes')
        archived=folder/'preserved.csv';archived.write_bytes(original.read_bytes());historical=old.drift.file_sha(original)
        legacy['historical_expected_source_hashes'][str(original)]=historical
        sha=fixtures.save(path,legacy)
        stack.enter_context(patch.object(core.archive,'INVENTORY',path));stack.enter_context(patch.object(core.archive,'INVENTORY_SHA',sha))
        snapshot=old.begin(manifest_path=path,manifest_sha256=sha)
        value=old.import_probe(snapshot,probe,probe_sha);final=old.finish(snapshot)
        tasks=folder/'tasks';tasks.mkdir();taskpath=tasks/'0.json';tasksha=fixtures.save(taskpath,value)
        index=dict(schema='ndx_selected_delta_exact_gap_completion_index_v1',manifest=dict(path=str(path),sha256=sha),planned=2,status='PARTIAL',completed=[dict(path=str(taskpath),sha256=tasksha)],finalization=final,
            historical_full_source_closure_verified=False,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
        indexpath=tasks/'index_old.json';indexsha=fixtures.save(indexpath,index)
        contract=dict(rows={str(original):dict(expected_historical_sha256=historical,archived_path=str(archived),archived_sha256=historical,historical_expected_bytes_preserved=True)},authority_source_hashes={str(archived):historical})
        stack.enter_context(patch.object(core.archive,'load_contract',return_value=contract))
        manifest=core.build_manifest(legacy_index_path=indexpath,legacy_index_sha256=indexsha)
        manifestpath=folder/'archive_manifest.json';manifestsha=fixtures.save(manifestpath,manifest)
        return manifestpath,manifestsha,original,archived,value,contract

    def test_missing_live_bytes_restore_without_fit_and_one_new_fit_privately(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            path,sha,original,archived,legacy,contract=self.fixture(Path(d),stack)
            original.unlink()
            globals_before=core.old.state
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            with patch.object(core.old.selected.trace,'evaluate_with_window_trace',side_effect=AssertionError('restore must not fit')):
                restored=core.restore_legacy(snapshot,'0')
                self.assertEqual(restored['legacy_original_wrapper'],legacy)
                with self.assertRaisesRegex(ValueError,'must restore'):core.evaluate(snapshot,'0')
            with patch.object(core.old.selected.trace,'evaluate_with_window_trace',wraps=core.old.selected.trace.evaluate_with_window_trace) as traced:
                result=core.evaluate(snapshot,'1');self.assertEqual(traced.call_count,1)
            self.assertEqual(result['schema'],'SELECTED_ARCHIVE_RESOLUTION_TASK_V1')
            final=core.finish(snapshot);core.verify_finished(snapshot)
            self.assertEqual(final['completed'],2)
            self.assertEqual(len(final['archive_resolutions']),1)
            self.assertNotIn(str(original),final['live_verified_source_hashes'])
            self.assertFalse(final['historical_full_source_closure_verified'])
            self.assertIs(core.old.state,globals_before)

    def test_archive_and_nonarchive_drift_rejected_and_not_gap_upgraded(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            path,sha,original,archived,legacy,contract=self.fixture(Path(d),stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            archived.write_bytes(b'changed')
            core.restore_legacy(snapshot,'0')
            with self.assertRaises(ValueError):core.finish(snapshot)
            archived.write_bytes(b'exact historical bytes')
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            core.state(snapshot)['contexts'][legacy['original']['context_path']]['changed']['returns'].iloc[0,0]+=.1
            with self.assertRaisesRegex(ValueError,'typed input'):core.finish(snapshot)

    def test_orphan_rejected_before_snapshot_and_zero_fit_runner_restore(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            folder=Path(d);path,sha,*_=self.fixture(folder,stack)
            output=folder/'new_tasks';output.mkdir();orphan=output/'later.json';orphan.write_text('{}')
            with patch.object(core,'begin',side_effect=AssertionError('must reject before begin')):
                with self.assertRaisesRegex(ValueError,'Unindexed'):runner.run(manifest_path=path,manifest_sha256=sha,output=output,max_new_tasks=0)
            orphan.unlink()
            with patch.object(core.old.selected.trace,'evaluate_with_window_trace',side_effect=AssertionError('no fit')):
                result=runner.run(manifest_path=path,manifest_sha256=sha,output=output,max_new_tasks=0)
                again=runner.run(manifest_path=path,manifest_sha256=sha,output=output,max_new_tasks=0,resume_index=result['path'],resume_index_sha256=result['sha256'])
            self.assertEqual(result['legacy_imports'],1);self.assertEqual(again['legacy_imports'],0)
            self.assertEqual(result['new_fits'],0)

    def test_wrong_manifest_queue_or_saved_disclosure_rejected(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            folder=Path(d);path,sha,*_=self.fixture(folder,stack)
            manifest=json.loads(path.read_bytes());bad=deepcopy(manifest);bad['corrections'][0]['new']+=.001
            badpath=folder/'bad.json';badsha=fixtures.save(badpath,bad)
            with self.assertRaisesRegex(ValueError,'hard-plan'):core.begin(manifest_path=badpath,manifest_sha256=badsha)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha);value=core.restore_legacy(snapshot,'0');core.finish(snapshot)
            value['non20_risk_projection_fields_independently_recomputed']=True
            badsha=fixtures.save(badpath,value);next_snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            with self.assertRaisesRegex(ValueError,'wrapper differs'):core.restore(next_snapshot,badpath,badsha)
            (folder/'tasks'/'remote.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'unindexed'):core.begin(manifest_path=path,manifest_sha256=sha)

    def test_publish_failure_never_exposes_partial_final_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'task.json'
            with patch.object(runner.os,'link',side_effect=OSError('interrupted before atomic link')):
                with self.assertRaises(OSError):runner.publish(path,{'large':'x'*10000})
            self.assertFalse(path.exists());self.assertEqual(list(Path(d).iterdir()),[])
            first=runner.publish(path,{'value':1})
            with self.assertRaises(FileExistsError):runner.publish(path,{'value':2})
            self.assertEqual(core.old.read(path,first['sha256']),{'value':1})

    def test_per_task_avoids_full_scan_but_finish_catches_unrelated_source_drift(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            path,sha,*_=self.fixture(Path(d),stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            with patch.object(core,'verify_all',side_effect=AssertionError('No full scan per task')):
                core.restore_legacy(snapshot,'0')
                core.evaluate(snapshot,'1')
            entry=core.state(snapshot)['rows']['0'];checkpoint=Path(entry['checkpoint_path']);before=checkpoint.read_bytes()
            checkpoint.write_bytes(before+b' ')
            with self.assertRaises(ValueError):core.finish(snapshot)

    def test_task_checkpoint_and_numerical_code_drift_reject_before_fit(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            path,sha,*_=self.fixture(Path(d),stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            row=core.state(snapshot)['rows']['1'];checkpoint=Path(row['checkpoint_path']);raw=checkpoint.read_bytes()
            checkpoint.write_bytes(raw+b' ')
            with patch.object(core.old.selected.trace,'evaluate_with_window_trace',side_effect=AssertionError('No fit after drift')):
                with self.assertRaisesRegex(ValueError,'External artifact SHA'):core.evaluate(snapshot,'1')
                checkpoint.write_bytes(raw)
                file_sha=core.old.drift.file_sha
                with patch.object(core.old.drift,'file_sha',side_effect=lambda p:'0'*64 if Path(p)==core.old.selected.SOURCE else file_sha(p)):
                    with self.assertRaisesRegex(ValueError,'Numerical source changed'):core.evaluate(snapshot,'1')


if __name__=='__main__':unittest.main()
