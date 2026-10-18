"""Independent synthetic source/mode attacks; no producer or numerical imports."""
from copy import deepcopy
from pathlib import Path
import unittest
from scripts import ndx_legacy_target_distance_prefix_independent_readback_20260923 as m
import test_ndx_legacy_target_distance_prefix_independent_readback_20260923 as owner


def cohort():
    coordinate=dict(selection_date='2023-04-03',source_batch='batch',universe_track='track')
    task=dict(coordinate,job_id='job',decision_data_end='2023-03-31',tickers='GOOGL',holding_count=1,weight_spec='equal_weight')
    result=dict(tickers='GOOGL',holding_count=1,weight_spec='equal_weight',distance=.1)
    selected={'class-a':dict(ticker='GOOGL',issuer_id='ALPHABET',risk_chain='internet')}
    choice=dict(job_id='job',tickers='GOOGL',holding_count=1,weight_spec='equal_weight',selected=selected,metrics={'distance':.1})
    records=[dict(task=task,result=result,status='AVAILABLE'),dict(task=dict(task,job_id='other'),result=deepcopy(result),status='AVAILABLE')]
    diagnostics=[dict(result,job_id=job,fractional_risk_liquidity_passed=True) for job in ('job','other')]
    ref=dict(path=str((Path.cwd()/'synthetic-complete.json').resolve()),sha256='a'*64)
    frontier=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',coordinate=coordinate,original_decision_data_end='2023-03-31',
        original_count=2,candidate_diagnostics=diagnostics,complete_date_artifact=ref,independent_full_diff_artifact={'path':'diff','sha256':'b'*64})
    complete=dict(coordinate=coordinate,records=records,original_count=2,economic_inputs_complete=True,pending_count=0)
    independent=dict(schema='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1',date='2023-04-03',original_count=2,
        output_path=ref['path'],output_sha256=ref['sha256'],**dict.fromkeys(('whole_date_task_map_verified','ordered_full_record_diff_verified',
            'full_new_results_match_external_checkpoints','output_source_partitions_reverified'),True))
    return dict(choice=choice,queue=dict(coordinate=coordinate,historical_cutoff='2023-03-31',full_original_count=2,candidates=[]),
        frontier=frontier,complete=complete,independent=independent,universe=deepcopy(selected))


class LegacyIndependentReview(unittest.TestCase):
    def test_complete_source_and_different_diff_or_missing_cohort(self):
        args=cohort();selected,provenance=m.recover_full_candidate(**args)
        self.assertEqual(selected,args['choice']['selected']);self.assertFalse(provenance['old_queue_candidate_present'])
        for attack in ('diffpath','diffsha','missing','duplicate','scope','pending','invent_queue'):
            bad=deepcopy(args)
            if attack=='diffpath':bad['independent']['output_path']=str(Path.cwd()/'other.json')
            if attack=='diffsha':bad['independent']['output_sha256']='f'*64
            if attack=='missing':bad['complete']['records'].pop()
            if attack=='duplicate':bad['complete']['records'][1]=deepcopy(bad['complete']['records'][0])
            if attack=='scope':bad['complete']['records'][0]['task']['universe_track']='other'
            if attack=='pending':bad['complete']['pending_count']=False
            if attack=='invent_queue':bad['queue']['candidates']=[{'task':{'job_id':'job'}}]
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.recover_full_candidate(**bad)

    def test_same_issuer_wrong_security_is_not_same_candidate(self):
        args=cohort();args['universe']['class-c']=args['universe'].pop('class-a')
        with self.assertRaisesRegex(ValueError,'Typed selected'):m.recover_full_candidate(**args)

    def test_fake_equal_counts_and_started_actual_count_rejected(self):
        for attack in ('mode','numeric','import','planned','actual_on_started'):
            args=owner.step(4,6)
            if attack=='mode':args['raw']['materialization_mode']='NEW_ANCHORED_FIT'
            if attack=='numeric':args['raw']['numerical_fit_request_count']=1
            if attack=='import':args['final']['import_count']=1
            if attack=='planned':args['started']['planned_operation_counts']['deterministic_generation_request_count']=False
            if attack=='actual_on_started':args['started']['wrapper_call_attempt_count']=1
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_step(**args)

    def test_equal_cannot_claim_numerical_projection_recovery(self):
        args=owner.step(4,6)
        args['raw']['fitted']['projection_reconstruction_audit']=dict(attempt_count=1,attempts=[{'synthetic':'numerical-recovery'}])
        with self.assertRaises(ValueError):m.validate_step(**args)


if __name__=='__main__':unittest.main()
