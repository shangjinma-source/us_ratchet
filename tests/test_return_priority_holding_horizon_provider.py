import unittest
from datetime import date, timedelta

from backtest.return_priority_holding_horizon_provider import build_holding_horizon_provider


DAYS = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(29)]


def make(months=(0, 21, 24), actions=(), prices=None):
    return build_holding_horizon_provider(session_dates=DAYS,
        monthly_decisions=[dict(decision_date=DAYS[i], target_weights={'a': '1'}) for i in months],
        close_prices=prices or {'a': {d: '10' for d in DAYS}}, actions=actions)


def call(p, i, quantity=0, cash='100'):
    return p(decision_date=DAYS[i], active_date=DAYS[i+1],
             state=dict(asof=DAYS[i], cash=cash, shares={'a': quantity} if quantity else {}, receivable='9999'))


class HoldingHorizonTests(unittest.TestCase):
    def test_early_flat_then_rebuy_starts_new_clock(self):
        p = make(months=(0,))
        call(p, 0)
        call(p, 1, quantity=10, cash='0')
        call(p, 2, quantity=0, cash='100')
        result = call(p, 3, quantity=10, cash='0')
        self.assertEqual(result['holding_entry_dates']['a'], DAYS[3])
        self.assertEqual(result['holding_session_ages']['a'], 1)

    def test_flat_after_monthly_waits_until_next_monthly(self):
        p = make(months=(0, 22, 26))
        call(p, 0)
        for i in range(1, 23):
            result = call(p, i, quantity=10, cash='0')
        self.assertIn('a', result['exit_trigger_dates'])  # month reset while exit unfilled
        for i in range(23, 26):
            result = call(p, i, cash='100')
            self.assertEqual(result['orders'], [])
            self.assertIn('a', result['exit_trigger_dates'])
        result = call(p, 26, cash='100')
        self.assertEqual(result['released_exit_latches'], ['a'])
        self.assertEqual(result['orders'][0]['side'], 'BUY')

    def test_actual_entry_clock_month_reset_exit_priority_and_no_rebuy(self):
        p = make()
        self.assertEqual(call(p, 0)['holding_entry_dates'], {})
        for i in range(1, 21):
            result = call(p, i, quantity=10, cash='0')
            self.assertNotIn('a', result['exit_trigger_dates'])
        result = call(p, 21, quantity=10, cash='0')
        self.assertEqual(result['base_target_shares']['a'], 10)
        self.assertEqual(result['effective_target_shares']['a'], 0)
        self.assertEqual(result['holding_session_ages']['a'], 21)
        self.assertEqual(result['orders'][0]['active_date'], DAYS[22])
        self.assertEqual(result['orders'][0]['side'], 'SELL')
        result = call(p, 22, quantity=10, cash='100')  # unfilled sell, cash cannot reopen
        self.assertEqual([o['side'] for o in result['orders']], ['SELL'])
        result = call(p, 23, cash='100')  # actual flat, but no monthly reset yet
        self.assertEqual(result['orders'], [])
        self.assertIn('a', result['exit_trigger_dates'])
        result = call(p, 24, cash='100')
        self.assertEqual(result['released_exit_latches'], ['a'])
        self.assertEqual(result['orders'][0]['side'], 'BUY')
        result = call(p, 25, quantity=10, cash='0')
        self.assertEqual(result['holding_session_ages']['a'], 1)

    def test_add_reduce_and_split_never_reset_entry(self):
        event = dict(date=DAYS[10], security_id='a', type='split', new_shares=2, old_shares=1, source_references=['synthetic'])
        prices = {'a': {d: '10' if i<10 else '5' for i,d in enumerate(DAYS)}}
        p = make(months=(0,), actions=[event], prices=prices)
        call(p, 0)
        for i in range(1, 22):
            quantity = (10 if i<5 else 11 if i<8 else 9) if i<10 else 18
            result = call(p, i, quantity=quantity, cash='0')
        self.assertEqual(result['holding_entry_dates']['a'], DAYS[1])
        self.assertEqual(result['holding_session_ages']['a'], 21)
        self.assertEqual(result['base_target_shares']['a'], 20)
        self.assertEqual(result['orders'][0]['quantity'], 18)

    def test_unfilled_initial_buys_do_not_age_and_initial_nonzero_blocks(self):
        self.assertEqual(call(make(), 0, quantity=1)['reason'], 'INITIAL_POSITION_ENTRY_UNKNOWN')
        p = make(months=(0,))
        for i in range(23):
            result = call(p, i)
        self.assertEqual(result['holding_entry_dates'], {})
        self.assertEqual(result['exit_trigger_dates'], {})
        self.assertEqual(result['orders'][0]['side'], 'BUY')

    def test_future_payload_unread(self):
        p = make(prices={'a': {DAYS[0]: '10', DAYS[1]: object()}},
                 actions=[dict(date=DAYS[2], security_id=object())])
        self.assertEqual(call(p, 0)['status'], 'READY')

    def test_gate_rebuilds_cash_allocation_not_only_filters_orders(self):
        p = build_holding_horizon_provider(session_dates=DAYS,
            monthly_decisions=[dict(decision_date=DAYS[0], target_weights={'a': '1'}),
                dict(decision_date=DAYS[21], target_weights={'a': '0.75', 'b': '0.25'})],
            close_prices={s:{d:'10' for d in DAYS} for s in ('a','b','c')})
        call(p, 0)
        for i in range(1,22):
            result = p(decision_date=DAYS[i], active_date=DAYS[i+1],
                state=dict(asof=DAYS[i], cash='20', shares={'a':1,'c':7}))
        # Base buys two a shares first, exhausting cash before b. Rebuilding
        # after gating must instead fund b, without borrowing either sale.
        self.assertEqual([(o['security_id'],o['side'],o['quantity']) for o in result['orders']], [('a','SELL',1),('c','SELL',7),('b','BUY',2)])
        self.assertEqual(result['reserved_cash'], '20')
        self.assertEqual(result['effective_target_shares'], {'a':0,'b':2,'c':0})


if __name__ == '__main__':
    unittest.main()
