from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from test_ndx_base_window_delta_research import setup_cache
from backtest import ndx_base_window_snapshot_research as fast


def fixture(directory,*,anchored=True,single=False):
    parameters,saved=setup_cache(directory,anchored=anchored,single=single)
    inputs=parameters['arguments']['inputs'];day=str(inputs['returns'].index[70].date())
    cell=dict(ticker='AAA',session=day,old=float(inputs['returns'].iloc[70,0]),new=float(inputs['returns'].iloc[70,0])+.18)
    row=dict(new_job_id='synthetic-job',task=parameters['arguments']['task'],
        checkpoint_path=str(parameters['checkpoint_path']),checkpoint_sha256=parameters['checkpoint_sha256'])
    manifest=dict(schema='ndx_base_window_snapshot_manifest_v1',source_hashes=parameters['arguments']['source_hashes'],
        context=dict(path=str(parameters['context_path']),sha256=parameters['context_sha256']),
        typed_context=dict(path=str(parameters['typed_context_path']),sha256=parameters['typed_context_sha256']),
        corrections=[cell],tasks=[row])
    path=Path(directory)/'snapshot_manifest.json';raw=json.dumps(manifest,sort_keys=True).encode();path.write_bytes(raw)
    arguments=dict(manifest_path=path,manifest_sha256=hashlib.sha256(raw).hexdigest())
    corrected=deepcopy(inputs);corrected['returns'].loc[day,'AAA']=cell['new']
    return arguments,parameters,corrected


class SnapshotTests(unittest.TestCase):
    def test_external_completed_probe_import_does_not_repeat_numerical_work(self):
        with tempfile.TemporaryDirectory() as directory:
            args,parameters,corrected=fixture(directory)
            expected=fast.sealed.evaluate_window_delta(**parameters,corrected_inputs=corrected)
            probe=dict(schema='ndx_base_window_delta_probe_v1',selected=dict(new_job_id='synthetic-job',parent_task=parameters['arguments']['task']),result=expected,
                numerical_input_digests=dict(original=fast.sealed._input_digest(parameters['arguments']['inputs']),corrected=fast.sealed._input_digest(corrected)))
            path=Path(directory)/'probe.json';raw=json.dumps(probe,sort_keys=True).encode();path.write_bytes(raw)
            snapshot=fast.begin_snapshot(**args)
            collision=Path(directory)/'fixture.txt';original=collision.read_bytes();collision.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'Conflicting imported source'):
                fast.import_probe(snapshot,probe_path=collision,probe_sha256=hashlib.sha256(raw).hexdigest())
            collision.write_bytes(original)
            imported=fast.import_probe(snapshot,probe_path=path,probe_sha256=hashlib.sha256(raw).hexdigest())
            self.assertEqual(imported['mode'],'EXTERNALLY_BOUND_COMPLETED_PROBE_IMPORTED_NO_FIT')
            self.assertEqual(fast.evaluate_task(snapshot,'synthetic-job'),imported)
            fast._state(snapshot)['corrected']['returns'].iloc[0,0]+=.01
            with self.assertRaises(ValueError):fast.evaluate_task(snapshot,'synthetic-job')
            fast._state(snapshot)['corrected']['returns'].iloc[0,0]-=.01
            # Restore exact bytes rather than rely on floating subtraction.
            fast._state(snapshot)['corrected']=deepcopy(corrected)
            self.assertEqual(fast.finish_snapshot(snapshot)['status'],'COMPLETE')

    def test_external_valid_probe_for_other_corrected_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args,parameters,corrected=fixture(directory)
            result=fast.sealed.evaluate_window_delta(**parameters,corrected_inputs=corrected)
            probe=dict(schema='ndx_base_window_delta_probe_v1',selected=dict(new_job_id='synthetic-job',parent_task=parameters['arguments']['task']),result=result,
                numerical_input_digests=dict(original=fast.sealed._input_digest(parameters['arguments']['inputs']),corrected=fast.sealed._input_digest(corrected)))
            path=Path(directory)/'probe.json';raw=json.dumps(probe,sort_keys=True).encode();path.write_bytes(raw)
            manifest=json.loads(Path(args['manifest_path']).read_bytes());manifest['corrections'][0]['new']+=.01
            manifest_raw=json.dumps(manifest,sort_keys=True).encode();Path(args['manifest_path']).write_bytes(manifest_raw)
            args['manifest_sha256']=hashlib.sha256(manifest_raw).hexdigest()
            snapshot=fast.begin_snapshot(**args)
            with self.assertRaisesRegex(ValueError,'numerical inputs differ'):
                fast.import_probe(snapshot,probe_path=path,probe_sha256=hashlib.sha256(raw).hexdigest())

    def test_private_fast_path_matches_sealed_base_anchor_cost_and_k1(self):
        for anchored,single in ((False,False),(True,False),(True,True)):
            with tempfile.TemporaryDirectory() as directory:
                args,parameters,corrected=fixture(directory,anchored=anchored,single=single)
                expected=fast.sealed.evaluate_window_delta(**parameters,corrected_inputs=corrected)
                snapshot=fast.begin_snapshot(**args)
                result=fast.evaluate_task(snapshot,'synthetic-job')['result']
                self.assertEqual(result['evaluation']['result'],expected['evaluation']['result'])
                self.assertEqual(result['evaluation']['historical_window_weights'],expected['evaluation']['historical_window_weights'])
                self.assertEqual(result['window_cache_audit'],expected['window_cache_audit'])
                self.assertEqual(fast.finish_snapshot(snapshot)['status'],'COMPLETE')

    def test_date_source_drift_never_finalizes_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory);snapshot=fast.begin_snapshot(**args)
            fast.evaluate_task(snapshot,'synthetic-job')
            (Path(directory)/'fixture.txt').write_text('changed during date')
            with self.assertRaises(ValueError):fast.finish_snapshot(snapshot)
            with self.assertRaises(ValueError):fast.evaluate_task(snapshot,'synthetic-job')

    def test_forged_snapshot_unknown_source_and_mutated_typed_values_rejected(self):
        with self.assertRaises(ValueError):fast.evaluate_task(fast.DateSnapshot(),'synthetic-job')
        with tempfile.TemporaryDirectory() as directory:
            args,_,_=fixture(directory);snapshot=fast.begin_snapshot(**args);state=fast._state(snapshot)
            with self.assertRaises(ValueError):fast._verify_scoped(state,{str(Path(directory)/'unknown'):'a'*64})
            existing=next(iter(state['sources']))
            with self.assertRaises(ValueError):fast._verify_scoped(state,{existing:'f'*64})
            state['inputs']['returns'].iloc[0,0]+=.01
            with self.assertRaises(ValueError):fast.evaluate_task(snapshot,'synthetic-job')
            with self.assertRaises(ValueError):fast.finish_snapshot(snapshot)

    def test_changed_checkpoint_external_sha_still_read_per_task(self):
        with tempfile.TemporaryDirectory() as directory:
            args,parameters,_=fixture(directory);snapshot=fast.begin_snapshot(**args)
            Path(parameters['checkpoint_path']).write_text('{}')
            with self.assertRaises(ValueError):fast.evaluate_task(snapshot,'synthetic-job')
