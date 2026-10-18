"""Independent synthetic provenance and request-count attacks; no actual fit."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_legacy_target_distance_materialization_research as fixtures

m=fixtures.m


def cohort():
    coordinate=dict(selection_date=m.DATES[0],source_batch='batch',universe_track='technology')
    selected={'S':dict(ticker='T',issuer_id='I',risk_chain='R')}
    choice=dict(job_id='chosen',tickers='T',holding_count=1,weight_spec='equal_weight',selected=selected,metrics={'metric':1})
    records=[];diagnostics=[]
    for job in ('chosen','other'):
        task=dict(coordinate,job_id=job,decision_data_end=m.CUTOFFS[0],tickers='T',holding_count=1,weight_spec='equal_weight')
        result=dict(tickers='T',holding_count=1,weight_spec='equal_weight',metric=1)
        records.append(dict(task=task,result=result,status='AVAILABLE'))
        diagnostics.append(dict(job_id=job,fractional_risk_liquidity_passed=True,**result))
    complete=dict(coordinate=coordinate,records=records,original_count=2,economic_inputs_complete=True,pending_count=0)
    frontier=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',coordinate=coordinate,original_decision_data_end=m.CUTOFFS[0],
        original_count=2,candidate_diagnostics=diagnostics,complete_date_artifact=dict(path='full',sha256='a'*64),
        independent_full_diff_artifact=dict(path='diff',sha256='b'*64))
    independent=dict(schema='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1',date=m.DATES[0],original_count=2,
        output_path='full',output_sha256='a'*64,whole_date_task_map_verified=True,ordered_full_record_diff_verified=True,
        full_new_results_match_external_checkpoints=True,output_source_partitions_reverified=True)
    queue=dict(coordinate=coordinate,historical_cutoff=m.CUTOFFS[0],candidates=[],full_original_count=2)
    universe={'T':dict(security_id='S',**selected['S'])}
    return choice,queue,frontier,universe,complete,independent


class IndependentReview(unittest.TestCase):
    def test_full_diff_other_output_and_missing_cohort_diagnostic_rejected(self):
        for attack in ('diff_path','diff_sha','diff_flag','omit_record','omit_diagnostic','duplicate_diagnostic','pending','pending_bool','queue_count','queue_membership'):
            choice,queue,frontier,universe,complete,diff=cohort()
            if attack=='diff_path':diff['output_path']='other'
            if attack=='diff_sha':diff['output_sha256']='c'*64
            if attack=='diff_flag':diff['ordered_full_record_diff_verified']=1
            if attack=='omit_record':complete['records'].pop()
            if attack=='omit_diagnostic':frontier['candidate_diagnostics'].pop()
            if attack=='duplicate_diagnostic':frontier['candidate_diagnostics'][1]=deepcopy(frontier['candidate_diagnostics'][0])
            if attack=='pending':complete['pending_count']=1
            if attack=='pending_bool':complete['pending_count']=False
            if attack=='queue_count':queue['full_original_count']=1
            if attack=='queue_membership':queue['candidates']=[complete['records'][0]]
            with self.subTest(attack=attack),patch.object(m,'read',side_effect=[complete,diff]),self.assertRaises(ValueError):
                m.complete_candidate(choice,queue,frontier,universe,{})

    def test_task_scope_identity_and_metric_attacks_rejected(self):
        for attack in ('scope','cutoff','issuer','sid','metric','risk','cardinality'):
            choice,queue,frontier,universe,complete,diff=cohort()
            if attack=='scope':complete['records'][0]['task']['universe_track']='other'
            if attack=='cutoff':complete['records'][0]['task']['decision_data_end']='2023-04-01'
            if attack=='issuer':universe['T']['issuer_id']='OTHER'
            if attack=='sid':universe['T']['security_id']='OTHER'
            if attack=='metric':complete['records'][0]['result']['metric']=2
            if attack=='risk':universe['T']['risk_chain']='OTHER'
            if attack=='cardinality':complete['records'][0]['task']['holding_count']=True
            with self.subTest(attack=attack),patch.object(m,'read',side_effect=[complete,diff]),self.assertRaises(ValueError):
                m.complete_candidate(choice,queue,frontier,universe,{})

    def test_valid_full_cohort_does_not_require_old_queue_job(self):
        choice,queue,frontier,universe,complete,diff=cohort()
        with patch.object(m,'read',side_effect=[complete,diff]):selected,provenance=m.complete_candidate(choice,queue,frontier,universe,{})
        self.assertEqual(selected,choice['selected']);self.assertFalse(provenance['old_queue_candidate_present'])
        self.assertEqual(provenance['independent_full_diff_reference'],frontier['independent_full_diff_artifact'])

    def test_class_switch_full_prior_separate_from_surviving_sid(self):
        state=fixtures.fixture();old='security:issuer:CLASS_A';new='security:issuer:CLASS_C';enph='security:enph:COMMON'
        a=dict(ticker='GOOGL',issuer_id='issuer:alphabet',risk_chain='platform')
        c=dict(ticker='GOOG',issuer_id='issuer:alphabet',risk_chain='platform')
        e=dict(ticker='ENPH',issuer_id='issuer:enph',risk_chain='energy')
        state['periods'][2]['selected']={old:a,enph:e}
        state['periods'][3]['selected']={new:c,enph:e}
        state['periods'][3]['universe_by_sid']={old:a,new:c,enph:e}
        prior={old:.7,enph:.3};binding=m.lane_binding(state,3,prior)
        self.assertEqual(binding['fit_actual_previous_target_weights'],prior)
        self.assertEqual(set(binding['lane_risk_chains_by_security']),{old,new,enph})
        self.assertEqual(sum(prior.get(sid,0) for sid in state['periods'][3]['selected']),.3)
        with patch('backtest.ndx_dynamic_cutoff_refit_v2_research.refit_dynamic_cutoff_weights',return_value={}) as wrapper:
            state['periods'][3]['returns']='synthetic';m.fit_once(state,3,prior)
            self.assertEqual(wrapper.call_args.kwargs['previous_target_weights'],prior)
        del state['periods'][3]['universe_by_sid'][old]
        with self.assertRaises(ValueError):m.lane_binding(state,3,prior)

    def test_preflight_counts_not_actual_and_unresolved_started_no_retry(self):
        state=fixtures.fixture()
        with tempfile.TemporaryDirectory() as folder,fixtures.patches(state,folder),patch.object(m,'fit_once') as wrapper:
            result=m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0])
            self.assertNotIn('wrapper_call_attempt_count',result)
            self.assertEqual(result['planned_operation_counts']['deterministic_generation_request_count'],1)
            self.assertFalse(result['fit_performed']);wrapper.assert_not_called()
            path=Path(folder)/m.DATES[0];path.mkdir();(path/'started.json').write_text('{}')
            with self.assertRaises(ValueError):m.run_step(plan_reference=state['plan_reference'],output=folder,execution_date=m.DATES[0],execute=True)
            wrapper.assert_not_called()


if __name__=='__main__':unittest.main()
