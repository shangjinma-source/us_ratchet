"""Synthetic reference aggregation review, no task files or numeric audits."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_ctas_completed_index_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    def test_risk_name_and_internal_optimizer_claims_rejected(self):
        for attack in ('risk_name', 'optimizer_zero', 'bool_attempt', 'reader_source'):
            args = owner.fixture()
            item = args[3]
            if attack == 'risk_name':
                item['audit']['detail']['checks']['OTHER'] = item['audit']['detail']['checks'].pop('MAX_SINGLE_WEIGHT')
            elif attack == 'optimizer_zero':
                item['raw']['internal_optimizer_call_count'] = 0
            elif attack == 'bool_attempt':
                item['raw']['operation_counts'] = dict(item['raw']['operation_counts'], wrapper_call_attempt_count=True)
            else:
                key = next(p for p in m.PINS if 'independent_readback' in p)
                item['audit']['source_hashes'][key] = '0'*64
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.row_from_evidence(*args)

    def test_raw_only_recovery_keeps_post_reference_absent(self):
        args = owner.fixture()
        args[3]['postcheck'] = None
        args[3]['audit']['saved_postcheck'] = None
        row = m.row_from_evidence(*args)
        self.assertIsNone(row['postcheck_reference'])
        self.assertEqual(row['status'], 'FITTED_FIVE_RISKS_PASSED')

    def test_mixed_status_aggregation_does_not_claim_all_pass(self):
        tasks = [(dict(numerical_task_id=str(i)), {}) for i in range(102)]
        refs = [dict(path=str(i), sha256='a'*64) for i in range(102)]
        statuses = ['FITTED_FIVE_RISKS_PASSED']*99 + ['FITTED_FIVE_RISKS_FAILED', 'NUMERICAL_EXCEPTION_NO_RETURNED_FIT', 'VALIDATION_FAILURE_RECORDED']
        rows = [dict(status=s, returned_fit_count=int(s!='NUMERICAL_EXCEPTION_NO_RETURNED_FIT')) for s in statuses]
        old = [dict(numerical_task_id='old'+str(i),prior_rebinding_row={'nested':{'original_full_task':{'id':i}}}) for i in range(402)]
        with patch.object(m, 'tasks_and_references', return_value=(tasks, refs)), patch.object(m, 'row_from_evidence', side_effect=rows):
            value = m.assemble({'rebinding': {'rows': old}}, {str(i): {} for i in range(102)})
        self.assertEqual(value['batch_saved_attempt_and_readback_count'], 504)
        self.assertEqual(value['batch_original_risk_pass_count'], 501)
        self.assertEqual(value['remaining_unattempted_plan_task_count'], 37739733)
        self.assertFalse(value['all_new_batch_original_risks_passed'])
        self.assertFalse(value['all_plan_tasks_completed'])
        self.assertEqual(value['externally_completed_rebound_rows'], old)

    def test_guard_conflict_is_rejected_before_disk(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m.Path, 'read_bytes', side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})


if __name__ == '__main__':
    unittest.main()
