from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from test_ndx_candidate_input_equivalence_research import fixture
from backtest import ndx_base_window_delta_research as adapter


def setup_cache(directory,*,anchored=True,single=False):
    args=fixture(directory,'non_equal_fractional_v1')
    dates=pd.bdate_range('2023-01-02',periods=210)
    frame=pd.DataFrame(np.random.default_rng(773).normal(.0003,.013,(210,5)),index=dates,columns=args['inputs']['returns'].columns)
    args['inputs'].update(returns=frame,target_returns=frame.INC.copy(),nominal_prices=100*(1+frame).cumprod())
    args['task'].update(decision_data_end=str(dates[-1].date()),selection_date=str((dates[-1]+pd.offsets.BDay()).date()),
        weight_spec='constrained_fixed_shrinkage_turnover_anchor' if anchored else 'constrained_fixed_shrinkage')
    if single:args['task'].update(tickers='AAA',holding_count=1)
    saved=adapter.base.evaluate_non_equal_fractional(task=args['task'],inputs=args['inputs'])
    runner=adapter.checkpoints
    def save(name,value):
        path=Path(directory)/name;raw=runner._bytes(value);path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest();args['source_hashes'][str(path)]=sha
        return path,sha
    typed_path,typed_sha=save('typed.json',{'prepared_inputs':{k:runner.encoding._panel_context(v) for k,v in args['inputs'].items()}})
    context=dict(schema='ndx_non_equal_base_context_v1',planned=1,tasks=[args['task']],runtime=args['runtime'],numerical_sources=saved['source_hashes'],
        source_hashes={str(typed_path):typed_sha,str(Path(directory)/'fixture.txt'):args['source_hashes'][str(Path(directory)/'fixture.txt')]})
    context_path,context_sha=save('context.json',context)
    checkpoint=dict(schema='ndx_non_equal_base_checkpoint_v1',context_sha256=context_sha,task=args['task'],
        status='EVALUATED',result=runner.encoding._normalize(saved))
    checkpoint['checkpoint_sha256']=runner._sha(checkpoint)
    path,sha=save('checkpoint.json',checkpoint)
    params=dict(arguments=args,checkpoint_path=path,checkpoint_sha256=sha,context_path=context_path,
        context_sha256=context_sha,typed_context_path=typed_path,typed_context_sha256=typed_sha)
    return params,saved


def assert_economics(test,actual,expected):
    # Cached projection attempts are provenance, not newly executed attempts.
    test.assertEqual(actual['result'],expected['result'])
    test.assertEqual(actual['historical_window_weights'],expected['historical_window_weights'])


class BaseWindowDeltaTests(unittest.TestCase):
    def test_unchanged_input_reuses_every_window_and_preserves_base(self):
        with tempfile.TemporaryDirectory() as directory:
            params,saved=setup_cache(directory)
            result=adapter.evaluate_window_delta(**params,corrected_inputs=deepcopy(params['arguments']['inputs']))
            self.assertEqual(result['refitted_window_count'],0)
            assert_economics(self,result['evaluation'],saved)

    def test_nonanchor_reuses_after_fit_but_previous_target_cost_is_new(self):
        with tempfile.TemporaryDirectory() as directory:
            params,saved=setup_cache(directory,anchored=False)
            changed=deepcopy(params['arguments']['inputs']);changed['returns'].iloc[70,0]+=.18
            result=adapter.evaluate_window_delta(**params,corrected_inputs=changed)
            oracle=adapter.base.evaluate_non_equal_fractional(task=params['arguments']['task'],inputs=changed)
            assert_economics(self,result['evaluation'],oracle)
            modes=[r['mode'] for r in result['window_cache_audit']]
            self.assertEqual(modes[0],'REUSED_EXACT_FITTER_INPUT')
            self.assertEqual(modes[1:4],['REFITTED_ORIGINAL_BASE_FITTER']*3)
            self.assertTrue(all(m=='REUSED_EXACT_FITTER_INPUT' for m in modes[4:]))
            original_args=params['arguments'];new_args=dict(original_args,inputs=changed)
            old=adapter.recovery.recover(arguments=original_args,saved=saved)
            new=adapter.recovery.recover(arguments=new_args,saved=oracle)
            self.assertNotEqual(old['windows'][4]['cost'],new['windows'][4]['cost'])

    def test_anchor_propagates_beyond_direct_error_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=setup_cache(directory)
            changed=deepcopy(params['arguments']['inputs']);changed['returns'].iloc[70,0]+=.18
            result=adapter.evaluate_window_delta(**params,corrected_inputs=changed)
            oracle=adapter.base.evaluate_non_equal_fractional(task=params['arguments']['task'],inputs=changed)
            assert_economics(self,result['evaluation'],oracle)
            self.assertEqual(result['window_cache_audit'][4]['mode'],'REFITTED_ORIGINAL_BASE_FITTER')

    def test_single_name_never_refits_covariance_when_returns_change(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=setup_cache(directory,single=True)
            changed=deepcopy(params['arguments']['inputs']);changed['returns'].iloc[70,0]+=.18
            result=adapter.evaluate_window_delta(**params,corrected_inputs=changed)
            oracle=adapter.base.evaluate_non_equal_fractional(task=params['arguments']['task'],inputs=changed)
            self.assertEqual(result['refitted_window_count'],0)
            assert_economics(self,result['evaluation'],oracle)

    def test_external_checkpoint_sha_and_original_typed_cells_required(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=setup_cache(directory)
            changed=deepcopy(params['arguments']['inputs'])
            wrong=deepcopy(params);wrong['arguments']['inputs']['returns'].iloc[0,0]+=.01
            with self.assertRaises(ValueError):adapter.evaluate_window_delta(**wrong,corrected_inputs=changed)
            wrong_inputs=deepcopy(changed);wrong_inputs['universe'].loc[0,'issuer_id']='different'
            with self.assertRaises(ValueError):adapter.evaluate_window_delta(**params,corrected_inputs=wrong_inputs)
            Path(params['checkpoint_path']).write_text('{}')
            with self.assertRaises(ValueError):adapter.evaluate_window_delta(**params,corrected_inputs=changed)

    def test_original_source_closure_cannot_be_omitted_or_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            params,_=setup_cache(directory)
            changed=deepcopy(params['arguments']['inputs'])
            path=Path(directory)/'fixture.txt'
            missing=deepcopy(params);missing['arguments']['source_hashes'].pop(str(path))
            with self.assertRaises(ValueError):adapter.evaluate_window_delta(**missing,corrected_inputs=changed)
            path.write_text('changed source')
            with self.assertRaises(ValueError):adapter.evaluate_window_delta(**params,corrected_inputs=changed)
