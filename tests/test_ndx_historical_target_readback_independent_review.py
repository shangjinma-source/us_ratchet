import copy
import unittest
from test_ndx_historical_single_target_independent_audit_20260919 import bundle
from scripts import ndx_historical_single_target_independent_audit_20260919 as m


class TargetReadbackReview(unittest.TestCase):
    def test_coherent_future_matrix_or_old_task_cannot_replace_historical_inputs(self):
        for defect in ('future', 'old_task', 'source', 'permission'):
            args = list(copy.deepcopy(bundle()))
            value, raw, started, inputs, plan, numerical, sources = args
            if defect == 'future':
                encoded = copy.deepcopy(inputs['prices']['returns'])
                encoded['index'] = encoded['index'][126:]
                encoded['data'] = encoded['data'][126:]
                raw['explicit_fit_matrix'] = encoded
            elif defect == 'old_task':
                value['job_id'] = raw['job_id'] = started['job_id'] = m.STRUCTURE
                value['task']['task_id'] = raw['task']['task_id'] = m.STRUCTURE
            elif defect == 'source':
                value['historical_expected_source_hashes'].clear()
                raw['historical_expected_source_hashes'].clear()
                value['archive_resolution'] = {}
            else:
                value['legal_training_input_admitted'] = raw['legal_training_input_admitted'] = True
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                m.inspect(*args)

    def test_full_future_half_cannot_influence_matrix_and_scope_is_not_account_execution(self):
        args = list(bundle())
        before = m.inspect(*args)
        for row in args[3]['prices']['returns']['data'][126:]:
            row[:] = [999.0] * len(row)
        after = m.inspect(*args)
        self.assertTrue(m.exact(before, after))
        self.assertEqual(after['fit_rows'], 126)
        self.assertEqual(after['first_next_open'], '2026-03-19')


if __name__ == '__main__':
    unittest.main()
