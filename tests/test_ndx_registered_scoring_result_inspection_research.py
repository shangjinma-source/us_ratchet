from copy import deepcopy
import unittest
from backtest import ndx_registered_scoring_result_inspection_research as m
from backtest import ndx_registered_scoring_job_inputs_research as assembler
from backtest import ndx_multidecision_window_scoring_research as reducer
from test_ndx_registered_scoring_job_inputs_research import fixture as input_fixture


def fixture(spec='equal_weight'):
    args=input_fixture();args['registered_job']=args['registered_mode_plan']['tasks'][m.SPECS.index(spec)]
    inputs=assembler.assemble_registered_scoring_job_inputs(**args);fit=inputs['rolling_inputs'];names=[s['ticker'] for s in fit['securities']];dates=fit['return_dates'];previous=None;windows=[]
    for i in range(13):
        start=i*21;weights=[.25]*4 if spec=='equal_weight' or i%2==0 else [.1,.2,.3,.4];anchored=spec==m.SPECS[2]
        payload=dict(dates=dates[start:start+126],tickers=names,returns=fit['candidate_returns'][start:start+126])
        windows.append(dict(window_index=i,fit_first_return_end=dates[start],fit_last_return_end=dates[start+125],evaluation_first_return_end=dates[start+126],evaluation_last_return_end=dates[start+251],fit_data_sha256=m.digest(payload),weights=weights,projection_relaxed=False,requested_inner_prior=deepcopy(previous),fitter_anchor_used=deepcopy(previous) if anchored else None,fitter_anchor_strength=.25 if anchored else 0.))
        previous=dict(zip(names,weights))
    sources={f'/fixture/fitter{i}.py':'a'*64 for i in range(25)}
    saved=dict(schema='MULTIDECISION_CAUSAL_ROLLING_FITS_V1',cutoff=fit['cutoff'],securities=fit['securities'],weight_spec=spec,windows=windows,reconstruction_attempts=[],numerical_projection='V3_CERTIFIED_RECOVERY_ORIGINAL_PROBE_CLOSURE',inner_prior_policy='FIRST_NONE_THEN_SAME_CANDIDATE_PREVIOUS_TARGET',source_hashes=sources,source_bytes_authenticated=False,outer_lane_prior_applied=False,fit_performed=spec!='equal_weight',score_computed=False,point_in_time_verified=False,account_executed=False,promotion_allowed=False)
    score=reducer.reduce_fitted_scoring_windows(**inputs['reducer_inputs'],fitted_windows=windows)
    audit=m.arithmetic.inspect_fitted_scoring_windows(**inputs['reducer_inputs'],fitted_windows=windows,saved_score=score)
    return dict(assembled=inputs,saved_fit=saved,saved_score=score,saved_score_inspection=audit,numerical_source_hashes=sources,channel_bindings=args['channel_bindings'],original8_inputs=args['original8_inputs'],target_inputs=args['target_inputs'])


class Tests(unittest.TestCase):
    def test_three_specs_thirteen_matrices_original_sources(self):
        for spec in m.SPECS:
            args=fixture(spec);before=deepcopy(args);out=m.inspect_registered_scoring_result(**args)
            self.assertEqual(out['status'],'PASS');self.assertEqual(len(out['fit_matrix_hashes']),13)
            self.assertFalse(out['optimized_weights_independently_verified']);self.assertEqual(args,before)

    def test_same_candidate_prior_not_outer_and_first_none_strength(self):
        args=fixture(m.SPECS[2])
        for i,field,value in ((0,'fitter_anchor_strength',0.),(0,'fitter_anchor_used',{}),(1,'requested_inner_prior',None),(2,'fitter_anchor_used',dict.fromkeys('ABCD',.25))):
            bad=deepcopy(args);bad['saved_fit']['windows'][i][field]=value
            with self.assertRaises(ValueError):m.inspect_registered_scoring_result(**bad)

    def test_rehashed_input_cannot_replace_original_matrix(self):
        args=fixture()
        for action in ('matrix','fit_hash','source','report','return_type'):
            bad=deepcopy(args)
            if action=='matrix':
                for field in ('rolling_inputs','reducer_inputs'):bad['assembled'][field]['candidate_returns'][0][0]=.4
                bad['assembled']['content_sha256']=m.digest({k:v for k,v in bad['assembled'].items() if k!='content_sha256'})
            elif action=='fit_hash':bad['saved_fit']['windows'][12]['fit_data_sha256']='0'*64
            elif action=='source':bad['saved_fit']['source_hashes']=dict(bad['saved_fit']['source_hashes'],fake='f'*64)
            elif action=='report':bad['saved_score_inspection']['fit_performed']=0
            else:bad['saved_fit']['windows'][0]['weights'][0]=True
            with self.assertRaises(ValueError):m.inspect_registered_scoring_result(**bad)


if __name__=='__main__':unittest.main()
