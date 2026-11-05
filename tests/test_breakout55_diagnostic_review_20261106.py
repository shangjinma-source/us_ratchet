import unittest
from copy import deepcopy
from unittest.mock import patch
from scripts.research import review_breakout55_diagnostic_20261106 as reviewer


class DiagnosticReviewTests(unittest.TestCase):
    def test_real_blocked_book_never_gets_annualized(self):
        path = reviewer.ROOT / 'tmp/breakout55_diagnostic_20261106_2024_2026/book.json'
        result = reviewer.review('2024_2026', path)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(result['metrics'])
        self.assertIsNone(result['qqq_reference'])

    def test_reject_false_complete_and_broken_accounting(self):
        path = reviewer.ROOT / 'tmp/breakout55_diagnostic_20261106_2024_2026/book.json'
        original = reviewer.read
        source = original(path)
        for mode in ('complete', 'cash', 'equity', 'duplicate', 'label'):
            with self.subTest(mode=mode):
                book = deepcopy(source)
                if mode == 'complete':
                    book.update(status='COMPLETE', reason=None)
                elif mode == 'cash':
                    book['daily_ledger'][0]['cash'] = '-1'
                elif mode == 'equity':
                    book['daily_ledger'][0]['equity'] = '1'
                elif mode == 'duplicate':
                    book['daily_ledger'][1]['date'] = book['daily_ledger'][0]['date']
                else:
                    book.pop('evidence_status')
                with patch.object(reviewer, 'read', side_effect=lambda p: book if reviewer.Path(p) == path else original(p)):
                    with self.assertRaises(ValueError):
                        reviewer.review('2024_2026', path)


if __name__ == '__main__':
    unittest.main()
