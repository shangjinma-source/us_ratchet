import copy
import unittest
from scripts import ndx_adobe_event_endpoint_crosscheck_20260919 as m


class Tests(unittest.TestCase):
    def test_actual_endpoints_and_limited_claim(self):
        report = m.build()
        self.assertTrue(report['endpoint_ticker_sets_equal'])
        self.assertEqual(report['observed_event_rows'], 21)
        self.assertFalse(report['event_coverage_complete'])
        self.assertFalse(report['exact_security_membership_verified'])
        self.assertFalse(report['intermediate_membership_verified'])

    def test_missing_pair_does_not_silently_pass(self):
        before = [f'T{i}' for i in range(100)]
        after = before[1:]+['NEW']
        result = m.crosscheck(before, after, [])
        self.assertFalse(result['endpoint_ticker_sets_equal'])
        self.assertEqual(result['absent_from_reconstruction'], ['NEW'])
        self.assertEqual(result['extra_in_reconstruction'], ['T0'])

    def test_invalid_or_duplicate_actions_reject(self):
        before = [f'T{i}' for i in range(100)]
        row = dict(event_id='e', action='remove', ticker='T0',
                   effective_date='2023-06-01', event_status='effective')
        for rows in ([row, copy.deepcopy(row)], [dict(row,ticker='MISSING')],
                     [dict(row,event_status='superseded')], [dict(row,action='alias')]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                m.crosscheck(before, before, rows)


if __name__ == '__main__':
    unittest.main()
