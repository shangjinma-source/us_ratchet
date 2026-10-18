"""Synthetic single attempts and equal-only wrapper checks; no numerical optimizer."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_legacy_target_distance_materialization_research as m


def fixture():
    identity={f'S{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',risk_chain=f'R{i}') for i in range(7)}
    sets=[range(4),range(1,5),range(4),range(2,6),range(6),range(3,7)]
    periods=[]
    for i,indices in enumerate(sets):
        periods.append(dict(cutoff=m.CUTOFFS[i],selected={f'S{j}':identity[f'S{j}'] for j in indices},
            weight_spec=m.SPECS[i],parameters={'fit_days':126},universe_by_sid=deepcopy(identity),
            context_reference={},corrected_input_binding={},candidate_provenance={'origin':'synthetic'}))
    return dict(plan=m.expected_plan(),plan_reference={'path':'fixture','sha256':'a'*64},periods=periods,
        sources={},runtime={},calendar=sorted(m.CUTOFFS+m.DATES))


def fitted(state,index,previous):
    selected=state['periods'][index]['selected']
    return dict(targets={sid:dict(ticker=v['ticker'],issuer_id=v['issuer_id'],target_weight=1./len(selected)) for sid,v in selected.items()})


def patches(state,folder):
    stack=ExitStack();state['plan_reference']['path']=str(Path(folder)/'plan.json')
    stack.enter_context(patch.object(m,'OUTPUT',Path(folder)))
    stack.enter_context(patch.object(m,'prepare_plan',side_effect=lambda _:deepcopy(state)))
    stack.enter_context(patch.object(m,'verify_runtime'))
    stack.enter_context(patch.object(m,'validate_fit',return_value={'FIVE':True}))
    return stack


class LegacyTests(unittest.TestCase):
    def test_six_modes_counts_variable_k_and_full_prior(self):
        state=fixture()
        with tempfile.TemporaryDirectory() as folder,patches(state,folder),patch.object(m,'fit_once',side_effect=fitted) as wrapper:
            refs=[];previous=None;requests=[]
            for i,day in enumerate(m.DATES):
                result=m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=day,execute=True,completed_finalizations=refs)
                refs.append(result['final_reference']);requests.append(result['numerical_fit_request_count'])
                self.assertEqual(wrapper.call_args.args[2],previous)
                start=json.loads((Path(folder)/day/'started.json').read_bytes())
                self.assertNotIn('wrapper_call_attempt_count',start)
                self.assertEqual(start['planned_operation_counts']['wrapper_call_attempt_count'],1)
                raw=json.loads((Path(folder)/day/'raw.json').read_bytes())
                self.assertEqual(raw['import_count'],0)
                self.assertEqual(raw['materialization_mode'],m.MODES[i])
                self.assertIs(raw['optimizer_called_by_equal_branch'],False if m.MODES[i]=='DETERMINISTIC_EQUAL' else None)
                previous={sid:v['target_weight'] for sid,v in raw['fitted']['targets'].items()}
            self.assertEqual(wrapper.call_count,6);self.assertEqual(requests,[0,1,1,1,0,0])
            schedule=json.loads((Path(folder)/'schedule.json').read_bytes())
            self.assertEqual([len(r['targets']) for r in schedule['schedule']],[4,4,4,4,6,4])
            self.assertEqual(len(schedule['completed_finalization_references']),6)

    def test_numerical_failure_and_risk_failure_stop_without_fallback(self):
        state=fixture()
        with tempfile.TemporaryDirectory() as folder,patches(state,folder),patch.object(m,'fit_once',side_effect=RuntimeError('failure')):
            result=m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],execute=True)
            self.assertEqual(result['status'],'NUMERICAL_FAILURE_STOP')
            self.assertEqual(result['deterministic_generation_request_count'],1)
            with self.assertRaises(ValueError):m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[1],completed_finalizations=[result['final_reference']])
        with tempfile.TemporaryDirectory() as folder,patches(state,folder),patch.object(m,'fit_once',side_effect=fitted),patch.object(m,'validate_fit',return_value={'FIVE':False}):
            result=m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],execute=True)
            self.assertEqual(result['status'],'STRATEGY_FIVE_RISKS_FAILED_STOP')

    def test_crash_after_raw_external_recovery_never_calls_again(self):
        state=fixture();original=m.publish
        def publish(path,value):
            if Path(path).name=='finalization.json':raise OSError('crash')
            return original(path,value)
        with tempfile.TemporaryDirectory() as folder,patches(state,folder),patch.object(m,'fit_once',side_effect=fitted) as wrapper:
            with patch.object(m,'publish',side_effect=publish),self.assertRaises(OSError):
                m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],execute=True)
            with self.assertRaises(ValueError):m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],execute=True)
            def ref(name):
                p=Path(folder)/m.DATES[0]/name
                return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            result=m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],recover_raw=True,
                recovery_raw_reference=ref('raw.json'),recovery_started_reference=ref('started.json'))
            self.assertTrue(result['raw_recovered_without_refit']);self.assertEqual(wrapper.call_count,1)

    def test_fixed_namespace_and_raw_count_boolean_rejected(self):
        with patch.object(m,'prepare_plan') as prepare:
            with self.assertRaises(ValueError):m.run_step(plan_reference={},output=m.OUTPUT.with_name('copy'),execution_date=m.DATES[0])
            prepare.assert_not_called()
        state=fixture();raw=dict(schema='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1',plan_reference=state['plan_reference'],
            execution_date=m.DATES[0],previous_target_reference=None,previous_target_weights=None,started_reference={},
            **m.mode_counts(0),numerical_and_lane_binding=m.lane_binding(state,0,None),status='FIT_RETURNED',fitted={})
        m.validate_raw_envelope(state,0,raw,None,None,{})
        raw['wrapper_call_attempt_count']=True
        with self.assertRaises(ValueError):m.validate_raw_envelope(state,0,raw,None,None,{})

    def test_equal_wrapper_k4_k6_has_no_optimizer_and_preserves_prior(self):
        import pandas as pd
        from backtest import ndx_dynamic_cutoff_refit_v2_research as wrapper
        from backtest import ndx_joint_weight_evaluation_v2 as evaluation
        from backtest import ndx_concentration_projection_v2 as projection
        def forbidden(*args,**kwargs):raise AssertionError('Equal may not invoke shrinkage')
        original_bind=evaluation._bind
        def bind(function,**dependencies):
            if function is evaluation._SHRINKAGE:return forbidden
            return original_bind(function,**dependencies)
        for i in (0,4,5):
            state=fixture();period=state['periods'][i];names=[v['ticker'] for v in period['selected'].values()]
            period['parameters']=dict(fit_days=126,shrinkage_intensity=.35,turnover_anchor_strength=.25,
                max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
            period['returns']=pd.DataFrame({name:[.001]*126 for name in names},index=pd.date_range(end=m.CUTOFFS[i],periods=126))
            previous=None if i==0 else {sid:1./len(state['periods'][i-1]['selected']) for sid in state['periods'][i-1]['selected']}
            with patch.object(evaluation,'_bind',bind),patch.object(projection,'minimize',side_effect=AssertionError('No optimizer')) as optimizer:
                result=m.fit_once(state,i,previous)
                optimizer.assert_not_called()
            self.assertEqual(result['previous_target_weights'],previous or {})
            self.assertEqual(result['effective_anchor_strength'],0)
            self.assertTrue(all(v['target_weight']==1./len(names) for v in result['targets'].values()))
            self.assertEqual(result['projection_reconstruction_audit']['attempt_count'],0)
            state['numerical_sources']=result['source_hashes']
            period.update(decision_date=m.CUTOFFS[i],execution_date=m.DATES[i])
            self.assertTrue(all(m.validate_fit(state,i,result,previous).values()))
            bad=deepcopy(result);sids=list(bad['targets'])
            bad['targets'][sids[0]]['target_weight']+=.01;bad['targets'][sids[1]]['target_weight']-=.01
            with self.assertRaises(ValueError):m.validate_fit(state,i,bad,previous)

    def test_complete_candidate_requires_full_diff_and_keeps_old_queue_absence(self):
        selected={'S':dict(ticker='T',issuer_id='I',risk_chain='R')};coordinate=dict(selection_date='2023-04-03',source_batch='b',universe_track='u')
        task=dict(coordinate,job_id='j',decision_data_end='2023-03-31',tickers='T',holding_count=1,weight_spec='equal_weight')
        choice=dict(job_id='j',tickers='T',holding_count=1,weight_spec='equal_weight',selected=selected,metrics={'x':1})
        result=dict(tickers='T',holding_count=1,weight_spec='equal_weight',x=1)
        queue=dict(coordinate=coordinate,historical_cutoff='2023-03-31',candidates=[],full_original_count=1)
        universe={'T':dict(security_id='S',**selected['S'])}
        with tempfile.TemporaryDirectory() as folder:
            full=m.publish(Path(folder)/'full.json',dict(coordinate=coordinate,original_count=1,economic_inputs_complete=True,pending_count=0,
                records=[dict(task=task,result=result,status='AVAILABLE')]))
            diff=dict(schema='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1',date='2023-04-03',original_count=1,
                output_path=full['path'],output_sha256=full['sha256'],**dict.fromkeys(('whole_date_task_map_verified','ordered_full_record_diff_verified',
                    'full_new_results_match_external_checkpoints','output_source_partitions_reverified'),True))
            diffref=m.publish(Path(folder)/'diff.json',diff)
            frontier=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',coordinate=coordinate,original_decision_data_end='2023-03-31',
                original_count=1,complete_date_artifact=full,independent_full_diff_artifact=diffref,
                candidate_diagnostics=[dict(job_id='j',fractional_risk_liquidity_passed=True,**result)])
            restored,provenance=m.complete_candidate(choice,queue,frontier,universe,{})
            self.assertEqual(restored,selected);self.assertFalse(provenance['old_queue_candidate_present'])
            diff['output_sha256']='0'*64;frontier['independent_full_diff_artifact']=m.publish(Path(folder)/'bad.json',diff)
            with self.assertRaises(ValueError):m.complete_candidate(choice,queue,frontier,universe,{})


if __name__=='__main__':unittest.main()
