import unittest
from datetime import datetime, timezone
from fractions import Fraction
from core.broker_quota import free_buy_budget
from scripts.preview_broker_transfer import build_preview


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 1, 0, tzinfo=timezone.utc)
        self.document = dict(account_revision='r', month='2026-11',
            observed_at=self.now.isoformat(), remaining_hkd='8000',
            hkd_per_usd_budget='8', turnover_reserve_hkd='80')

    def test_net_budget_not_account_cash(self):
        self.assertEqual(free_buy_budget(self.document, account_revision='r', now=self.now), 990)

    def test_stale_invalid_or_future_allowance_rejected(self):
        cases = [('account_revision', 'old'), ('month','2026-10'),
            ('observed_at','2026-11-14T00:57:59+00:00'),
            ('observed_at','2026-11-14T01:00:01+00:00'),
            ('observed_at','2026-11-14T01:00:00'),
            ('remaining_hkd','250001'), ('remaining_hkd', True),
            ('hkd_per_usd_budget','7.8')]
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                free_buy_budget(dict(self.document, **{field:value}), account_revision='r', now=self.now)

    def test_real_preview_allocates_both_brokers(self):
        snapshot = dict(account=dict(holdings=[], orders=[], available_cash='5000',revision='r'),
            difference=dict(new_orders=[dict(side='BUY', security_id='a', quantity=20, limit_price='100')]),
            rows=[dict(security_id='a',ticker='ABC')], proposal_id='p',target_id='t',
            quote_valid_until='expiry',execution_session='session')
        result = build_preview(verification={'api_advice_passed':True},snapshot=snapshot,
            hsbc_cash='5000', usmart_cash='0',other_fee_reserve='5',transfer_fee_reserve='0',
            hsbc_waiver_exhausted=False,hsbc_quota=self.document,now=self.now)
        self.assertEqual(result['planned_hsbc_buys'][0]['quantity'],9)
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'],11)
        self.assertEqual(result['account_revision'],'r')
        self.assertFalse(result['executable'])
        self.assertEqual(Fraction(result['quota_budget_usd']),990)
        snapshot['account']['holdings']=[dict(security_id='a',quantity=1)]
        snapshot['difference']['new_orders'].append(dict(side='SELL',security_id='a',quantity=1,limit_price='100'))
        result=build_preview(verification={'api_advice_passed':True},snapshot=snapshot,
            hsbc_cash='5000',usmart_cash='0',other_fee_reserve='5',transfer_fee_reserve='0',
            hsbc_waiver_exhausted=False,hsbc_quota=self.document,now=self.now,
            broker_holdings=dict(account_revision='r',positions=[dict(broker='HSBC',security_id='a',quantity=1)]))
        self.assertEqual(result['status'],'QUOTA_RECONFIRM_AFTER_HSBC_SELLS')
        self.assertNotIn('planned_hsbc_buys',result)
