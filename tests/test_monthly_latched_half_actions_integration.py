"""Synthetic action mechanics through the real selector, provider and book.

Reviewed synthetic histories are injected; no provider/book/action functions are
mocked. These cases establish mechanics, not economic performance or data quality.
"""
from copy import deepcopy
from fractions import Fraction
import unittest

import test_continuous_guided_cost_stress as cost_tests
from test_return_priority_limit_book_v4 import event, bar
from backtest.continuous_guided_monthly_latched_half_next_open import (
    run_cost_monthly_latched_half_next_open,
)


class MonthlyLatchedHalfActionsIntegrationTests(unittest.TestCase):
    def fixture(self):
        assembled, bars, original = cost_tests.CostStressTests().data()
        days = assembled['session_dates']
        assembled['close_prices']['B'] = {day: '6' for day in days}
        assembled['close_prices']['C'] = {day: '1' for day in days}
        assembled['price_source_references'].update(B=['raw'], C=['raw'])
        bars.update(B={day: bar('6') for day in days},
                    C={day: bar('1') for day in days})
        # An expensive next open rations the first half-target purchase. Later
        # successor purchases must use the real remaining cash, never borrowing.
        bars['A'][days[1]].update(open='40', high='40')
        calls = []

        def resolver(**kwargs):
            calls.append(deepcopy(kwargs))
            inputs = original(**kwargs)
            day = kwargs['decision_date']
            for sid, history in inputs['histories'].items():
                basis = sid + ':' + day
                history['units']['basis_id'] = basis
                inputs['base_target']['price_units'][sid] = basis
                for row in history['closes'][:-1]:
                    row['close'] = '100' if day == days[0] else '1'
                history['closes'][-1]['close'] = assembled['close_prices'][sid][day]
            return inputs

        return assembled, bars, resolver, calls

    def run_candidate(self, assembled, bars, resolver):
        result = run_cost_monthly_latched_half_next_open(
            assembled=assembled, ohlc=bars, initial_cash='1000',
            fee_bps='0', slippage_bps='5', history_resolver=resolver)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        self.assertEqual(len(result['raw_selection_attempts']), 1)
        self.assertTrue(all(Fraction(row['cash']) >= 0 for row in result['daily_ledger']))
        return result

    def assert_migrated_and_filled(self, result, days):
        audits = result['provider_audit']
        ceiling = audits[0]['monthly_ceiling']['A']
        self.assertGreater(ceiling, 0)
        self.assertEqual(audits[0]['target_shares']['A'], ceiling // 2)
        for audit in audits[2:]:
            self.assertEqual(audit['monthly_ceiling'], {'B': ceiling * 2})
            self.assertEqual(audit['target_shares'], {'B': ceiling})
            self.assertTrue(audit['risk_overlay']['diagnostics']['B']['on'])
            self.assertEqual(audit['risk_overlay']['monthly_latch']['latched_security_ids'], ['B'])
        fills = [row for row in result['order_log']
                 if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED']
        self.assertTrue(any(row['security_id'] == 'A' for row in fills))
        self.assertTrue(any(row['security_id'] == 'B' and row['date'] >= days[3]
                            and row['side'] == 'BUY' for row in fills))
        self.assertFalse(any(row['security_id'] == 'A' and row['date'] >= days[2]
                             for row in fills))

    def test_split_identity_migrates_latch_and_subsequent_real_fill(self):
        assembled, bars, resolver, _ = self.fixture()
        days = assembled['session_dates']
        action = dict(date=days[2], security_id='A', new_security_id='B',
                      type='split_identity', old_shares=1, new_shares=2,
                      source_references=['official'])
        assembled['actions'] = [deepcopy(action)]
        assembled['provider_actions'] = [deepcopy(action)]
        bars['B'][days[2]].update(open='40', high='40')
        bars['B'][days[3]].update(open='1', low='1')
        result = self.run_candidate(assembled, bars, resolver)
        self.assert_migrated_and_filled(result, days)
        adjustment = result['provider_audit'][2]['target_adjustments'][0]
        self.assertEqual((adjustment['security_id'], adjustment['new_security_id']), ('A', 'B'))
        self.assertTrue(any(row['event'] == 'SPLIT_QUANTITY_AND_MARK_ADJUSTED'
                            for row in result['order_log']))

    def test_after_close_identity_wait_retains_latch_until_real_marks(self):
        assembled, bars, resolver, calls = self.fixture()
        days = assembled['session_dates']
        distribution = dict(event('AFTER_CLOSE'), effective_date=days[1],
                            parent_sid='A', post_parent_sid='B', parent_ratio='2',
                            child_ratio='1')
        assembled['distribution_events'] = [distribution]
        assembled['provider_actions'] = [dict(date=days[1], security_id='A',
            post_parent_sid='B', parent_ratio='2', type='distribution',
            source_references=['official'])]
        result = self.run_candidate(assembled, bars, resolver)
        self.assert_migrated_and_filled(result, days)
        wait = result['provider_audit'][1]
        self.assertEqual(wait['action'], 'WAIT_POST_ACTION_MARK')
        self.assertEqual(wait['orders'], [])
        self.assertNotIn('target_decision_date', wait)
        self.assertEqual(wait['target_adjustments'][0]['new_security_id'], 'B')
        self.assertNotIn(days[1], [call['decision_date'] for call in calls])
        self.assertFalse(any(row.get('date') == days[2] and
                             row['event'] == 'ASSUMED_NEXT_OPEN_FILLED'
                             for row in result['order_log']))
        first = result['daily_ledger'][0]['shares']['A']
        self.assertEqual(result['after_close_records'][0]['shares']['B'], first * 2)
        self.assertTrue(result['after_close_records'][0]['distribution_rights'])


if __name__ == '__main__':
    unittest.main()
