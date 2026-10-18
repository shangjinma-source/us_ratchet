from copy import deepcopy
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_corrected_frontier_cutoff_refit_archive_research as m
from test_ndx_corrected_complete_date_frontier_research import fixture as cohort_fixture


def context_fixture():
    dates=pd.bdate_range('2022-06-01','2022-07-29');names=['AMAT','AVGO','CDNS','GOOG','GOOGL','FTNT']
    returns=pd.DataFrame(.001,index=dates,columns=names)
    for ticker,date,old,new in m.typed.CORRECTIONS:returns.loc[date,ticker]=old
    parameters=dict(fit_days=20,shrinkage_intensity=.35,turnover_anchor_strength=.25,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
    contract=dict(parameters,window_days=10,step_days=5,transaction_cost_bps=10.,portfolio_cash_usd=25000.,minimum_cash_buffer_usd=100.,minimum_median_dollar_volume_usd=100000.)
    inputs=dict(returns=returns,nominal_prices=(returns+1).cumprod()*100,target_returns=pd.Series(.0005,index=dates),contract=contract,incumbent_weights={'GOOG':1.},
        universe=pd.DataFrame([dict(ticker=t,security_id='security:'+t,issuer_id='issuer:'+t,risk_chain='chain:'+t) for t in names]))
    context=dict(schema='ndx_joint_weight_checkpoint_v1',numerical_sources=m.typed.trace.full._LOADED_SOURCES,runtime=m.typed.current_runtime(),prepared_inputs={k:m.typed.encoding._panel_context(v) for k,v in inputs.items()})
    report=dict(original_decision_data_end='2022-07-29',coordinate=dict(selection_date='2022-08-01',source_batch='SYNTHETIC',universe_track='strict_technology'))
    sem=m.semantics.training_semantics(inputs=inputs,decision_data_end='2022-07-29',source_batch='SYNTHETIC',universe_track='strict_technology')
    report['original_training_contract_reference_sha256']=sem['training_semantics_sha256']
    return context,report,inputs


class Tests(unittest.TestCase):
    def test_exact_three_cells_full_six_binding_and_no_input_mutation(self):
        context,report,inputs=context_fixture();before=deepcopy(context)
        original,changed,identities,binding=m.correct_context(context,report,'2022-07-29')
        self.assertEqual(context,before);expected=inputs['returns'].copy()
        for ticker,date,old,new in m.typed.CORRECTIONS:expected.loc[date,ticker]=new
        pd.testing.assert_frame_equal(expected,changed['returns'],check_freq=False)
        for key in ('nominal_prices','target_returns','universe'):self.assertTrue(inputs[key].equals(changed[key]))
        self.assertEqual(len(binding['corrections']),3);self.assertEqual(len(identities),6)

    def test_nominal_unrelated_return_runtime_future_and_contract_reject(self):
        for mode in ('nominal','other_return','runtime','cutoff','missing'):
            context,report,inputs=context_fixture();cutoff='2022-07-29'
            if mode=='nominal':inputs['nominal_prices'].iloc[0,0]+=1
            if mode=='other_return':inputs['returns'].iloc[0,0]+=.01
            if mode=='runtime':context['runtime']['python']='0'
            if mode=='cutoff':cutoff='2022-08-01'
            if mode=='missing':inputs['contract'].pop('window_days')
            context['prepared_inputs']={k:m.typed.encoding._panel_context(v) for k,v in inputs.items()}
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.correct_context(context,report,cutoff)

    def test_complete_frontier_union_retains_failed_preference_and_no_winner(self):
        fixture=cohort_fixture();report=m.frontier.core.analyze_complete_corrected_date(**fixture)
        preference=report['user_preference_references'][0];report['risk_liquidity_frontier']=[r for r in report['risk_liquidity_frontier'] if r['job_id']!=preference['job_id']]
        queue=m.candidate_queue(report,fixture['complete_overlay']['records'])
        self.assertIn(preference['job_id'],{r['task']['job_id'] for r in queue})
        report['user_preference_references'][0]=deepcopy(preference);report['user_preference_references'][0]['holding_count']=999
        with self.assertRaises(ValueError):m.candidate_queue(report,fixture['complete_overlay']['records'])

    def test_small_real_equal_refit_five_risks_fail_retained_and_forged_boolean_rejected(self):
        context,report,inputs=context_fixture();_,changed,identities,_=m.correct_context(context,report,'2022-07-29')
        selected={identities['GOOG']['security_id']:{k:identities['GOOG'][k] for k in ('ticker','issuer_id','risk_chain')}}
        parameters={k:inputs['contract'][k] for k in m.PARAMETERS}
        fitted=m.fitter.refit_dynamic_cutoff_weights(returns=changed['returns'],cutoff='2022-07-29',selected=selected,weight_spec='equal_weight',previous_target_weights=None,**parameters)
        checks=m.check_fitted(fitted,selected,parameters,'2022-07-29');self.assertFalse(all(checks.values()));self.assertEqual(fitted['effective_anchor_strength'],0.)
        bad=deepcopy(fitted);bad['targets']['security:GOOG']['target_weight']=float('nan')
        with self.assertRaises(ValueError):m.check_fitted(bad,selected,parameters,'2022-07-29')
        bad=deepcopy(fitted);bad['declared_constraint_checks']['MAX_SINGLE_WEIGHT']=True
        with self.assertRaises(ValueError):m.check_fitted(bad,selected,parameters,'2022-07-29')


if __name__=='__main__':unittest.main()
