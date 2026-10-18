"""Adversarial persistence checks; no optimizer is called."""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_return_lane_target_materialization_research as core


class MaterializationPersistenceReview(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)
        self.plan_reference={'path':str(self.folder/'plan.json'),'sha256':'plan'}
        self.state={'sources':{},'plan_reference':self.plan_reference,'runtime':{'fixture':True},
                    'plan':{'selected_job_ids':['job']*6},
                    'first_refit':{'targets':{sid:{'target_weight':0.25} for sid in ('OLD_A','OLD_B','OLD_C','EXITING_D')}},
                    'periods':[{'cutoff':cutoff,'selected':{},'parameters':{},'weight_spec':'equal_weight'}
                               for cutoff in core.CUTOFFS]}
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(core,'prepare_plan',side_effect=lambda reference:deepcopy(self.state)))
        self.stack.enter_context(patch.object(core,'validate_fit',return_value={'all':True}))
        self.stack.enter_context(patch.object(core,'verify_runtime',return_value=None))
        self.stack.enter_context(patch.object(core,'fit_once',side_effect=AssertionError('Optimizer forbidden')))

    def first_without_marker(self):
        raw={'schema':'RETURN_TARGET_RAW_RESULT_V1','execution_date':core.DATES[0],
             'plan_reference':self.plan_reference,'previous_target_reference':None,
             'previous_target_weights':None,'status':'FIT_RETURNED',
             'new_fit_attempt_count':0,'first_fit_imported_without_refit':True,
             'fitted':deepcopy(self.state['first_refit']),
             'started_reference':{'path':str(self.folder/core.DATES[0]/'started.json'),'sha256':'missing'}}
        reference=core.publish(self.folder/core.DATES[0]/'raw.json',raw)
        final={'schema':'RETURN_TARGET_STEP_FINALIZATION_V1','plan_reference':self.plan_reference,
               'execution_date':core.DATES[0],'raw_reference':reference,
               'status':'TARGET_FIVE_RISKS_PASSED','risk_checks':{'all':True},'detail':None,
               'fallback_performed':False,'whole_lot_execution_performed':False,'promotion_allowed':False}
        return core.publish(self.folder/core.DATES[0]/'finalization.json',final)

    def test_previous_raw_without_durable_attempt_cannot_feed_anchor(self):
        reference=self.first_without_marker()
        with self.assertRaises((ValueError,FileNotFoundError)):
            core.run_step(plan_reference=self.plan_reference,output=self.folder,
                          execution_date=core.DATES[1],execute=False,completed_finalizations=[reference])

    def test_skipped_previous_date_never_falls_back(self):
        with self.assertRaises(ValueError):
            core.run_step(plan_reference=self.plan_reference,output=self.folder,
                          execution_date=core.DATES[1],execute=False)

    def test_started_tamper_after_raw_cannot_publish_success(self):
        original_publish=core.publish
        def tamper_after_raw(path,value):
            reference=original_publish(path,value)
            if Path(path).name=='raw.json':
                (Path(path).parent/'started.json').write_text('{}')
            return reference
        with patch.object(core,'publish',side_effect=tamper_after_raw):
            with self.assertRaises(ValueError):
                core.run_step(plan_reference=self.plan_reference,output=self.folder,
                              execution_date=core.DATES[0],execute=True)
        self.assertFalse((self.folder/core.DATES[0]/'finalization.json').exists())

    def import_first(self):
        report=core.run_step(plan_reference=self.plan_reference,output=self.folder,
                             execution_date=core.DATES[0],execute=True)
        self.assertEqual(report['new_fit_attempt_count'],0)
        return report['final_reference']

    def test_next_fit_receives_complete_previous_strategic_target(self):
        first=self.import_first()
        seen=[]
        def observe(state,index,previous):
            seen.append(deepcopy(previous))
            return deepcopy(self.state['first_refit'])
        with patch.object(core,'fit_once',side_effect=observe):
            report=core.run_step(plan_reference=self.plan_reference,output=self.folder,
                                 execution_date=core.DATES[1],execute=True,completed_finalizations=[first])
        self.assertEqual(seen,[{sid:0.25 for sid in ('OLD_A','OLD_B','OLD_C','EXITING_D')}])
        self.assertEqual(report['new_fit_attempt_count'],1)
        self.assertFalse(report['complete_six_period_schedule_published'])

    def test_numerical_failure_is_durable_and_cannot_retry_or_skip(self):
        first=self.import_first()
        with patch.object(core,'fit_once',side_effect=RuntimeError('synthetic numeric failure')) as fit:
            report=core.run_step(plan_reference=self.plan_reference,output=self.folder,
                                 execution_date=core.DATES[1],execute=True,completed_finalizations=[first])
            self.assertEqual(report['status'],'NUMERICAL_FAILURE_STOP')
            self.assertTrue((self.folder/core.DATES[1]/'raw.json').exists())
            with self.assertRaises(ValueError):
                core.run_step(plan_reference=self.plan_reference,output=self.folder,
                              execution_date=core.DATES[1],execute=True,completed_finalizations=[first])
            with self.assertRaises(ValueError):
                core.run_step(plan_reference=self.plan_reference,output=self.folder,
                              execution_date=core.DATES[2],execute=True,
                              completed_finalizations=[first,report['final_reference']])
            self.assertEqual(fit.call_count,1)

    def test_raw_recovery_requires_external_saved_hashes(self):
        self.import_first()
        (self.folder/core.DATES[0]/'finalization.json').unlink()
        with self.assertRaises(ValueError):
            core.run_step(plan_reference=self.plan_reference,output=self.folder,
                          execution_date=core.DATES[0],recover_raw=True)

    def test_unknown_orphan_evidence_prevents_new_attempt(self):
        destination=self.folder/core.DATES[0]
        destination.mkdir()
        (destination/'failure.json').write_text('{}')
        with self.assertRaises(ValueError):
            core.run_step(plan_reference=self.plan_reference,output=self.folder,
                          execution_date=core.DATES[0],execute=True)
        self.assertFalse((destination/'started.json').exists())


class MaterializationNumericalBindingReview(unittest.TestCase):
    def fixture(self):
        import pandas as pd
        calendar=pd.date_range(end='2023-03-31',periods=126,freq='B')
        selected={f'SID{index}':{'ticker':f'T{index}','issuer_id':f'I{index}','risk_chain':f'R{index}'}
                  for index in range(4)}
        frame=pd.DataFrame({f'T{index}':[0.001*(index+1)]*126 for index in range(4)},index=calendar)
        parameters=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,
                        max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,
                        minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
        period=dict(cutoff='2023-03-31',selected=selected,parameters=parameters,returns=frame,weight_spec='equal_weight')
        sources={'synthetic_numerical_source':'fixture'}
        fitted=dict(source_hashes=sources,cutoff='2023-03-31',fit_end='2023-03-31',fit_start=calendar[0].date().isoformat(),
                    fit_row_count=126,declared_parameters={key:value for key,value in parameters.items() if key!='fit_days'},
                    weight_spec='equal_weight',checkpoint_weights_used=False,previous_target_weights={},
                    risk_chains_by_security={sid:row['risk_chain'] for sid,row in selected.items()},
                    surviving_anchor_mass=0,effective_anchor_strength=0,
                    anchor_by_security={sid:0 for sid in selected},
                    targets={sid:{'ticker':row['ticker'],'issuer_id':row['issuer_id'],'target_weight':.25} for sid,row in selected.items()},
                    declared_constraint_checks={key:True for key in ('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')},
                    declared_constraints_passed=True,
                    fit_data_sha256=core.digest(dict(dates=[day.date().isoformat() for day in calendar],
                        tickers=list(frame.columns),returns=frame.to_numpy().tolist())),
                    point_in_time_verified=False,source_authenticity_verified=False,promotion_allowed=False,
                    historical_task_evaluation_performed=False,order_generation_allowed=False)
        return {'periods':[period],'numerical_sources':sources},fitted

    def test_real_validator_binds_matrix_prior_and_permission(self):
        state,fitted=self.fixture()
        self.assertTrue(all(core.validate_fit(state,0,fitted,None).values()))
        for field,value in [('fit_data_sha256','0'*64),('promotion_allowed',True),
                            ('previous_target_weights',{'SID0':1})]:
            changed=deepcopy(fitted);changed[field]=value
            with self.assertRaises(ValueError):
                core.validate_fit(state,0,changed,None)


if __name__=='__main__':
    unittest.main()
