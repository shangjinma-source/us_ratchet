import unittest
from backtest.return_priority_limit_book_summary_v4 import summarize_limit_book_v4


class SummaryV4Tests(unittest.TestCase):
    def fixture(self):
        return dict(status='COMPLETE', daily_ledger=[dict(date='2026-01-02', equity='110')],
                    order_log=[], cash='110', shares={}, receivable='0',
                    terminal_state_valuation_synchronized=True, final_wealth_basis='REGULAR_CLOSE_CURRENT_STATE')

    def summarize(self, outcome):
        return summarize_limit_book_v4(outcome, [], '100', ['2026-01-01', '2026-01-02'])

    def test_full_period_requires_synchronized_terminal_state(self):
        result = self.summarize(self.fixture())
        self.assertEqual(result['total_return'], '1/10')
        outcome = self.fixture(); outcome.update(terminal_state_valuation_synchronized=False,
            final_wealth_basis='REGULAR_CLOSE_BEFORE_AFTER_HOURS_ACTION')
        result = self.summarize(outcome)
        self.assertFalse(result['complete_full_period']); self.assertIsNone(result['annualized_return'])
        self.assertEqual(result['last_observed_equity'], '110'); self.assertIsNone(result['terminal_target_difference'])

    def test_no_ledger_is_not_zero_observed_drawdown(self):
        outcome = self.fixture(); outcome.update(status='BLOCKED', daily_ledger=[])
        result = self.summarize(outcome)
        self.assertIsNone(result['partial_observed_drawdown']); self.assertIsNone(result['last_observed_equity'])

    def test_missing_interior_ledger_cannot_claim_full_interval(self):
        result = summarize_limit_book_v4(self.fixture(), [], '100', ['2025-12-31', '2026-01-01', '2026-01-02'])
        self.assertFalse(result['complete_full_period']); self.assertIsNone(result['total_return'])


if __name__ == '__main__':
    unittest.main()
