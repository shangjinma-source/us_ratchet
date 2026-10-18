from copy import deepcopy
import unittest
import test_ndx_combined_fractional_frontier_research as fixtures
from backtest import ndx_corrected_complete_date_frontier_research as module


def fixture():
    old=fixtures.fixture(4);records=[];signature=old['training_semantics']['training_semantics_sha256']
    for i,source in enumerate(old['records']):
        record=dict(source,overlay_record_id=str(i),status='AVAILABLE',original_training_semantics_sha256=signature,correction_signature='CORRECTED3',overlay_mode='OLD_AVAILABLE')
        records.append(record)
    # One original pending record is now legitimately complete, not a filtered frontier.
    records[-1]['origin']='DELTA';records[-1]['overlay_mode']='SELECTED_DELTA_COMPLETE_DATE';records[-1]['original_training_semantics_sha256']=None
    counts={o:dict(planned=sum(r['origin']==o for r in records),available=sum(r['origin']==o for r in records),pending=0) for o in module.ORIGINS}
    complete=dict(schema='ndx_selected_complete_date_overlay_v1',coordinate={k:old['expected_date'][k] for k in ('source_batch','universe_track','selection_date')},records=records,
        records_sha256=module.digest(records),counts=counts,original_count=4,available_count=4,pending_count=0,selected_delta_added=1,economic_inputs_complete=True,
        scope='ORIGINAL_RESEARCHED_SUBPOOL_NOT_FULL_NDX',historical_full_source_closure_verified=False,point_in_time_verified=False,promotion_allowed=False,selection_performed=False,winner=None)
    parent=deepcopy(complete);parent.update(schema='ndx_corrected_delta_paired_overlay_limited_drift_v2',available_count=3,pending_count=1,economic_inputs_complete=False)
    parent['records'][-1].update(status='PENDING_NUMERICAL_DELTA',result=None,overlay_mode='PENDING')
    parent['records_sha256']=module.digest(parent['records']);parent['counts']['DELTA'].update(available=0,pending=1)
    return dict(complete_overlay=complete,original_parent=parent,original_training_semantics=old['training_semantics'],delta_contracts={'3':deepcopy(old['training_semantics']['payload']['contract'])})


class Tests(unittest.TestCase):
    def test_all_original_candidates_all_k_ties_and_old_numerical_kernel(self):
        args=fixture();report=module.analyze_complete_corrected_date(**args)
        self.assertEqual(report['original_count'],4)
        self.assertEqual(len(report['raw_frontier']),4)
        self.assertEqual(sum(r['count'] for r in report['groups']),4)
        self.assertEqual({r['holding_count'] for r in report['groups']},{1,4})
        self.assertFalse(report['full_ndx_pool_coverage_verified']);self.assertFalse(report['selection_performed'])
        self.assertEqual(report['original_delta_semantics_hash_absent_count'],1)
        self.assertEqual(len(report['user_preference_references']),1)

    def test_new_corrected_winner_not_restricted_to_old_frontier_and_failure_reasons_retained(self):
        args=fixture();r=args['complete_overlay']['records'][-1]
        r['result']['return_p50_vs_012922']+=.2
        r['result']['portfolio_min_median_dollar_volume_usd']=50.;r['result']['liquidity_constraint_passed']=False
        args['complete_overlay']['records_sha256']=module.digest(args['complete_overlay']['records'])
        report=module.analyze_complete_corrected_date(**args)
        self.assertEqual([r['job_id'] for r in report['raw_frontier']],['3'])
        self.assertEqual(len(report['risk_liquidity_frontier']),3)
        row=next(r for r in report['candidate_diagnostics'] if r['job_id']=='3')
        self.assertIn('liquidity_constraint_passed',row['failed_fractional_checks'])
        self.assertFalse(row['legacy_whole_lot_used_as_competition_gate'])

    def test_resigned_pending_missing_duplicate_wrong_date_and_changed_available_reject(self):
        for defect in ('pending','missing','duplicate','date','available','nan','bool','scope','contract','delta_contract'):
            args=fixture();overlay=args['complete_overlay'];rows=overlay['records']
            if defect=='pending':rows[-1]['status']='PENDING_NUMERICAL_DELTA'
            elif defect=='missing':rows.pop()
            elif defect=='duplicate':rows[-1]=deepcopy(rows[0])
            elif defect=='date':rows[-1]['task']['selection_date']='2024-03-01'
            elif defect=='available':rows[0]['result']['return_p50']+=.01
            elif defect=='nan':rows[-1]['result']['return_p50']=float('nan')
            elif defect=='bool':rows[-1]['result']['return_p50_vs_012922']=True
            elif defect=='scope':overlay['scope']='ALL_NDX'
            elif defect=='contract':args['original_training_semantics']['payload']['contract']['max_single_weight']=.5
            else:args['delta_contracts']['3']['max_single_weight']=.5
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                overlay['records_sha256']=module.digest(rows)
                module.analyze_complete_corrected_date(**args)


if __name__=='__main__':unittest.main()
