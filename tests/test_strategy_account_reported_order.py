"""User-reported order amounts, with synthetic valuation marks, no real writes."""
from fractions import Fraction
import unittest
from core.strategy_account_ledger import create_account, apply_event
from data.strategy_account_preview import preview_scoped_account


class ReportedOrderTests(unittest.TestCase):
    def test_unfilled_partial_cancel_and_cash_bases_do_not_duplicate_buy(self):
        for basis, amount in [('TOTAL_UNINVESTED','20000'),('AVAILABLE_AFTER_RESERVATIONS','1489.06')]:
            with self.subTest(basis=basis):
                state=create_account('isolated-test')
                def event(kind, **fields):
                    nonlocal state
                    state,_=apply_event(state,dict(event_id=str(len(state['events'])),kind=kind,**fields),
                                        expected_revision=state['revision'])
                event('ORDER_OPEN',order_id='reported-order',security_id='SNDK-test',side='BUY',
                      quantity=14,limit_price='1322.21',fee_per_share='0')
                event('CASH_CONFIRM',amount=amount,cash_basis=basis)
                self.assertEqual(Fraction(state['reserved_cash']),Fraction('18510.94'))
                self.assertEqual(Fraction(state['available_cash']),Fraction('1489.06'))
                def preview():
                    at='2026-10-16T15:00:00Z'
                    mark=dict(security_id='SNDK-test',currency='USD',price_basis='SYNTHETIC_TEST',observed_at=at,price='1300')
                    limit=dict(security_id='SNDK-test',price_basis='SYNTHETIC_TEST',observed_at=at,buy='1300',sell='1300')
                    return preview_scoped_account(state=state,legacy_shares={},marks={'SNDK-test':mark},
                        limits={'SNDK-test':limit},target_quantities={'SNDK-test':14},now=at,
                        maximum_mark_age_seconds=120,fee_bps='0')
                self.assertEqual(preview()['new_orders'],[])
                self.assertEqual(state['shares'],{})
                event('FILL',order_id='reported-order',quantity=5,price='1322.21',fees='0',executed_at='2026-10-16T14:59:00Z')
                with self.assertRaisesRegex(ValueError,'CASH_RECONFIRMATION_REQUIRED'):preview()
                event('CASH_CONFIRM',amount='13388.95',cash_basis='TOTAL_UNINVESTED')
                self.assertEqual(state['orders']['reported-order']['remaining_quantity'],9)
                self.assertEqual(preview()['new_orders'],[])
                event('CANCEL',order_id='reported-order')
                order=preview()['new_orders'][0]
                self.assertEqual((order['side'],order['quantity']),('BUY',9))


if __name__=='__main__':unittest.main()
