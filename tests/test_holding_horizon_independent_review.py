"""Independent synthetic lifecycle tests; no historical inputs or search."""
import unittest
from datetime import date, timedelta
from backtest.return_priority_holding_horizon_provider import build_holding_horizon_provider
from backtest.return_priority_limit_book import run_limit_book


class IndependentHorizonReview(unittest.TestCase):
    def test_kernel_execution_exit_day_and_monthly_reentry(self):
        days = [(date(2030, 1, 1) + timedelta(days=i)).isoformat() for i in range(29)]
        provider = build_holding_horizon_provider(session_dates=days,
            monthly_decisions=[{'decision_date': days[i], 'target_weights': {'x': '1'}} for i in (0, 21, 24)],
            close_prices={'x': {d: '10' for d in days}})
        audit = []
        def capture(**kwargs):
            result = provider(**kwargs)
            audit.append(result)
            return result
        result = run_limit_book(session_dates=days, initial_cash='20000', order_provider=capture,
            ohlc={'x': {d: dict(open='10', high='11', low='9', close='10') for d in days}})
        self.assertEqual(result['status'], 'COMPLETE')
        fills = [(r['date'], r['side'], r['quantity']) for r in result['order_log'] if r['event'] == 'ASSUMED_FILLED']
        self.assertEqual(fills, [(days[1], 'BUY', 2000), (days[22], 'SELL', 2000), (days[25], 'BUY', 2000)])
        self.assertEqual(audit[21]['holding_session_ages']['x'], 21)
        self.assertEqual(audit[22]['orders'], [])
        self.assertEqual(audit[23]['orders'], [])
        self.assertEqual(audit[25]['holding_session_ages']['x'], 1)
        self.assertEqual(result['cash'], '0')

    def test_expired_exit_reprices_and_never_funds_same_session_buys(self):
        days = [(date(2030, 1, 1) + timedelta(days=i)).isoformat() for i in range(26)]
        prices = {s: {d: '10' for d in days} for s in ('x','y')}
        provider = build_holding_horizon_provider(session_dates=days,
            monthly_decisions=[{'decision_date': days[0], 'target_weights': {'x':'1'}},
                               {'decision_date': days[21], 'target_weights': {'x':'0.5','y':'0.5'}}], close_prices=prices)
        for i in range(22):
            state = dict(asof=days[i],cash='100' if i==0 else '0',shares={} if i==0 else {'x':10})
            result = provider(decision_date=days[i], active_date=days[i+1], state=state)
        self.assertEqual([(r['security_id'],r['side']) for r in result['orders']], [('x','SELL')])
        self.assertEqual(result['wait_cash'][0]['security_id'], 'y')
        prices['x'][days[22]] = '8.001'
        result = provider(decision_date=days[22],active_date=days[23],state=dict(asof=days[22],cash='0',shares={'x':10}))
        self.assertEqual(result['orders'][0]['limit'], '801/100')
        self.assertEqual(result['orders'][0]['quantity'], 10)
        self.assertEqual(result['reserved_cash'], '0')

    def test_target_split_with_zero_actual_shares_and_fractional_block(self):
        days=['2030-01-01','2030-01-02','2030-01-03','2030-01-04']
        for numerator, denominator, expected in [(2,1,'READY'),(1,3,'BLOCKED')]:
            provider=build_holding_horizon_provider(session_dates=days,
                monthly_decisions=[dict(decision_date=days[0],target_weights={'x':'1'})],
                close_prices={'x':{d:'10' for d in days}},
                actions=[dict(date=days[1],security_id='x',type='split',new_shares=numerator,old_shares=denominator,source_references=['synthetic'])])
            provider(decision_date=days[0],active_date=days[1],state=dict(asof=days[0],cash='100',shares={}))
            result=provider(decision_date=days[1],active_date=days[2],state=dict(asof=days[1],cash='100',shares={}))
            self.assertEqual(result['status'],expected)
            if expected=='READY':
                self.assertEqual(result['base_target_shares']['x'],20)
                self.assertEqual(result['holding_entry_dates'],{})
            else:self.assertEqual(result['reason'],'FRACTIONAL_SPLIT_TARGET_UNSUPPORTED')


if __name__ == '__main__':
    unittest.main()
