import unittest
from backtest.cash_balance_policy_book import run_next_open_book


class CashPolicyBookTests(unittest.TestCase):
    days = ['2026-10-01', '2026-10-02', '2026-10-05']

    def bars(self):
        return {sid: {day: dict(open='10', high='10', low='10', close='10')
                      for day in self.days} for sid in ['A', 'B']}

    def test_sell_proceeds_wait_until_next_decision_before_funding_buy(self):
        def provider(*, decision_date, active_date, state):
            targets = {'A': 0, 'B': 20}
            orders = []
            for sid, target in targets.items():
                delta = target-state['shares'].get(sid, 0)
                if delta:
                    orders.append(dict(id=decision_date+sid, security_id=sid,
                        side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                        decision_date=decision_date, active_date=active_date, decision_mark='10'))
            return dict(status='READY', orders=orders)
        book = run_next_open_book(session_dates=self.days, ohlc=self.bars(),
            initial_cash='100', initial_shares={'A': 10}, fee_bps='0', slippage_bps='0',
            order_provider=provider)
        self.assertEqual(book['status'], 'COMPLETE')
        self.assertEqual(book['daily_ledger'][0]['shares'], {'A': 0, 'B': 10})
        self.assertEqual(book['daily_ledger'][0]['cash'], '100')
        self.assertEqual(book['shares'], {'A': 0, 'B': 20})
        self.assertEqual(book['cash'], '0')

    def test_flow_snapshot_is_coherent_without_rewriting_previous_close(self):
        snapshots = []
        def provider(**arguments):
            snapshots.append(arguments['state'])
            return dict(status='READY', orders=[])
        book = run_next_open_book(session_dates=self.days, ohlc=self.bars(),
            initial_cash='100', initial_shares={'A': 10}, fee_bps='0', slippage_bps='0',
            order_provider=provider, external_cash_flows=[
                dict(date=self.days[0], amount='200'), dict(date=self.days[1], amount='-50')])
        self.assertEqual(book['status'], 'COMPLETE')
        self.assertEqual(book['external_flows'], '150')
        self.assertEqual(snapshots[1]['cash'], '250')
        self.assertEqual(snapshots[1]['daily_ledger'][-1]['equity'], '350')
        self.assertEqual(book['daily_ledger'][0]['cash'], '300')
        self.assertEqual(book['daily_ledger'][0]['equity'], '400')
        self.assertEqual(book['daily_ledger'][1]['equity'], '350')

    def test_unfunded_withdrawal_stops_before_any_trade(self):
        book = run_next_open_book(session_dates=self.days, ohlc=self.bars(),
            initial_cash='100', initial_shares={'A': 10}, fee_bps='0', slippage_bps='0',
            orders=[], external_cash_flows=[dict(date=self.days[0], amount='-101')])
        self.assertEqual(book['reason'], 'WITHDRAWAL_EXCEEDS_CONFIRMED_CASH')
        self.assertEqual(book['cash'], '100')
        self.assertEqual(book['daily_ledger'], [])


if __name__ == '__main__':
    unittest.main()
