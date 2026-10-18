"""Regression readback of isolated annual draft, no search or book execution."""
import json
import unittest
from pathlib import Path
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4

ROOT = Path(__file__).resolve().parents[1]


class AnnualHonaBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.draft = json.loads((ROOT / 'tmp/annual_continuous_draft_20261016_v3/draft_prepared.json').read_text(encoding='utf-8'))

    def test_known_when_issued_rows_never_count_as_ordinary_history(self):
        windows = {window['decision_date']: window for window in self.draft['windows']}
        for day, expected in [('2026-06-30', 2), ('2026-09-30', 66)]:
            row = next(row for row in windows[day]['candidates'] if row['ticker'] == 'HONA')
            self.assertEqual(row['identity_binding']['regular_way_start'], '2026-06-29')
            guard = row['identity_history_guard']
            self.assertEqual(guard['valid_regular_closes'], expected)
            self.assertIn('2026-06-15', guard['pre_regular_dates'])
            self.assertIn('INSUFFICIENT_253_REGULAR_SESSION_CLOSES', guard['reasons'])
            self.assertIsNone(row['security_id'])
            self.assertEqual(len(windows[day]['candidates']), 101)

    def test_tri_still_blocks_v4_and_no_yearly_cash_reset(self):
        self.assertEqual(self.draft['status'], 'BLOCKED_NOT_EXECUTABLE')
        self.assertFalse(self.draft['yearly_capital_reset'])
        with self.assertRaisesRegex(ValueError, 'MISSING_CANDIDATE_DECISION_PRICE:security:0001075124:884903808'):
            assemble_monthly_execution_inputs_v4(self.draft)


if __name__ == '__main__':
    unittest.main()
