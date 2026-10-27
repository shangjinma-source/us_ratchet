from fractions import Fraction
import unittest
from backtest.guidance_cash_next_open_book_research_v1 import run_next_open_book
from backtest.historical_dividend_next_open_book_research import run_next_open_book as baseline


class NewsCashBookTests(unittest.TestCase):
    def setup_book(self, fraction='1', split=False, cancel=False):
        days = ['2026-01-28', '2026-01-29', '2026-01-30', '2026-02-02']
        bars = {sid: {day: dict(open='10', high='10', low='10', close='10') for day in days} for sid in ('A', 'B')}
        def provider(*, decision_date, active_date, state):
            orders = []
            if decision_date == days[0]:
                orders.append(dict(id='sell', security_id='A', side='SELL', quantity=10,
                                   decision_mark='10', decision_date=decision_date, active_date=active_date))
            orders.append(dict(id='buy-'+active_date, security_id='B', side='BUY', quantity=30,
                               decision_mark='10', decision_date=decision_date, active_date=active_date))
            return dict(status='READY', orders=orders, target_decision_date=days[0] if decision_date < days[2] else days[2],
                        news_sale_fractions={'sell': fraction} if decision_date == days[0] else {})
        args = dict(session_dates=days, ohlc=bars, initial_cash='20', initial_shares={'A': 10},
                    fee_bps='10', slippage_bps='5', order_provider=provider,
                    news_allocation_dates=[days[0], days[2]])
        if split:
            args['events'] = [dict(date=days[1], type='split', security_id='A', old_shares=1, new_shares=2, source_references=['synthetic'])]
        if cancel:
            args['events'] = [dict(date=days[1], type='merger', security_id='A', share_cash='10', source_references=['synthetic'])]
        return args

    def test_realized_cash_held_across_sessions_then_released(self):
        result = run_next_open_book(**self.setup_book())
        self.assertEqual(result['status'], 'COMPLETE')
        rows = result['daily_ledger']
        net = Fraction(10) * Fraction('10') * Fraction('0.9995') * Fraction('0.999')
        self.assertEqual(Fraction(rows[0]['news_reserved_cash']), net)
        self.assertEqual(rows[0]['shares']['B'], 1)
        self.assertEqual(rows[1]['shares']['B'], 1)
        self.assertEqual(rows[2]['news_reserved_cash'], '0')
        self.assertGreater(rows[2]['shares']['B'], rows[1]['shares']['B'])
        for row in rows:
            self.assertEqual(Fraction(row['equity']), Fraction(row['cash']) + Fraction(row['stock_value']))

    def test_only_incremental_fraction_reserved(self):
        result = run_next_open_book(**self.setup_book(fraction='1/2'))
        first = result['daily_ledger'][0]
        net = Fraction(10) * 10 * Fraction('0.9995') * Fraction('0.999') / 2
        self.assertEqual(Fraction(first['news_reserved_cash']), net)
        self.assertEqual(first['shares']['B'], 6)

    def test_split_adjusted_fill_drives_reservation(self):
        result = run_next_open_book(**self.setup_book(fraction='1/2', split=True))
        reserved = [entry for entry in result['order_log'] if entry['event'] == 'NEWS_NET_PROCEEDS_RESERVED'][0]
        fill = [entry for entry in result['order_log'] if entry.get('id') == 'sell' and entry['event'] == 'ASSUMED_NEXT_OPEN_FILLED'][0]
        self.assertEqual(fill['quantity'], 20)
        self.assertEqual(Fraction(reserved['amount']), (20 * Fraction(fill['price']) - Fraction(fill['fee'])) / 2)

    def test_no_fill_no_reserved_proceeds(self):
        result = run_next_open_book(**self.setup_book(cancel=True))
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['news_cash_reservation']['amount'], '0')
        self.assertFalse(any(entry['event'] == 'NEWS_NET_PROCEEDS_RESERVED' for entry in result['order_log']))
        self.assertTrue(any(entry['event'] == 'CANCELLED_TERMINATION' for entry in result['order_log']))

    def test_disabled_path_exactly_matches_original(self):
        args = self.setup_book()
        del args['news_allocation_dates']
        self.assertEqual(run_next_open_book(**args), baseline(**args))

    def test_invalid_attribution_rejected(self):
        for fraction in ['2', '-1', '1/3', True]:
            result = run_next_open_book(**self.setup_book(fraction=fraction))
            self.assertEqual(result['reason'], 'INVALID_NEWS_SALE_ATTRIBUTION')

    def test_daily_epoch_cannot_release_reserved_cash(self):
        args = self.setup_book()
        provider = args['order_provider']
        def bad_provider(**kwargs):
            result = provider(**kwargs)
            result['target_decision_date'] = kwargs['decision_date']
            return result
        args['order_provider'] = bad_provider
        self.assertEqual(run_next_open_book(**args)['reason'], 'NEWS_ALLOCATION_BINDING_MISMATCH')

    def test_wait_keeps_reserve_without_epoch_field(self):
        args = self.setup_book()
        provider = args['order_provider']
        def waiting_provider(**kwargs):
            if kwargs['decision_date'] == '2026-01-29':
                return dict(status='READY', action='WAIT_POST_ACTION_MARK', orders=[], news_sale_fractions={})
            return provider(**kwargs)
        args['order_provider'] = waiting_provider
        result = run_next_open_book(**args)
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['daily_ledger'][0]['news_reserved_cash'], result['daily_ledger'][1]['news_reserved_cash'])

    def test_failed_new_epoch_admission_does_not_release(self):
        args = self.setup_book()
        provider = args['order_provider']
        def invalid_provider(**kwargs):
            result = provider(**kwargs)
            if kwargs['decision_date'] == '2026-01-30':
                result['news_sale_fractions'] = {'absent': '1'}
            return result
        args['order_provider'] = invalid_provider
        result = run_next_open_book(**args)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertGreater(Fraction(result['news_cash_reservation']['amount']), 0)
        self.assertEqual(result['news_cash_reservation']['allocation_epoch'], '2026-01-28')

    def test_all_split_attributions_checked_before_first_sell(self):
        args = self.setup_book()
        args['initial_shares']['B'] = 2
        args['events'] = [dict(date='2026-01-29', type='split', security_id='B', old_shares=2, new_shares=1, source_references=['synthetic'])]
        def provider(**kwargs):
            orders = [dict(id=identity, security_id=sid, side='SELL', quantity=quantity,
                           decision_mark='10', decision_date=kwargs['decision_date'], active_date=kwargs['active_date'])
                      for identity, sid, quantity in [('first', 'A', 10), ('second', 'B', 2)]]
            return dict(status='READY', orders=orders, target_decision_date='2026-01-28', news_sale_fractions={'second': '1/2'})
        args['order_provider'] = provider
        result = run_next_open_book(**args)
        self.assertEqual(result['reason'], 'FRACTIONAL_NEWS_SALE_AFTER_ACTION')
        self.assertFalse(any(entry['event'] == 'ASSUMED_NEXT_OPEN_FILLED' for entry in result['order_log']))
