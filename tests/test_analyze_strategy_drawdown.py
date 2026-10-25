"""Saved-book analyzer rejects invalid dates/state and supports an initial peak."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_strategy_drawdown import analyze_book


def sample_book():
    rows = [dict(date='2025-01-02', cash='10', shares={'stock': 1},
                 stock_value='85', equity='95'),
            dict(date='2026-01-01', cash='10', shares={'stock': 1},
                 stock_value='80', equity='90')]
    return dict(
        status='COMPLETE', external_flows='0', total_return='-1/10',
        selection_account_states=[dict(decision_date='2025-01-01',
            account_state=dict(asof='2025-01-01', cash='100', shares={}),
            valuation_quotes=[dict(security_id='stock', ticker='STOCK')])],
        daily_ledger=rows, drawdown=dict(maximum_close_drawdown='1/10'),
        state_date='2026-01-01', last_valued_date='2026-01-01', cash='10',
        shares={'stock': 1}, terminal_state_valuation_synchronized=True,
        final_wealth_basis='REGULAR_CLOSE_CURRENT_STATE',
        fee_bps='0', slippage_bps='0', execution_assumption='test-only',
        independent_oos=False, point_in_time_certified=False,
        provider_audit=[dict(risk_overlay=dict(state=dict(
            session_date=row['date'], last_closes={'stock': row['stock_value']})))
            for row in rows],
        order_log=[dict(date='2025-01-02', event='ASSUMED_NEXT_OPEN_FILLED',
                        security_id='stock', side='BUY', quantity=1, price='90', fee='0')])


class SavedDrawdownTests(unittest.TestCase):
    def analyze(self, book):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'book.json'
            path.write_text(json.dumps(book), encoding='utf-8')
            return analyze_book(path)

    def test_initial_all_cash_peak_reconciles_without_price_snapshot(self):
        result = self.analyze(sample_book())
        episode = result['worst_episode']
        self.assertEqual(episode['peak_date'], '2025-01-01')
        self.assertEqual(episode['attribution_status'], 'EXACT_ENDPOINT_AND_FILL_RECONCILIATION')
        self.assertEqual(episode['contributions'][0]['net_profit_loss'], -10)
        self.assertEqual(episode['contributions'][0]['peak_weight_percent'], 0)
        self.assertEqual(episode['residual'], '0')

    def test_nonpositive_initial_equity_rejected(self):
        for value in ('0', '-100'):
            with self.subTest(value=value):
                book = sample_book()
                book['selection_account_states'][0]['account_state']['cash'] = value
                with self.assertRaisesRegex(ValueError, 'Initial equity must be positive'):
                    self.analyze(book)

    def test_zero_or_negative_elapsed_period_rejected(self):
        for start in ('2026-01-01', '2026-01-02'):
            with self.subTest(start=start):
                book = sample_book()
                book['selection_account_states'][0]['decision_date'] = start
                book['selection_account_states'][0]['account_state']['asof'] = start
                with self.assertRaisesRegex(ValueError, 'must follow the initial'):
                    self.analyze(book)

    def test_terminal_date_and_state_tampering_rejected(self):
        mutations = [('state_date', '2026-01-02'), ('last_valued_date', '2025-12-31'),
                     ('terminal_state_valuation_synchronized', False),
                     ('final_wealth_basis', 'REGULAR_CLOSE_BEFORE_AFTER_HOURS_ACTION'),
                     ('cash', '11'), ('shares', {'stock': 2}),
                     ('distribution_rights', [{'units': '1'}])]
        for key, value in mutations:
            with self.subTest(key=key):
                book = sample_book()
                book[key] = deepcopy(value)
                with self.assertRaisesRegex(ValueError, 'Terminal'):
                    self.analyze(book)

    def test_missing_nonempty_endpoint_marks_rejected(self):
        book = sample_book()
        book['provider_audit'] = book['provider_audit'][:1]
        with self.assertRaisesRegex(ValueError, 'Unique endpoint risk-price'):
            self.analyze(book)


if __name__ == '__main__':
    unittest.main()
