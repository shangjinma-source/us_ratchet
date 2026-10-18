from copy import deepcopy
import unittest
from backtest.conditional_gross_income_schedule import build_schedule


def event():
    return dict(account='a', sid='s', date='2026-01-02', kind='dividends', quantity=3,
                ready_for_conditional_gross_receivable_schedule=True,
                published_rate_times_quantity_exact='3/2',
                published_terms=dict(amount='0.5', payment_date='2026-01-05', currency='USD',
                                     share_unit='COMMON_SHARE', evidence_level='ISSUER_OR_SEC_WEB_OBSERVATION', url='https://example.invalid'))


class ScheduleTests(unittest.TestCase):
    def test_ex_date_is_receivable_not_paid_cash(self):
        result = build_schedule([event()], ['2026-01-01', '2026-01-02', '2026-01-05'])
        before, ex_day, pay_day = result['rows']
        self.assertEqual(before['recognized_gross_income_exact'], '0')
        self.assertEqual(ex_day['theoretical_gross_paid_exact'], '0')
        self.assertEqual(ex_day['outstanding_gross_receivable_exact'], '3/2')
        self.assertEqual(pay_day['theoretical_gross_paid_exact'], '3/2')
        self.assertEqual(pay_day['outstanding_gross_receivable_exact'], '0')
        self.assertFalse(result['account_cash_written'])

    def test_missing_terms_remain_explicit_and_payment_after_window_receivable(self):
        ready = event(); missing = deepcopy(ready)
        missing.update(sid='other', ready_for_conditional_gross_receivable_schedule=False,
                       missing_fields=['PRIMARY_PAYMENT_DATE'])
        result = build_schedule([ready, missing], ['2026-01-01', '2026-01-02'])
        self.assertEqual(len(result['excluded']), 1)
        self.assertEqual(result['rows'][-1]['outstanding_gross_receivable_exact'], '3/2')
        self.assertIsNone(result['complete_total_return'])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            build_schedule([ready, ready], ['2026-01-01', '2026-01-02'])


if __name__ == '__main__':
    unittest.main()
