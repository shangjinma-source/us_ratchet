import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_twenty_historical_single_target_20260919 as m


def fixture():
    sources={};document=m.read(m.INPUT,sources);plan=m.read(m.PLAN,sources)
    row=next(r for r in plan['delta']['tasks'] if r['task_id']==m.STRUCTURE_TASK)
    fit,task,calendar=m.historical_view(document,row)
    state=dict(task=task,fit_returns=fit,execution_observation_calendar=calendar,input_reference=m.INPUT,
        independent_input_audit_reference=dict(path='audit',sha256='a'*64),structure_reference={'original_task_id':m.STRUCTURE_TASK},
        conditional_coordinate_provenance=[],supplemental_dated_provenance={},static_risk_and_liquidity_roles={},numerical_sources={},historical_expected_source_hashes={})
    sids=sorted(task['selected']);tickers=[task['selected'][s]['ticker'] for s in sids]
    payload=dict(dates=[d.date().isoformat() for d in fit.index],tickers=tickers,returns=fit[tickers].to_numpy().tolist())
    result=dict(schema='ndx_dynamic_cutoff_refit_research_v2',cutoff=task['cutoff'],weight_spec=task['weight_spec'],fit_row_count=126,fit_data_sha256=m.digest(payload),fit_start=payload['dates'][0],fit_end=payload['dates'][-1],declared_parameters={k:float(v) for k,v in task['parameters'].items() if k!='fit_days'},previous_target_weights={},surviving_anchor_mass=0.,effective_anchor_strength=0.,anchor_by_security={s:0. for s in sids},risk_chains_by_security={s:task['selected'][s]['risk_chain'] for s in sids},targets={s:dict(ticker=task['selected'][s]['ticker'],issuer_id=task['selected'][s]['issuer_id'],target_weight=.125) for s in sids},declared_constraint_checks={k:True for k in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')},declared_constraints_passed=True,source_hashes={},projection_reconstruction_audit=dict(schema='ndx_projection_reconstruction_audit_v1',promotion_allowed=False,prior_results_reused=False,attempt_count=1,attempts=[{}]),**dict.fromkeys(('checkpoint_weights_used','point_in_time_verified','source_authenticity_verified','promotion_allowed','historical_task_evaluation_performed','order_generation_allowed'),False))
    return state,result,document,row


class SingleTargetTests(unittest.TestCase):
    def test_actual_fit_view_and_new_historical_job(self):
        state,result,document,row=fixture()
        self.assertEqual(len(state['fit_returns']),126);self.assertEqual(str(state['fit_returns'].index[-1].date()),'2026-03-18')
        self.assertNotEqual(state['task']['task_id'],m.STRUCTURE_TASK);self.assertEqual(len(state['execution_observation_calendar']),127)
        self.assertTrue(m.validate_fit(result,state)['risk_pass'])
        bad=copy.deepcopy(state);bad['fit_returns']=m.typed.decode(document['prices']['returns'])
        with self.assertRaises(ValueError):m.validate_fit(result,bad)

    def test_preflight_zero_calls_and_single_exclusive_fit(self):
        state,result,_,_=fixture()
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'prepare',return_value=state),patch.object(m,'verify_sources',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',return_value=result) as fit:
            self.assertEqual(m.run(directory)['actual_fitter_calls'],0)
            saved=m.run(directory,execute=True);value=json.loads(Path(saved['path']).read_bytes())
            self.assertEqual(value['baseline_close_date'],'2026-03-18');self.assertEqual(value['first_next_open_observation'],'2026-03-19')
            self.assertEqual(len(fit.call_args.kwargs['returns']),126)
            self.assertTrue((Path(directory)/'raw_fit_receipt.json').exists())
            with self.assertRaises(ValueError):m.run(directory,execute=True)
            self.assertEqual(fit.call_count,1)

    def test_raw_result_survives_failed_audit_and_retry_refused(self):
        state,result,_,_=fixture();result['fit_data_sha256']='0'*64
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'prepare',return_value=state),patch.object(m,'verify_sources',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',return_value=result) as fit:
            with self.assertRaises(ValueError):m.run(directory,execute=True)
            self.assertTrue((Path(directory)/'raw_fit_receipt.json').exists());self.assertFalse((Path(directory)/'target.json').exists())
            with self.assertRaises(ValueError):m.run(directory,execute=True)
            self.assertEqual(fit.call_count,1)

    def test_changed_selected_input_rejected_after_raw_preserved(self):
        state,result,_,_=fixture()
        def fitting(**kwargs):
            kwargs['selected'][next(iter(kwargs['selected']))]['risk_chain']='changed'
            return result
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'prepare',return_value=state),patch.object(m,'verify_sources',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=fitting):
            with self.assertRaises(ValueError):m.run(directory,execute=True)
            self.assertTrue((Path(directory)/'raw_fit_receipt.json').exists());self.assertFalse((Path(directory)/'target.json').exists())

    def test_risk_failure_is_retained_as_fit_diagnostic(self):
        state,result,_,_=fixture()
        for sid,weight in zip(sorted(result['targets']),[.4,.1]+[.5/6]*6):result['targets'][sid]['target_weight']=weight
        result['declared_constraint_checks']['MINIMUM_EFFECTIVE_N']=False;result['declared_constraints_passed']=False
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'prepare',return_value=state),patch.object(m,'verify_sources',return_value={}),patch.object(m.fitter,'refit_dynamic_cutoff_weights',return_value=result):
            saved=m.run(directory,execute=True);value=json.loads(Path(saved['path']).read_bytes())
            self.assertEqual(value['status'],'FITTED_FIVE_RISKS_FAILED');self.assertFalse(value['execution_performed'])
            self.assertFalse((Path(directory)/'failure.json').exists())


if __name__=='__main__':unittest.main()
