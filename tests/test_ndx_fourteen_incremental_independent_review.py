"""Independent fail-closed checks; no build, fitter, or publication."""
import unittest
from scripts import ndx_latest_fourteen_incremental_plan_20260919 as module


class IncrementalIndependentReview(unittest.TestCase):
    def test_uncompleted_row_cannot_arrive_with_completed_or_reuse_claim(self):
        for field, value in [('completed_old_result_verified', True),
                             ('result_reused', True),
                             ('status', 'COMPLETED')]:
            with self.subTest(field=field):
                row = dict(task={}, old_equivalent_task_id='old',
                           fit_data_sha256='m', status='PENDING_OLD_OR_NEW',
                           completed_old_result_verified=False, result_reused=False)
                row[field] = value
                with self.assertRaises(ValueError):
                    module.mark_completed({'tasks': [row]},
                                          {'canonical_tasks': [{'task_id': 'old'}]},
                                          {'details': []})

    def test_duplicate_original_task_identity_is_not_silently_collapsed(self):
        with self.assertRaises(ValueError):
            module.mark_completed({'tasks': []},
                                  {'canonical_tasks': [{'task_id': 'old'}, {'task_id': 'old'}]},
                                  {'details': []})


if __name__ == '__main__':
    unittest.main()
