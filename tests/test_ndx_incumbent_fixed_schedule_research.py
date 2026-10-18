from copy import deepcopy
import unittest

from scripts import ndx_incumbent_fixed_schedule_research as schedule


class IncumbentFixedScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = schedule.build_report()

    def test_real_archive_targets_and_control_semantics(self):
        report = self.report
        self.assertEqual(report['decision_count'], 15)
        self.assertEqual(report['calendar_count'], 295)
        self.assertEqual(report['initial_cash_usd'], 25000)
        self.assertEqual(report['minimum_cash_buffer_usd'], 100)
        self.assertEqual(report['transaction_cost_bps'], 10)
        self.assertFalse(report['risk_is_order_gate'])
        self.assertFalse(report['weights_refitted'])
        self.assertEqual(report['overlay_security_ids'], ['security:incumbent_overlay:TSM'])
        self.assertTrue(all(row['targets'] == report['schedule'][0]['targets'] for row in report['schedule']))
        self.assertEqual(report['risk_provenance']['date_end'], '2024-06-03')

    def test_reject_changed_weights_missing_duplicate_or_wrong_clock(self):
        for fault in ('weights', 'targets', 'missing', 'duplicate', 'not_next', 'last'):
            report = deepcopy(self.report)
            parameters = dict(prior_schedule=deepcopy(report['schedule'][:14]),
                reference_schedule=deepcopy(report['schedule']), calendar=report['calendar'],
                original_weights=report['original_weights'])
            if fault == 'weights': parameters['original_weights']['NVDA'] += .01
            if fault == 'targets': next(iter(parameters['prior_schedule'][2]['targets'].values()))['target_weight'] += .01
            if fault == 'missing': parameters['reference_schedule'].pop()
            if fault == 'duplicate': parameters['reference_schedule'][1] = parameters['reference_schedule'][0]
            if fault == 'not_next': parameters['reference_schedule'][0]['execution_date'] = '2023-04-04'
            if fault == 'last': parameters['reference_schedule'][-1]['execution_date'] = '2024-06-04'
            with self.assertRaises(ValueError, msg=fault): schedule._extend(**parameters)


if __name__ == '__main__':
    unittest.main()
