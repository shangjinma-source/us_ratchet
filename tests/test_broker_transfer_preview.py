import unittest
from scripts.preview_broker_transfer import build_preview


class PreviewTests(unittest.TestCase):
    def make(self, **changes):
        snapshot = dict(account=dict(holdings=[], orders=[], available_cash='1000', revision='r'),
                        difference=dict(new_orders=[dict(side='BUY', security_id='a', quantity=2, limit_price='100')]),
                        rows=[dict(security_id='a', ticker='ABC')], proposal_id='p', target_id='t',
                        quote_valid_until='expiry', execution_session='session')
        args = dict(verification=dict(api_advice_passed=True), snapshot=snapshot,
                    hsbc_cash='1000', usmart_cash='0', other_fee_reserve='25',
                    transfer_fee_reserve='0', hsbc_waiver_exhausted=True, hsbc_minimum_cash='0')
        args.update(changes)
        return args

    def test_live_binding(self):
        result = build_preview(**self.make())
        self.assertEqual(result['proposal_id'], 'p')
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'], 2)
        self.assertFalse(result['executable'])
        self.assertTrue(result['requires_reprice_after_transfer'])

    def test_stale_snapshot_never_funds(self):
        result = build_preview(**self.make(verification=dict(api_advice_passed=False)))
        self.assertEqual(result['status'], 'WAIT_VERIFIED_ADVICE')
        self.assertNotIn('proposed_transfer_credit_usd', result)

    def test_no_double_counting_cash(self):
        result = build_preview(**self.make(usmart_cash='1000'))
        self.assertEqual(result['status'], 'BROKER_CASH_TOTAL_MISMATCH')

    def test_unknown_existing_broker_holdings(self):
        args = self.make()
        args['snapshot']['account']['holdings'] = [dict(quantity=1)]
        self.assertEqual(build_preview(**args)['status'], 'BROKER_HOLDINGS_MAPPING_REQUIRED')
