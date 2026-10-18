import unittest
from backtest.return_priority_monthly_target_provider import build_monthly_target_provider


DATES = ['2024-01-30', '2024-01-31', '2024-02-01', '2024-02-02']


def state(day, cash='100', **shares):
    return dict(asof=day, cash=cash, shares=shares, receivable='9999')


def make(plans=None, prices=None, actions=()):
    return build_monthly_target_provider(session_dates=DATES,
        monthly_decisions=plans or [dict(decision_date=DATES[0], target_weights={'a': '1'})],
        close_prices=prices or {'a': {d: '10' for d in DATES}, 'b': {d: '10' for d in DATES}}, actions=actions)


class MonthlyProviderTests(unittest.TestCase):
    def test_unfilled_reposts_new_close_without_resizing(self):
        p = make(prices={'a': {DATES[0]: '10', DATES[1]: '9.999'}})
        first = p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0]))
        second = p(decision_date=DATES[1], active_date=DATES[2], state=state(DATES[1]))
        self.assertEqual(first['orders'][0]['quantity'], 10)
        self.assertEqual(second['orders'][0]['quantity'], 10)
        self.assertEqual(second['orders'][0]['limit'], '999/100')
        self.assertNotEqual(first['orders'][0]['id'], second['orders'][0]['id'])

    def test_sell_proceeds_only_next_decision_and_receivable_excluded(self):
        p = make(plans=[dict(decision_date=DATES[0], target_weights={'b': '1'})])
        first = p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0], cash='0', a=10))
        self.assertEqual(first['target_shares'], {'b': 10})
        self.assertEqual(first['investable_equity_at_reset'], '100')
        self.assertEqual([o['side'] for o in first['orders']], ['SELL'])
        self.assertEqual(first['wait_cash'][0]['remaining_deficit'], 10)
        second = p(decision_date=DATES[1], active_date=DATES[2], state=state(DATES[1], cash='100'))
        self.assertEqual(second['orders'][0]['side'], 'BUY')
        self.assertEqual(second['orders'][0]['quantity'], 10)

    def test_partial_cash_deficit_descending_and_sid_tie(self):
        p = make(plans=[dict(decision_date=DATES[0], target_weights={'a': '0.6', 'b': '0.4'})])
        first = p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0], cash='30', b=7))
        self.assertEqual(first['status'], 'READY')
        self.assertEqual([(o['security_id'], o['quantity']) for o in first['orders'] if o['side']=='BUY'], [('a', 3)])
        self.assertEqual(first['wait_cash'][0]['remaining_deficit'], 3)
        p = make(plans=[dict(decision_date=DATES[0], target_weights={'a': '0.5', 'b': '0.5'})],
                 prices={sid: {d: '10' for d in DATES} for sid in ['a', 'b', 'c']})
        first = p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0], cash='30', c=7))
        self.assertEqual([o['security_id'] for o in first['orders'] if o['side']=='BUY'], ['a'])

    def test_month_replaces_target_retains_actual_residual(self):
        p = make(plans=[dict(decision_date=DATES[0], target_weights={'a': '1'}),
                        dict(decision_date=DATES[1], target_weights={'b': '1'})])
        p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0]))
        result = p(decision_date=DATES[1], active_date=DATES[2], state=state(DATES[1], cash='0', a=10))
        self.assertEqual(result['target_shares'], {'b': 10})
        self.assertEqual(result['orders'][0]['security_id'], 'a')
        self.assertEqual(result['orders'][0]['side'], 'SELL')
        self.assertTrue(result['wait_cash'])

    def test_split_target_once_even_no_actual_position(self):
        p = make(actions=[dict(date=DATES[1], security_id='a', type='split', new_shares=2, old_shares=1, source_references=['fixture'])],
                 prices={'a': {DATES[0]: '10', DATES[1]: '5', DATES[2]: '5'}})
        first = p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0]))
        self.assertEqual(first['orders'][0]['quantity'], 10)  # kernel adjusts active order
        second = p(decision_date=DATES[1], active_date=DATES[2], state=state(DATES[1]))
        third = p(decision_date=DATES[2], active_date=DATES[3], state=state(DATES[2]))
        self.assertEqual(second['target_shares']['a'], 20)
        self.assertEqual(third['target_shares']['a'], 20)

    def test_fractional_target_unknown_action_and_future_payload(self):
        for action, reason in [
            (dict(type='split', new_shares=1, old_shares=3, source_references=['fixture']), 'FRACTIONAL_SPLIT_TARGET_UNSUPPORTED'),
            (dict(type='identity_change'), 'UNSUPPORTED_EXPOSED_ACTION')]:
            p = make(actions=[dict(date=DATES[1], security_id='a', **action)])
            p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0]))
            result = p(decision_date=DATES[1], active_date=DATES[2], state=state(DATES[1]))
            self.assertEqual(result['reason'], reason)
        p = make(prices={'a': {DATES[0]: '10', DATES[1]: object()}}, actions=[dict(date=DATES[2], security_id=object())])
        self.assertEqual(p(decision_date=DATES[0], active_date=DATES[1], state=state(DATES[0]))['status'], 'READY')


if __name__ == '__main__':
    unittest.main()
