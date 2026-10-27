"""Synthetic repair execution checks, not evidence of historical news efficacy."""
from fractions import Fraction
import unittest

from backtest.guidance_cash_next_open_book_research_v1 import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.guidance_news_risk_research_v1 import GuidanceNewsRiskAdapter


def event(identity, kind, available, *, repairs=None, security='A', key='same-period'):
    row = dict(id=identity, classification=kind, available_at=available,
               security_id=security, comparison_key=key, period_end='2026-12-31',
               review_reference='SYNTHETIC_ONLY', source_hashes=['synthetic-source'])
    if repairs is not None:
        row['repairs_event_id'] = repairs
    return row


class ExplicitRepairExecutionTests(unittest.TestCase):
    def execute(self, events, *, drop=False):
        days = ['2026-01-27', '2026-01-28', '2026-01-29', '2026-01-30',
                '2026-02-02', '2026-02-03']
        prices = {day: '8' if drop and day >= days[1] else '10' for day in days}
        bars = {'A': {day: dict(open=price, high=price, low=price, close=price)
                      for day, price in prices.items()}}
        risk = GuidanceNewsRiskAdapter(MonthlyExitCoreResearchAdapter(), events=events,
            session_closes={day: day+'T21:00:00Z' for day in days},
            action_policy='BLOCK_NEW_BUYS', release_policy='EXPLICIT_REPAIR')
        trace = {}

        def provider(*, decision_date, active_date, state):
            epoch = days[0] if decision_date < '2026-02-02' else '2026-02-02'
            target, diagnostics = risk.apply(day=decision_date, month=epoch,
                target={'A': 5}, closes={'A': prices[decision_date]}, shares=state['shares'])
            trace[decision_date] = dict(target=target, diagnostics=diagnostics)
            delta = target['A'] - state['shares'].get('A', 0)
            orders = [] if not delta else [dict(id='order:'+decision_date, security_id='A',
                side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                decision_date=decision_date, active_date=active_date, decision_mark=prices[decision_date])]
            return dict(status='READY', orders=orders, target_decision_date=epoch, news_sale_fractions={})

        book = run_next_open_book(session_dates=days, ohlc=bars, initial_cash='100',
            initial_shares={'A': 2}, fee_bps='10', slippage_bps='5', order_provider=provider,
            news_allocation_dates=[days[0], '2026-02-02'])
        self.assertEqual(book['status'], 'COMPLETE', book.get('reason'))
        fills = [row for row in book['order_log'] if row.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
        cash, shares, fees = Fraction(100), 2, Fraction(0)
        for fill in fills:
            count, price, fee = fill['quantity'], Fraction(fill['price']), Fraction(fill['fee'])
            self.assertIs(type(count), int)
            self.assertGreater(count, 0)
            self.assertEqual(fee, count * price / 1000)
            sign = 1 if fill['side'] == 'BUY' else -1
            self.assertEqual(price, Fraction(prices[fill['date']]) * (1 + sign*Fraction(5,10000)))
            shares += sign*count
            cash -= sign*count*price + fee
            fees += fee
            self.assertGreaterEqual(shares, 0)
            self.assertGreaterEqual(cash, 0)
        self.assertEqual(Fraction(book['cash']), cash)
        self.assertEqual(book['shares'].get('A', 0), shares)
        self.assertEqual(Fraction(book['fees']), fees)
        for row in book['daily_ledger']:
            self.assertEqual(Fraction(row['equity']), Fraction(row['cash']) +
                             row['shares'].get('A', 0)*Fraction(prices[row['date']]))
            self.assertEqual(Fraction(row['news_reserved_cash']), 0)
        return book, trace, fills

    def test_close_timestamp_repair_waits_for_next_close_then_following_open(self):
        events = [event('cut', 'CUT', '2026-01-26T15:00:00Z'),
                  event('repair', 'REPAIRED', '2026-01-28T21:00:00Z', repairs='cut')]
        _, trace, fills = self.execute(events)
        self.assertEqual(trace['2026-01-28']['target']['A'], 2)
        self.assertEqual(trace['2026-01-28']['diagnostics']['guidance_news']['active_event_ids'], ['cut'])
        self.assertEqual(trace['2026-01-29']['target']['A'], 5)
        self.assertEqual([(row['date'], row['side'], row['quantity']) for row in fills],
                         [('2026-01-30', 'BUY', 3)])

    def test_original_twenty_percent_exit_survives_repair_until_month_reset(self):
        events = [event('cut', 'CUT', '2026-01-26T15:00:00Z'),
                  event('repair', 'REPAIRED', '2026-01-29T15:00:00Z', repairs='cut')]
        _, trace, fills = self.execute(events, drop=True)
        self.assertEqual(trace['2026-01-28']['diagnostics']['state']['exited'], ['A'])
        self.assertEqual(trace['2026-01-29']['diagnostics']['guidance_news']['active_event_ids'], [])
        self.assertEqual(trace['2026-01-29']['target']['A'], 0)
        self.assertEqual(trace['2026-01-30']['target']['A'], 0)
        self.assertEqual(trace['2026-02-02']['target']['A'], 5)
        self.assertEqual([(row['date'], row['side'], row['quantity']) for row in fills],
                         [('2026-01-29', 'SELL', 2), ('2026-02-03', 'BUY', 5)])

    def test_old_event_unrelated_period_and_other_security_cannot_release(self):
        events = [event('old-cut', 'CUT', '2026-01-26T15:00:00Z'),
                  event('current-cut', 'CUT', '2026-01-27T15:00:00Z'),
                  event('old-repair', 'REPAIRED', '2026-01-28T15:00:00Z', repairs='old-cut'),
                  event('other-period', 'REPAIRED', '2026-01-28T16:00:00Z', repairs='current-cut', key='unrelated'),
                  event('other-security', 'REPAIRED', '2026-01-28T17:00:00Z', repairs='current-cut', security='B')]
        _, trace, fills = self.execute(events)
        self.assertEqual(fills, [])
        for row in trace.values():
            self.assertEqual(row['target']['A'], 2)
            self.assertEqual(row['diagnostics']['guidance_news']['active_event_ids'], ['current-cut'])


if __name__ == '__main__':
    unittest.main()
