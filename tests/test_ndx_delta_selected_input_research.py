from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_delta_paired_trace_recovery_research import prepare
from test_ndx_delta_paired_trace_recovery_v2_research import add_gap
from backtest import ndx_delta_selected_input_research as selected


def fixture(directory,anchored=True):
    params,_=prepare(directory,anchored)
    add_gap(params)
    panel=params['arguments']['inputs']['returns']
    cells=tuple((panel.columns[column],str(panel.index[row].date()),float(panel.iloc[row,column]),float(panel.iloc[row,column])+.02)
                for row,column in ((2,0),(3,1),(70,4)))
    params['corrected_inputs']=deepcopy(params['arguments']['inputs'])
    for ticker,date,old,new in cells:params['corrected_inputs']['returns'].loc[date,ticker]=new
    return params,cells


class SelectedDeltaTests(unittest.TestCase):
    def test_one_new_full_v3_exact_oracle_anchor_and_nonanchor_input_globals_unchanged(self):
        for anchored in (False,True):
            with tempfile.TemporaryDirectory() as directory:
                params,cells=fixture(directory,anchored)
                before=selected.provenance._digest(params['arguments']['inputs'])
                changed_before=selected.provenance._digest(params['corrected_inputs'])
                binding=dict(vars(selected.trace.binding))
                expected=selected.trace.full.evaluate_joint_weight_task_v3(params['arguments']['task'],**params['corrected_inputs'])
                with (patch.object(selected,'CORRECTIONS',cells),patch.object(selected,'correction_sources',return_value={}),
                      patch.object(selected.trace,'evaluate_with_window_trace',wraps=selected.trace.evaluate_with_window_trace) as evaluate):
                    result=selected.evaluate_selected_delta(**params)
                self.assertEqual(evaluate.call_count,1)
                self.assertEqual(result['result'],expected)
                self.assertEqual(result['new_fitted_window_count'],expected['rolling_fit_window_count'])
                self.assertEqual(result['old_input_numerical_evaluation_count'],0)
                self.assertFalse(result['original_result_reproduced'])
                self.assertFalse(result['window_fit_reuse_performed'])
                self.assertFalse(result['original_historical_provenance_verified'])
                self.assertEqual(before,selected.provenance._digest(params['arguments']['inputs']))
                self.assertEqual(changed_before,selected.provenance._digest(params['corrected_inputs']))
                self.assertEqual(binding,dict(vars(selected.trace.binding)))

    def test_no_change_wrong_cell_nominal_target_runtime_and_original_inputs_reject_before_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            params,cells=fixture(directory)
            for defect in ('no_change','wrong_cell','nominal','target','runtime','original'):
                bad=deepcopy(params)
                if defect=='no_change':bad['corrected_inputs']=deepcopy(bad['arguments']['inputs'])
                elif defect=='wrong_cell':bad['corrected_inputs']['returns'].iloc[10,0]+=.01
                elif defect=='nominal':bad['corrected_inputs']['nominal_prices'].iloc[70,0]+=.01
                elif defect=='target':bad['corrected_inputs']['target_returns'].iloc[70]+=.01
                elif defect=='runtime':bad['arguments']['runtime']['python']='wrong'
                else:bad['arguments']['inputs']['returns'].iloc[10,0]+=.01
                with (patch.object(selected,'CORRECTIONS',cells),patch.object(selected,'correction_sources',return_value={}),
                      patch.object(selected.trace,'evaluate_with_window_trace') as evaluate):
                    with self.assertRaises(ValueError):selected.evaluate_selected_delta(**bad)
                    evaluate.assert_not_called()

    def test_benchmark_only_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            params,cells=fixture(directory)
            panel=params['arguments']['inputs']['returns'];ticker=panel.columns[4]
            cells=tuple((ticker,str(panel.index[row].date()),float(panel.iloc[row,4]),.08) for row in (70,71,72))
            params['corrected_inputs']=deepcopy(params['arguments']['inputs'])
            for ticker,date,old,new in cells:params['corrected_inputs']['returns'].loc[date,ticker]=new
            with (patch.object(selected,'CORRECTIONS',cells),patch.object(selected,'correction_sources',return_value={}),
                  patch.object(selected.trace,'evaluate_with_window_trace') as evaluate):
                with self.assertRaisesRegex(ValueError,'Selected fitted/forward'):selected.evaluate_selected_delta(**params)
                evaluate.assert_not_called()

    def test_checkpoint_identity_resigned_and_other_missing_evidence_rejected(self):
        for defect in ('task','evidence','external_sha'):
            with tempfile.TemporaryDirectory() as directory:
                params,cells=fixture(directory)
                if defect=='task':
                    path=Path(params['checkpoint_path']);value=json.loads(path.read_bytes())
                    value['task']['tickers']='INVALID';value.pop('checkpoint_sha256')
                    value['checkpoint_sha256']=selected.encoding._sha(value)
                    raw=selected.encoding._json_bytes(value);path.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
                    params['checkpoint_sha256']=digest;params['arguments']['source_hashes'][str(path)]=digest
                elif defect=='evidence':params['arguments']['source_hashes'].pop(str(Path(directory)/'fixture.txt'))
                else:params['checkpoint_sha256']='0'*64
                with (patch.object(selected,'CORRECTIONS',cells),patch.object(selected,'correction_sources',return_value={}),
                      patch.object(selected.trace,'evaluate_with_window_trace') as evaluate):
                    with self.assertRaises(ValueError):selected.evaluate_selected_delta(**params)
                    evaluate.assert_not_called()

    def test_context_and_argument_runtime_resigned_together_still_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            params,cells=fixture(directory)
            context=json.loads(Path(params['context_path']).read_bytes())
            context['runtime']['numpy']='other-version'
            params['arguments']['runtime']=deepcopy(context['runtime'])
            checkpoint=json.loads(Path(params['checkpoint_path']).read_bytes())
            checkpoint['context_sha256']=selected.encoding._sha(context)
            checkpoint.pop('checkpoint_sha256');checkpoint['checkpoint_sha256']=selected.encoding._sha(checkpoint)
            for name,value in (('context',context),('checkpoint',checkpoint)):
                path=Path(params[name+'_path']);raw=selected.encoding._json_bytes(value);path.write_bytes(raw)
                digest=hashlib.sha256(raw).hexdigest();params[name+'_sha256']=digest
                params['arguments']['source_hashes'][str(path)]=digest
            with (patch.object(selected,'CORRECTIONS',cells),patch.object(selected,'correction_sources',return_value={}),
                  patch.object(selected.trace,'evaluate_with_window_trace') as evaluate):
                with self.assertRaisesRegex(ValueError,'actual process runtime'):selected.evaluate_selected_delta(**params)
                evaluate.assert_not_called()


if __name__=='__main__':unittest.main()
