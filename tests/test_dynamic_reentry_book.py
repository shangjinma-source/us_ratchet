from copy import deepcopy
import unittest

from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.dynamic_reentry_journal import advance_journal


class ReentryBookTests(unittest.TestCase):
    def test_prior_month_exit_filled_on_reset_is_not_a_reentry(self):
        import test_dynamic_reentry_comparison as fixtures
        fixture = fixtures.ReentryComparisonTests()
        anchor = fixture.days[2]

        def builder(*, decision_date, state, prior_risk_state):
            end = fixture.days.index(decision_date)
            inputs = fixture.inputs(end)
            for key in ('prior_risk_state', 'cash', 'holdings'):
                del inputs[key]
            if end >= 2:
                history = inputs['history_inputs']
                history['base_target']['monthly_decision_date'] = anchor
                history['session_dates'] = history['session_dates'][2:]
                history['session_close_times']['closes'] = {
                    day: clock for day, clock in history['session_close_times']['closes'].items()
                    if day >= anchor}
                history['histories']['A']['closes'] = history['histories']['A']['closes'][2:]
            return inputs

        provider, audit = build_dynamic_provider(builder,
            authorized_risk_reset_dates=[anchor], reentry_policy='LATER_CLOSE')
        bars = {'A': {day: dict(open=price, high=price, low=price, close=price)
                      for day, price in zip(fixture.days, fixture.prices)}}
        result = run_next_open_book(session_dates=fixture.days, ohlc=bars,
            initial_cash='300', initial_shares={'A': 1}, fee_bps='0',
            slippage_bps='0', order_provider=provider)
        self.assertEqual(result['status'], 'COMPLETE')
        fills = [row for row in result['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(row['date'], row['side']) for row in fills],
                         [(anchor, 'SELL'), (fixture.days[3], 'BUY')])
        self.assertEqual(audit[-1]['reentry_execution_inputs']['executed_reentries'], [])
        self.assertEqual(audit[-1]['signal']['comparison']['risk_state']['peaks'], {'A': '91'})

    def run_case(self, policy, missed_buy=False):
        import test_dynamic_reentry_comparison as fixtures
        fixture = fixtures.ReentryComparisonTests()
        fixture.days = [*fixture.days, '2026-10-09']
        fixture.prices = [*fixture.prices, '70']

        def builder(*, decision_date, state, prior_risk_state):
            inputs = fixture.inputs(fixture.days.index(decision_date))
            for key in ('prior_risk_state', 'cash', 'holdings'):
                del inputs[key]
            return inputs

        provider, audit = build_dynamic_provider(builder, reentry_policy=policy)
        bars = {'A': {day: dict(open=price, high=price, low=price, close=price)
                      for day, price in zip(fixture.days, fixture.prices)}}
        bars['A']['2026-10-07'].update(open='10000' if missed_buy else '92', high='10000' if missed_buy else '92')
        result = run_next_open_book(session_dates=fixture.days, ohlc=bars, initial_cash='300',
                                   initial_shares={'A': 1}, fee_bps='0', slippage_bps='0', order_provider=provider)
        return result, audit

    def test_actual_fills_drive_exit_wait_reentry_and_second_exit(self):
        result, audit = self.run_case('LATER_CLOSE')
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        fills = [row for row in result['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([(r['date'], r['side'], r['price']) for r in fills],
                         [('2026-10-05', 'SELL', '75'), ('2026-10-07', 'BUY', '92'), ('2026-10-09', 'SELL', '70')])
        self.assertEqual(result['cash'], '353')
        self.assertEqual(audit[2]['signal']['target_differences'], [])
        self.assertEqual(audit[3]['signal']['comparison']['risk_state']['exited'], ['A'])
        self.assertEqual(audit[4]['signal']['comparison']['risk_state']['peaks'], {'A': '92'})
        self.assertEqual(audit[5]['signal']['comparison']['risk_state']['exited'], ['A'])
        control, _ = self.run_case('MONTHLY_ONLY')
        self.assertEqual(control['cash'], '375')
        self.assertEqual(len([r for r in control['order_log'] if r['event'] == 'ASSUMED_NEXT_OPEN_FILLED']), 1)

    def test_unfilled_buy_does_not_clear_latch_or_reset_peak(self):
        result, audit = self.run_case('LATER_CLOSE', missed_buy=True)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(audit[4]['reentry_execution_inputs']['executed_reentries'], [])
        self.assertEqual(audit[4]['signal']['comparison']['risk_state']['exited'], ['A'])
        self.assertEqual(audit[4]['signal']['comparison']['risk_state']['peaks'], {'A': '100'})

    def test_missing_or_changed_fill_cannot_be_reinterpreted(self):
        fill = dict(id='earlier', event='ASSUMED_NEXT_OPEN_FILLED', date='2026-10-02', side='SELL',
                    security_id='A', quantity=1, price='80')
        journal = dict(orders={}, seen_fills={}, exits={}, entries=[])
        state = dict(shares={'A': 0}, order_log=[fill])
        original = deepcopy(state)
        recorded = advance_journal(journal, state=state, decision_date='2026-10-05', events=[])
        self.assertEqual(recorded['exits'], {})  # Unrelated sell is not a risk-exit instruction.
        self.assertEqual(state, original)
        state['order_log'] = []
        with self.assertRaisesRegex(ValueError, 'FILL_MISSING'):
            advance_journal(recorded, state=state, decision_date='2026-10-06', events=[])
        state['order_log'] = [dict(fill, price='81')]
        with self.assertRaisesRegex(ValueError, 'FILL_CHANGED'):
            advance_journal(recorded, state=state, decision_date='2026-10-06', events=[])


if __name__ == '__main__':
    unittest.main()
