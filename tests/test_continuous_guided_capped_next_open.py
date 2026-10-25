from copy import deepcopy
from fractions import Fraction
import unittest
from unittest.mock import patch

import test_continuous_guided_half_next_open as fixture
from backtest import continuous_guided_account_decision as selector
from backtest.continuous_guided_capped_next_open import run_capped_next_open
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class ExitOnSecondDecision:
    """Deterministic fixture to verify cash feedback, not a proposed strategy."""
    def __init__(self):
        self.calls = 0

    def apply(self, **arguments):
        self.calls += 1
        target = arguments['target']
        if self.calls == 2:
            target = {security: 0 for security in target}
        return target, {'fixture': True}


class CappedBookTests(unittest.TestCase):
    def data(self):
        assembled, bars, _ = fixture.GuidedHalfTests().data()
        day = assembled['session_dates'][2]
        second = deepcopy(assembled['monthly_inputs'][0])
        second['decision_date'] = day
        second['search_arguments'].update(decision_date=day, quote_as_of=day,
                                         prices={'A': assembled['close_prices']['A'][day]})
        second['valuation_quotes'][0].update(as_of=day, price=assembled['close_prices']['A'][day])
        assembled['monthly_inputs'].append(second)
        return assembled, bars

    def run_book(self, assembled, bars, risk=None):
        return run_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='1000',
                                   fee_bps='0', slippage_bps='5', risk=risk)

    def test_actual_sale_cash_enters_next_month_search(self):
        assembled, bars = self.data()
        with patch.object(selector, 'original_search', wraps=selector.original_search) as searches:
            result = self.run_book(assembled, bars, ExitOnSecondDecision())
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(searches.call_count, 2)
        self.assertTrue(any(row.get('side') == 'SELL' and row['event'] == 'ASSUMED_NEXT_OPEN_FILLED'
                            for row in result['order_log']))
        state = result['selection_account_states'][1]['account_state']
        self.assertEqual(sum(state['shares'].values()), 0)
        self.assertEqual(Fraction(searches.call_args_list[1].kwargs['entered_cash']), Fraction(state['cash']))
        day = assembled['session_dates'][2]
        ledger = next(row for row in result['daily_ledger'] if row['date'] == day)
        self.assertEqual(state['cash'], ledger['cash'])
        self.assertFalse(result['performance_validated'])

    def test_future_open_cannot_change_previous_close_decision(self):
        assembled, bars = self.data()
        original = self.run_book(assembled, bars)
        changed = deepcopy(bars)
        changed['A'][assembled['session_dates'][1]] = dict(open='999', high='999', low='8', close='8')
        later = self.run_book(assembled, changed)
        self.assertEqual(original['provider_audit'][0], later['provider_audit'][0])

    def test_deployed_exit_rule_then_next_month_reselection(self):
        assembled, bars = self.data()
        result = self.run_book(assembled, bars, MonthlyExitCoreResearchAdapter())
        self.assertEqual(result['status'], 'COMPLETE')
        audit = result['provider_audit']
        self.assertEqual(audit[1]['risk_overlay']['state']['exited'], ['A'])
        self.assertEqual(audit[1]['target_shares'], {'A': 0})
        self.assertGreater(audit[2]['target_shares']['A'], 0)
        self.assertEqual(audit[2]['risk_overlay']['state']['exited'], [])
        self.assertEqual(sum(result['selection_account_states'][1]['account_state']['shares'].values()), 0)


if __name__ == '__main__':
    unittest.main()
