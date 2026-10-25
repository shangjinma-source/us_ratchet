from copy import deepcopy
import unittest

import test_review_daily_ui_capture_v1 as fixtures
from scripts.review_daily_ui_capture_v3 import POLICY, review


class FrontierReviewTests(unittest.TestCase):
    def capture(self):
        fixture = fixtures.ReviewTests()
        capture = fixture.dom(fixture.capture())
        target = capture['state']['target']
        target.update(proposal_id='a' * 64,
                      proposal_targets=deepcopy(target['targets']),
                      risk_monthly_targets={'S': 2})
        # The selected proposal can contain a stock absent from the raw basket.
        target['targets'] = [dict(security_id='OLD', quantity=9)]
        capture['state']['daily'].update(policy_id=POLICY,
            proposal_id='a' * 64, risk_monthly_targets={'S': 2})
        return capture

    def test_new_security_and_immutable_capture(self):
        capture = self.capture()
        original = deepcopy(capture)
        result = review(capture)
        self.assertEqual(result['status'], 'INTRADAY_UI_CHECKS_PASS')
        self.assertFalse(result['proposal_calculation_independently_verified'])
        self.assertEqual(capture, original)

    def test_stale_or_missing_proposal_rejected(self):
        for change in ('binding', 'rows', 'map', 'duplicate', 'policy', 'bool'):
            capture = self.capture()
            target = capture['state']['target']
            daily = capture['state']['daily']
            if change == 'binding': daily['proposal_id'] = 'b' * 64
            elif change == 'rows': target.pop('proposal_targets')
            elif change == 'map': daily['risk_monthly_targets'] = {'OLD': 9}
            elif change == 'duplicate': target['proposal_targets'] *= 2
            elif change == 'policy': daily['policy_id'] = 'MONTHLY_CAP50_EXIT20'
            else: target['proposal_targets'][0]['quantity'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                review(capture)

    def test_wait_does_not_pass_or_hide_visible_order(self):
        capture = self.capture()
        capture['state']['daily'].update(status='WAIT', new_orders=[])
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_VISIBLE_ORDER'):
            review(capture)
        capture['visible_rows'][0]['orders'] = []
        self.assertEqual(review(capture)['status'], 'NOT_ACCEPTED_WAIT')

    def test_quote_expiry_checks_retained(self):
        capture = self.capture()
        capture['state']['daily']['reference_quotes']['S']['reference_valid_until'] = capture['observed_at']
        with self.assertRaisesRegex(ValueError, 'EXPIRED_PRICE'):
            review(capture)


if __name__ == '__main__':
    unittest.main()
