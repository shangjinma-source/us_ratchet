import unittest
from scripts.research.audit_pullback_result_20261105 import audit


class CompletedLedgerAuditTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(date=day, cash=cash, shares={}, stock_value='0',
                     merger_receivable='0', dividend_receivable='0', equity=cash)
                for day, cash in [('2021-01-04', '80'), ('2021-01-05', '100')]]
        book = dict(status='COMPLETE', initial_cash='100', daily_ledger=rows,
                    order_log=[], maximum_drawdown='1/5')
        document = dict(assembled=dict(session_dates=['2020-12-31', '2021-01-04', '2021-01-05']), ohlc={})
        return book, document

    def test_known_drawdown_and_recovery(self):
        book, document = self.fixture()
        result = audit(book, document)
        self.assertEqual(result['maximum_close_drawdown'], .2)
        self.assertEqual(result['longest_underwater_sessions'], 1)
        self.assertEqual(result['ending_underwater_sessions'], 0)
        self.assertEqual(result['cagr'], 0)

    def test_reject_partial_even_if_status_complete(self):
        book, document = self.fixture()
        book['daily_ledger'].pop()
        with self.assertRaisesRegex(ValueError, 'FULL_WINDOW_REQUIRED'):
            audit(book, document)

    def test_reject_blocked_and_unreconciled_account(self):
        book, document = self.fixture()
        book['status'] = 'BLOCKED'
        with self.assertRaisesRegex(ValueError, 'COMPLETE_ACCOUNT_REQUIRED'):
            audit(book, document)
        book['status'] = 'COMPLETE'
        book['daily_ledger'][0]['cash'] = '81'
        with self.assertRaisesRegex(ValueError, 'EQUITY_RECONCILIATION'):
            audit(book, document)


if __name__ == '__main__':
    unittest.main()
