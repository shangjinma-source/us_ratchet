from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_delta_paired_trace_recovery_research import prepare
from backtest import ndx_delta_paired_trace_recovery_v2_research as v2


def add_gap(params,*,path=None,sha=None):
    context_path=Path(params['context_path']);context=json.loads(context_path.read_bytes())
    evidence=v2._restore(context['source_evidence'])
    evidence['historical_loader_config']=dict(path=path or v2.GAP_PATH,sha256=sha or v2.GAP_EXPECTED_SHA)
    context['source_evidence']=v2.encoding._normalize(evidence)
    checkpoint=json.loads(Path(params['checkpoint_path']).read_bytes());checkpoint['context_sha256']=v2.encoding._sha(context)
    checkpoint.pop('checkpoint_sha256');checkpoint['checkpoint_sha256']=v2.encoding._sha(checkpoint)
    for name,value in (('context',context),('checkpoint',checkpoint)):
        target=Path(params[name+'_path']);raw=v2.encoding._json_bytes(value);target.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
        params[name+'_sha256']=digest;params['arguments']['source_hashes'][str(target)]=digest
    return params


class DeclaredGapTests(unittest.TestCase):
    def test_precise_gap_reported_while_original_full_result_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            params,original=prepare(directory);add_gap(params)
            expected=v2.trace.full.evaluate_joint_weight_task_v3(params['arguments']['task'],**params['corrected_inputs'])
            result=v2.recover_paired_delta(**params)
            self.assertEqual(result['result'],expected)
            self.assertEqual(result['original_result'],original)
            gap,=result['historical_loader_provenance_gaps']
            self.assertEqual(gap['path'],v2.GAP_PATH);self.assertEqual(gap['expected_historical_sha256'],v2.GAP_EXPECTED_SHA)
            self.assertEqual(gap['observed_current_sha256'],hashlib.sha256(Path(v2.GAP_PATH).read_bytes()).hexdigest())
            self.assertFalse(result['original_historical_provenance_verified'])
            self.assertFalse(result['point_in_time_verified']);self.assertFalse(result['no_fit_reuse'])

    def test_other_pointer_or_other_hash_or_unbound_typed_inputs_rejected_before_fit(self):
        for defect in ('path','sha','typed'):
            with tempfile.TemporaryDirectory() as directory:
                params,_=prepare(directory)
                add_gap(params,path=str(Path(directory)/'other.yaml') if defect=='path' else None,
                    sha='0'*64 if defect=='sha' else None)
                if defect=='typed':params['arguments']['inputs']['returns'].iloc[0,0]+=.01
                with patch.object(v2.trace,'evaluate_with_window_trace') as traced:
                    with self.assertRaises(ValueError):v2.recover_paired_delta(**params)
                    traced.assert_not_called()

    def test_missing_other_original_source_and_full_result_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=prepare(directory);add_gap(params)
            bad=deepcopy(params);bad['arguments']['source_hashes'].pop(str(Path(directory)/'fixture.txt'))
            with self.assertRaisesRegex(ValueError,'Other original evidence'):v2.recover_paired_delta(**bad)
            original=v2.trace.evaluate_with_window_trace(task=params['arguments']['task'],inputs=params['arguments']['inputs'])
            original['result']['whole_lot_path_return_net']+=.01
            with patch.object(v2.trace,'evaluate_with_window_trace',return_value=original):
                with self.assertRaisesRegex(ValueError,'full v3 checkpoint'):v2.recover_paired_delta(**params)
