from unittest import TestCase
from data.strategy_followup_summary_v1 import summarize


class SummaryTests(TestCase):
    def row(self, key='a', **values):
        result = dict(observation_id=key*64, status='CONDITIONAL_PRICE_OBSERVATION',
            actual_fill_inferred=False, performance_computed=False, security_id='security:a',
            ticker='A', observation_session='2026-10-22', side='SELL',
            reference_limit='100', closing_price='90', price_change_vs_reference='-1/10')
        result.update(values)
        return result

    def test_repeated_refreshes_are_one_stock_day_not_trade_returns(self):
        result = summarize([self.row(), self.row('b', reference_limit='120', price_change_vs_reference='-1/4')])
        self.assertEqual(result['stock_sessions'], 1)
        self.assertEqual(result['observations'], 2)
        self.assertEqual(result['items'][0]['price_change_min'], '-1/4')
        self.assertFalse(result['performance_computed'])

    def test_sides_and_dates_remain_separate(self):
        result = summarize([self.row(), self.row('b', side='BUY'), self.row('c', observation_session='2026-10-23')])
        self.assertEqual(len(result['items']), 3)
        self.assertEqual(result['stock_sessions'], 2)

    def test_conflicting_and_miscomputed_rows_rejected(self):
        for rows in ([self.row(), self.row()], [self.row(), self.row('b', closing_price='80', price_change_vs_reference='-1/5')],
                     [self.row(price_change_vs_reference='1/10')]):
            with self.assertRaises(ValueError):
                summarize(rows)
