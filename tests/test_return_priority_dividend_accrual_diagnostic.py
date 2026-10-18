"""Hand-calculated artificial entitlement paths; no real source or strategy IO."""
from copy import deepcopy
from fractions import Fraction
import unittest

from backtest.return_priority_dividend_accrual_diagnostic import (
    diagnose_dividend_accrual, DividendDiagnosticInputError, PRICE_BASIS,
)


def arguments():
    return dict(book=dict(status='COMPLETE_CONDITIONAL_PAPER_BOOK', daily_rows=[
        dict(session='2026-01-05', shares={'A': 10}, close_equity=100, external_cash_flow=0, cash=0),
        dict(session='2026-01-06', shares={'B': 5}, close_equity=90, external_cash_flow=0, cash=20),
        dict(session='2026-01-07', shares={'B': 5}, close_equity=80, external_cash_flow=0, cash=20),
    ], executions=[{'untouched': True}]), initial_shares={'A': 2}, initial_equity=100,
        events=[], price_basis=PRICE_BASIS, same_share_unit_basis=True)


def event(identifier, security, day, amount):
    return dict(id=identifier, security_id=security, event_date=day, amount_per_share=amount)


class DividendAccrualTests(unittest.TestCase):
    def test_initial_sell_buy_eligibility_and_immutable_book(self):
        values = arguments()
        values['events'] = [event('first', 'A', '2026-01-05', 1), event('sold', 'A', '2026-01-06', 1),
                            event('bought', 'B', '2026-01-06', 3), event('held', 'B', '2026-01-07', 2)]
        original = deepcopy(values)
        result = diagnose_dividend_accrual(**values)
        self.assertEqual(values, original)
        self.assertEqual({row['id']: row['eligible_shares'] for row in result['gross_accrual_events']},
                         {'first': 2, 'sold': 10, 'bought': 0, 'held': 5})
        self.assertEqual(result['cumulative_gross_entitlement'], '22')
        self.assertEqual([row['derived_close_equity'] for row in result['daily_rows']], ['102'] * 3)
        self.assertEqual(Fraction(result['derived_net_return']), Fraction(1, 50))
        self.assertEqual(result['derived_max_drawdown'], '0')
        self.assertFalse(result['cash_credited'])
        self.assertFalse(result['payment_verified'])
        self.assertFalse(result['total_return_certified'])

    def test_exact_returns_drawdown_and_no_events_do_not_prove_coverage(self):
        result = diagnose_dividend_accrual(**arguments())
        self.assertEqual(Fraction(result['derived_net_return']), Fraction(-1, 5))
        self.assertEqual(Fraction(result['derived_max_drawdown']), Fraction(-1, 5))
        self.assertEqual(Fraction(result['daily_rows'][-1]['daily_net_return']), Fraction(-1, 9))
        self.assertFalse(result['event_coverage_complete_verified'])
        self.assertFalse(result['annualization_performed'])

    def test_outside_ignored_but_inside_missing_session_rejected(self):
        values = arguments()
        values['events'] = [event('old', 'A', '2026-01-04', 1), event('later', 'A', '2026-01-08', 1)]
        result = diagnose_dividend_accrual(**values)
        self.assertEqual(result['ignored_outside_window_event_count'], 2)
        self.assertEqual(result['gross_accrual_events'], [])
        values['book']['daily_rows'].pop(1)
        values['events'] = [event('missing', 'A', '2026-01-06', 1)]
        with self.assertRaises(DividendDiagnosticInputError):
            diagnose_dividend_accrual(**values)

    def test_duplicates_and_invalid_events_rejected_including_outside(self):
        for events in ([event('x', 'A', '2026-01-01', 1), event('x', 'B', '2026-01-02', 1)],
                       [event('x', 'A', '2026-01-05', 1), event('y', 'A', '2026-01-05', 2)]):
            with self.subTest(events=events), self.assertRaises(DividendDiagnosticInputError):
                diagnose_dividend_accrual(**dict(arguments(), events=events))
        for amount in (-1, True, 'NaN', float('inf'), '1/0', None):
            with self.subTest(amount=amount), self.assertRaises(DividendDiagnosticInputError):
                diagnose_dividend_accrual(**dict(arguments(), events=[event('x', 'A', '2026-01-05', amount)]))

    def test_assumptions_complete_book_flows_and_share_units_required(self):
        variants = [dict(price_basis='ADJCLOSE'), dict(same_share_unit_basis=False),
                    dict(initial_shares={'A': 1.5}), dict(initial_shares={'A': True}), dict(initial_equity=0)]
        for change in variants:
            with self.subTest(change=change), self.assertRaises(DividendDiagnosticInputError):
                diagnose_dividend_accrual(**dict(arguments(), **change))
        for field, value in (('external_cash_flow', 1), ('external_cash_flow', -1), ('shares', {'A': -1}),
                             ('session', 'bad'), ('close_equity', 0)):
            values = arguments()
            values['book']['daily_rows'][1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DividendDiagnosticInputError):
                diagnose_dividend_accrual(**values)
        values = arguments()
        values['book']['status'] = 'BLOCKED'
        with self.assertRaises(DividendDiagnosticInputError):
            diagnose_dividend_accrual(**values)


if __name__ == '__main__':
    unittest.main()
