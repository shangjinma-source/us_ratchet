from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from scripts import ndx_corrected_cohort_consumer_readiness_20260919 as module


class Tests(unittest.TestCase):
    def test_real_bound_inventory_counts_and_no_direct_execution_claim(self):
        report=module.build()
        self.assertEqual(sum(r['pending_in_bound_overlay'] for r in report['dates']),11254)
        self.assertEqual(report['original_count'],351255)
        self.assertEqual(len(report['consumer_contracts']),7)
        self.assertTrue(all(not r['complete_corrected_date_consumable'] for r in report['dates']))
        for key in ('training_performed','execution_performed','execution_ready','full_ndx_pool_coverage_verified','latest_selected_completed_count_observed'):
            self.assertIs(report[key],False)

    def test_pending_denominator_duplicate_dates_and_status_upgrade_rejected(self):
        inventory=json.loads(module.INVENTORY.read_bytes());plan=json.loads(module.PLAN.read_bytes())
        for defect in ('bool','partial','relabel','date','descriptor','plan'):
            bad=deepcopy(inventory);tasks=deepcopy(plan)
            if defect=='bool':bad['pending_count']=True
            elif defect=='partial':bad['dates'][0]['pending']-=1;bad['dates'][0]['available']+=1
            elif defect=='relabel':bad['promotion_allowed']=True
            elif defect=='date':bad['dates'][1]['date']=bad['dates'][0]['date']
            elif defect=='descriptor':bad['dates'][0]['overlay_sha256']='0'*64
            else:tasks['dates'][0]['tasks'].append(deepcopy(tasks['dates'][0]['tasks'][0]))
            with self.subTest(defect=defect),self.assertRaises(ValueError):module.validate_inventory(bad,tasks)

    def test_wrong_hard_inventory_and_consumer_contract_change_reject(self):
        with patch.object(module,'INVENTORY_SHA','0'*64):
            with self.assertRaises(ValueError):module.build()
        with self.assertRaisesRegex(ValueError,'contract changed'):
            module.inspect_contract('scripts/ndx_combined_fractional_frontier.py','run_date',('NEW_CORRECTED_OVERLAY_ALREADY_ACCEPTED',),{})


if __name__=='__main__':unittest.main()
