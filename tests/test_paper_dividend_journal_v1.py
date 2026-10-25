from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import unittest

from core.strategy_account_ledger import canonical
from backtest.paper_dividend_journal_v1 import create, append, replay
import test_paper_dividend_payment_v1 as fixtures


class DividendJournalTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PaperPaymentTests(); self.f.setUp()
        self.journal = create(self.f.book)
        raw = canonical(self.f.review); rh = sha256(raw).hexdigest()
        eh = sha256(self.f.right_bytes).hexdigest()
        base = self.f.fixture.f
        self.evidence = dict(books={self.f.book['revision']:self.f.book}, authority=base.authority,
            admitted_decisions=base.admitted, admitted_settlements=base.settlements,
            admitted_reviews={rh:raw}, admitted_entitlements={eh:self.f.right_bytes}, source_files={rh:self.f.sources})
        self.request = dict(operation_id='payment-1', expected_revision=self.journal['revision'],
            book_revision=self.f.book['revision'], entitlement_sha256=eh, review_sha256=rh)
        self.now = datetime.fromisoformat('2026-11-20T16:00:00+00:00')

    def call(self, journal=None, request=None):
        return append(journal or self.journal, request or self.request, clock=lambda:self.now, **self.evidence)

    def test_json_roundtrip_replay_duplicate_and_unchanged_trade_cash(self):
        before = deepcopy(self.f.book)
        result = self.call()
        loaded = json.loads(canonical(result))
        self.assertEqual(replay(loaded, **self.evidence), result)
        self.assertEqual(self.call(loaded), result)
        self.assertEqual(result['paid_net'], '23/10')
        self.assertEqual(len(result['entries']), 1)
        self.assertFalse(result['spendable_cash_integrated'])
        self.assertEqual(self.f.book, before)

    def test_different_operation_cannot_pay_same_event_twice(self):
        result = self.call()
        request = dict(self.request, operation_id='second-id', expected_revision=result['revision'])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'): self.call(result, request)
        with self.assertRaisesRegex(ValueError, 'OPERATION_CONFLICT'):
            self.call(result, dict(self.request, expected_revision=result['revision']))

    def test_tampering_or_missing_sources_cannot_replay(self):
        result = self.call()
        for change in (lambda x:x.update(paid_net='100'),
                       lambda x:x['entries'][0]['payment'].update(net='100'),
                       lambda x:x.update(revision='0'*64)):
            altered = deepcopy(result); change(altered)
            with self.assertRaises(ValueError): replay(altered, **self.evidence)
        self.evidence['source_files'][self.request['review_sha256']] = {'paper-payment-review':b'changed'}
        with self.assertRaisesRegex(ValueError, 'SOURCE_CLOSURE'): replay(result, **self.evidence)

    def test_unreplayable_trade_book_is_rejected(self):
        self.f.book['cash'] = '999999'
        with self.assertRaisesRegex(ValueError, 'BOOK_REPLAY'): self.call()


if __name__ == '__main__': unittest.main()
