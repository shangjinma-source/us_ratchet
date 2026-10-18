from copy import deepcopy
from unittest.mock import patch
import unittest
import pandas as pd
from test_ndx_multidecision_rolling_fit_research import inputs
from backtest import ndx_multidecision_rolling_fit_research as m

class Review(unittest.TestCase):
    def test_real_synthetic_shrinkage_matches_frozen_fitter(self):
        a=inputs()
        a['candidate_returns']=[[.001 if (i+j)%8<4 else -.001 for j in (0,2,4,6)] for i in range(504)]
        frame=m.prepare_panel(**a,weight_spec=m.SPECS[1])
        expected=[]
        for i in range(13):
            w=m.binding._SHRINKAGE(frame.iloc[i*21:i*21+126],tuple('ABCD'),**m.PARAMETERS,risk_chain_by_ticker=dict(zip('ABCD','ABCD')),anchor_weights=None,turnover_anchor_strength=0.)
            expected.append(w.tolist())
        out=m.fit_causal_scoring_windows(**a,weight_spec=m.SPECS[1])
        self.assertEqual([x['weights'] for x in out['windows']],expected)
        self.assertFalse(out['score_computed']);self.assertTrue(out['fit_performed'])

    def test_future_matrix_changes_do_not_leak_into_first_fit(self):
        a=inputs();b=deepcopy(a)
        for row in b['candidate_returns'][126:]:row[:]=[.9]*4
        calls=[]
        def fitter(history,tickers,**kwargs):
            calls.append((history.to_numpy().tolist(),kwargs['anchor_weights'],kwargs['turnover_anchor_strength']))
            return pd.Series(.25,index=tickers)
        outs=[]
        for x in (a,b):outs.append(m.fit_windows_with_fitter(m.prepare_panel(**x,weight_spec=m.SPECS[2]),x['securities'],m.SPECS[2],fitter))
        self.assertEqual(calls[0][0],calls[13][0]);self.assertEqual(outs[0][0]['fit_data_sha256'],outs[1][0]['fit_data_sha256'])
        self.assertIsNone(calls[0][1]);self.assertEqual(calls[0][2],.25)
        self.assertTrue(all(len(c[0])==126 for c in calls))

    def test_final_source_drift_and_bad_fitted_column_order(self):
        a=inputs()
        with patch.object(m,'source_hashes',side_effect=[{'code':'before'},{'code':'after'}]):
            with self.assertRaisesRegex(ValueError,'Source drift'):m.fit_causal_scoring_windows(**a,weight_spec='equal_weight')
        frame=m.prepare_panel(**a,weight_spec=m.SPECS[1])
        def wrong(history,tickers,**kwargs):return pd.Series(.25,index=list(reversed(tickers)))
        with self.assertRaisesRegex(ValueError,'column order'):m.fit_windows_with_fitter(frame,a['securities'],m.SPECS[1],wrong)

if __name__=='__main__':unittest.main()
