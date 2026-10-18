from contextlib import ExitStack
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_return_lane_target_materialization_research as core


class ReturnTargetTests(unittest.TestCase):
    def fixture(self):
        reference=dict(path='fixture-plan',sha256='a'*64)
        fit=dict(targets={'sid-a':dict(ticker='AAA',issuer_id='issuer-a',target_weight=.6),
                          'sid-b':dict(ticker='BBB',issuer_id='issuer-b',target_weight=.4)},
            risk_chains_by_security={'sid-a':'a','sid-b':'b'})
        periods=[dict(cutoff=cutoff,selected={'sid-a':dict(ticker='AAA',issuer_id='issuer-a',risk_chain='a')},
            parameters={'fit_days':126},weight_spec='constrained_fixed_shrinkage_turnover_anchor') for cutoff in core.CUTOFFS]
        state=dict(plan_reference=reference,plan={'selected_job_ids':['job'+str(i) for i in range(6)]},periods=periods,
            first_refit=fit,sources={},runtime={'fixture':'one'},calendar=list(core.CUTOFFS))
        return reference,state

    def patches(self,state):
        stack=ExitStack()
        stack.enter_context(patch.object(core,'prepare_plan',side_effect=lambda _:copy.deepcopy(state)))
        stack.enter_context(patch.object(core,'verify_runtime'))
        stack.enter_context(patch.object(core,'validate_fit',return_value={'FIVE':True}))
        return stack

    def test_first_import_no_optimizer_and_second_receives_full_target(self):
        reference,state=self.fixture()
        with tempfile.TemporaryDirectory() as folder,self.patches(state),patch.object(core,'fit_once',return_value=state['first_refit']) as fitter:
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
        with tempfile.TemporaryDirectory() as folder,self.patches(state):
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
        with tempfile.TemporaryDirectory() as folder,self.patches(state),patch.object(core,'validate_fit',return_value={'FIVE':False}):
            result=core.run_step(plan_reference=reference,output=folder,execution_date=core.DATES[0],execute=True)
            self.assertEqual(result['status'],'STRATEGY_FIVE_RISKS_FAILED_STOP')
            self.assertFalse((Path(folder)/'schedule.json').exists())

    def test_raw_recovery_requires_external_hash_and_never_refits(self):
        reference,state=self.fixture();original=core.publish
        def crash_final(path,value):
            if Path(path).name=='finalization.json':raise OSError('synthetic crash')
            return original(path,value)
        with tempfile.TemporaryDirectory() as folder,self.patches(state),patch.object(core,'fit_once') as fitter:
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
        with tempfile.TemporaryDirectory() as folder,self.patches(state),patch.object(core,'fit_once',return_value=state['first_refit']) as fitter:
            completed=[]
            for index,day in enumerate(core.DATES):
                result=core.run_step(plan_reference=reference,output=folder,execution_date=day,execute=True,
                    completed_finalizations=completed)
                completed.append(result['final_reference'])
                self.assertEqual(result['complete_six_period_schedule_published'],index==5)
            self.assertEqual(fitter.call_count,5)
            report=json.loads((Path(folder)/'schedule.json').read_bytes())
            self.assertEqual(report['completed_finalization_references'],completed)
            self.assertEqual(len(report['schedule']),6)


if __name__=='__main__':unittest.main()
