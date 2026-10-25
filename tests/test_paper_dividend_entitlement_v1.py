from datetime import datetime
from hashlib import sha256
from unittest import TestCase
from core.strategy_account_ledger import canonical
import test_current_strategy_prospective_paper_book_v1 as fixture
from data.paper_dividend_entitlement_v1 import prepare_entitlement


class EntitlementBindingTests(TestCase):
    def setUp(self):
        self.f=fixture.ProspectiveBookTests();self.f.setUp()
        self.book=self.f.fill(self.f.accept(self.f.book))
        self.sources={'reviewed-event':b'fixture only'}
        self.review=dict(schema='PAPER_ORDINARY_DIVIDEND_REVIEW_V1',scope='ISOLATED_PAPER_DIVIDEND_ONLY',
            status='REVIEWED_EVENT_AND_CONSTANT_SHARE_UNITS',account_id=self.book['account_id'],
            book_revision=self.book['revision'],descriptor_sha256=self.book['descriptor_sha256'],
            registration_sha256=self.book['registration_sha256'],event_id='dividend-A',security_id='A',
            eligibility_rule='REVIEWED_PRE_EX_SESSION_OPEN_PAPER_HOLDINGS',kind='ORDINARY_CASH_DIVIDEND',
            currency='USD',unresolved_actions=[],special_entitlement_conditions=[],amount_per_share='0.33',
            available_at='2026-11-02T15:30:00+00:00',ex_session_date='2026-11-02',
            entitlement_at='2026-11-02T14:30:00+00:00',payable_at='2026-11-20T00:00:00+00:00',
            source_sha256={n:sha256(b).hexdigest() for n,b in self.sources.items()})

    def call(self, review=None, admitted=True, sources=None):
        raw=canonical(review or self.review)
        return prepare_entitlement(book=self.book,authority=self.f.authority,admitted_decisions=self.f.admitted,
            admitted_settlements=self.f.settlements,review_bytes=raw,
            admitted_reviews={sha256(raw).hexdigest():raw} if admitted else {},
            source_files=self.sources if sources is None else sources,
            clock=lambda:datetime.fromisoformat('2026-11-02T16:00:00+00:00'))

    def test_full_replay_to_unpaid_projection(self):
        result=self.call()
        self.assertEqual(result['entitlement']['eligible_shares'],10)
        self.assertEqual(result['projection']['unpaid_gross'],'33/10')
        self.assertEqual(result['projection']['paid_cash'],'0')
        self.assertFalse(result['account_mutated'])

    def test_unadmitted_or_altered_sources_rejected(self):
        with self.assertRaisesRegex(ValueError,'NOT_ADMITTED'):self.call(admitted=False)
        with self.assertRaisesRegex(ValueError,'SOURCE_CLOSURE'):self.call(sources={'reviewed-event':b'changed'})

    def test_wrong_account_units_boundary_or_future_review_rejected(self):
        for changed,reason in [({'account_id':'real-account'},'BOOK_BINDING'),
                ({'unresolved_actions':['split']},'ELIGIBILITY_UNRESOLVED'),
                ({'entitlement_at':'2026-11-02T15:00:00+00:00'},'EVENT_BOUNDARY'),
                ({'available_at':'2026-11-03T00:00:00+00:00'},'FUTURE_REVIEW')]:
            with self.assertRaisesRegex(ValueError,reason):self.call(dict(self.review,**changed))
