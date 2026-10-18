import unittest
from datetime import date, timedelta
from backtest.return_priority_swing_limit_plan import build_swing_limit_plan


def arguments():
    dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(20)]
    bars = [dict(date=d, open='10', high='12', low='9', close='10') for d in dates]
    bars[-1].update(open='11', close='11')
    return dict(mode='trend_exit', decision_date=dates[-1], next_session='2024-01-21',
                frozen_weights={'x': '1/2'}, initial_cash='100', available_cash='100', shares={},
                observed_ohlc={'x': dict(basis='DECISION_NOMINAL_SHARE_UNITS', unit_asof=dates[-1],
                                         complete_session_history=True, bars=bars)})


class SwingLimitTests(unittest.TestCase):
    def test_entry_formula_whole_shares_and_future_poison(self):
        args = arguments()
        args['observed_ohlc']['x']['bars'].append({'date': '9999-01-01', 'close': object()})
        result = build_swing_limit_plan(**args)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['diagnostics']['x']['atr14'], '3')
        self.assertEqual(result['orders'][0]['limit'], '51/5')
        self.assertEqual(result['orders'][0]['quantity'], 4)
        self.assertEqual(result['reservation_cash'], '204/5')

    def test_modes_differ_only_on_strong_held_exit(self):
        args = arguments()
        args['shares'] = {'x': 4}
        self.assertEqual(build_swing_limit_plan(**args)['orders'], [])
        args.update(mode='band_exit', entry_positions={'x': dict(average_cost='9.001', entry_atr14='1',
                    basis='DECISION_NOMINAL_SHARE_UNITS', unit_asof=args['decision_date'])})
        result = build_swing_limit_plan(**args)
        self.assertEqual(result['orders'][0]['limit'], '1101/100')
        self.assertEqual(result['orders'][0]['quantity'], 4)
        args['observed_ohlc']['x']['bars'][-1]['close'] = '10'
        for mode in ('trend_exit', 'band_exit'):
            args['mode'] = mode
            self.assertEqual(build_swing_limit_plan(**args)['orders'][0]['limit'], '497/50')

    def test_cash_shortage_no_partial_or_sell_financing(self):
        args = arguments()
        args['available_cash'] = '1'
        result = build_swing_limit_plan(**args)
        self.assertEqual(result['status'], 'CASH_ALLOCATION_REQUIRED')
        self.assertEqual(result['orders'], [])
        self.assertEqual(len(result['proposed_orders']), 1)

    def test_history_and_units_fail_closed(self):
        args = arguments()
        args['observed_ohlc']['x']['bars'].pop(0)
        self.assertEqual(build_swing_limit_plan(**args)['status'], 'BLOCKED')
        args = arguments()
        args['observed_ohlc']['x']['basis'] = 'UNKNOWN'
        self.assertEqual(build_swing_limit_plan(**args)['status'], 'BLOCKED')

    def test_duplicate_missing_decision_and_bad_range_block(self):
        args = arguments()
        args['observed_ohlc']['x']['bars'].append(args['observed_ohlc']['x']['bars'][-1])
        self.assertEqual(build_swing_limit_plan(**args)['status'], 'BLOCKED')
        args = arguments()
        args['decision_date'] = '2024-01-21'
        args['next_session'] = '2024-01-22'
        args['observed_ohlc']['x']['unit_asof'] = args['decision_date']
        self.assertEqual(build_swing_limit_plan(**args)['status'], 'BLOCKED')
        args = arguments()
        args['observed_ohlc']['x']['bars'][-1]['low'] = '15'
        self.assertEqual(build_swing_limit_plan(**args)['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
