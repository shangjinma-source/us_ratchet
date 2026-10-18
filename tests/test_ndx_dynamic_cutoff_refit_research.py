import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from backtest import ndx_dynamic_cutoff_refit_research as refit


class CutoffRefitTests(unittest.TestCase):
    def fixture(self):
        dates=pd.bdate_range('2023-01-02',periods=140)
        rng=np.random.default_rng(132)
        returns=pd.DataFrame(rng.normal(0,.01,(140,4)),index=dates,columns=list('ABCD'))
        return dict(returns=returns,cutoff=str(dates[-1].date()),
            selected={key:dict(ticker=key,issuer_id='issuer:'+key,risk_chain=key) for key in 'ABCD'},
            weight_spec='constrained_fixed_shrinkage_turnover_anchor')

    def test_latest126_no_initial_uniform_anchor(self):
        args=self.fixture(); result=refit.refit_dynamic_cutoff_weights(**args)
        self.assertEqual(result['fit_start'],str(args['returns'].index[-126].date()))
        self.assertEqual(result['fit_end'],args['cutoff'])
        self.assertEqual(result['effective_anchor_strength'],0.)
        self.assertTrue(result['declared_constraints_passed'])
        self.assertFalse(result['checkpoint_weights_used'])

    def test_anchor_surviving_identity_zero_new_and_disabled_nonanchor(self):
        args=self.fixture(); args['previous_target_weights']={'A':.2,'B':.3,'OLD':.5}
        result=refit.refit_dynamic_cutoff_weights(**args)
        self.assertEqual(result['anchor_by_security'],{'A':.4,'B':.6,'C':0.,'D':0.})
        self.assertEqual(result['effective_anchor_strength'],.25)
        args['weight_spec']='constrained_fixed_shrinkage'
        self.assertEqual(refit.refit_dynamic_cutoff_weights(**args)['effective_anchor_strength'],0.)
        args['previous_target_weights']={'OLD':1.}; args['weight_spec']='constrained_fixed_shrinkage_turnover_anchor'
        self.assertEqual(refit.refit_dynamic_cutoff_weights(**args)['effective_anchor_strength'],0.)

    def test_equal_spec_and_small_k_not_risk_admission(self):
        args=self.fixture(); args['weight_spec']='equal_weight'
        result=refit.refit_dynamic_cutoff_weights(**args)
        self.assertTrue(all(t['target_weight']==.25 for t in result['targets'].values()))
        args['selected']={'A':args['selected']['A']}; args['weight_spec']='constrained_fixed_shrinkage'
        result=refit.refit_dynamic_cutoff_weights(**args)
        self.assertFalse(result['declared_constraints_passed'])
        self.assertTrue(result['single_name_projection_relaxed'])
        self.assertTrue(result['risk_chain_projection_relaxed'])

    def test_future_cutoff_and_boolean_rejected(self):
        args=self.fixture(); args['cutoff']=str(args['returns'].index[-2].date())
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)
        args=self.fixture(); args['returns']['A']=True
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)
        args=self.fixture(); args['cutoff']+='T00:00:00'
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)

    def test_old_rows_not_used_numerically_but_all_selected_values_validated(self):
        args=self.fixture(); first=refit.refit_dynamic_cutoff_weights(**args)
        args['returns'].iloc[:14]=.5
        second=refit.refit_dynamic_cutoff_weights(**args)
        self.assertEqual(first['targets'],second['targets'])
        self.assertEqual(first['fit_data_sha256'],second['fit_data_sha256'])
        args['returns'].iloc[0,0]=float('nan')
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)
        args=self.fixture(); args['returns']['UNSELECTED']=float('nan')
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)

    def test_identity_and_source_guard(self):
        args=self.fixture(); args['selected']['B']['issuer_id']='issuer:A'
        with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**args)
        with patch.object(refit,'_LOADED_SHA','0'*64):
            with self.assertRaises(ValueError): refit.refit_dynamic_cutoff_weights(**self.fixture())


if __name__=='__main__': unittest.main()
