from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_delta_paired_trace_recovery_research import prepare
from test_ndx_delta_paired_trace_recovery_v2_research import add_gap
from backtest import ndx_delta_paired_snapshot_research as core


def fixture(directory,anchored=True):
    parameters,_=prepare(directory,anchored);add_gap(parameters)
    arguments=parameters['arguments'];inputs=arguments['inputs'];corrected=parameters['corrected_inputs'];date=str(inputs['returns'].index[70].date())
    corrections=[dict(ticker='INC',session=date,old=float(inputs['returns'].iloc[70,4]),new=float(corrected['returns'].iloc[70,4]))]
    row=dict(new_job_id='synthetic',task=arguments['task'],runtime=arguments['runtime'],
        context_path=str(parameters['context_path']),context_sha256=parameters['context_sha256'],
        checkpoint_path=str(parameters['checkpoint_path']),checkpoint_sha256=parameters['checkpoint_sha256'])
    context=json.loads(Path(row['context_path']).read_bytes());gaps=core.sealed.validate_historical_evidence(context,arguments['source_hashes'])
    parent=dict(dates=[dict(date='synthetic-date',tasks=[row])],errors=corrections,source_hashes=arguments['source_hashes'],
        historical_context_gap_observations={row['context_path']:dict(context_sha256=row['context_sha256'],gaps=gaps)},
        probe=dict(date='synthetic-date',task=row))
    def save(name,value):
        path=Path(directory)/name;raw=json.dumps(value,sort_keys=True).encode();path.write_bytes(raw)
        return str(path),hashlib.sha256(raw).hexdigest()
    parent_path,parent_sha=save('parent.json',parent)
    manifest=dict(schema='ndx_delta_paired_snapshot_manifest_v1',parent_plan_path=parent_path,parent_plan_sha256=parent_sha,
        tasks=[row],planned=1,corrections=corrections,source_hashes=dict(arguments['source_hashes'],**{parent_path:parent_sha}))
    path,sha=save('manifest.json',manifest)
    return dict(manifest_path=path,manifest_sha256=sha),parameters,parent


class DeltaSnapshotTests(unittest.TestCase):
    def test_actual_runtime_mismatch_rejected_before_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory)
            with patch.object(core.platform,'python_version',return_value='different-runtime'),patch.object(core.sealed.trace,'evaluate_with_window_trace') as traced:
                with self.assertRaisesRegex(ValueError,'Actual process runtime'):core.begin_snapshot(**args)
                traced.assert_not_called()

    def test_original_v2_anchor_and_nonanchor_outputs_preserved_private_bindings(self):
        for anchored in (True,False):
            with tempfile.TemporaryDirectory() as directory:
                args,parameters,_=fixture(directory,anchored)
                expected=core.sealed.recover_paired_delta(**parameters);expected.pop('source_hashes')
                before=dict(core.sealed.recover_paired_delta.__globals__)
                snapshot=core.begin_snapshot(**args);actual=core.evaluate_task(snapshot,'synthetic')
                self.assertEqual(actual['result'],expected)
                self.assertTrue(all(core.sealed.recover_paired_delta.__globals__[k] is v for k,v in before.items()))
                self.assertEqual(core.finish_snapshot(snapshot)['status'],'COMPLETE')

    def test_import_and_external_restore_do_not_call_original_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            args,parameters,parent=fixture(directory);result=core.sealed.recover_paired_delta(**parameters)
            manifest=json.loads(Path(args['manifest_path']).read_bytes())
            probe=dict(schema='ndx_delta_three_cell_paired_gap_probe_v2',selected=parent['probe'],
                plan_path=manifest['parent_plan_path'],plan_sha256=manifest['parent_plan_sha256'],result=result)
            path=Path(directory)/'probe.json';raw=json.dumps(probe).encode();path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            snapshot=core.begin_snapshot(**args)
            with patch.object(core.sealed.trace,'evaluate_with_window_trace') as traced:
                value=core.import_probe(snapshot,probe_path=path,probe_sha256=sha);traced.assert_not_called()
            self.assertEqual(core.finish_snapshot(snapshot)['status'],'COMPLETE')
            saved=Path(directory)/'saved.json';raw=json.dumps(value).encode();saved.write_bytes(raw)
            snapshot=core.begin_snapshot(**args)
            with patch.object(core.sealed.trace,'evaluate_with_window_trace') as traced:
                core.restore_task(snapshot,checkpoint_path=saved,checkpoint_sha256=hashlib.sha256(raw).hexdigest());traced.assert_not_called()
            self.assertEqual(core.finish_snapshot(snapshot)['status'],'COMPLETE')

    def test_source_and_typed_drift_forged_capability_unknown_sha_rejected(self):
        with self.assertRaises(ValueError):core.evaluate_task(core.Snapshot(),'unknown')
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory);snapshot=core.begin_snapshot(**args);state=core._state(snapshot)
            with self.assertRaises(ValueError):core._verify_scoped(state,{'unknown':'0'*64})
            item=next(iter(state['contexts'].values()));item['corrected']['returns'].iloc[0,0]+=.1
            with self.assertRaisesRegex(ValueError,'typed snapshot'):core.evaluate_task(snapshot,'synthetic')
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory);snapshot=core.begin_snapshot(**args);core.evaluate_task(snapshot,'synthetic')
            (Path(directory)/'fixture.txt').write_text('changed')
            with self.assertRaises(ValueError):core.finish_snapshot(snapshot)
            with self.assertRaises(ValueError):core.evaluate_task(snapshot,'synthetic')

    def test_checkpoint_rehashed_and_bad_shared_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args,params,_=fixture(directory);snapshot=core.begin_snapshot(**args)
            Path(params['checkpoint_path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'External artifact SHA'):core.evaluate_task(snapshot,'synthetic')
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory);path=Path(args['manifest_path']);manifest=json.loads(path.read_bytes())
            manifest['corrections'][0]['new']+=.1;raw=json.dumps(manifest).encode();path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'plan task/input'):core.begin_snapshot(manifest_path=path,manifest_sha256=hashlib.sha256(raw).hexdigest())
