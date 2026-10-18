import unittest
from datetime import date, timedelta
from scripts.return_priority_historical_swing_experiment import reconstruct_entries, scale_orders, provider_for


class RunnerTests(unittest.TestCase):
    def test_entry_day_split_atr_once_then_holding_split(self):
        logs = [dict(date='2024-01-02', event='CORPORATE_ACTION', security_id='x', type='split',
                     action_details=dict(new_shares=10, old_shares=1)),
                dict(date='2024-01-02', event='ASSUMED_FILLED', security_id='x', id='buy', side='BUY', quantity=10, price='10')]
        result = reconstruct_entries(logs, {'buy': '20'}, '2024-01-02', {'x': 10})
        self.assertEqual(result['x']['entry_atr14'], '2')
        self.assertEqual(result['x']['average_cost'], '10')
        logs.append(dict(date='2024-01-03', event='CORPORATE_ACTION', security_id='x', type='split', action_details=dict(new_shares=2, old_shares=1)))
        result = reconstruct_entries(logs, {'buy': '20'}, '2024-01-03', {'x': 20})
        self.assertEqual(result['x']['entry_atr14'], '1')
        self.assertEqual(result['x']['average_cost'], '5')
        with self.assertRaises(ValueError):
            reconstruct_entries(logs, {'buy': '20'}, '2024-01-02', {'x': 10})

    def test_common_cash_scaling_no_sell_financing(self):
        orders = [dict(id='x', side='BUY', quantity=3, limit='10'), dict(id='y', side='BUY', quantity=7, limit='10'),
                  dict(id='sell', side='SELL', quantity=10, limit='100')]
        result, changes = scale_orders(orders, '50')
        self.assertEqual([r['quantity'] for r in result], [1, 3, 10])
        self.assertTrue(all(row['common_factor'] == '1/2' for row in changes))
        self.assertEqual(orders[0]['quantity'], 3)

    def test_callback_never_reads_future_bar_or_event(self):
        days = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(21)]
        prices = {day: dict(open='10', high='12', low='9', close='10') for day in days[:20]}
        prices[days[19]]['close'] = '11'
        prices[days[20]] = object()
        window = dict(nominal_ohlc={'x': prices}, calendar=days, frozen_weights={'x': '1'}, initial_cash='100',
                      events={'split_events': [dict(date=days[20], new_shares=object())]})
        plans = []
        callback = provider_for(window, 'trend_exit', plans)
        result = callback(decision_date=days[19], active_date=days[20],
                          state=dict(order_log=[], shares={}, terminated_security_ids=[], cash='100', asof=days[19]))
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['orders'][0]['quantity'], 9)


if __name__ == '__main__':
    unittest.main()
