"""Adversarial reader checks without invoking the execution engine."""
import copy
import unittest
from scripts import ndx_two_period_account_comparison_20260919 as m
from test_ndx_two_period_account_comparison_20260919 import fixture


class ComparisonReview(unittest.TestCase):
    def test_daily_decision_trade_denominators(self):
        changes = (
            lambda e: e['daily'].pop(3),
            lambda e: e['decisions'].append(copy.deepcopy(e['decisions'][0])),
            lambda e: e['trades'].append({'session': '2023-04-03'}),
            lambda e: e['daily'][0].update(cash_usd=True),
            lambda e: e['decisions'][0].update(target_k=True),
            lambda e: e['decisions'][0].update(projected_cash_usd=25000),
        )
        for change in changes:
            c,t,p,i,_ = fixture()
            change(c['execution'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.audit_account(c,t,p,i)

    def test_reference_scope_and_clock(self):
        for key in ('currency_fx_equivalence_verified','nav_publication_time_verified',
                    'risk_is_order_gate','subscription_redemption_fee_equivalence_verified'):
            c,t,p,i,prefix = fixture()
            _,metrics = m.audit_account(c,t,p,i)
            prefix[key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.compare(prefix,c['calendar'],metrics)
        c,t,p,i,prefix = fixture()
        _,metrics = m.audit_account(c,t,p,i)
        prefix['nav']['rows'][-1]['session'] = '2023-05-02'
        with self.assertRaises(ValueError):
            m.compare(prefix,c['calendar'],metrics)


if __name__ == '__main__':
    unittest.main()
