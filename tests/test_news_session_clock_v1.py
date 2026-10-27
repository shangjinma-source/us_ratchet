import unittest
from scripts.research.build_news_session_clock_v1 import build, event_execution


class SessionClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clock = build()
        cls.rows = cls.clock['sessions']
        cls.by_date = {row['date']: row for row in cls.rows}

    def test_dst_and_special_closure(self):
        self.assertEqual(self.by_date['2024-03-08']['close'], '2024-03-08T21:00:00+00:00')
        self.assertEqual(self.by_date['2024-03-11']['close'], '2024-03-11T20:00:00+00:00')
        self.assertNotIn('2025-01-09', self.by_date)
        self.assertIn('2021-06-18', self.by_date)
        self.assertNotIn('2022-06-20', self.by_date)

    def test_early_close_strict_boundary_and_holiday(self):
        before = event_execution(self.rows, '2023-07-03T16:59:59Z')
        equal = event_execution(self.rows, '2023-07-03T17:00:00Z')
        self.assertEqual((before['decision_date'], before['execution_date']), ('2023-07-03', '2023-07-05'))
        self.assertEqual((equal['decision_date'], equal['execution_date']), ('2023-07-05', '2023-07-06'))

    def test_after_close_and_finite_end(self):
        row = event_execution(self.rows, '2026-01-30T21:10:41Z')
        self.assertEqual(row['execution_date'], '2026-02-03')
        self.assertIsNone(event_execution(self.rows, '2026-07-30T19:59:59Z'))
        with self.assertRaisesRegex(ValueError, 'TIMEZONE_REQUIRED'):
            event_execution(self.rows, '2026-01-30T21:10:41')


if __name__ == '__main__':
    unittest.main()
