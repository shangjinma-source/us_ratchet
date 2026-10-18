import unittest
from backtest.return_priority_limit_book import run_limit_book


def order(side='BUY', q=5, limit='10', **kwargs):
    return dict(id='o', security_id='x', decision_date='2024-01-01', active_date='2024-01-02',
                side=side, quantity=q, limit=limit, **kwargs)


def run(orders, bar=None, **kwargs):
    return run_limit_book(session_dates=['2024-01-01', '2024-01-02'], orders=orders,
                          ohlc={'x': {'2024-01-02': bar or dict(open='9', high='12', low='8', close='11'),
                                      '9999-01-01': object()}}, initial_cash='100', **kwargs)


class LimitBookTests(unittest.TestCase):
    def test_off_session_event_blocks_without_rolling_forward(self):
        event = dict(date='2024-01-02', security_id='x', type='split',
                     new_shares=2, old_shares=1, source_references=['official'])
        result = run_limit_book(session_dates=['2024-01-01', '2024-01-03'],
                               orders=[], initial_cash='100', initial_shares={'x': 10},
                               events=[event], ohlc={'x': {'2024-01-03': dict(open='5', high='5', low='5', close='5')}})
        self.assertEqual(result['reason'], 'INVALID_EVENT_SCHEDULE')
        self.assertEqual(result['shares'], {'x': 10})
        self.assertEqual(result['daily_ledger'], [])
        ignored = [{'date': '2024-01-01', 'type': object()}, {'date': '9999-01-01', 'type': object()}]
        self.assertEqual(run([], events=ignored)['status'], 'COMPLETE')

    def test_unexposed_merger_still_terminates_future_buy(self):
        later = order()
        later.update(decision_date='2024-01-02', active_date='2024-01-03')
        event = dict(date='2024-01-02', security_id='x', type='merger', share_cash='12', source_references=['official'])
        result = run_limit_book(session_dates=['2024-01-01', '2024-01-02', '2024-01-03'],
                                orders=[later], ohlc={}, initial_cash='100', events=[event])
        self.assertEqual(result['reason'], 'TERMINATED_SECURITY_ORDER')
        self.assertEqual(result['cash'], '100')
        self.assertEqual(result['receivable'], '0')
        event.pop('source_references')
        self.assertEqual(run([], events=[event])['reason'], 'EVENT_EVIDENCE_REQUIRED')

    def test_invalid_schedule_is_not_silently_ignored(self):
        for active in ('2023-12-31', '2024-01-01', '2024-01-02'):
            invalid = order()
            invalid['active_date'] = active
            result = run_limit_book(session_dates=['2024-01-01', '2024-01-03'],
                                    orders=[invalid], ohlc={}, initial_cash='100')
            self.assertEqual(result['reason'], 'INVALID_ORDER_SCHEDULE')
        self.assertEqual(run([{'active_date': '9999-01-01', 'quantity': object()}])['status'], 'COMPLETE')

    def test_gap_improvement_and_cash_conservation(self):
        result = run([order()])
        self.assertEqual(result['cash'], '55')
        self.assertEqual(result['shares']['x'], 5)
        self.assertEqual(result['daily_ledger'][0]['equity'], '110')
        result = run([order('SELL', 5)], initial_shares={'x': 5},
                     bar=dict(open='12', high='13', low='11', close='12'))
        self.assertEqual(result['cash'], '160')

    def test_expiry_and_future_poison(self):
        result = run([order(limit='7'), {'active_date': '9999-01-01', 'quantity': object()}],
                     events=[{'date': '9999-01-01', 'type': object()}])
        self.assertEqual(result['order_log'][-1]['event'], 'EXPIRED_UNFILLED')
        self.assertEqual(result['cash'], '100')

    def test_no_sales_financing_or_same_day_roundtrip(self):
        self.assertEqual(run([order(q=11)])['reason'], 'BUY_RESERVATIONS_EXCEED_AVAILABLE_CASH')
        sell = order('SELL')
        sell['id'] = 'sell'
        self.assertEqual(run([order(), sell], initial_shares={'x': 5})['status'], 'BLOCKED')
        self.assertEqual(run([sell])['reason'], 'SELL_EXCEEDS_PRIOR_HOLDINGS')
        sell['security_id'] = 'y'
        result = run([order(q=11), sell], initial_shares={'y': 5})
        self.assertEqual(result['reason'], 'BUY_RESERVATIONS_EXCEED_AVAILABLE_CASH')

    def test_bad_bars_timing_and_order_only_unknown_action(self):
        self.assertEqual(run([order()], bar=dict(open='9', low='10', high='12', close='11'))['reason'], 'INCONSISTENT_OHLC')
        wrong = order()
        wrong['decision_date'] = '2023-12-31'
        self.assertEqual(run([wrong])['reason'], 'ORDER_NOT_NEXT_SESSION')
        event = dict(date='2024-01-02', security_id='x', type='spinoff', source_references=['official'])
        self.assertEqual(run([order()], events=[event])['reason'], 'UNMODELLED_HELD_OR_ORDERED_ACTION')
        self.assertEqual(run_limit_book(session_dates=['2024-01-01', '2024-01-02'], orders=[order()], ohlc={}, initial_cash='100')['reason'], 'MISSING_OR_INVALID_REQUIRED_OHLC')

    def test_split_adjusts_order_and_holdings(self):
        event = dict(date='2024-01-02', security_id='x', type='split', new_shares=10,
                     old_shares=1, source_references=['official'])
        result = run([order('SELL', 5, '10')], initial_shares={'x': 5}, events=[event],
                     bar=dict(open='1', high='1.2', low='.8', close='1'))
        self.assertEqual(result['cash'], '150')
        self.assertEqual(result['shares']['x'], 0)
        result = run([order(limit='10.01')], events=[event])
        self.assertEqual(result['reason'], 'NONINTEGER_OR_SUBCENT_SPLIT_ORDER')

    def test_merger_cancels_orders_and_keeps_receivable(self):
        event = dict(date='2024-01-02', security_id='x', type='merger', share_cash='12', source_references=['official'])
        result = run_limit_book(session_dates=['2024-01-01', '2024-01-02'], orders=[order('SELL')],
                               ohlc={}, initial_cash='100', initial_shares={'x': 5}, events=[event])
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['cash'], '100')
        self.assertEqual(result['receivable'], '60')
        event['type'] = 'spinoff'
        self.assertEqual(run([], initial_shares={'x': 5}, events=[event])['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
