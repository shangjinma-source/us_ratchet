"""Offline acceptance fixture supplied explicitly; never captures a live page."""
import json
import os
from copy import deepcopy
from pathlib import Path
import unittest

from scripts.review_daily_ui_capture_v4 import review


@unittest.skipUnless(os.environ.get('UI_CAPTURE_REVIEW_FIXTURE'), 'Explicit saved capture required')
class UnifiedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture = json.loads(Path(os.environ['UI_CAPTURE_REVIEW_FIXTURE']).read_bytes())

    def test_actual_financial_checks_pass(self):
        self.assertEqual(review(self.capture)['status'], 'INTRADAY_UI_CHECKS_PASS')

    def test_column_counts_fail(self):
        for count in (7, 9):
            capture = deepcopy(self.capture)
            capture['visible_rows'][0]['dom_cells'] = (capture['visible_rows'][0]['dom_cells'] + ['extra'])[:count]
            with self.assertRaises(ValueError):
                review(capture)

    def test_wrong_financial_action_fails_original_checks(self):
        capture = deepcopy(self.capture)
        row = capture['visible_rows'][0]
        original = '\t'.join(row['dom_cells'])
        row['dom_cells'][4] = '买入 999 股'
        capture['page_text'] = capture['page_text'].replace(original, '\t'.join(row['dom_cells']))
        with self.assertRaises(ValueError):
            review(capture)

    def test_news_action_cannot_be_formal_order(self):
        capture = deepcopy(self.capture)
        capture['visible_rows'][0]['dom_cells'][7] = '买入 999 股'
        with self.assertRaisesRegex(ValueError, 'OUTSIDE_ACCEPTANCE_SCOPE'):
            review(capture)

    def test_news_header_required(self):
        self.capture['page_text'] = self.capture['page_text'].replace('原因\t新闻影响', '原因\t今日动作')
        with self.assertRaisesRegex(ValueError, 'HEADER_REQUIRED'):
            review(self.capture)


if __name__ == '__main__':
    unittest.main()
