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

    def test_minimum_cash_reduces_plan_without_changing_strategy(self):
        args = self.make(hsbc_cash='1000', hsbc_minimum_cash='850')
        result = build_preview(**args)
        self.assertTrue(result['budget_reduced'])
        self.assertEqual(result['original_strategy_buys'][0]['quantity'], 2)
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'], 1)
        self.assertGreaterEqual(float(__import__('fractions').Fraction(result['hsbc_remaining_if_funded_usd'])),850)
        self.assertEqual(args['snapshot']['difference']['new_orders'][0]['quantity'],2)

    def test_minimum_already_unmet(self):
        result = build_preview(**self.make(hsbc_minimum_cash='1300'))
        self.assertEqual(result['status'],'HSBC_MINIMUM_RESERVE_NOT_MET')

    def test_confirmed_holdings_allow_remaining_buy_preview(self):
        args = self.make(broker_holdings=dict(account_revision='r', positions=[
            dict(broker='HSBC', security_id='a', quantity=1)]))
        args['snapshot']['account']['holdings'] = [dict(security_id='a', quantity=1)]
        result = build_preview(**args)
        self.assertEqual(result['status'], 'FUNDING_PLAN_ONLY')
        self.assertEqual(result['planned_usmart_buys'][0]['quantity'], 2)
        self.assertFalse(result['executable'])

    def test_mapping_cannot_duplicate_or_use_stale_holdings(self):
        cases = [
            ('old', [dict(broker='HSBC', security_id='a', quantity=1)], 'BROKER_HOLDINGS_REVISION_MISMATCH'),
            ('r', [dict(broker='HSBC', security_id='a', quantity=1), dict(broker='USMART', security_id='a', quantity=1)], 'BROKER_HOLDINGS_TOTAL_MISMATCH'),
            ('r', [dict(broker='HSBC', security_id='a', quantity=True)], 'BROKER_HOLDINGS_INVALID'),
            ('r', None, 'BROKER_HOLDINGS_INVALID'),
        ]
        for revision, positions, expected in cases:
            with self.subTest(expected=expected):
                args = self.make(broker_holdings=dict(account_revision=revision, positions=positions))
                args['snapshot']['account']['holdings'] = [dict(security_id='a', quantity=1)]
                self.assertEqual(build_preview(**args)['status'], expected)

    def test_existing_sell_does_not_fund_new_buys(self):
        args = self.make(broker_holdings=dict(account_revision='r', positions=[
            dict(broker='HSBC', security_id='a', quantity=1)]))
        args['snapshot']['account']['holdings'] = [dict(security_id='a', quantity=1)]
        args['snapshot']['difference']['new_orders'][0]['side'] = 'SELL'
        self.assertEqual(build_preview(**args)['status'], 'BROKER_SELL_EXCEEDS_HOLDINGS')

    def test_sells_split_by_ownership_without_funding_buys(self):
        args = self.make(broker_holdings=dict(account_revision='r', positions=[
            dict(broker='HSBC', security_id='a', quantity=3),
            dict(broker='USMART', security_id='a', quantity=2)]))
        args['snapshot']['account']['holdings'] = [dict(security_id='a', quantity=5)]
        args['snapshot']['difference']['new_orders'].append(
            dict(side='SELL', security_id='a', quantity=4, limit_price='500'))
        result = build_preview(**args)
        self.assertEqual([(r['broker'], r['quantity']) for r in result['planned_broker_sells']], [('HSBC',3),('USMART',1)])
        self.assertEqual(result['proposed_transfer_credit_usd'], '5672/25')
        self.assertFalse(result['unfilled_sale_proceeds_included'])

    def test_sell_only_not_blocked_by_transfer_reserve(self):
        args = self.make(hsbc_minimum_cash='1300', broker_holdings=dict(account_revision='r', positions=[
            dict(broker='HSBC', security_id='a', quantity=2)]))
        args['snapshot']['account']['holdings'] = [dict(security_id='a', quantity=2)]
        args['snapshot']['difference']['new_orders'][0]['side'] = 'SELL'
        result = build_preview(**args)
        self.assertEqual(result['status'], 'FUNDING_PLAN_ONLY')
        self.assertEqual(result['proposed_transfer_credit_usd'], '0')
        self.assertEqual(result['planned_usmart_buys'], [])
