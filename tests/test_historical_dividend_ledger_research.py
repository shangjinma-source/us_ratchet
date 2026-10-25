import unittest
from fractions import Fraction
from backtest.historical_dividend_ledger_research import create, accrue, pay


class DividendLedgerTests(unittest.TestCase):
    def event(self, **changes):
        return dict(event_id='d1', security_id='A', ex_date='2020-03-02',
                    payment_date='2020-03-16', amount_per_share='1.25',
                    withholding_rate='0.3', assumption='Explicit research tax assumption',
                    currency='USD', **changes)

    def accrued(self, quantity=10):
        return accrue(create(), self.event(), session_date='2020-03-02', opening_quantity=quantity)

    def test_pre_trade_snapshot_and_zero_ex_date_buyer(self):
        # Intraday selling cannot change the already captured entitlement.
        state = self.accrued()
        self.assertEqual(state['receivable'], '35/4')
        self.assertEqual(state['paid_cash'], '0')
        self.assertEqual(self.accrued(0)['receivable'], '0')

    def test_event_idempotency_and_conflict(self):
        state = self.accrued()
        self.assertEqual(accrue(state, self.event(), session_date='2020-03-02', opening_quantity=10), state)
        with self.assertRaises(ValueError):
            accrue(state, self.event(), session_date='2020-03-02', opening_quantity=0)

    def test_payment_and_equity_conservation(self):
        state = self.accrued()
        with self.assertRaisesRegex(ValueError, 'NOT_DUE'):
            pay(state, event_id='d1', payment_id='p1', session_date='2020-03-13')
        paid = pay(state, event_id='d1', payment_id='p1', session_date='2020-03-16')
        self.assertEqual(Fraction(paid['paid_cash']) + Fraction(paid['receivable']), Fraction(state['receivable']))
        self.assertEqual(paid['receivable'], '0')
        self.assertEqual(pay(paid, event_id='d1', payment_id='p1', session_date='2020-03-16'), paid)
        with self.assertRaisesRegex(ValueError, 'ALREADY_PAID'):
            pay(paid, event_id='d1', payment_id='p2', session_date='2020-03-16')

    def test_unknown_payment_date_stays_receivable(self):
        event = self.event()
        event['payment_date'] = None
        state = accrue(create(), event, session_date='2020-03-02', opening_quantity=10)
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_PAYMENT_DATE'):
            pay(state, event_id='d1', payment_id='p1', session_date='2021-01-01')
        self.assertEqual(state['paid_cash'], '0')


if __name__ == '__main__':
    unittest.main()
