"""Independent synthetic checks; no actual198 assembly or weight audits."""
from copy import deepcopy
import unittest
import test_ndx_new_cutoff_v4_completed_task_rebinding_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    def test_original_location_and_normalized_prior_are_validated(self):
        for field, value in [('location_id', '0' * 64), ('expected_fitter_previous_target_weights', None)]:
            arguments = owner.fixture()
            arguments[0]['full_task'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.rebind(*arguments)

    def test_nested_matrix_and_prior_location_tampering_reject(self):
        for attack in ('matrix', 'location'):
            row, reference, panel, plan, index = owner.fixture()
            for name in ('started_reference', 'raw_reference', 'postcheck_reference', 'independent_readback_reference'):
                row[name] = {'path': 'synthetic/' + name, 'sha256': 'a' * 64}
            previous = m.rebind(row, reference, panel, plan, index)
            if attack == 'matrix':
                previous['verified_fit_data_sha256'] = '0' * 64
            else:
                previous['new_location_identity']['rank'] += 1
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.rebind_index_row('externally_completed_rebound_rows', 0, previous, panel, plan, index)

    def test_nested_evidence_is_independent_copy(self):
        row, reference, panel, plan, index = owner.fixture()
        for name in ('started_reference', 'raw_reference', 'postcheck_reference', 'independent_readback_reference'):
            row[name] = {'path': 'synthetic/' + name, 'sha256': 'a' * 64}
        previous = m.rebind(row, reference, panel, plan, index)
        snapshot = deepcopy(previous)
        result = m.rebind_index_row('externally_completed_rebound_rows', 0, previous, panel, plan, index)
        result['new_location_identity']['rank'] = 999
        result['old_completed_row']['raw_reference']['path'] = 'changed'
        self.assertEqual(previous, snapshot)
        self.assertEqual(result['original_index_row'], snapshot)
        self.assertEqual(result['prior_rebinding_row'], snapshot)


if __name__ == '__main__':
    unittest.main()
