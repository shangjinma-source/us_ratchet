from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_drawdown_lane_target_materialization_research as core


class DrawdownTargetTests(unittest.TestCase):
    def test_sealed_lane_and_import_coordinates(self):
        sources={}
        lane=core.read(core.HARD_LANE,sources)
        self.assertEqual(core.OUTPUT.name,'drawdown_lane_targets_20260923_v1')
        self.assertEqual(core.expected_plan()['schema'],'DRAWDOWN_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1')
        for index,decision in enumerate(lane['decisions']):
            choices=decision['lanes']['DRAWDOWN']
            self.assertEqual(len(choices),1)
            self.assertEqual(choices[0]['job_id'],core.JOBS[index])
            self.assertEqual({v['ticker'] for v in choices[0]['selected'].values()},{'BKR','CDNS','ENPH','FTNT'})
            self.assertEqual(choices[0]['weight_spec'],'constrained_fixed_shrinkage' if index==5 else 'constrained_fixed_shrinkage_turnover_anchor')
        for index,ref,audit_ref in ((0,core.HARD_FIRST,core.HARD_AUDIT),(5,core.HARD_LAST,core.HARD_LAST_AUDIT)):
            wrapper=core.read(ref,sources);audit=core.read(audit_ref,sources)
            matches=[row for row in audit['details'] if row['job_id']==core.JOBS[index]]
            self.assertEqual(len(matches),1)
            self.assertEqual(matches[0]['result_reference'],ref)
            self.assertEqual(matches[0]['status'],'FITTED_FIVE_RISKS_PASSED')
            fitted=wrapper['result']['refit']
            self.assertEqual(fitted['previous_target_weights'],{})
            self.assertEqual(fitted['effective_anchor_strength'],0)
            self.assertEqual(matches[0]['typed_decimal']['fit_data_sha256'],fitted['fit_data_sha256'])
            self.assertTrue(all(value is True for value in matches[0]['typed_decimal']['decimal_risks']['checks'].values()))
        core.verify(sources)

    def fixture(self):
        reference=dict(path='fixture-plan',sha256='a'*64)
        fit=dict(targets={'sid-a':dict(ticker='AAA',issuer_id='issuer-a',target_weight=.6),
                          'sid-b':dict(ticker='BBB',issuer_id='issuer-b',target_weight=.4)},
            risk_chains_by_security={'sid-a':'a','sid-b':'b'})
        periods=[dict(cutoff=cutoff,selected={'sid-a':dict(ticker='AAA',issuer_id='issuer-a',risk_chain='a'),'sid-b':dict(ticker='BBB',issuer_id='issuer-b',risk_chain='b')},
            parameters={'fit_days':126},weight_spec='constrained_fixed_shrinkage_turnover_anchor') for cutoff in core.CUTOFFS]
        state=dict(plan_reference=reference,plan={'selected_job_ids':['job'+str(i) for i in range(6)]},periods=periods,
            first_refit=fit,last_refit=copy.deepcopy(fit),sources={},runtime={'fixture':'one'},calendar=list(core.CUTOFFS))
        for period in periods:
            period.update(universe_by_sid=copy.deepcopy(period['selected']),context_reference={'path':'fixture-context','sha256':'b'*64},corrected_input_binding={})
        return reference,state

    def patches(self,state,folder):
        state['plan_reference']['path']=str(Path(folder)/'plan.json')
        stack=ExitStack()
        stack.enter_context(patch.object(core,'OUTPUT',Path(folder)))
        stack.enter_context(patch.object(core,'prepare_plan',side_effect=lambda _:copy.deepcopy(state)))
        stack.enter_context(patch.object(core,'verify_runtime'))
        stack.enter_context(patch.object(core,'validate_fit',return_value={'FIVE':True}))
        return stack

    def test_first_import_no_optimizer_and_second_receives_full_target(self):
        reference,state=self.fixture()
        with tempfile.TemporaryDirectory() as folder,self.patches(state,folder),patch.object(core,'fit_once',return_value=state['first_refit']) as fitter:
            first=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            fitter.assert_not_called()
            second=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[1],execute=True,
                completed_finalizations=[first['final_reference']])
            self.assertEqual(second['status'],'TARGET_FIVE_RISKS_PASSED')
            self.assertEqual(fitter.call_args.args[2],{'sid-a':.6,'sid-b':.4})
            with self.assertRaisesRegex(ValueError,'already finalized'):
                core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[1],execute=True,
                    completed_finalizations=[first['final_reference']])
            self.assertEqual(fitter.call_count,1)

    def test_numerical_failure_is_raw_saved_and_blocks_successors(self):
        reference,state=self.fixture()
        with tempfile.TemporaryDirectory() as folder,self.patches(state,folder):
            first=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            with patch.object(core,'fit_once',side_effect=RuntimeError('solver failed')) as fitter:
                second=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[1],execute=True,
                    completed_finalizations=[first['final_reference']])
                self.assertEqual(second['status'],'NUMERICAL_FAILURE_STOP')
                raw=json.loads((Path(folder)/core.DATES[1]/'raw.json').read_bytes())
                self.assertEqual(raw['error'],'solver failed')
                with self.assertRaisesRegex(ValueError,'unsuccessful'):
                    core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[2],execute=True,
                        completed_finalizations=[first['final_reference'],second['final_reference']])
                self.assertEqual(fitter.call_count,1)

    def test_strategy_risk_failure_is_distinct(self):
        reference,state=self.fixture()
        with tempfile.TemporaryDirectory() as folder,self.patches(state,folder),patch.object(core,'validate_fit',return_value={'FIVE':False}):
            result=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            self.assertEqual(result['status'],'STRATEGY_FIVE_RISKS_FAILED_STOP')
            self.assertFalse((Path(folder)/'schedule.json').exists())

    def test_raw_recovery_requires_external_hash_and_never_refits(self):
        reference,state=self.fixture();original=core.publish
        def crash_final(path,value):
            if Path(path).name=='finalization.json':raise OSError('synthetic crash')
            return original(path,value)
        with tempfile.TemporaryDirectory() as folder,self.patches(state,folder),patch.object(core,'fit_once') as fitter:
            with patch.object(core,'publish',side_effect=crash_final),self.assertRaises(OSError):
                core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            with self.assertRaisesRegex(ValueError,'Existing attempt'):
                core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            with self.assertRaisesRegex(ValueError,'Externally bound'):
                core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],recover_raw=True)
            def ref(name):
                path=Path(folder)/core.DATES[0]/name
                return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            result=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],recover_raw=True,
                recovery_raw_reference=ref('raw.json'),recovery_started_reference=ref('started.json'))
            self.assertTrue(result['raw_recovered_without_refit']);fitter.assert_not_called()

    def test_complete_schedule_requires_all_six_finalization_references(self):
        reference,state=self.fixture()
        with tempfile.TemporaryDirectory() as folder,self.patches(state,folder),patch.object(core,'fit_once',return_value=state['first_refit']) as fitter:
            completed=[]
            for index,day in enumerate(core.DATES):
                result=core.run_step(plan_reference=reference,output=folder,execution_date=day,execute=True,
                    completed_finalizations=completed)
                completed.append(result['final_reference'])
                self.assertEqual(result['complete_six_period_schedule_published'],index==5)
            self.assertEqual(fitter.call_count,4)
            report=json.loads((Path(folder)/'schedule.json').read_bytes())
            self.assertEqual(report['completed_finalization_references'],completed)
            self.assertEqual(len(report['schedule']),6)
            last=json.loads((Path(folder)/core.DATES[-1]/'raw.json').read_bytes())
            self.assertEqual(last['new_fit_attempt_count'],0)
            self.assertEqual(last['numerical_and_lane_binding']['fit_actual_previous_target_weights'],{})
            self.assertEqual(last['numerical_and_lane_binding']['lane_previous_target_weights'],{'sid-a':.6,'sid-b':.4})
            self.assertEqual(last['fitted'],state['last_refit'])

    def test_lane_union_retains_exits_and_missing_current_risk_fails(self):
        reference,state=self.fixture()
        state['periods'][0]['selected']['sid-exit']=dict(ticker='OLD',issuer_id='issuer-old',risk_chain='old-chain')
        state['periods'][1]['universe_by_sid']['sid-exit']=copy.deepcopy(state['periods'][0]['selected']['sid-exit'])
        prior={'sid-a':.4,'sid-b':.4,'sid-exit':.2}
        binding=core.lane_binding(state,1,prior)
        self.assertEqual(binding['lane_risk_chains_by_security']['sid-exit'],'old-chain')
        self.assertEqual(binding['fit_actual_previous_target_weights'],prior)
        del state['periods'][1]['universe_by_sid']['sid-exit']
        with self.assertRaises(ValueError):core.lane_binding(state,1,prior)

    def test_output_copy_fails_before_prepare_and_import_cannot_call_fitter(self):
        with patch.object(core,'prepare_plan',side_effect=AssertionError('Must fail before prepare')):
            with self.assertRaises(ValueError):core.run_step(plan_reference={},output=core.OUTPUT.with_name('copy'),execution_date=core.DATES[0])
        for index in (0,5):
            with self.assertRaises(ValueError):core.fit_once({},index,None)

    def test_last_import_validates_original_prior_not_lane_prior(self):
        import pandas as pd
        from backtest import ndx_dynamic_refit_schedule_research as schedule
        reference,state=self.fixture();period=state['periods'][5]
        period['returns']=pd.DataFrame({'AAA':[.001]*126,'BBB':[.002]*126},index=pd.date_range('2023-01-01',periods=126))
        fitted=state['last_refit'];fitted['previous_target_weights']={}
        fitted['fit_data_sha256']=core.digest(dict(dates=[d.date().isoformat() for d in period['returns'].index],
            tickers=['AAA','BBB'],returns=period['returns'].to_numpy().tolist()))
        fitted.update(dict.fromkeys(('point_in_time_verified','source_authenticity_verified','promotion_allowed',
            'historical_task_evaluation_performed','order_generation_allowed'),False))
        state['numerical_sources']={};prior={'sid-a':.6,'sid-b':.4}
        with patch.object(schedule,'_validate_refit',return_value={'FIVE':True}) as validator:
            core.validate_fit(state,5,copy.deepcopy(fitted),prior)
            self.assertIsNone(validator.call_args.args[2])
            changed=copy.deepcopy(fitted);changed['previous_target_weights']=prior
            with self.assertRaisesRegex(ValueError,'original numerical provenance'):core.validate_fit(state,5,changed,prior)


if __name__=='__main__':unittest.main()
