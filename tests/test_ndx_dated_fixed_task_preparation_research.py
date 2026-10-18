"""Synthetic fixed compositions only, no saved source materialization/fit."""
from copy import deepcopy
import unittest
from backtest import ndx_dated_fixed_task_preparation_research as m
from backtest import ndx_dated_training_panel_research as training
from test_ndx_dated_training_panel_research import fixture as training_fixture


def fixture():
    panel=training.prepare_dated_training_panel(**training_fixture());selected=panel['fit_payload']['selected_by_security'];eligible=[s for s in selected if s!='S001']
    refs={k:dict(path=k+'.json',sha256='a'*64) for k in ('training','training_audit','prior','plan')}
    sources={str(i):format(i,'064x') for i in range(25)}
    ctx=dict(decision_cutoff='2026-09-21',parameters=deepcopy(m.PARAMETERS),weight_specs=deepcopy(m.SPECS),previous_target_weights=None,fitter_source_fingerprint=m.digest(sources),shard_size=1000,order_version='ISSUER_SID_PREFIX_LEX_V1',group_fingerprint='b'*64)
    plan=dict(schema='ISSUER_ALL_K_LAZY_INTERVAL_PLAN_V1',context=ctx,fitter_source_hashes=sources,plan_id='c'*64,planned_canonical_task_count=m.FULL_TASK_COUNT,cardinalities=[dict(k=k,planned_combination_count=10000000 if 4<=k<=20 else 0) for k in range(1,77)])
    combinations=[];positions=[]
    olddates=panel['evaluation_references'][0]['return_end_dates']
    for k in range(4,21):
        for rank in range(32):
            prefix=sorted(eligible[rank:rank+k]);position=dict(k=k,rank=rank,prefix_security_ids=prefix,selection_kind='SID_COVERAGE',proposal_index=len(positions));positions.append(position)
            chosen={s:deepcopy(selected[s]) for s in prefix};matrix=dict(dates=olddates,tickers=[chosen[s]['ticker'] for s in prefix],returns=[[.02]*k for _ in range(126)]);matrixsha=m.digest(matrix);tasks=[]
            for si,spec in enumerate(m.SPECS):
                identity=dict(schema='ISSUER_CANONICAL_NUMERICAL_TASK_IDENTITY_V1',cutoff='2026-09-21',holding_count=k,selected=chosen,weight_spec=spec,parameters=deepcopy(m.PARAMETERS),requested_previous_target_weights=None,fit_data_sha256=matrixsha,fitter_source_fingerprint=ctx['fitter_source_fingerprint'])
                location=dict(schema='ISSUER_PREFIX_TASK_LOCATION_IDENTITY_V1',plan_reference=refs['plan'],plan_id=plan['plan_id'],shard_id=m.digest(dict(ctx,k=k,start=0,stop=1000)),order_version=ctx['order_version'],group_fingerprint=ctx['group_fingerprint'],k=k,rank=rank,spec_index=si,weight_spec=spec)
                tasks.append(dict(numerical_task_id=m.digest(identity),numerical_identity=identity,location_id=m.digest(location),location_identity=location,status='MATERIALIZED_NOT_ATTEMPTED',wrapper_call_attempt_count=0,fit_performed=False))
            combinations.append(dict(k=k,rank=rank,prefix_security_ids=prefix,fitter_sorted_security_ids=prefix,selection_position=position,fit_matrix=matrix,fit_data_sha256=matrixsha,tasks=tasks))
    old=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_V1',status='PREPARED_NOT_ATTEMPTED',materialized=dict(plan_reference=refs['plan'],plan_id=plan['plan_id'],fitter_source_hashes=sources,materialized_task_count=1632,combination_count=544,full_plan_task_denominator=m.FULL_TASK_COUNT,combinations=combinations),schedule=dict(positions=positions),fit_performed=False,point_in_time_verified=False,legal_training_input_admitted=False,execution_authorized=False,winner_selected=False)
    return dict(training_panel=panel,training_reference=refs['training'],training_readback_reference=refs['training_audit'],prior_preparation=old,prior_preparation_reference=refs['prior'],original_lazy_plan=plan,original_plan_reference=refs['plan'])


def resign(panel):
    panel['training_frame_sha256']=m.digest(panel['fit_payload']['returns']);panel['fit_payload_sha256']=m.digest(panel['fit_payload']);panel['content_sha256']=m.digest({k:v for k,v in panel.items() if k!='content_sha256'})


class TasksTests(unittest.TestCase):
    def test_fixed_compositions_all_new_ids(self):
        a=fixture();out=m.prepare_dated_tasks(**a)
        self.assertEqual(len(out['combinations']),544);self.assertEqual(out['materialized_task_count'],1632);self.assertFalse(set(out['new_unattempted_numerical_task_ids'])&set(out['prior_different_cutoff_numerical_task_ids']))
        self.assertEqual(out['full_plan_task_denominator'],m.FULL_TASK_COUNT);self.assertEqual(out['new_cutoff_completed_task_count'],0)
        for c,old in zip(out['combinations'],a['prior_preparation']['materialized']['combinations']):
            self.assertEqual(c['prefix_security_ids'],old['prefix_security_ids']);self.assertEqual(c['fit_matrix']['dates'][-1],'2026-03-20');self.assertEqual(len(c['tasks']),3)
            self.assertEqual(c['tasks'][0]['complete_prior_different_cutoff_task'],old['tasks'][0]);self.assertIsNone(c['tasks'][0]['numerical_identity']['requested_previous_target_weights'])

    def test_only_changed_cutoff_or_future_matrix_rejected(self):
        for mode in ('future','oldvalues','prior'):
            a=fixture();p=a['training_panel']
            if mode=='future':p['fit_payload']['returns']['index'][-1]='2026-03-23T00:00:00'
            elif mode=='oldvalues':p['fit_payload']['returns']['data'][0][0]=.02
            else:a['original_lazy_plan']['context']['previous_target_weights']={}
            resign(p)
            with self.assertRaises(ValueError):m.prepare_dated_tasks(**a)

    def test_reordered_sid_location_and_spec_attack(self):
        for mode in ('sid','location','spec','count'):
            a=fixture();c=a['prior_preparation']['materialized']['combinations'][0]
            if mode=='sid':c['fitter_sorted_security_ids']=list(reversed(c['fitter_sorted_security_ids']))
            elif mode=='location':
                t=c['tasks'][0];t['location_identity']['plan_reference']=dict(path='other',sha256='a'*64);t['location_id']=m.digest(t['location_identity'])
            elif mode=='spec':c['tasks'].reverse()
            else:a['prior_preparation']['materialized']['materialized_task_count']=True
            with self.assertRaises(ValueError):m.prepare_dated_tasks(**a)

if __name__=='__main__':unittest.main()
