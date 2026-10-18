from copy import deepcopy
import hashlib,json
import unittest
from backtest import ndx_registered_scoring_result_inspection_research as inspector
from test_ndx_registered_scoring_result_inspection_research import fixture


class Review(unittest.TestCase):
    def test_rehashed_assembly_authorities_and_offset_types_are_not_ignored(self):
        args=fixture()
        for name,value in [('execution_authorized',True),('dispatch_authorized',0),('point_in_time_verified',True),('offset',False)]:
            bad=deepcopy(args);assembled=bad['assembled']
            if name=='offset':assembled['channel_bindings_preserved'][0]['return_index_start']=value
            else:assembled[name]=value
            assembled['content_sha256']=inspector.digest({k:v for k,v in assembled.items() if k!='content_sha256'})
            with self.subTest(name=name),self.assertRaises(ValueError):inspector.inspect_registered_scoring_result(**bad)

    def test_fit_window_hashes_independent_reconstruction_and_middle_prior(self):
        args=fixture('constrained_fixed_shrinkage_turnover_anchor')
        out=inspector.inspect_registered_scoring_result(**args)
        source=args['assembled']['rolling_inputs'];expected=[]
        for i in range(13):
            first=21*i
            payload={'dates':source['return_dates'][first:first+126], 'tickers':[row['ticker'] for row in source['securities']], 'returns':source['candidate_returns'][first:first+126]}
            expected.append(hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest())
        self.assertEqual(out['fit_matrix_hashes'],expected)
        self.assertFalse(out['optimized_weights_independently_verified'])
        bad=deepcopy(args);bad['saved_fit']['windows'][7]['fitter_anchor_used']=bad['saved_fit']['windows'][0]['requested_inner_prior']
        with self.assertRaises(ValueError):inspector.inspect_registered_scoring_result(**bad)

    def test_saved_projection_claim_is_not_reoptimization_and_omission_is_rejected(self):
        args=fixture()
        for action in ('omit','relaxed_type','future','recovery_equal'):
            bad=deepcopy(args)
            if action=='omit':bad['saved_fit']['windows'].pop(6)
            elif action=='relaxed_type':bad['saved_fit']['windows'][3]['projection_relaxed']=0
            elif action=='future':bad['saved_fit']['windows'][0]['fit_last_return_end']=bad['saved_fit']['windows'][0]['evaluation_last_return_end']
            else:bad['saved_fit']['reconstruction_attempts']=[{'optimizer_message':'claimed','reconstruction':{'certified':True},'independent_certificate':{'certified':True},'failed_optimizer_vector':[0.0]*9}]
            with self.assertRaises(ValueError):inspector.inspect_registered_scoring_result(**bad)


if __name__=='__main__':unittest.main()
