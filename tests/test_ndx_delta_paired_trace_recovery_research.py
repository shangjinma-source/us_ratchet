from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_candidate_input_equivalence_research import fixture
from backtest import ndx_delta_paired_trace_recovery_research as recovery


def prepare(directory,anchored=True):
    args=fixture(directory,'joint_weight_v3')
    if not anchored:args['task']['weight_spec']='constrained_fixed_shrinkage'
    result=recovery.trace.full.evaluate_joint_weight_task_v3(args['task'],**args['inputs'])
    encoder=recovery.encoding
    context=dict(schema='ndx_joint_weight_checkpoint_v1',runtime=args['runtime'],tasks=[args['task']],
        numerical_sources=recovery.trace.full._LOADED_SOURCES,
        prepared_inputs={k:encoder._panel_context(v) for k,v in args['inputs'].items()},
        source_evidence=encoder._normalize({'fixture':dict(path=str(Path(directory)/'fixture.txt'),sha256=args['source_hashes'][str(Path(directory)/'fixture.txt')])}))
    checkpoint=dict(context_sha256=encoder._sha(context),task=args['task'],status='EVALUATED',result=encoder._normalize(result))
    checkpoint['checkpoint_sha256']=encoder._sha(checkpoint)
    references={}
    for name,value in (('context',context),('checkpoint',checkpoint)):
        path=Path(directory)/(name+'.json');raw=encoder._json_bytes(value);path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
        args['source_hashes'][str(path)]=sha;references[name+'_path']=path;references[name+'_sha256']=sha
    corrected=deepcopy(args['inputs']);corrected['returns'].iloc[70,4]+=.07
    return dict(arguments=args,corrected_inputs=corrected,**references),result


class DeltaPairedTests(unittest.TestCase):
    def test_one_original_trace_matches_corrected_real_v3_and_keeps_other_channels(self):
        for anchored in (True,False):
            with tempfile.TemporaryDirectory() as directory:
                params,old=prepare(directory,anchored)
                expected=recovery.trace.full.evaluate_joint_weight_task_v3(params['arguments']['task'],**params['corrected_inputs'])
                with patch.object(recovery.trace,'evaluate_with_window_trace',wraps=recovery.trace.evaluate_with_window_trace) as observed:
                    result=recovery.recover_paired_delta(**params)
                    self.assertEqual(observed.call_count,1)
                for key in recovery.PAIRED:self.assertAlmostEqual(result['result'][key],expected[key],places=12)
                self.assertEqual({k:v for k,v in result['result'].items() if k not in recovery.PAIRED},
                    {k:v for k,v in old.items() if k not in recovery.PAIRED})
                self.assertEqual(result['result'],expected)
                self.assertFalse(result['no_fit_reuse']);self.assertEqual(result['new_input_fit_count'],0)

    def test_selected_nominal_target_and_runtime_change_rejected_before_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            original,_=prepare(directory)
            for field in ('returns','nominal_prices','target_returns'):
                params=deepcopy(original)
                if field=='target_returns':params['corrected_inputs'][field].iloc[70]+=.01
                else:params['corrected_inputs'][field].iloc[70,0]+=.01
                with patch.object(recovery.trace,'evaluate_with_window_trace') as observed:
                    with self.assertRaises(ValueError):recovery.recover_paired_delta(**params)
                    observed.assert_not_called()

    def test_full_original_checkpoint_not_just_paired_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=prepare(directory);path=Path(params['checkpoint_path']);checkpoint=json.loads(path.read_bytes())
            decoded=recovery._restore(checkpoint['result']);decoded['whole_lot_path_return_net']+=.01
            checkpoint['result']=recovery.encoding._normalize(decoded);checkpoint.pop('checkpoint_sha256')
            checkpoint['checkpoint_sha256']=recovery.encoding._sha(checkpoint)
            raw=recovery.encoding._json_bytes(checkpoint);path.write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
            params['checkpoint_sha256']=sha;params['arguments']['source_hashes'][str(path)]=sha
            with self.assertRaisesRegex(ValueError,'full v3 checkpoint'):recovery.recover_paired_delta(**params)

    def test_trace_missing_window_and_weights_and_source_sha_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=prepare(directory)
            trace=recovery.trace.evaluate_with_window_trace(task=params['arguments']['task'],inputs=params['arguments']['inputs'])
            for defect in ('missing','weight'):
                bad=deepcopy(trace)
                if defect=='missing':bad['historical_window_weights'].pop()
                else:bad['historical_window_weights'][0]['weights']['AAA']=float('nan')
                with patch.object(recovery.trace,'evaluate_with_window_trace',return_value=bad):
                    with self.assertRaises(ValueError):recovery.recover_paired_delta(**params)
            params['arguments']['source_hashes'][str(recovery.SOURCE)]='0'*64
            with self.assertRaisesRegex(ValueError,'Conflicting loaded'):recovery.recover_paired_delta(**params)
