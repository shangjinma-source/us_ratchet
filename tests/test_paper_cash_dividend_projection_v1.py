from unittest import TestCase
from backtest.paper_cash_dividend_projection_v1 import project


class DividendProjectionTests(TestCase):
    def fixtures(self):
        right=dict(event_id='one', kind='ORDINARY_CASH_DIVIDEND',currency='USD',eligible_shares=10,
            amount_per_share='0.33',entitlement_evidence_sha256='a'*64,entitlement_at='2026-10-07T13:30:00+00:00',
            payable_at='2026-10-28T00:00:00+00:00',available_at='2026-10-08T00:00:00+00:00')
        payment=dict(event_id='one',payment_id='paid',currency='USD',payment_evidence_sha256='b'*64,
            paid_at='2026-10-28T12:00:00+00:00',available_at='2026-10-28T13:00:00+00:00',
            gross='3.3',withholding='0.99',fees='0',net='2.31')
        return right,payment

    def test_unpaid_even_after_payable_date_never_counts_as_cash(self):
        right,_=self.fixtures()
        result=project([right],[],observed_at='2026-10-29T00:00:00+00:00')
        self.assertEqual(result['paid_cash'],'0');self.assertEqual(result['unpaid_gross'],'33/10')

    def test_duplicate_payment_idempotent_and_no_current_position_dependency(self):
        right,payment=self.fixtures()
        result=project([right],[payment,payment],observed_at='2026-10-29T00:00:00+00:00')
        self.assertEqual(result['paid_cash'],'231/100');self.assertEqual(result['unpaid_gross'],'0')
        self.assertFalse(result['entitlement_inferred'])

    def test_unknown_deductions_early_payments_and_conflicts_rejected(self):
        right,payment=self.fixtures()
        for changed in (dict(payment,withholding=None),dict(payment,paid_at='2026-10-20T12:00:00+00:00'),dict(payment,net='3.3')):
            with self.assertRaises(ValueError):project([right],[changed],observed_at='2026-10-29T00:00:00+00:00')
        with self.assertRaises(ValueError):project([right],[payment,dict(payment,payment_id='another')],observed_at='2026-10-29T00:00:00+00:00')

    def test_binary_floats_and_boolean_money_rejected(self):
        right,payment=self.fixtures()
        for value in (True,False,0.33):
            with self.assertRaisesRegex(ValueError,'DIVIDEND_EXACT_AMOUNT_REQUIRED'):
                project([dict(right,amount_per_share=value)],[],observed_at='2026-10-29T00:00:00+00:00')
        for field in ('gross','withholding','fees','net'):
            for value in (False,0.0):
                with self.assertRaisesRegex(ValueError,'DIVIDEND_EXACT_AMOUNT_REQUIRED'):
                    project([right],[dict(payment,**{field:value})],observed_at='2026-10-29T00:00:00+00:00')

    def test_fractional_cents_preserved_and_inputs_unchanged(self):
        from copy import deepcopy
        right,payment=self.fixtures()
        right.update(eligible_shares=3,amount_per_share='0.015')
        payment.update(gross='0.045',withholding='0.0135',fees='0',net='0.0315')
        before=deepcopy((right,payment))
        result=project([right],[payment],observed_at='2026-10-29T00:00:00+00:00')
        self.assertEqual(result['paid_cash'],'63/2000')
        self.assertEqual((right,payment),before)
