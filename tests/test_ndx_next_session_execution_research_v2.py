import unittest

from test_ndx_next_session_execution_research import fixture
from backtest.ndx_next_session_execution_research import simulate_next_session_execution_research as old_simulate
from backtest.ndx_next_session_execution_research_v2 import simulate_next_session_execution_research_v2 as simulate


def event(session, numerator=20, denominator=1, ticker='A'):
    return dict(ticker=ticker, session=str(session.date()), new_shares=numerator,
                old_shares=denominator, source_url='https://example.org/split', evidence_sha256='a'*64)


class NextSessionSplitTests(unittest.TestCase):
    def test_twenty_for_one_equity_continuity(self):
        inputs = fixture()
        dates = inputs['execution_calendar']
        inputs['prices'].loc[dates[0], 'A'] = 200.
        inputs['initial_shares'] = dict(A=1, B=20, C=20)
        inputs['schedule'] = [(dates[-1], dict(A=1/3, B=1/3, C=1/3))]
        result = simulate(**inputs, corporate_actions=[event(dates[1])])
        self.assertEqual(result['initial_equity_usd'], 700.)
        self.assertEqual([d['equity_usd'] for d in result['daily']], [700.]*4)
        self.assertEqual(result['daily'][0]['shares']['A'], 1)
        self.assertEqual(result['daily'][1]['shares']['A'], 20)
        self.assertEqual(result['path_return_net'], 0.)
        self.assertEqual(result['path_max_drawdown'], 0.)
        self.assertEqual(result['total_fees_usd'], 0.)
        self.assertFalse(result['corporate_action_evidence_authenticated'])
        self.assertFalse(result['corporate_action_coverage_verified'])

    def test_cross_event_basket_cancelled_no_fill_or_retry(self):
        inputs = fixture()
        result = simulate(**inputs, corporate_actions=[event(inputs['execution_calendar'][1])])
        self.assertEqual(result['executions'], [])
        self.assertEqual(result['cancelled_pending_plan_count'], 1)
        self.assertEqual(result['cancelled_plans'][0]['fees_usd'], 0.)
        self.assertEqual(result['terminal_shares'], dict(A=0, B=0, C=0))
        self.assertEqual(result['terminal_cash_usd'], 100.)
        self.assertIsNone(result['pending_plan'])
        self.assertEqual(result['trade_execution_count'], 0)

    def test_reverse_fractional_entitlement_fails_closed(self):
        inputs = fixture()
        inputs['initial_shares'] = dict(A=1, B=1, C=1)
        with self.assertRaisesRegex(ValueError, 'FRACTIONAL_SPLIT'):
            simulate(**inputs, corporate_actions=[event(inputs['execution_calendar'][1], 1, 2)])

    def test_no_events_equal_old_economic_path(self):
        inputs = fixture()
        old = old_simulate(**inputs)
        new = simulate(**inputs, corporate_actions=[])
        fields = ('daily', 'decisions', 'executions', 'pending_plan', 'risk_failure_days',
                  'initial_equity_usd', 'terminal_equity_usd', 'terminal_cash_usd', 'terminal_shares',
                  'total_fees_usd', 'path_return_net', 'path_max_drawdown', 'all_days_constraints_passed')
        for field in fields:
            self.assertEqual(old[field], new[field], field)

    def test_first_session_missing_ticker_duplicate_or_outside_rejected(self):
        inputs = fixture()
        dates = inputs['execution_calendar']
        invalid = ([event(dates[0])], [event(dates[1], ticker='Z')],
                   [event(dates[1]), event(dates[1])],
                   [{**event(dates[1]), 'session': '1999-01-01'}])
        for events in invalid:
            with self.assertRaises(ValueError):
                simulate(**inputs, corporate_actions=events)
        with self.assertRaises(ValueError):
            simulate(**inputs, corporate_actions=None)

    def test_split_cancellation_precedes_new_scheduled_plan(self):
        inputs = fixture()
        dates = inputs['execution_calendar']
        inputs['schedule'].append((dates[1], dict(A=1/3, B=1/3, C=1/3)))
        result = simulate(**inputs, corporate_actions=[event(dates[1])])
        self.assertEqual(result['cancelled_pending_plan_count'], 1)
        self.assertEqual(len(result['executions']), 1)
        self.assertEqual(result['executions'][0]['decision_date'], str(dates[1].date()))
        self.assertEqual(result['executions'][0]['execution_date'], str(dates[2].date()))


if __name__ == '__main__':
    unittest.main()
