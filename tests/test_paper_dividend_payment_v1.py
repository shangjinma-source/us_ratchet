from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import unittest

from core.strategy_account_ledger import canonical
from data.paper_dividend_payment_v1 import prepare_payment
import test_paper_dividend_entitlement_v1 as fixtures


class PaperPaymentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EntitlementBindingTests()
        self.fixture.setUp()
        self.book = self.fixture.book
        self.right = self.fixture.call()['entitlement']
        self.right_bytes = canonical(self.right)
        self.sources = {'paper-payment-review': b'isolated fixture, not broker payment'}
        self.review = dict(schema='PAPER_CASH_PAYMENT_REVIEW_V1', scope='ISOLATED_PAPER_DIVIDEND_ONLY',
            status='REVIEWED_PAPER_PAYMENT', unresolved_items=[], account_id=self.book['account_id'],
            descriptor_sha256=self.book['descriptor_sha256'], registration_sha256=self.book['registration_sha256'],
            book_revision=self.book['revision'], entitlement_sha256=sha256(self.right_bytes).hexdigest(),
            event_id=self.right['event_id'], payment_id='paper-payment-1', currency='USD',
            gross='3.30', withholding='0.99', fees='0.01', net='2.30',
            paid_at='2026-11-20T15:00:00+00:00', available_at='2026-11-20T15:01:00+00:00',
            source_sha256={k:sha256(v).hexdigest() for k,v in self.sources.items()})

    def call(self, changes=None, admitted=True, sources=None, right_admitted=True):
        raw = canonical(dict(self.review, **(changes or {})))
        return prepare_payment(book=self.book, entitlement=self.right, review_bytes=raw,
            admitted_reviews={sha256(raw).hexdigest():raw} if admitted else {},
            admitted_entitlements={sha256(self.right_bytes).hexdigest():self.right_bytes} if right_admitted else {},
            source_files=self.sources if sources is None else sources,
            clock=lambda:datetime.fromisoformat('2026-11-20T16:00:00+00:00'))

    def test_exact_net_prepared_repeat_is_identical_and_no_book_mutation(self):
        before = deepcopy(self.book)
        result = self.call()
        self.assertEqual(result, self.call())
        self.assertEqual(result['projection']['paid_cash'], '23/10')
        self.assertEqual(result['projection']['unpaid_gross'], '0')
        self.assertEqual(result['status'], 'PAPER_PAYMENT_PREPARED_NOT_POSTED')
        self.assertEqual(self.book, before)

    def test_payable_date_alone_and_unsigned_or_changed_evidence_not_enough(self):
        for kwargs in ({'admitted':False}, {'right_admitted':False}, {'sources':{'paper-payment-review':b'changed'}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.call(**kwargs)

    def test_account_revision_event_and_unknown_deductions_rejected(self):
        for changes in ({'account_id':'other'}, {'book_revision':'old'}, {'event_id':'other'},
                        {'entitlement_sha256':'0'*64}, {'withholding':None}, {'fees':None},
                        {'net':'3.30'}, {'gross':3.30}, {'unresolved_items':['tax']}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.call(changes)

    def test_early_payment_and_future_review_rejected(self):
        for changes in ({'paid_at':'2026-11-19T15:00:00+00:00'},
                        {'available_at':'2026-11-21T15:00:00+00:00'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.call(changes)


if __name__ == '__main__': unittest.main()
