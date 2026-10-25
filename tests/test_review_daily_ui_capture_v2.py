import unittest
from copy import deepcopy
from test_review_daily_ui_capture_v1 import ReviewTests
from scripts.review_daily_ui_capture_v2 import review


class CapDisplayReviewTests(unittest.TestCase):
    def capture(self):
        fixture = ReviewTests()
        capture = fixture.dom(fixture.capture())
        capture['state']['target']['targets'][0]['quantity'] = 4
        capture['state']['daily'].update(policy_id='MONTHLY_CAP50_EXIT20',
                                          risk_monthly_targets={'S': 2})
        return capture

    def test_current_capped_column_and_original_evidence_preserved(self):
        capture = self.capture()
        original = deepcopy(capture)
        result = review(capture)
        self.assertEqual(result['status'], 'INTRADAY_UI_CHECKS_PASS')
        self.assertEqual(result['raw_monthly_targets'], {'S': 4})
        self.assertEqual(result['displayed_monthly_targets'], {'S': 2})
        self.assertFalse(result['cap_calculation_independently_verified'])
        self.assertEqual(capture, original)

    def test_invalid_cap_cannot_rescue_dom(self):
        for value in ({'S': 5}, {'S': -1}, {'S': True}, {'OTHER': 2}, {}):
            capture = self.capture()
            capture['state']['daily']['risk_monthly_targets'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'CAPPED_MONTHLY_'):
                review(capture)
        capture = self.capture()
        capture['state']['daily']['policy_id'] = 'UNREVIEWED'
        with self.assertRaisesRegex(ValueError, 'UNREVIEWED_MONTHLY_DISPLAY_POLICY'):
            review(capture)

    def test_exited_empty_position_hold_and_stale_action(self):
        capture = self.capture()
        daily = capture['state']['daily']
        daily.update(status='HOLD', new_orders=[], reference_quotes={},
                     effective_target_quantities={'S': 0},
                     daily_gate=dict(status='DAILY_TARGET_READY', rows=[dict(
                         security_id='S', action='HOLD', held=0, effective_target=0)]))
        explanation = '已触发月内峰值回落20%退出；当前保持空仓，本月不再买入。'
        capture['visible_rows'] = [dict(security_id='S', orders=[], dom_match_count=1,
            dom_cells=['S', '0', '2', '0', '空仓，无需操作', '暂无有效建议', explanation],
            explanation=explanation)]
        self.assertEqual(review(capture)['status'], 'HOLD_UI_CHECKS_PASS')
        for action in ('持有，无需操作', '买入 2 股'):
            changed = deepcopy(capture)
            changed['visible_rows'][0]['dom_cells'][4] = action
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'HOLD_DOM_MISMATCH'):
                review(changed)

    def test_legacy_column_and_stale_quote_still_rejected(self):
        capture = self.capture()
        capture['visible_rows'][0]['dom_cells'][2] = '4'
        with self.assertRaisesRegex(ValueError, 'DOM_MONTHLY_TARGET_MISMATCH'):
            review(capture)
        capture = self.capture()
        capture['state']['daily']['reference_quotes']['S']['reference_valid_until'] = capture['observed_at']
        with self.assertRaisesRegex(ValueError, 'EXPIRED_PRICE'):
            review(capture)

    def test_ready_review_includes_existing_nontrading_holding(self):
        capture = self.capture()
        capture['state']['account']['holdings'].append(dict(security_id='T', quantity=3))
        capture['account_after'] = deepcopy(capture['state']['account'])
        capture['state']['target']['targets'].append(dict(security_id='T', quantity=6))
        daily = capture['state']['daily']
        daily['risk_monthly_targets']['T'] = 3
        daily['effective_target_quantities']['T'] = 3
        daily['daily_gate']['rows'].append(dict(security_id='T', action='HOLD', held=3, effective_target=3))
        capture['visible_rows'].append(dict(security_id='T', orders=[], dom_match_count=1,
            dom_cells=['T', '3', '3', '3', '持有，无需操作', '暂无有效建议', '已符合今日持仓目标，无需买卖。'],
            explanation='已符合今日持仓目标，无需买卖。'))
        self.assertEqual(review(capture)['status'], 'INTRADAY_UI_CHECKS_PASS')
        for kind in ('missing', 'duplicate', 'no_reason', 'held', 'target', 'action', 'missing_gate'):
            changed = deepcopy(capture)
            if kind == 'missing': changed['visible_rows'].pop()
            elif kind == 'duplicate': changed['visible_rows'].append(deepcopy(changed['visible_rows'][-1]))
            elif kind == 'missing_gate': changed['state']['daily']['daily_gate']['rows'].pop()
            else:
                column = {'no_reason': 6, 'held': 1, 'target': 3, 'action': 4}[kind]
                changed['visible_rows'][-1]['dom_cells'][column] = '' if kind == 'no_reason' else '999'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                review(changed)
        waiting = deepcopy(capture)
        waiting['state']['daily']['daily_gate']['rows'][-1].update(action='BUY', effective_target=4)
        waiting['state']['daily']['effective_target_quantities']['T'] = 4
        waiting['visible_rows'][-1]['dom_cells'][3:5] = ['4', '等待']
        waiting['visible_rows'][-1]['dom_cells'][6] = '可用现金不足，等待资金到账。'
        waiting['visible_rows'][-1]['explanation'] = '可用现金不足，等待资金到账。'
        self.assertEqual(review(waiting)['status'], 'INTRADAY_UI_CHECKS_PASS')

    def test_extra_visible_order_cannot_be_accepted(self):
        capture = self.capture()
        capture['visible_rows'].append(dict(security_id='UNRELATED', orders=[dict(side='BUY', quantity=1)]))
        with self.assertRaisesRegex(ValueError, 'UNEXPECTED_VISIBLE_ORDER'):
            review(capture)


if __name__ == '__main__':
    unittest.main()
