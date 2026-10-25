from copy import deepcopy
import unittest

from data.paper_dividend_trade_lineage_v1 import reconcile
from backtest.paper_dividend_journal_v1 import create
import test_paper_dividend_journal_v1 as fixtures


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DividendJournalTests(); self.f.setUp()

    def test_current_book_links_without_crediting_cash(self):
        journal = self.f.call(); book = self.f.f.book; before = deepcopy(book)
        result = reconcile(book, journal, evidence=self.f.evidence)
        self.assertEqual(result['reviewed_payments'], 1)
        self.assertFalse(result['spendable_cash_integrated'])
        self.assertEqual(book, before)

    def test_valid_later_book_payment_cannot_attach_to_earlier_book(self):
        # Both books replay, but the earlier branch does not contain the
        # trade revision used to establish the dividend payment.
        from backtest.current_strategy_prospective_paper_book_v1 import create_book
        from datetime import datetime
        book = self.f.f.book
        initial = create_book(authority=self.f.evidence['authority'],
            clock=lambda: datetime.fromisoformat(book['initialized_at']))
        self.assertNotEqual(initial['revision'], book['revision'])
        with self.assertRaisesRegex(ValueError, 'NONANCESTOR'):
            reconcile(initial, self.f.call(), evidence=self.f.evidence)

    def test_empty_journal_identity_and_tampered_book_rejected(self):
        book = self.f.f.book
        wrong = dict(book, account_id='different-account')
        with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
            reconcile(book, create(wrong), evidence=self.f.evidence)
        wrong = deepcopy(book); wrong['cash']='99999'
        with self.assertRaisesRegex(ValueError, 'BOOK_REPLAY'):
            reconcile(wrong, self.f.call(), evidence=self.f.evidence)


if __name__ == '__main__': unittest.main()
