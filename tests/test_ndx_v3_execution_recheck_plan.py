import unittest
from unittest.mock import patch

from scripts import ndx_v3_execution_recheck_plan as plan


class RecheckPlanTests(unittest.TestCase):
    def test_malformed_identity_rejected_before_read(self):
        for value in (None, True, '', 'A' * 64, '../context'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'digests required'):
                    plan.prepare_case(value, plan.CASES[0][1])

    def test_loaded_source_drift_rejected(self):
        with patch.object(plan, '_LOADED_SHA', '0' * 64):
            with self.assertRaisesRegex(ValueError, 'Loaded source drift'):
                plan.prepare_case(*plan.CASES[0])

    def test_real_captured_cases_have_bound_coordinates_and_full_clock(self):
        result = plan.run()
        self.assertFalse(result['real_execution_performed'])
        self.assertFalse(result['promotion_allowed'])
        self.assertEqual(len(result['cases']), 4)
        for index, row in enumerate(result['cases']):
            with self.subTest(job=row['job_id']):
                self.assertEqual(set(row['coordinate']), set(plan.encoding.COORDINATE_FIELDS))
                self.assertEqual(row['coordinate']['holding_count'], row['holding_count'])
                self.assertEqual(row['coordinate']['selection_date'],
                                 '2024-02-01' if index < 3 else '2024-04-01')
                self.assertEqual(row['periodic_decision_count'], 17 if index < 3 else 18)
                self.assertEqual(row['day_count'], 357 if index < 3 else 378)
                self.assertGreater(row['periodic_decision_count'], row['legacy_decision_count'])
                self.assertTrue(row['failed_components'])
                self.assertFalse(row['promotion_allowed'])
                self.assertFalse(row['portfolio_selection_precedes_execution'])
                self.assertFalse(row['fresh_oos_consumed'])
                self.assertTrue(row['retrospective_fixed_portfolio_diagnostic'])

    def test_every_fit_and_decision_matches_explicit_full_calendar(self):
        for identity in plan.CASES:
            case = plan.prepare_case(*identity)
            contract = case['inputs']['contract']
            calendar = case['inputs']['returns'].index
            end_index = calendar.get_loc(case['prices'].index[-1])
            positions = list(range(contract['fit_days'], end_index + 1, contract['step_days']))
            schedule = case['clock']['schedule']
            self.assertEqual(len(schedule), len(positions))
            for row, position in zip(schedule, positions):
                self.assertEqual(row['execution_date'], str(calendar[position].date()))
                self.assertEqual(row['fit_start'], str(calendar[position-contract['fit_days']].date()))
                self.assertEqual(row['fit_end'], str(calendar[position-1].date()))
                self.assertLess(row['fit_end'], row['execution_date'])


if __name__ == '__main__':
    unittest.main()
