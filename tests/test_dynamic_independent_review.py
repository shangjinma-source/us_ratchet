from copy import deepcopy
from datetime import date, timedelta
import unittest

from backtest.dynamic_independent_review import review_account, review_selection_inputs, review_reentry_journal
from backtest.dynamic_historical_inputs import build_historical_inputs
from backtest.dynamic_switch_provider import build_dynamic_provider
from backtest.current_quantity_v2_next_open_book import run_next_open_book


class IndependentReviewTests(unittest.TestCase):
    def test_split_and_ads_fraction_are_rebuilt_without_cash_credit(self):
        days = ['2026-10-01', '2026-10-02', '2026-10-05']
        for kind in ('split', 'ads_conversion'):
            with self.subTest(kind=kind):
                successor = 'B' if kind == 'ads_conversion' else 'A'
                event = dict(type=kind, event_id='action', date=days[1], security_id='A',
                             new_shares='1' if kind == 'ads_conversion' else '2',
                             old_shares='2' if kind == 'ads_conversion' else '1',
                             source_references=['fixture'], delivery_model='DTC_BENEFICIAL_INTERESTS')
                if successor != 'A':
                    event['new_security_id'] = successor
                bars = {'A': {days[0]: dict(open='100', high='100', low='100', close='100')}}
                bars.setdefault(successor, {}).update({d: dict(open=p, high=p, low=p, close=p)
                    for d, p in zip(days[1:], ['200', '210'] if successor == 'B' else ['50', '55'])})
                fractions = {'action': {'PARENT_FRACTIONAL_CASH_RIGHT': dict(known_asof=days[1],
                    security_id='B', units='1/2', amount='7', source_references=['fixture'])}}
                bundle = dict(session_dates=days, ohlc=bars, initial_cash='300', initial_shares={'A': 3},
                              fee_bps='0', slippage_bps='0', actions=[event], distribution_fractional_cash_values=fractions)
                book = run_next_open_book(session_dates=days, ohlc=bars, initial_cash='300', initial_shares={'A': 3},
                    fee_bps='0', slippage_bps='0', events=[event], orders=[],
                    account_model='DTC_BENEFICIAL_INTERESTS', distribution_fractional_cash_values=fractions,
                    price_source_references={'A': ['fixture'], 'B': ['fixture']})
                audit = []
                for i, day in enumerate(days[:-1]):
                    prior = book['daily_ledger'][i-1] if i else dict(cash='300', shares={'A': 3}, distribution_rights=[])
                    state = dict(asof=day, cash=prior['cash'], shares=prior['shares'], distribution_rights=prior['distribution_rights'])
                    equity = 600 if not i else 500 if successor == 'B' else 600
                    audit.append(dict(input_account=state, decision_account=state, post_close_events_replayed=[],
                        capital_basis=dict(tradable_equity=str(equity), nontradable_equity_excluded_from_selection='7' if i and successor == 'B' else '0'),
                        signal=dict(signal_date=day, targets=state['shares'], target_differences=[])))
                metrics = review_account(bundle, dict(book=book, audit=audit))
                self.assertEqual(book['cash'], '300')
                self.assertEqual(metrics['final_equity'], '517' if successor == 'B' else '630')

    def test_rights_accounting_before_and_after_close_and_tampering(self):
        import test_dynamic_nontradable_capital as fixtures
        for timing in ('BEFORE_OPEN', 'AFTER_CLOSE'):
            with self.subTest(timing=timing):
                book, audit = fixtures.NontradableCapitalTests().run_case(timing=timing)
                days = [audit[0]['signal']['signal_date']]+[r['date'] for r in book['daily_ledger']]
                values = {'A': ['100', '80', '110', '110'], 'B': ['100']*4, 'C': ['10000']*4}
                bars = {s: {d: dict(open=p, close=p) for d, p in zip(days, series)} for s, series in values.items()}
                event = next(r['action_details'] for r in book['order_log'] if r['event'] == 'DISTRIBUTION_APPLIED')
                bundle = dict(session_dates=days, ohlc=bars, initial_cash='300', initial_shares={'A': 1},
                              fee_bps='0', slippage_bps='0', distribution_events=[event], distribution_fractional_cash_values={})
                document = dict(book=book, audit=audit)
                metrics = review_account(bundle, document)
                self.assertEqual(metrics['final_equity'], '10410')
                self.assertEqual(metrics['final_nontradable_value'], '10000')
                corrupt = deepcopy(document)
                corrupt['book']['daily_ledger'][-1]['cash'] = '999'
                with self.assertRaisesRegex(ValueError, 'ledger wealth'):
                    review_account(bundle, corrupt)

    def make_saved_case(self):
        calendar = []
        day = date(2024, 1, 1)
        while len(calendar) < 259:
            if day.weekday() < 5:
                calendar.append(day.isoformat())
            day += timedelta(days=1)
        sessions = calendar[252:]
        series = {'A': {d: str(100 if i < 254 else 70) for i, d in enumerate(calendar)},
                  'B': {d: str(100+i) for i, d in enumerate(calendar)}}
        bars = {s: {d: dict(open=p, high=p, low=p, close=p) for d, p in prices.items()} for s, prices in series.items()}
        bundle = dict(label='fixture', session_dates=sessions, calendar=calendar,
                      session_close_times=dict(closes={d: d+'T21:00:00+00:00' for d in calendar}, review_reference='fixture'),
                      eligibility={d: ['A', 'B'] for d in sessions}, training_series=series, ohlc=bars,
                      metadata={'A': {}, 'B': {}}, reset_dates=[sessions[0]], search_template={},
                      initial_cash='1000', initial_shares={'A': 1}, fee_bps='0', slippage_bps='10', risk_events=[],
                      distribution_events=[], actions=[], distribution_fractional_cash_values={})
        saved = {}
        builder = build_historical_inputs(bundle, selector=lambda **kw: dict(selected=dict(quantities={'B': 1})),
            selection_recorder=lambda d, a, s: saved.update({d: dict(arguments=a, selection=s)}))
        provider, audit = build_dynamic_provider(builder, nontradable_policy='SELECT_TRADABLE_REPORT_TOTAL')
        book = run_next_open_book(session_dates=sessions, ohlc=bars, initial_cash='1000', initial_shares={'A': 1},
                                 fee_bps='0', slippage_bps='10', order_provider=provider)
        return bundle, dict(book=book, audit=audit, book_id='L-A'), saved

    def test_saved_decisions_and_independent_arithmetic(self):
        bundle, document, saved = self.make_saved_case()
        metrics = review_account(bundle, document)
        self.assertGreater(metrics['fills'], 0)
        self.assertEqual(review_selection_inputs(bundle, document, saved.__getitem__)['selection_days'], 6)
        saved[next(iter(saved))]['arguments']['entered_cash'] = '99999'
        with self.assertRaisesRegex(ValueError, 'optimizer capital'):
            review_selection_inputs(bundle, document, saved.__getitem__)

    def test_reentry_fill_arithmetic(self):
        import test_dynamic_reentry_book as fixtures
        book, audit = fixtures.ReentryBookTests().run_case('LATER_CLOSE')
        days = [audit[0]['signal']['signal_date']]+[r['date'] for r in book['daily_ledger']]
        bars = {'A': {d: dict(open=p, close=p) for d, p in zip(days, ['100', '80', '75', '90', '91', '72', '70'])}}
        bars['A']['2026-10-07']['open'] = '92'
        bundle = dict(session_dates=days, ohlc=bars, initial_cash='300', initial_shares={'A': 1}, fee_bps='0', slippage_bps='0')
        metrics = review_account(bundle, dict(book=book, audit=audit))
        self.assertEqual(metrics['fills'], 3)
        self.assertEqual(metrics['final_equity'], '353')
        self.assertEqual(review_reentry_journal(bundle, dict(book=book, audit=audit)),
                         dict(reentry_fills=1, reentry_followed_by_risk_exit=1))
        corrupt = deepcopy(audit)
        corrupt[4]['reentry_execution_inputs']['executed_reentries'] = []
        with self.assertRaisesRegex(ValueError, 'execution journal'):
            review_reentry_journal(bundle, dict(book=book, audit=corrupt))


if __name__ == '__main__':
    unittest.main()
