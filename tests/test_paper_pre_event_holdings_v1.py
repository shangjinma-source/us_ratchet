from copy import deepcopy
from datetime import datetime
from unittest import TestCase
import test_current_strategy_prospective_paper_book_v1 as fixture
from data.paper_pre_event_holdings_v1 import holdings_before_session


class HistoricalPaperHoldingsTests(TestCase):
    def setUp(self):
        self.f = fixture.ProspectiveBookTests()
        self.f.setUp()

    def read(self, book, day='2026-11-02'):
        return holdings_before_session(book=book, authority=self.f.authority,
            admitted_decisions=self.f.admitted, admitted_settlements=self.f.settlements,
            session_date=day, clock=lambda: datetime.fromisoformat('2026-11-02T16:00:00+00:00'))

    def test_pending_order_is_not_a_holding(self):
        accepted = self.f.accept(self.f.book)
        result = self.read(accepted)
        self.assertEqual(result['status'], 'WAIT_PRIOR_ORDER_SETTLEMENT')
        self.assertFalse(result['entitlement_verified'])

    def test_later_sale_does_not_erase_prior_holdings(self):
        bought = self.f.fill(self.f.accept(self.f.book))
        decision = self.f.decision(bought, orders=[dict(security_id='A', side='SELL', quantity=10,
            limit_price='100')], day='2026-11-02', effective={'A': 0})
        accepted = self.f.apply(bought, dict(kind='ACCEPT', operation_id='sell',
            expected_revision=bought['revision'], decision_bytes=decision), '2026-11-02T15:00:10+00:00')
        minutes={'sell:0':[dict(security_id='A', start='2026-11-02T15:01:00+00:00',
            end='2026-11-02T15:02:00+00:00', open='100', high='101', low='99', close='100')]}
        sold=self.f.apply(accepted,self.f.settlement_request(accepted,'sell-fill',minutes,
            '2026-11-02T15:02:00+00:00'),'2026-11-02T15:02:01+00:00')
        before=deepcopy(sold)
        self.assertEqual(sold['shares']['A'],0)
        self.assertEqual(self.read(sold)['shares'],{'A':10})
        self.assertEqual(self.read(sold,'2026-10-30')['shares'],{})
        self.assertEqual(sold,before)

    def test_tampered_book_and_future_boundary_rejected(self):
        bought=self.f.fill(self.f.accept(self.f.book))
        changed=deepcopy(bought);changed['shares']['A']=100
        with self.assertRaisesRegex(ValueError,'BOOK_REPLAY'):self.read(changed)
        with self.assertRaisesRegex(ValueError,'FUTURE_BOUNDARY'):self.read(bought,'2026-11-27')
        with self.assertRaisesRegex(ValueError,'SESSION_REQUIRED'):self.read(bought,'2026-11-03')
